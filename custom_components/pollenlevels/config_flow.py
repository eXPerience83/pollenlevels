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
from homeassistant.helpers.selector import (
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SectionConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    section,
)

from .const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_HTTP_REFERRER,
    CONF_LANGUAGE_CODE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    FORECAST_SENSORS_CHOICES,
    MAX_FORECAST_DAYS,
    MIN_FORECAST_DAYS,
    POLLEN_API_TIMEOUT,
    SECTION_API_KEY_OPTIONS,
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

API_KEY_URL = "https://developers.google.com/maps/documentation/pollen/get-api-key"
RESTRICTING_API_KEYS_URL = (
    "https://developers.google.com/maps/api-security-best-practices"
)


def _extract_error_message(body: str | None, api_key: str | None) -> str | None:
    """Extract a concise error message from an HTTP response body."""

    if not body:
        return None

    redacted = redact_api_key(body, api_key) or body
    message: str | None = None

    try:
        data = json.loads(redacted)
    except Exception:
        data = None

    if isinstance(data, dict):
        error_obj = data.get("error") if isinstance(data.get("error"), dict) else None
        if error_obj is not None:
            message = error_obj.get("message")
        if not message:
            message = data.get("message")

    if not message:
        message = redacted.strip() or None

    if message and len(message) > 160:
        return message[:160]

    return message


def _classify_403_error(message: str | None) -> str:
    """Return an error key for a 403 response based on the message."""

    if not message:
        return "invalid_auth"

    lowered = message.lower()
    auth_hints = ("invalid", "key", "referer", "referrer", "not allowed", "denied")
    billing_hints = ("billing", "enable", "enabled", "project")

    if any(hint in lowered for hint in auth_hints):
        return "invalid_auth"
    if any(hint in lowered for hint in billing_hints):
        return "cannot_connect"

    return "invalid_auth"


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Optional(
            CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
        ): NumberSelector(
            NumberSelectorConfig(
                min=1,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="h",
            )
        ),
        vol.Optional(CONF_LANGUAGE_CODE): TextSelector(TextSelectorConfig()),
        section(SECTION_API_KEY_OPTIONS, SectionConfig(collapsed=True)): {
            vol.Optional(CONF_HTTP_REFERRER, default=""): TextSelector(
                TextSelectorConfig()
            ),
        },
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


def _safe_coord(value: float | None, *, lat: bool) -> float | None:
    """Return a validated latitude/longitude or None if unset/invalid."""

    try:
        if lat:
            return cv.latitude(value)
        return cv.longitude(value)
    except (vol.Invalid, TypeError, ValueError):
        return None


def _get_location_schema(hass: Any) -> vol.Schema:
    """Return schema for name + location with defaults from HA config."""

    default_name = getattr(hass.config, "location_name", "") or DEFAULT_ENTRY_TITLE
    default_lat = _safe_coord(getattr(hass.config, "latitude", None), lat=True)
    default_lon = _safe_coord(getattr(hass.config, "longitude", None), lat=False)

    if default_lat is not None and default_lon is not None:
        location_field = vol.Required(
            CONF_LOCATION,
            default={
                CONF_LATITUDE: default_lat,
                CONF_LONGITUDE: default_lon,
            },
        )
    else:
        location_field = vol.Required(CONF_LOCATION)

    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=default_name): str,
            location_field: LocationSelector(LocationSelectorConfig(radius=False)),
        }
    )


def _validate_location_dict(
    location: dict[str, Any] | None,
) -> tuple[float, float] | None:
    """Validate location dict and return (lat, lon) or None on error."""

    if not isinstance(location, dict):
        return None

    lat_val = location.get(CONF_LATITUDE)
    lon_val = location.get(CONF_LONGITUDE)

    if lat_val is None or lon_val is None:
        return None

    try:
        lat = cv.latitude(lat_val)
        lon = cv.longitude(lon_val)
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
        description_placeholders: dict[str, Any] | None = None,
    ) -> tuple[dict[str, str], dict[str, Any] | None]:
        """Validate user or reauth input and return normalized data."""

        placeholders = description_placeholders
        errors: dict[str, str] = {}
        normalized: dict[str, Any] = dict(user_input)
        normalized.pop(CONF_NAME, None)
        normalized.pop(CONF_LOCATION, None)

        # Normalize update interval (selectors do not coerce types).
        interval_raw = user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        try:
            interval = int(interval_raw)
        except (TypeError, ValueError):
            interval = DEFAULT_UPDATE_INTERVAL
        if interval < 1:
            interval = 1
        normalized[CONF_UPDATE_INTERVAL] = interval

        raw_referrer = user_input.get(CONF_HTTP_REFERRER, "")
        referrer = raw_referrer.strip() if isinstance(raw_referrer, str) else ""
        normalized[CONF_HTTP_REFERRER] = referrer or None

        latlon = None
        if CONF_LOCATION in user_input:
            latlon = _validate_location_dict(user_input.get(CONF_LOCATION))
            if latlon is None:
                _LOGGER.debug(
                    "Invalid coordinates provided (values redacted): parsing failed"
                )
                errors[CONF_LOCATION] = "invalid_coordinates"
                return errors, None
        else:
            try:
                lat = cv.latitude(user_input.get(CONF_LATITUDE))
                lon = cv.longitude(user_input.get(CONF_LONGITUDE))
                latlon = (lat, lon)
            except (vol.Invalid, TypeError):
                _LOGGER.debug(
                    "Invalid coordinates provided (values redacted): parsing failed"
                )
                # Legacy lat/lon path (e.g., reauth) has no CONF_LOCATION field on the form
                errors["base"] = "invalid_coordinates"
                return errors, None

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
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=POLLEN_API_TIMEOUT),
                headers={"Referer": referrer} if referrer else None,
            ) as resp:
                status = resp.status
                raw = await resp.read()
                try:
                    body_str = raw.decode()
                except Exception:
                    body_str = str(raw)
                redacted_body = redact_api_key(body_str, user_input.get(CONF_API_KEY))

                if status in (401, 403):
                    message = _extract_error_message(
                        redacted_body, user_input.get(CONF_API_KEY)
                    )
                    if placeholders is not None and message:
                        placeholders["error_message"] = message

                    if status == 403:
                        errors["base"] = _classify_403_error(message)
                    else:
                        errors["base"] = "invalid_auth"
                elif status == 429:
                    _LOGGER.debug("Validation HTTP 429 (body omitted)")
                    errors["base"] = "quota_exceeded"
                elif status != 200:
                    _LOGGER.debug("Validation HTTP %s (body omitted)", status)
                    errors["base"] = "cannot_connect"
                    if placeholders is not None:
                        placeholders["error_message"] = (
                            _extract_error_message(
                                redacted_body, user_input.get(CONF_API_KEY)
                            )
                            or "Unable to validate the API key with the pollen service."
                        )
                else:
                    _LOGGER.debug(
                        "Validation HTTP %s — %s",
                        status,
                        redacted_body,
                    )
                    try:
                        data = json.loads(body_str) if body_str else {}
                    except Exception:
                        data = {}
                    if not data.get("dailyInfo"):
                        _LOGGER.warning("Validation: 'dailyInfo' missing")
                        errors["base"] = "cannot_connect"
                        if placeholders is not None:
                            placeholders["error_message"] = (
                                "API response missing expected pollen forecast information."
                            )

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
                "Validation timeout (%ss): %s",
                POLLEN_API_TIMEOUT,
                redact_api_key(err, user_input.get(CONF_API_KEY)),
            )
            errors["base"] = "cannot_connect"
            if placeholders is not None:
                redacted = redact_api_key(err, user_input.get(CONF_API_KEY))
                placeholders["error_message"] = (
                    redacted
                    or f"Validation request timed out ({POLLEN_API_TIMEOUT} seconds)."
                )
        except aiohttp.ClientError as err:
            _LOGGER.error(
                "Connection error: %s",
                redact_api_key(err, user_input.get(CONF_API_KEY)),
            )
            errors["base"] = "cannot_connect"
            if placeholders is not None:
                redacted = redact_api_key(err, user_input.get(CONF_API_KEY))
                placeholders["error_message"] = (
                    redacted or "Network error while connecting to the pollen service."
                )
        except Exception as err:  # defensive
            _LOGGER.exception(
                "Unexpected error in Pollen Levels config flow while validating input: %s",
                redact_api_key(err, user_input.get(CONF_API_KEY)),
            )
            errors["base"] = "unknown"
            if placeholders is not None:
                placeholders.pop("error_message", None)

        return errors, None

    async def async_step_user(self, user_input=None):
        """Handle initial step."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, Any] = {}

        description_placeholders.setdefault("api_key_url", API_KEY_URL)
        description_placeholders.setdefault(
            "restricting_api_keys_url", RESTRICTING_API_KEYS_URL
        )

        if user_input:
            errors, normalized = await self._async_validate_input(
                user_input,
                check_unique_id=True,
                description_placeholders=description_placeholders,
            )
            if not errors and normalized is not None:
                entry_name = str(user_input.get(CONF_NAME, "")).strip()
                title = entry_name or DEFAULT_ENTRY_TITLE
                if not normalized.get(CONF_HTTP_REFERRER):
                    normalized.pop(CONF_HTTP_REFERRER, None)
                return self.async_create_entry(title=title, data=normalized)

        base_schema = STEP_USER_DATA_SCHEMA.schema.copy()
        base_schema.update(_get_location_schema(self.hass).schema)

        suggested_values = {
            CONF_LANGUAGE_CODE: self.hass.config.language,
            CONF_NAME: getattr(self.hass.config, "location_name", "")
            or DEFAULT_ENTRY_TITLE,
        }

        lat = _safe_coord(getattr(self.hass.config, "latitude", None), lat=True)
        lon = _safe_coord(getattr(self.hass.config, "longitude", None), lat=False)
        if lat is not None and lon is not None:
            suggested_values[CONF_LOCATION] = {
                CONF_LATITUDE: lat,
                CONF_LONGITUDE: lon,
            }

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(base_schema),
                {**suggested_values, **(user_input or {})},
            ),
            errors=errors,
            description_placeholders=description_placeholders,
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
        placeholders = {
            "latitude": f"{self._reauth_entry.data.get(CONF_LATITUDE)}",
            "longitude": f"{self._reauth_entry.data.get(CONF_LONGITUDE)}",
        }

        if user_input:
            combined: dict[str, Any] = {**self._reauth_entry.data, **user_input}
            errors, normalized = await self._async_validate_input(
                combined,
                check_unique_id=False,
                description_placeholders=placeholders,
            )
            if not errors and normalized is not None:
                if not normalized.get(CONF_HTTP_REFERRER):
                    normalized.pop(CONF_HTTP_REFERRER, None)
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
                ): str,
                section(SECTION_API_KEY_OPTIONS, SectionConfig(collapsed=True)): {
                    vol.Optional(
                        CONF_HTTP_REFERRER,
                        default=self._reauth_entry.data.get(CONF_HTTP_REFERRER, ""),
                    ): TextSelector(TextSelectorConfig()),
                },
            }
        )

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
        placeholders = {"title": self.entry.title or DEFAULT_ENTRY_TITLE}

        if user_input is not None:
            try:
                interval_val = int(
                    user_input.get(
                        CONF_UPDATE_INTERVAL,
                        self.entry.options.get(
                            CONF_UPDATE_INTERVAL,
                            self.entry.data.get(
                                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                            ),
                        ),
                    )
                )
                if interval_val < 1:
                    interval_val = 1
                user_input[CONF_UPDATE_INTERVAL] = interval_val

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
                user_input[CONF_FORECAST_DAYS] = days

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
                errors["base"] = "unknown"

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
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="h",
                        )
                    ),
                    vol.Optional(
                        CONF_LANGUAGE_CODE, default=current_lang
                    ): TextSelector(TextSelectorConfig()),
                    vol.Optional(
                        CONF_FORECAST_DAYS, default=current_days
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_FORECAST_DAYS,
                            max=MAX_FORECAST_DAYS,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_CREATE_FORECAST_SENSORS, default=current_mode
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=FORECAST_SENSORS_CHOICES,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )
