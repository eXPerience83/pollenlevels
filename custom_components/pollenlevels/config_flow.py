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
from homeassistant.data_entry_flow import SectionConfig, section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_HTTP_REFERER,
    CONF_LANGUAGE_CODE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    FORECAST_SENSORS_CHOICES,
    MAX_FORECAST_DAYS,
    MIN_FORECAST_DAYS,
    POLLEN_API_KEY_URL,
    POLLEN_API_TIMEOUT,
    RESTRICTING_API_KEYS_URL,
    SECTION_API_KEY_OPTIONS,
    is_invalid_api_key_message,
    normalize_http_referer,
)
from .util import extract_error_message, redact_api_key

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
        vol.Optional(CONF_LANGUAGE_CODE): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        section(SECTION_API_KEY_OPTIONS, SectionConfig(collapsed=True)): {
            vol.Optional(CONF_HTTP_REFERER, default=""): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
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


def _parse_int_option(
    value: Any,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
    error_key: str | None = None,
) -> tuple[int, str | None]:
    """Parse a numeric option to int and enforce bounds."""

    try:
        parsed = int(float(value if value is not None else default))
    except (TypeError, ValueError):
        return default, error_key

    if min_value is not None and parsed < min_value:
        return parsed, error_key

    if max_value is not None and parsed > max_value:
        return parsed, error_key

    return parsed, None


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

        placeholders = (
            description_placeholders if description_placeholders is not None else {}
        )
        errors: dict[str, str] = {}
        normalized: dict[str, Any] = dict(user_input)
        normalized.pop(CONF_NAME, None)
        normalized.pop(CONF_LOCATION, None)

        headers: dict[str, str] | None = None
        try:
            http_referer = normalize_http_referer(normalized.get(CONF_HTTP_REFERER))
        except ValueError:
            errors[CONF_HTTP_REFERER] = "invalid_http_referrer"
            return errors, None

        if http_referer:
            headers = {"Referer": http_referer}
            normalized[CONF_HTTP_REFERER] = http_referer
        else:
            normalized.pop(CONF_HTTP_REFERER, None)

        try:
            parsed_update_interval = int(
                float(normalized.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
            )
        except (TypeError, ValueError):
            errors[CONF_UPDATE_INTERVAL] = "invalid_update_interval"
            return errors, None

        normalized[CONF_UPDATE_INTERVAL] = parsed_update_interval

        if normalized[CONF_UPDATE_INTERVAL] < 1:
            errors[CONF_UPDATE_INTERVAL] = "invalid_update_interval"
            return errors, None

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
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=POLLEN_API_TIMEOUT),
            ) as resp:
                status = resp.status
                if status == 401:
                    _LOGGER.debug("Validation HTTP 401 (body omitted)")
                    errors["base"] = "invalid_auth"
                    placeholders["error_message"] = await extract_error_message(
                        resp, "HTTP 401"
                    )
                elif status == 403:
                    _LOGGER.debug("Validation HTTP 403 (body omitted)")
                    error_message = await extract_error_message(resp, "HTTP 403")
                    if is_invalid_api_key_message(error_message):
                        errors["base"] = "invalid_auth"
                    else:
                        errors["base"] = "cannot_connect"
                    placeholders["error_message"] = error_message
                elif status == 429:
                    _LOGGER.debug("Validation HTTP 429 (body omitted)")
                    errors["base"] = "quota_exceeded"
                    placeholders["error_message"] = await extract_error_message(
                        resp, "HTTP 429"
                    )
                elif status != 200:
                    _LOGGER.debug("Validation HTTP %s (body omitted)", status)
                    errors["base"] = "cannot_connect"
                    placeholders["error_message"] = await extract_error_message(
                        resp, f"HTTP {status}"
                    )
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
        description_placeholders: dict[str, Any] = {
            "api_key_url": POLLEN_API_KEY_URL,
            "restricting_api_keys_url": RESTRICTING_API_KEYS_URL,
        }

        if user_input:
            sanitized_input: dict[str, Any] = dict(user_input)
            section_values = sanitized_input.get(SECTION_API_KEY_OPTIONS)
            raw_http_referer = sanitized_input.get(CONF_HTTP_REFERER)
            if raw_http_referer is None and isinstance(section_values, dict):
                raw_http_referer = section_values.get(CONF_HTTP_REFERER)
            sanitized_input.pop(SECTION_API_KEY_OPTIONS, None)

            sanitized_input.pop(CONF_HTTP_REFERER, None)
            if raw_http_referer:
                sanitized_input[CONF_HTTP_REFERER] = raw_http_referer

            errors, normalized = await self._async_validate_input(
                sanitized_input,
                check_unique_id=True,
                description_placeholders=description_placeholders,
            )
            if not errors and normalized is not None:
                entry_name = str(user_input.get(CONF_NAME, "")).strip()
                title = entry_name or DEFAULT_ENTRY_TITLE
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
            "api_key_url": POLLEN_API_KEY_URL,
            "restricting_api_keys_url": RESTRICTING_API_KEYS_URL,
        }

        if user_input:
            combined: dict[str, Any] = {**self._reauth_entry.data, **user_input}
            errors, normalized = await self._async_validate_input(
                combined,
                check_unique_id=False,
                description_placeholders=placeholders,
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

        options_schema = vol.Schema(
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
                vol.Optional(CONF_LANGUAGE_CODE, default=current_lang): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Optional(CONF_FORECAST_DAYS, default=current_days): NumberSelector(
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
                        mode=SelectSelectorMode.DROPDOWN,
                        options=FORECAST_SENSORS_CHOICES,
                    )
                ),
            }
        )

        if user_input is not None:
            normalized_input: dict[str, Any] = {**self.entry.options, **user_input}
            interval_value, interval_error = _parse_int_option(
                normalized_input.get(CONF_UPDATE_INTERVAL, current_interval),
                current_interval,
                min_value=1,
                error_key="invalid_update_interval",
            )
            normalized_input[CONF_UPDATE_INTERVAL] = interval_value
            if interval_error:
                errors[CONF_UPDATE_INTERVAL] = interval_error

            if errors.get(CONF_UPDATE_INTERVAL):
                return self.async_show_form(
                    step_id="init",
                    data_schema=options_schema,
                    errors=errors,
                    description_placeholders=placeholders,
                )

            forecast_days, days_error = _parse_int_option(
                normalized_input.get(CONF_FORECAST_DAYS, current_days),
                current_days,
                min_value=MIN_FORECAST_DAYS,
                max_value=MAX_FORECAST_DAYS,
                error_key="invalid_forecast_days",
            )
            normalized_input[CONF_FORECAST_DAYS] = forecast_days
            if days_error:
                errors[CONF_FORECAST_DAYS] = days_error

            try:
                # Language: allow empty; if provided, validate & normalize.
                raw_lang = normalized_input.get(
                    CONF_LANGUAGE_CODE,
                    self.entry.options.get(
                        CONF_LANGUAGE_CODE,
                        self.entry.data.get(CONF_LANGUAGE_CODE, ""),
                    ),
                )
                lang = raw_lang.strip() if isinstance(raw_lang, str) else ""
                if lang:
                    lang = is_valid_language_code(lang)
                normalized_input[CONF_LANGUAGE_CODE] = lang  # persist normalized

                # forecast_days within 1..5
                days = normalized_input[CONF_FORECAST_DAYS]

                # per-day sensors vs number of days
                mode = normalized_input.get(
                    CONF_CREATE_FORECAST_SENSORS,
                    self.entry.options.get(CONF_CREATE_FORECAST_SENSORS, "none"),
                )
                needed = {"D+1": 2, "D+1+2": 3}.get(mode, 1)
                if days < needed:
                    errors[CONF_CREATE_FORECAST_SENSORS] = "invalid_option_combo"

            except vol.Invalid as ve:
                _LOGGER.warning(
                    "Options language validation failed for '%s': %s",
                    normalized_input.get(CONF_LANGUAGE_CODE),
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
                return self.async_create_entry(title="", data=normalized_input)

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
            description_placeholders=placeholders,
        )
