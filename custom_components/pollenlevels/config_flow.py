"""Config & options flow for Pollen Levels.

Notes:
- Unified per-day sensors option ('create_forecast_sensors'): "none" | "D+1" | "D+1+2".
- Allows empty language (omit languageCode). Trims language whitespace on save.
- Redacts API keys in debug logs.
- Timeout handling: on Python 3.14, built-in `TimeoutError` also covers `asyncio.TimeoutError`,
  so catching `TimeoutError` is sufficient and preferred.

IMPORTANT:
- Keep schema construction centralized so defaults are applied consistently.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE, CONF_NAME
from homeassistant.exceptions import ConfigEntryAuthFailed
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
from homeassistant.helpers.update_coordinator import UpdateFailed

from .client import GooglePollenApiClient, PollenQuotaExceededError
from .const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LEGACY_ENTRY_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    FORECAST_SENSORS_CHOICES,
    MAX_FORECAST_DAYS,
    MAX_UPDATE_INTERVAL_HOURS,
    MIN_FORECAST_DAYS,
    MIN_UPDATE_INTERVAL_HOURS,
    POLLEN_API_KEY_URL,
    RESTRICTING_API_KEYS_URL,
    SUBENTRY_TYPE_LOCATION,
)
from .util import (
    api_key_unique_id,
    normalize_sensor_mode,
    redact_api_key,
    redact_sensitive_values,
    safe_parse_int,
    validate_latitude,
    validate_location_pair,
    validate_longitude,
)

_LOGGER = logging.getLogger(__name__)

FORECAST_DAYS_OPTIONS = [
    str(i) for i in range(MIN_FORECAST_DAYS, MAX_FORECAST_DAYS + 1)
]
_FORECAST_MODE_MIN_DAYS = {"D+1": 2, "D+1+2": 3}

# BCP-47-ish regex (common patterns, not full grammar).
LANGUAGE_CODE_REGEX = re.compile(
    r"^[A-Za-z]{2,3}"
    r"(?:-[A-Za-z]{4})?"  # optional script
    r"(?:-(?:[A-Za-z]{2}|\d{3}))?"  # optional region
    r"(?:-(?:[A-Za-z0-9]{5,8}|\d[A-Za-z0-9]{3}))?$",  # optional single variant
    re.IGNORECASE,
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


def _safe_coord(value: Any, *, lat: bool) -> float | None:
    """Return a validated latitude/longitude or None if unset/invalid."""
    if lat:
        return validate_latitude(value)
    return validate_longitude(value)


def _format_visible_coordinate(value: Any, *, lat: bool) -> str:
    """Format coordinates for UI placeholders with 2 decimals.

    Returns an empty string when value is missing or invalid.
    """
    parsed = _safe_coord(value, lat=lat)
    if parsed is None:
        return ""
    return f"{parsed:.2f}"


def _required_forecast_days_for_mode(mode: str) -> int:
    """Return the minimum forecast days required for a sensor mode."""
    return _FORECAST_MODE_MIN_DAYS.get(mode, MIN_FORECAST_DAYS)


def _normalize_forecast_mode_for_save(raw_value: Any) -> str:
    """Normalize a forecast sensor mode before saving it."""
    return normalize_sensor_mode(raw_value, _LOGGER)


def _forecast_mode_combo_error(forecast_days: int, mode: str) -> str | None:
    """Return an error key when forecast days and mode are incompatible."""
    if forecast_days < _required_forecast_days_for_mode(mode):
        return "invalid_option_combo"
    return None


def _safe_error_message(error: Exception | str, fallback: str) -> str:
    """Return a non-empty error message suitable for form placeholders."""
    message = str(error).strip()
    return message or fallback


def _redact_validation_error(
    error: object,
    api_key: str | None,
    latitude: float | None,
    longitude: float | None,
) -> str:
    """Redact validation errors before logging or showing placeholders."""
    return redact_sensitive_values(
        error,
        api_key=api_key,
        latitude=latitude,
        longitude=longitude,
    ).strip()


def _daily_info_is_valid(data: Any) -> bool:
    """Return whether a validation response contains usable dailyInfo."""
    daily_info = data.get("dailyInfo") if isinstance(data, dict) else None
    if not isinstance(daily_info, list) or not daily_info:
        return False

    has_usable_entry = False
    for item in daily_info:
        if not isinstance(item, dict):
            return False

        date = item.get("date")
        if isinstance(date, dict) and all(
            safe_parse_int(date.get(part)) is not None
            for part in ("year", "month", "day")
        ):
            has_usable_entry = True

        if isinstance(item.get("pollenTypeInfo"), list) and item["pollenTypeInfo"]:
            has_usable_entry = True

        if isinstance(item.get("plantInfo"), list) and item["plantInfo"]:
            has_usable_entry = True

    return has_usable_entry


async def _async_validate_api_location(
    hass: Any,
    *,
    api_key: str,
    latitude: float,
    longitude: float,
    language_code: str | None,
    errors: dict[str, str],
    description_placeholders: dict[str, Any],
) -> bool:
    """Validate that the API key can fetch pollen data for one location."""
    try:
        session = async_get_clientsession(hass)
        client = GooglePollenApiClient(session=session, api_key=api_key)
        data = await client.async_fetch_pollen_data(
            latitude=latitude,
            longitude=longitude,
            days=1,
            language_code=language_code,
        )

        if not _daily_info_is_valid(data):
            _LOGGER.warning("Validation: 'dailyInfo' missing or invalid")
            errors["base"] = "cannot_connect"
            description_placeholders["error_message"] = (
                "API response missing expected pollen forecast information."
            )
            return False

        return True

    except ConfigEntryAuthFailed as err:
        _LOGGER.warning("Authentication failed during validation")
        errors["base"] = "invalid_auth"
        redacted = _redact_validation_error(err, api_key, latitude, longitude)
        description_placeholders["error_message"] = _safe_error_message(
            redacted, "Authentication failed."
        )
    except PollenQuotaExceededError as err:
        errors["base"] = "quota_exceeded"
        redacted = _redact_validation_error(err, api_key, latitude, longitude)
        if re.fullmatch(r"HTTP\s+429(?::)?", redacted, flags=re.IGNORECASE):
            redacted = ""
        description_placeholders["error_message"] = _safe_error_message(
            redacted, "Quota exceeded."
        )
    except UpdateFailed as err:
        errors["base"] = "cannot_connect"
        redacted = _redact_validation_error(err, api_key, latitude, longitude)
        if re.fullmatch(r"HTTP\s+\d+(?::)?", redacted, flags=re.IGNORECASE):
            redacted = ""
        description_placeholders["error_message"] = _safe_error_message(
            redacted, "Failed to connect to the pollen service."
        )
    except TimeoutError as err:
        _LOGGER.warning(
            "Validation timeout: %s",
            _redact_validation_error(err, api_key, latitude, longitude),
        )
        errors["base"] = "cannot_connect"
        redacted = _redact_validation_error(err, api_key, latitude, longitude)
        description_placeholders["error_message"] = _safe_error_message(
            redacted, "Validation request timed out."
        )
    except aiohttp.ClientError as err:
        _LOGGER.error(
            "Connection error: %s",
            _redact_validation_error(err, api_key, latitude, longitude),
        )
        errors["base"] = "cannot_connect"
        redacted = _redact_validation_error(err, api_key, latitude, longitude)
        description_placeholders["error_message"] = _safe_error_message(
            redacted, "Network error while connecting to the pollen service."
        )
    except Exception as err:  # defensive
        _LOGGER.error(
            "Unexpected error in Pollen Levels config flow while validating input "
            "(%s): %s",
            type(err).__name__,
            _redact_validation_error(err, api_key, latitude, longitude)
            or "no error details",
        )
        errors["base"] = "unknown"
        description_placeholders.pop("error_message", None)

    return False


def _build_step_user_schema(hass: Any, user_input: dict[str, Any] | None) -> vol.Schema:
    """Build the full step user schema without flattening nested sections."""
    user_input = user_input or {}

    default_name = str(
        user_input.get(CONF_NAME)
        or getattr(hass.config, "location_name", "")
        or DEFAULT_ENTRY_TITLE
    )

    location_default = None
    if isinstance(user_input.get(CONF_LOCATION), dict):
        location_default = user_input[CONF_LOCATION]
    else:
        lat = _safe_coord(getattr(hass.config, "latitude", None), lat=True)
        lon = _safe_coord(getattr(hass.config, "longitude", None), lat=False)
        if lat is not None and lon is not None:
            location_default = {CONF_LATITUDE: lat, CONF_LONGITUDE: lon}

    if location_default is not None:
        location_field = vol.Required(CONF_LOCATION, default=location_default)
    else:
        location_field = vol.Required(CONF_LOCATION)

    update_interval_raw = user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    interval_default = _sanitize_update_interval_for_default(update_interval_raw)
    forecast_days_default = _sanitize_forecast_days_for_default(
        user_input.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS)
    )
    sensor_mode_default = _sanitize_forecast_mode_for_default(
        user_input.get(CONF_CREATE_FORECAST_SENSORS, FORECAST_SENSORS_CHOICES[0])
    )

    schema = vol.Schema(
        {
            vol.Required(CONF_API_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_NAME, default=default_name): str,
            location_field: LocationSelector(LocationSelectorConfig(radius=False)),
            vol.Optional(
                CONF_UPDATE_INTERVAL,
                default=interval_default,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_UPDATE_INTERVAL_HOURS,
                    max=MAX_UPDATE_INTERVAL_HOURS,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="h",
                )
            ),
            vol.Optional(
                CONF_LANGUAGE_CODE,
                default=user_input.get(
                    CONF_LANGUAGE_CODE, getattr(hass.config, "language", "")
                ),
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            vol.Optional(
                CONF_FORECAST_DAYS,
                default=forecast_days_default,
            ): SelectSelector(
                SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=FORECAST_DAYS_OPTIONS,
                )
            ),
            vol.Optional(
                CONF_CREATE_FORECAST_SENSORS,
                default=sensor_mode_default,
            ): SelectSelector(
                SelectSelectorConfig(
                    mode=SelectSelectorMode.DROPDOWN,
                    options=FORECAST_SENSORS_CHOICES,
                )
            ),
        }
    )
    return schema


def _build_location_subentry_schema(
    hass: Any,
    user_input: dict[str, Any] | None,
    *,
    name_default: str | None = None,
    location_default: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build the schema for adding or editing one location subentry."""
    user_input = user_input or {}
    default_name = str(
        user_input.get(CONF_NAME)
        or name_default
        or getattr(hass.config, "location_name", "")
        or DEFAULT_ENTRY_TITLE
    )

    if isinstance(user_input.get(CONF_LOCATION), dict):
        location_default = user_input[CONF_LOCATION]
    elif location_default is None:
        lat = _safe_coord(getattr(hass.config, "latitude", None), lat=True)
        lon = _safe_coord(getattr(hass.config, "longitude", None), lat=False)
        if lat is not None and lon is not None:
            location_default = {CONF_LATITUDE: lat, CONF_LONGITUDE: lon}

    if location_default is not None:
        location_field = vol.Required(CONF_LOCATION, default=location_default)
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

    return validate_location_pair(lat_val, lon_val)


def _api_key_unique_id(api_key: str) -> str:
    """Return a stable, non-secret unique ID for one shared API key."""
    return api_key_unique_id(api_key)


def _location_unique_id(lat: float, lon: float) -> str:
    """Return the legacy coordinate unique ID format."""
    return f"{lat:.4f}_{lon:.4f}"


def _location_subentry_data(
    *,
    title: str,
    lat: float,
    lon: float,
    legacy_entry_id: str | None = None,
) -> dict[str, Any]:
    """Return ConfigSubentryData for one pollen location."""
    data: dict[str, Any] = {
        CONF_LATITUDE: lat,
        CONF_LONGITUDE: lon,
    }
    if legacy_entry_id:
        data[CONF_LEGACY_ENTRY_ID] = legacy_entry_id
    return {
        "subentry_type": SUBENTRY_TYPE_LOCATION,
        "title": title,
        "data": data,
        "unique_id": _location_unique_id(lat, lon),
    }


def _parent_entry_data(normalized: dict[str, Any]) -> dict[str, Any]:
    """Return parent config entry data for v3 storage."""
    return {CONF_API_KEY: normalized[CONF_API_KEY]}


def _parent_entry_options(normalized: dict[str, Any]) -> dict[str, Any]:
    """Return parent config entry options for v3 storage."""
    options: dict[str, Any] = {}
    for key in (
        CONF_UPDATE_INTERVAL,
        CONF_LANGUAGE_CODE,
        CONF_FORECAST_DAYS,
        CONF_CREATE_FORECAST_SENSORS,
    ):
        if key in normalized:
            options[key] = normalized[key]
    return options


def _entry_api_key(entry: config_entries.ConfigEntry) -> str | None:
    """Return a stripped parent API key or None when unavailable."""
    raw_api_key = (entry.data or {}).get(CONF_API_KEY)
    if not isinstance(raw_api_key, str):
        return None
    api_key = raw_api_key.strip()
    return api_key or None


def _entry_language_code(entry: config_entries.ConfigEntry) -> str | None:
    """Return the parent API response language for subentry validation."""
    raw_language = (entry.options or {}).get(
        CONF_LANGUAGE_CODE, (entry.data or {}).get(CONF_LANGUAGE_CODE)
    )
    if not isinstance(raw_language, str):
        return None
    language = raw_language.strip()
    return language or None


def _first_location_data(entry: config_entries.ConfigEntry) -> dict[str, Any]:
    """Return the first location data for validating parent reauth/reconfigure."""
    location_data = _location_data_for_validation(entry)
    if location_data:
        return location_data[0]
    return dict(entry.data or {})


def _location_data_for_validation(
    entry: config_entries.ConfigEntry,
) -> list[dict[str, Any]]:
    """Return all configured location data candidates for API-key validation."""
    locations: list[dict[str, Any]] = []
    for subentry in (getattr(entry, "subentries", {}) or {}).values():
        if getattr(subentry, "subentry_type", None) == SUBENTRY_TYPE_LOCATION:
            locations.append(dict(subentry.data or {}))
    if locations:
        return locations
    data = dict(entry.data or {})
    if CONF_LATITUDE in data or CONF_LONGITUDE in data:
        return [data]
    return []


def _should_try_next_location(errors: dict[str, str]) -> bool:
    """Return whether validation failure may be specific to one location."""
    if errors == {"base": "invalid_coordinates"}:
        return True
    return errors == {"base": "cannot_connect"}


def _has_duplicate_location(
    entry: config_entries.ConfigEntry,
    unique_id: str,
    *,
    current_subentry_id: str | None = None,
) -> bool:
    """Return whether a location unique id already exists in this parent entry."""
    for subentry in (getattr(entry, "subentries", {}) or {}).values():
        if getattr(subentry, "subentry_type", None) != SUBENTRY_TYPE_LOCATION:
            continue
        if current_subentry_id and subentry.subentry_id == current_subentry_id:
            continue
        if getattr(subentry, "unique_id", None) == unique_id:
            return True
    return False


def _entry_for_parent_unique_id(
    hass: Any, unique_id: str
) -> config_entries.ConfigEntry | None:
    """Return an existing parent entry with this API-key unique ID."""
    config_entry_manager = getattr(hass, "config_entries", None)
    lookup = getattr(config_entry_manager, "async_entry_for_domain_unique_id", None)
    if callable(lookup):
        return lookup(DOMAIN, unique_id)

    async_entries = getattr(config_entry_manager, "async_entries", None)
    if callable(async_entries):
        for candidate in async_entries(DOMAIN):
            if getattr(candidate, "unique_id", None) == unique_id:
                return candidate
    return None


async def _async_reload_parent_after_subentry_create(hass: Any, entry_id: str) -> None:
    """Reload the parent after Home Assistant persists the created subentry."""
    await asyncio.sleep(0)
    schedule_reload = getattr(hass.config_entries, "async_schedule_reload", None)
    if callable(schedule_reload):
        schedule_reload(entry_id)
        return

    async_reload = getattr(hass.config_entries, "async_reload", None)
    if callable(async_reload):
        result = async_reload(entry_id)
        if asyncio.iscoroutine(result):
            await result


def _parse_int_option(
    value: Any,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
    error_key: str | None = None,
) -> tuple[int, str | None]:
    """Parse a numeric option to int and enforce bounds."""
    parsed = safe_parse_int(value if value is not None else default)
    if parsed is None:
        return default, error_key

    if min_value is not None and parsed < min_value:
        return parsed, error_key

    if max_value is not None and parsed > max_value:
        return parsed, error_key

    return parsed, None


def _parse_update_interval(value: Any, default: int) -> tuple[int, str | None]:
    """Parse and validate the update interval in hours."""
    return _parse_int_option(
        value,
        default=default,
        min_value=MIN_UPDATE_INTERVAL_HOURS,
        max_value=MAX_UPDATE_INTERVAL_HOURS,
        error_key="invalid_update_interval",
    )


def _sanitize_update_interval_for_default(raw_value: Any) -> int:
    """Parse and clamp an update interval value to be used as a UI default."""
    parsed, _ = _parse_update_interval(raw_value, DEFAULT_UPDATE_INTERVAL)
    return max(MIN_UPDATE_INTERVAL_HOURS, min(MAX_UPDATE_INTERVAL_HOURS, parsed))


def _sanitize_forecast_days_for_default(raw_value: Any) -> str:
    """Parse and clamp forecast days to be used as a UI default."""
    parsed, _ = _parse_int_option(
        raw_value,
        DEFAULT_FORECAST_DAYS,
        min_value=MIN_FORECAST_DAYS,
        max_value=MAX_FORECAST_DAYS,
        error_key="invalid_forecast_days",
    )
    parsed = max(MIN_FORECAST_DAYS, min(MAX_FORECAST_DAYS, parsed))
    return str(parsed)


def _sanitize_forecast_mode_for_default(raw_value: Any) -> str:
    """Normalize forecast sensor mode to be used as a UI default."""
    mode = normalize_sensor_mode(raw_value, _LOGGER)
    if mode in FORECAST_SENSORS_CHOICES:
        return mode
    return FORECAST_SENSORS_CHOICES[0]


class PollenLevelsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Pollen Levels."""

    VERSION = 6

    @staticmethod
    def async_get_options_flow(
        entry: config_entries.ConfigEntry,
    ) -> PollenLevelsOptionsFlow:
        """Return the options flow handler."""
        return PollenLevelsOptionsFlow()

    @classmethod
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {SUBENTRY_TYPE_LOCATION: PollenLevelsLocationSubentryFlow}

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

        api_key = str(user_input.get(CONF_API_KEY, "")) if user_input else ""
        api_key = api_key.strip()

        if not api_key:
            errors[CONF_API_KEY] = "empty"
            return errors, None

        interval_value, interval_error = _parse_update_interval(
            normalized.get(CONF_UPDATE_INTERVAL),
            default=DEFAULT_UPDATE_INTERVAL,
        )
        normalized[CONF_UPDATE_INTERVAL] = interval_value
        if interval_error:
            errors[CONF_UPDATE_INTERVAL] = interval_error
            placeholders.pop("error_message", None)
            return errors, None

        forecast_days, days_error = _parse_int_option(
            normalized.get(CONF_FORECAST_DAYS),
            DEFAULT_FORECAST_DAYS,
            min_value=MIN_FORECAST_DAYS,
            max_value=MAX_FORECAST_DAYS,
            error_key="invalid_forecast_days",
        )
        normalized[CONF_FORECAST_DAYS] = forecast_days
        if days_error:
            errors[CONF_FORECAST_DAYS] = days_error
            placeholders.pop("error_message", None)
            return errors, None

        mode = _normalize_forecast_mode_for_save(
            normalized.get(CONF_CREATE_FORECAST_SENSORS, FORECAST_SENSORS_CHOICES[0])
        )
        combo_error = _forecast_mode_combo_error(forecast_days, mode)
        if combo_error:
            errors[CONF_CREATE_FORECAST_SENSORS] = combo_error
            placeholders.pop("error_message", None)
            return errors, None
        normalized[CONF_CREATE_FORECAST_SENSORS] = mode

        latlon = None
        if CONF_LOCATION in user_input:
            latlon = _validate_location_dict(user_input.get(CONF_LOCATION))
            if latlon is None:
                _LOGGER.debug(
                    "Invalid coordinates provided (values redacted): parsing failed"
                )
                errors[CONF_LOCATION] = "invalid_coordinates"
                placeholders.pop("error_message", None)
                return errors, None
        else:
            latlon = validate_location_pair(
                user_input.get(CONF_LATITUDE), user_input.get(CONF_LONGITUDE)
            )
            if latlon is None:
                _LOGGER.debug(
                    "Invalid coordinates provided (values redacted): parsing failed"
                )
                errors["base"] = "invalid_coordinates"
                placeholders.pop("error_message", None)
                return errors, None

        lat, lon = latlon
        normalized[CONF_LATITUDE] = lat
        normalized[CONF_LONGITUDE] = lon

        if check_unique_id:
            # Keep unique_id formatting aligned with legacy entries for
            # duplicate detection compatibility across upgrades.
            uid = f"{lat:.4f}_{lon:.4f}"
            try:
                await self.async_set_unique_id(uid, raise_on_progress=False)
                self._abort_if_unique_id_configured()
            except Exception as err:  # defensive
                _LOGGER.exception(
                    "Unique ID setup failed for coordinates (values redacted): %s",
                    redact_api_key(err, api_key),
                )
                raise

        normalized[CONF_API_KEY] = api_key

        try:
            raw_lang = user_input.get(CONF_LANGUAGE_CODE, "")
            lang = raw_lang.strip() if isinstance(raw_lang, str) else ""
            if lang:
                lang = is_valid_language_code(lang)

            if not await _async_validate_api_location(
                self.hass,
                api_key=api_key,
                latitude=lat,
                longitude=lon,
                language_code=lang or None,
                errors=errors,
                description_placeholders=placeholders,
            ):
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
            placeholders.pop("error_message", None)

        return errors, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle initial step."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, Any] = {
            "api_key_url": POLLEN_API_KEY_URL,
            "restricting_api_keys_url": RESTRICTING_API_KEYS_URL,
        }

        if user_input:
            sanitized_input: dict[str, Any] = dict(user_input)

            errors, normalized = await self._async_validate_input(
                sanitized_input,
                check_unique_id=False,
                description_placeholders=description_placeholders,
            )
            if not errors and normalized is not None:
                await self.async_set_unique_id(
                    _api_key_unique_id(normalized[CONF_API_KEY]),
                    raise_on_progress=False,
                )
                if hasattr(
                    getattr(self.hass, "config_entries", None),
                    "async_entry_for_domain_unique_id",
                ):
                    self._abort_if_unique_id_configured()
                entry_name = str(user_input.get(CONF_NAME, "")).strip()
                title = entry_name or DEFAULT_ENTRY_TITLE
                subentry = _location_subentry_data(
                    title=title,
                    lat=normalized[CONF_LATITUDE],
                    lon=normalized[CONF_LONGITUDE],
                )
                return self.async_create_entry(
                    title=title,
                    data=_parent_entry_data(normalized),
                    options=_parent_entry_options(normalized),
                    subentries=[subentry],
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_step_user_schema(self.hass, user_input),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle re-authentication when credentials become invalid."""
        return await self.async_step_reauth_confirm()

    async def _async_handle_api_key_confirm(
        self,
        *,
        entry: config_entries.ConfigEntry,
        step_id: str,
        success_reason: str,
        user_input: dict[str, Any] | None,
        persist_normalized_data: bool = True,
    ) -> config_entries.ConfigFlowResult:
        """Render/process an API-key confirmation step for an existing entry."""
        errors: dict[str, str] = {}
        location_data = _first_location_data(entry)
        placeholders = {
            "latitude": _format_visible_coordinate(
                location_data.get(CONF_LATITUDE), lat=True
            ),
            "longitude": _format_visible_coordinate(
                location_data.get(CONF_LONGITUDE), lat=False
            ),
            "api_key_url": POLLEN_API_KEY_URL,
            "restricting_api_keys_url": RESTRICTING_API_KEYS_URL,
        }

        if user_input:
            location_candidates = _location_data_for_validation(entry) or [
                dict(entry.data or {})
            ]
            display_errors: dict[str, str] | None = None
            display_placeholders: dict[str, Any] | None = None

            for candidate in location_candidates:
                candidate_placeholders = dict(placeholders)
                combined: dict[str, Any] = {
                    **entry.options,
                    **entry.data,
                    **candidate,
                    **user_input,
                }
                errors, normalized = await self._async_validate_input(
                    combined,
                    check_unique_id=False,
                    description_placeholders=candidate_placeholders,
                )
                if not errors and normalized is not None:
                    updated_api_key = str(normalized.get(CONF_API_KEY, "")).strip()
                    updated_unique_id = _api_key_unique_id(updated_api_key)
                    existing_entry = _entry_for_parent_unique_id(
                        self.hass, updated_unique_id
                    )
                    if existing_entry is not None and getattr(
                        existing_entry, "entry_id", None
                    ) != getattr(entry, "entry_id", None):
                        errors = {"base": "already_configured"}
                        display_errors = errors
                        display_placeholders = candidate_placeholders
                        break
                    if persist_normalized_data:
                        data_updates = normalized
                    else:
                        data_updates = {
                            CONF_API_KEY: updated_api_key,
                        }
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates=data_updates,
                        unique_id=updated_unique_id,
                        reason=success_reason,
                    )

                if not _should_try_next_location(errors):
                    display_errors = errors
                    display_placeholders = candidate_placeholders
                    break
                if display_errors is None:
                    display_errors = errors
                    display_placeholders = candidate_placeholders

            errors = display_errors or errors
            if display_placeholders is not None:
                placeholders.update(display_placeholders)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_API_KEY,
                    default="",
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
            }
        )

        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Prompt for a refreshed API key and validate it."""
        entry = self._get_reauth_entry()
        if entry is None:
            return self.async_abort(reason="reauth_failed")
        return await self._async_handle_api_key_confirm(
            entry=entry,
            step_id="reauth_confirm",
            success_reason="reauth_successful",
            user_input=user_input,
            persist_normalized_data=False,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Prompt for a refreshed API key from the reconfigure UI."""
        entry = self._get_reconfigure_entry()
        if entry is None:
            return self.async_abort(reason="reconfigure_failed")
        return await self._async_handle_api_key_confirm(
            entry=entry,
            step_id="reconfigure",
            success_reason="reconfigure_successful",
            user_input=user_input,
            persist_normalized_data=False,
        )


class PollenLevelsLocationSubentryFlow(config_entries.ConfigSubentryFlow):
    """Handle adding and updating pollen location subentries."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Add a new pollen location to an existing parent entry."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, Any] = {}
        entry = self._get_entry()

        if user_input is not None:
            title = str(user_input.get(CONF_NAME, "")).strip() or DEFAULT_ENTRY_TITLE
            latlon = _validate_location_dict(user_input.get(CONF_LOCATION))
            if latlon is None:
                errors[CONF_LOCATION] = "invalid_coordinates"
            else:
                lat, lon = latlon
                unique_id = _location_unique_id(lat, lon)
                if _has_duplicate_location(entry, unique_id):
                    errors["base"] = "already_configured"
                else:
                    api_key = _entry_api_key(entry)
                    if api_key is None:
                        errors["base"] = "invalid_auth"
                        description_placeholders["error_message"] = "Invalid API key."
                    elif await _async_validate_api_location(
                        self.hass,
                        api_key=api_key,
                        latitude=lat,
                        longitude=lon,
                        language_code=_entry_language_code(entry),
                        errors=errors,
                        description_placeholders=description_placeholders,
                    ):
                        self.hass.async_create_task(
                            _async_reload_parent_after_subentry_create(
                                self.hass, entry.entry_id
                            ),
                            name=(
                                "reload Pollen Levels parent after location "
                                "subentry create"
                            ),
                        )
                        return self.async_create_entry(
                            title=title,
                            data={CONF_LATITUDE: lat, CONF_LONGITUDE: lon},
                            unique_id=unique_id,
                        )

        form_kwargs: dict[str, Any] = {
            "step_id": "user",
            "data_schema": _build_location_subentry_schema(self.hass, user_input),
            "errors": errors,
        }
        if description_placeholders:
            form_kwargs["description_placeholders"] = description_placeholders
        return self.async_show_form(**form_kwargs)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Update an existing pollen location subentry."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, Any] = {}
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        subentry_data = dict(subentry.data or {})
        location_default = {
            CONF_LATITUDE: subentry_data.get(CONF_LATITUDE),
            CONF_LONGITUDE: subentry_data.get(CONF_LONGITUDE),
        }

        if user_input is not None:
            title = str(user_input.get(CONF_NAME, "")).strip() or DEFAULT_ENTRY_TITLE
            latlon = _validate_location_dict(user_input.get(CONF_LOCATION))
            if latlon is None:
                errors[CONF_LOCATION] = "invalid_coordinates"
            else:
                lat, lon = latlon
                unique_id = _location_unique_id(lat, lon)
                if _has_duplicate_location(
                    entry, unique_id, current_subentry_id=subentry.subentry_id
                ):
                    errors["base"] = "already_configured"
                else:
                    api_key = _entry_api_key(entry)
                    if api_key is None:
                        errors["base"] = "invalid_auth"
                        description_placeholders["error_message"] = "Invalid API key."
                    elif await _async_validate_api_location(
                        self.hass,
                        api_key=api_key,
                        latitude=lat,
                        longitude=lon,
                        language_code=_entry_language_code(entry),
                        errors=errors,
                        description_placeholders=description_placeholders,
                    ):
                        data = {
                            CONF_LATITUDE: lat,
                            CONF_LONGITUDE: lon,
                        }
                        legacy_entry_id = subentry_data.get(CONF_LEGACY_ENTRY_ID)
                        if legacy_entry_id:
                            data[CONF_LEGACY_ENTRY_ID] = legacy_entry_id
                        return self.async_update_reload_and_abort(
                            entry,
                            subentry,
                            title=title,
                            data=data,
                            unique_id=unique_id,
                        )

        form_kwargs: dict[str, Any] = {
            "step_id": "reconfigure",
            "data_schema": _build_location_subentry_schema(
                self.hass,
                user_input,
                name_default=subentry.title,
                location_default=location_default,
            ),
            "errors": errors,
        }
        if description_placeholders:
            form_kwargs["description_placeholders"] = description_placeholders
        return self.async_show_form(**form_kwargs)


class PollenLevelsOptionsFlow(config_entries.OptionsFlowWithReload):
    """Handle options for an existing entry."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Display/process options form."""
        errors: dict[str, str] = {}
        placeholders = {"title": self.config_entry.title or DEFAULT_ENTRY_TITLE}

        current_interval_raw = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL,
            self.config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        current_interval = _sanitize_update_interval_for_default(current_interval_raw)
        current_lang = self.config_entry.options.get(
            CONF_LANGUAGE_CODE,
            self.config_entry.data.get(CONF_LANGUAGE_CODE, self.hass.config.language),
        )
        current_days_raw = self.config_entry.options.get(
            CONF_FORECAST_DAYS,
            self.config_entry.data.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS),
        )
        current_days_default = _sanitize_forecast_days_for_default(current_days_raw)
        current_days = int(current_days_default)
        current_mode = self.config_entry.options.get(CONF_CREATE_FORECAST_SENSORS)
        if current_mode is None:
            current_mode = self.config_entry.data.get(
                CONF_CREATE_FORECAST_SENSORS, "none"
            )
        current_mode = _sanitize_forecast_mode_for_default(current_mode)

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL, default=current_interval
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_UPDATE_INTERVAL_HOURS,
                        max=MAX_UPDATE_INTERVAL_HOURS,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="h",
                    )
                ),
                vol.Optional(CONF_LANGUAGE_CODE, default=current_lang): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Optional(
                    CONF_FORECAST_DAYS, default=current_days_default
                ): SelectSelector(
                    SelectSelectorConfig(
                        mode=SelectSelectorMode.DROPDOWN,
                        options=FORECAST_DAYS_OPTIONS,
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
            normalized_input: dict[str, Any] = {
                **self.config_entry.options,
                **user_input,
            }
            interval_value, interval_error = _parse_update_interval(
                normalized_input.get(CONF_UPDATE_INTERVAL, current_interval),
                current_interval,
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
                raw_lang = normalized_input.get(
                    CONF_LANGUAGE_CODE,
                    self.config_entry.options.get(
                        CONF_LANGUAGE_CODE,
                        self.config_entry.data.get(CONF_LANGUAGE_CODE, ""),
                    ),
                )
                lang = raw_lang.strip() if isinstance(raw_lang, str) else ""
                if lang:
                    lang = is_valid_language_code(lang)
                normalized_input[CONF_LANGUAGE_CODE] = lang

                days = normalized_input[CONF_FORECAST_DAYS]
                mode = _normalize_forecast_mode_for_save(
                    normalized_input.get(
                        CONF_CREATE_FORECAST_SENSORS,
                        current_mode,
                    )
                )
                normalized_input[CONF_CREATE_FORECAST_SENSORS] = mode
                combo_error = _forecast_mode_combo_error(days, mode)
                if combo_error:
                    errors[CONF_CREATE_FORECAST_SENSORS] = combo_error

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
                    redact_api_key(err, self.config_entry.data.get(CONF_API_KEY)),
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
