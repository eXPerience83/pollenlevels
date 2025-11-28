"""Config & options flow for Pollen Levels.

Notes:
- Unified per-day sensors option ('create_forecast_sensors'): "none" | "D+1" | "D+1+2".
- Allows empty language (omit languageCode). Trims language whitespace on save.
- Redacts API keys in debug logs.
- Timeout handling: on Python 3.14, built-in `TimeoutError` also covers `asyncio.TimeoutError`,
  so catching `TimeoutError` is sufficient and preferred.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import aiohttp
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE, CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import LocationSelector, LocationSelectorConfig

from .const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    FORECAST_SENSORS_CHOICES,
    MAX_FORECAST_DAYS,
    MIN_FORECAST_DAYS,
)
from .util import redact_api_key

_LOGGER = logging.getLogger(__name__)

# BCP-47-ish regex (common patterns, not full grammar).
LANGUAGE_CODE_REGEX = re.compile(
    r"^[A-Za-z]{2,3}"
    r"(?:-[A-Za-z]{4})?"  # optional script
    r"(?:-(?:[A-Za-z]{2}|\d{3}))?"  # optional region
    r"(?:-(?:[A-Za-z0-9]{5,8}|\d[A-Za-z0-9]{3}))?$",  # optional single variant
    re.IGNORECASE,
)


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
        vol.Optional(CONF_LANGUAGE_CODE): str,
    }
)


def is_valid_language_code(value: str) -> str:
    """Validate language code format; return normalized (trimmed) value."""
    if not isinstance(value, str):
        raise vol.Invalid("invalid_language")
    norm = value.strip()
    if not norm:
        raise vol.Invalid("empty")
    if not LANGUAGE_CODE_REGEX.match(norm):
        _LOGGER.warning("Invalid language code format (BCP-47-like): %s", value)
        raise vol.Invalid("invalid_language")
    return norm


def _language_error_to_form_key(error: vol.Invalid) -> str:
    """Convert voluptuous validation errors into form error keys."""

    message = getattr(error, "error_message", "")
    if message == "empty":
        return "empty"
    if message == "invalid_language":
        return "invalid_language_format"
    return "invalid_language_format"


def _get_location_schema(hass: Any) -> vol.Schema:
    """Return schema for name + location with defaults from HA config."""

    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=hass.config.location_name): str,
            vol.Required(
                CONF_LOCATION,
                default={
                    CONF_LATITUDE: hass.config.latitude,
                    CONF_LONGITUDE: hass.config.longitude,
                },
            ): LocationSelector(LocationSelectorConfig(radius=False)),
        }
    )


def _validate_location_dict(
    location: dict[str, Any] | None,
) -> tuple[float, float] | None:
    """Validate location dict and return (lat, lon) or None on error."""

    if not isinstance(location, dict):
        return None

    try:
        lat = cv.latitude(location.get(CONF_LATITUDE))
        lon = cv.longitude(location.get(CONF_LONGITUDE))
    except (vol.Invalid, TypeError, ValueError):
        return None

    return lat, lon


class PollenLevelsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Pollen Levels."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow state."""
        self._reauth_entry: config_entries.ConfigEntry | None = None

    @staticmethod
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        """Return the options flow handler."""
        return PollenLevelsOptionsFlow(entry)

    async def _async_validate_input(
        self,
        user_input: dict[str, Any],
        *,
        check_unique_id: bool,
    ) -> tuple[dict[str, str], dict[str, Any] | None]:
        """Validate user or reauth input and return normalized data."""

        errors: dict[str, str] = {}
        normalized: dict[str, Any] = dict(user_input)
        normalized.pop(CONF_NAME, None)
        normalized.pop(CONF_LOCATION, None)

        latlon = _validate_location_dict(user_input.get(CONF_LOCATION))
        if latlon is None:
            try:
                lat = cv.latitude(user_input.get(CONF_LATITUDE))
                lon = cv.longitude(user_input.get(CONF_LONGITUDE))
            except (vol.Invalid, TypeError):
                _LOGGER.debug(
                    "Invalid coordinates provided (values redacted): parsing failed"
                )
                errors[CONF_LOCATION] = "invalid_coordinates"
                return errors, None
            latlon = (lat, lon)

        lat, lon = latlon
        normalized[CONF_LATITUDE] = lat
        normalized[CONF_LONGITUDE] = lon

        if check_unique_id:
            uid = f"{lat:.4f}_{lon:.4f}"
            try:
                await self.async_set_unique_id(uid, raise_on_progress=False)
                self._abort_if_unique_id_configured()
            except Exception as err:  # defensive
                _LOGGER.exception(
                    "Unique ID setup failed for coordinates (values redacted): %s",
                    redact_api_key(err, user_input.get(CONF_API_KEY)),
                )
                raise

        try:
            # Allow blank language; if present, validate & normalize
            raw_lang = user_input.get(CONF_LANGUAGE_CODE, "")
            lang = raw_lang.strip() if isinstance(raw_lang, str) else ""
            if lang:
                lang = is_valid_language_code(lang)

            session = async_get_clientsession(self.hass)
            params = {
                "key": user_input[CONF_API_KEY],
                "location.latitude": f"{lat:.6f}",
                "location.longitude": f"{lon:.6f}",
                "days": 1,
            }
            if lang:
                params["languageCode"] = lang

            url = "https://pollen.googleapis.com/v1/forecast:lookup"

            # SECURITY: Avoid logging URL+params (contains coordinates/key)
            _LOGGER.debug("Validating Pollen API (days=%s, lang_set=%s)", 1, bool(lang))

            # Add explicit timeout to prevent UI hangs on provider issues
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                status = resp.status
                if status == 403:
                    _LOGGER.debug("Validation HTTP 403 (body omitted)")
                    errors["base"] = "invalid_auth"
                elif status == 429:
                    _LOGGER.debug("Validation HTTP 429 (body omitted)")
                    errors["base"] = "quota_exceeded"
                elif status != 200:
                    _LOGGER.debug("Validation HTTP %s (body omitted)", status)
                    errors["base"] = "cannot_connect"
                else:
                    raw = await resp.read()
                    try:
                        body_str = raw.decode()
                    except Exception:
                        body_str = str(raw)
                    _LOGGER.debug(
                        "Validation HTTP %s — %s",
                        status,
                        redact_api_key(body_str, user_input.get(CONF_API_KEY)),
                    )
                    try:
                        data = json.loads(body_str) if body_str else {}
                    except Exception:
                        data = {}
                    if not data.get("dailyInfo"):
                        _LOGGER.warning("Validation: 'dailyInfo' missing")
                        errors["base"] = "cannot_connect"

            if errors:
                return errors, None

            normalized[CONF_LANGUAGE_CODE] = lang
            return errors, normalized

        except vol.Invalid as ve:
            _LOGGER.warning(
                "Language code validation failed for '%s': %s",
                user_input.get(CONF_LANGUAGE_CODE),
                ve,
            )
            errors[CONF_LANGUAGE_CODE] = _language_error_to_form_key(ve)
        except TimeoutError as err:
            # Catch built-in TimeoutError; on Python 3.14 this also covers asyncio.TimeoutError.
            _LOGGER.warning(
                "Validation timeout (10s): %s",
                redact_api_key(err, user_input.get(CONF_API_KEY)),
            )
            errors["base"] = "cannot_connect"
        except aiohttp.ClientError as err:
            _LOGGER.error(
                "Connection error: %s",
                redact_api_key(err, user_input.get(CONF_API_KEY)),
            )
            errors["base"] = "cannot_connect"
        except Exception as err:  # defensive
            _LOGGER.exception(
                "Unexpected error in Pollen Levels config flow while validating input: %s",
                redact_api_key(err, user_input.get(CONF_API_KEY)),
            )
            errors["base"] = "unknown"

        return errors, None

    async def async_step_user(self, user_input=None):
        """Handle initial step."""
        errors: dict[str, str] = {}

        if user_input:
            errors, normalized = await self._async_validate_input(
                user_input, check_unique_id=True
            )
            if not errors and normalized is not None:
                entry_name = str(user_input.get(CONF_NAME, "")).strip()
                title = entry_name or DEFAULT_ENTRY_TITLE
                return self.async_create_entry(title=title, data=normalized)

        base_schema = STEP_USER_DATA_SCHEMA.schema.copy()
        base_schema.update(_get_location_schema(self.hass).schema)

        suggested_values = {
            CONF_LANGUAGE_CODE: self.hass.config.language,
            CONF_NAME: self.hass.config.location_name,
            CONF_LOCATION: {
                CONF_LATITUDE: self.hass.config.latitude,
                CONF_LONGITUDE: self.hass.config.longitude,
            },
        }

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(base_schema),
                {**suggested_values, **(user_input or {})},
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """Handle re-authentication when credentials become invalid."""

        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reauth_failed")

        self._reauth_entry = entry
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        """Prompt for a refreshed API key and validate it."""

        assert self._reauth_entry is not None

        errors: dict[str, str] = {}

        if user_input:
            combined: dict[str, Any] = {**self._reauth_entry.data, **user_input}
            errors, normalized = await self._async_validate_input(
                combined, check_unique_id=False
            )
            if not errors and normalized is not None:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry, data=normalized
                )
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_API_KEY,
                    default=self._reauth_entry.data.get(CONF_API_KEY, ""),
                ): str
            }
        )

        placeholders = {
            "latitude": f"{self._reauth_entry.data.get(CONF_LATITUDE)}",
            "longitude": f"{self._reauth_entry.data.get(CONF_LONGITUDE)}",
        }

        # Ensure the form posts back to this handler.
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )


class PollenLevelsOptionsFlow(config_entries.OptionsFlow):
    """Handle options for an existing entry."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input=None):
        """Display/process options form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Language: allow empty; if provided, validate & normalize.
                raw_lang = user_input.get(
                    CONF_LANGUAGE_CODE,
                    self.entry.options.get(
                        CONF_LANGUAGE_CODE, self.entry.data.get(CONF_LANGUAGE_CODE, "")
                    ),
                )
                lang = raw_lang.strip() if isinstance(raw_lang, str) else ""
                if lang:
                    lang = is_valid_language_code(lang)
                user_input[CONF_LANGUAGE_CODE] = lang  # persist normalized

                # forecast_days within 1..5
                days = int(
                    user_input.get(
                        CONF_FORECAST_DAYS,
                        self.entry.options.get(
                            CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS
                        ),
                    )
                )
                if days < MIN_FORECAST_DAYS or days > MAX_FORECAST_DAYS:
                    errors[CONF_FORECAST_DAYS] = "invalid_option_combo"

                # per-day sensors vs number of days
                mode = user_input.get(
                    CONF_CREATE_FORECAST_SENSORS,
                    self.entry.options.get(CONF_CREATE_FORECAST_SENSORS, "none"),
                )
                needed = 1
                if mode == "D+1":
                    needed = 2
                elif mode == "D+1+2":
                    needed = 3
                if days < needed:
                    errors[CONF_CREATE_FORECAST_SENSORS] = "invalid_option_combo"

            except vol.Invalid as ve:
                _LOGGER.warning(
                    "Options language validation failed for '%s': %s",
                    user_input.get(CONF_LANGUAGE_CODE),
                    ve,
                )
                errors[CONF_LANGUAGE_CODE] = _language_error_to_form_key(ve)
            except Exception as err:  # defensive
                _LOGGER.exception(
                    "Options validation error: %s",
                    redact_api_key(err, self.entry.data.get(CONF_API_KEY)),
                )
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Defaults: prefer options, fallback to data/HA config
        current_interval = self.entry.options.get(
            CONF_UPDATE_INTERVAL,
            self.entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        current_lang = self.entry.options.get(
            CONF_LANGUAGE_CODE,
            self.entry.data.get(CONF_LANGUAGE_CODE, self.hass.config.language),
        )
        current_days = self.entry.options.get(
            CONF_FORECAST_DAYS,
            self.entry.data.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS),
        )
        current_mode = self.entry.options.get(CONF_CREATE_FORECAST_SENSORS, "none")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=current_interval
                    ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                    vol.Optional(CONF_LANGUAGE_CODE, default=current_lang): str,
                    vol.Optional(CONF_FORECAST_DAYS, default=current_days): vol.In(
                        list(range(MIN_FORECAST_DAYS, MAX_FORECAST_DAYS + 1))
                    ),
                    vol.Optional(
                        CONF_CREATE_FORECAST_SENSORS, default=current_mode
                    ): vol.In(FORECAST_SENSORS_CHOICES),
                }
            ),
            errors=errors,
        )
