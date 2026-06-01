"""Initialize Pollen Levels integration.

Notes:
- Adds a top-level DEBUG log when the force_update service is invoked to aid debugging.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable
from types import MappingProxyType
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol  # Service schema validation
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import GooglePollenApiClient
from .const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LEGACY_ENTRY_ID,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_FORECAST_DAYS,
    MAX_UPDATE_INTERVAL_HOURS,
    MIN_FORECAST_DAYS,
    MIN_UPDATE_INTERVAL_HOURS,
    SUBENTRY_TYPE_LOCATION,
)
from .coordinator import PollenDataUpdateCoordinator
from .runtime import (
    PollenLevelsConfigEntry,
    PollenLevelsRuntimeData,
    PollenLocationRuntime,
)
from .sensor import ForecastSensorMode
from .util import (
    normalize_sensor_mode,
    redact_sensitive_values,
    safe_parse_int,
    validate_location_pair,
)

# Ensure YAML config is entry-only for this domain (no YAML schema).
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)
TARGET_ENTRY_VERSION = 4
PLATFORMS = ["sensor", "button"]

# ---- Service -------------------------------------------------------------


def _coordinates_are_valid(lat: float, lon: float) -> bool:
    """Return whether coordinates are finite and in accepted ranges."""
    return (
        math.isfinite(lat)
        and math.isfinite(lon)
        and -90.0 <= lat <= 90.0
        and -180.0 <= lon <= 180.0
    )


def _location_unique_id(lat: Any, lon: Any) -> str | None:
    """Return the legacy coordinate unique id if coordinates are valid."""
    try:
        lat_float = float(lat)
        lon_float = float(lon)
    except (TypeError, ValueError):
        return None
    if not _coordinates_are_valid(lat_float, lon_float):
        return None
    return f"{lat_float:.4f}_{lon_float:.4f}"


def _iter_location_subentries(
    entry: ConfigEntry,
) -> list[tuple[str, str, dict[str, Any], str | None]]:
    """Return location configuration tuples for setup."""
    subentries = getattr(entry, "subentries", {}) or {}
    locations: list[tuple[str, str, dict[str, Any], str | None]] = []
    for subentry in subentries.values():
        if getattr(subentry, "subentry_type", None) != SUBENTRY_TYPE_LOCATION:
            continue
        data = dict(getattr(subentry, "data", {}) or {})
        legacy_entry_id = data.get(CONF_LEGACY_ENTRY_ID)
        if not isinstance(legacy_entry_id, str) or not legacy_entry_id:
            legacy_entry_id = None
        locations.append(
            (
                subentry.subentry_id,
                (subentry.title or "").strip() or DEFAULT_ENTRY_TITLE,
                data,
                legacy_entry_id,
            )
        )

    if locations:
        return locations

    # Compatibility fallback for not-yet-migrated or test entries.
    data = dict(entry.data or {})
    if CONF_LATITUDE in data and CONF_LONGITUDE in data:
        locations.append(
            (
                entry.entry_id,
                (entry.title or "").strip() or DEFAULT_ENTRY_TITLE,
                data,
                entry.entry_id,
            )
        )
    return locations


def _make_migrated_subentry(entry: ConfigEntry) -> ConfigSubentry | None:
    """Build the one-location subentry used by the conservative v3 migration."""
    data = dict(entry.data or {})
    if CONF_LATITUDE not in data or CONF_LONGITUDE not in data:
        return None

    title = (entry.title or "").strip() or DEFAULT_ENTRY_TITLE
    subentry_data = {
        CONF_LATITUDE: data.get(CONF_LATITUDE),
        CONF_LONGITUDE: data.get(CONF_LONGITUDE),
        CONF_LEGACY_ENTRY_ID: entry.entry_id,
    }
    return ConfigSubentry(
        data=MappingProxyType(subentry_data),
        subentry_type=SUBENTRY_TYPE_LOCATION,
        title=title,
        unique_id=_location_unique_id(
            subentry_data[CONF_LATITUDE], subentry_data[CONF_LONGITUDE]
        ),
    )


def _add_migrated_subentry_for_tests(
    entry: ConfigEntry, subentry: ConfigSubentry
) -> None:
    """Fallback used by lightweight tests without Home Assistant's entry manager."""
    subentries = dict(getattr(entry, "subentries", {}) or {})
    subentries[subentry.subentry_id] = subentry
    entry.subentries = subentries


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy entries to the v3 parent/subentry storage model."""
    try:
        target_version = TARGET_ENTRY_VERSION
        current_version_raw = getattr(entry, "version", 1)
        current_version = (
            current_version_raw if isinstance(current_version_raw, int) else 1
        )
        legacy_key = "http_referer"
        existing_data = entry.data or {}
        existing_options = entry.options or {}
        existing_subentries = getattr(entry, "subentries", {}) or {}
        cleanup_needed = (
            legacy_key in existing_data
            or legacy_key in existing_options
            or CONF_CREATE_FORECAST_SENSORS in existing_data
            or CONF_LATITUDE in existing_data
            or CONF_LONGITUDE in existing_data
            or CONF_UPDATE_INTERVAL in existing_data
            or CONF_LANGUAGE_CODE in existing_data
            or CONF_FORECAST_DAYS in existing_data
            or not existing_subentries
        )
        if not cleanup_needed and CONF_CREATE_FORECAST_SENSORS in existing_options:
            stored_mode = existing_options.get(CONF_CREATE_FORECAST_SENSORS)
            stored_mode_raw = getattr(stored_mode, "value", stored_mode)
            if stored_mode_raw is not None:
                stored_mode_raw = str(stored_mode_raw)
                cleanup_needed = (
                    normalize_sensor_mode(stored_mode_raw, _LOGGER) != stored_mode_raw
                )
        if current_version >= target_version and not cleanup_needed:
            return True

        new_data = {CONF_API_KEY: existing_data.get(CONF_API_KEY)}
        new_data = {
            key: value
            for key, value in new_data.items()
            if isinstance(value, str) and value.strip()
        }
        new_options = dict(existing_options)
        for option_key in (
            CONF_UPDATE_INTERVAL,
            CONF_LANGUAGE_CODE,
            CONF_FORECAST_DAYS,
        ):
            if option_key not in new_options and option_key in existing_data:
                new_options[option_key] = existing_data[option_key]

        mode = new_options.get(
            CONF_CREATE_FORECAST_SENSORS,
            existing_data.get(CONF_CREATE_FORECAST_SENSORS),
        )

        mode_raw = getattr(mode, "value", mode)
        if mode_raw is not None:
            mode_raw = str(mode_raw)
            normalized_mode = normalize_sensor_mode(mode_raw, _LOGGER)
            if new_options.get(CONF_CREATE_FORECAST_SENSORS) != normalized_mode:
                new_options[CONF_CREATE_FORECAST_SENSORS] = normalized_mode
        else:
            new_options.pop(CONF_CREATE_FORECAST_SENSORS, None)

        new_options.pop(legacy_key, None)

        if not existing_subentries:
            subentry = _make_migrated_subentry(entry)
            if subentry is not None:
                if hasattr(hass.config_entries, "async_add_subentry"):
                    hass.config_entries.async_add_subentry(entry, subentry)
                else:
                    _add_migrated_subentry_for_tests(entry, subentry)

        new_version = max(current_version, target_version)
        if new_data != existing_data or new_options != existing_options:
            hass.config_entries.async_update_entry(
                entry, data=new_data, options=new_options, version=new_version
            )
        else:
            hass.config_entries.async_update_entry(entry, version=new_version)
        return True
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        _LOGGER.exception(
            "Failed to migrate per-day sensor mode to entry options for entry %s "
            "(version=%s)",
            entry.entry_id,
            getattr(entry, "version", None),
        )
        return False


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register force_update service."""
    _LOGGER.debug("PollenLevels async_setup called")

    async def handle_force_update_service(call: ServiceCall) -> None:
        """Refresh pollen data for all entries."""
        _LOGGER.debug("Executing force_update service for all Pollen Levels entries")
        entries = list(hass.config_entries.async_entries(DOMAIN))
        tasks: list[Awaitable[None]] = []
        task_entries: list[tuple[ConfigEntry, str, Any]] = []
        for entry in entries:
            runtime = getattr(entry, "runtime_data", None)
            locations = getattr(runtime, "locations", None) or {}
            if not locations:
                coordinator = getattr(runtime, "coordinator", None)
                if coordinator:
                    tasks.append(coordinator.async_request_refresh())
                    task_entries.append((entry, entry.entry_id, coordinator))
                    continue
                _LOGGER.debug(
                    "Skipping force_update for entry %s (no location coordinators)",
                    entry.entry_id,
                )
                continue

            for location in locations.values():
                coordinator = getattr(location, "coordinator", None)
                if not coordinator:
                    continue
                tasks.append(coordinator.async_request_refresh())
                task_entries.append((entry, location.subentry_id, coordinator))

        if not tasks:
            _LOGGER.debug("No coordinators available for force_update")
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for (entry, subentry_id, coordinator), result in zip(
            task_entries, results, strict=False
        ):
            if isinstance(result, asyncio.CancelledError):
                _LOGGER.debug(
                    "Manual refresh cancelled for entry %s subentry %s",
                    entry.entry_id,
                    subentry_id,
                )
                continue
            if isinstance(result, Exception):
                api_key = (entry.data or {}).get(CONF_API_KEY)
                safe_message = redact_sensitive_values(
                    result,
                    api_key=api_key,
                    latitude=getattr(
                        coordinator,
                        "lat",
                        (entry.data or {}).get(CONF_LATITUDE),
                    ),
                    longitude=getattr(
                        coordinator,
                        "lon",
                        (entry.data or {}).get(CONF_LONGITUDE),
                    ),
                )
                if subentry_id == entry.entry_id:
                    _LOGGER.warning(
                        "Manual refresh failed for entry %s (%s): %s",
                        entry.entry_id,
                        type(result).__name__,
                        safe_message or "no error details",
                    )
                else:
                    _LOGGER.warning(
                        "Manual refresh failed for entry %s subentry %s (%s): %s",
                        entry.entry_id,
                        subentry_id,
                        type(result).__name__,
                        safe_message or "no error details",
                    )

    # Enforce empty payload for the service; reject unknown fields for clearer errors.
    hass.services.async_register(
        DOMAIN, "force_update", handle_force_update_service, schema=vol.Schema({})
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: PollenLevelsConfigEntry
) -> bool:
    """Forward config entry to sensor platform."""
    _LOGGER.debug(
        "PollenLevels async_setup_entry for entry_id=%s title=%s",
        entry.entry_id,
        entry.title,
    )

    options = entry.options or {}

    parsed_hours = safe_parse_int(
        options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
    )
    hours = parsed_hours if parsed_hours is not None else DEFAULT_UPDATE_INTERVAL
    hours = max(MIN_UPDATE_INTERVAL_HOURS, min(MAX_UPDATE_INTERVAL_HOURS, hours))
    parsed_forecast_days = safe_parse_int(
        options.get(
            CONF_FORECAST_DAYS,
            entry.data.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS),
        )
    )
    forecast_days = (
        parsed_forecast_days
        if parsed_forecast_days is not None
        else DEFAULT_FORECAST_DAYS
    )
    forecast_days = max(MIN_FORECAST_DAYS, min(MAX_FORECAST_DAYS, forecast_days))
    language = options.get(CONF_LANGUAGE_CODE, entry.data.get(CONF_LANGUAGE_CODE))
    raw_mode = options.get(
        CONF_CREATE_FORECAST_SENSORS,
        entry.data.get(CONF_CREATE_FORECAST_SENSORS, ForecastSensorMode.NONE),
    )
    normalized_mode = normalize_sensor_mode(raw_mode, _LOGGER)
    try:
        mode = ForecastSensorMode(normalized_mode)
    except (ValueError, TypeError):
        mode = ForecastSensorMode.NONE
    create_d1 = (
        mode in (ForecastSensorMode.D1, ForecastSensorMode.D1_D2) and forecast_days >= 2
    )
    create_d2 = mode == ForecastSensorMode.D1_D2 and forecast_days >= 3

    api_key = entry.data.get(CONF_API_KEY)
    if not isinstance(api_key, str) or not api_key.strip():
        raise ConfigEntryAuthFailed("Invalid API key")
    api_key = api_key.strip()

    session = async_get_clientsession(hass)
    client = GooglePollenApiClient(session, api_key)

    locations: dict[str, PollenLocationRuntime] = {}
    for subentry_id, title, data, legacy_entry_id in _iter_location_subentries(entry):
        raw_lat = data.get(CONF_LATITUDE)
        raw_lon = data.get(CONF_LONGITUDE)
        latlon = validate_location_pair(raw_lat, raw_lon)
        if latlon is None:
            _LOGGER.warning(
                "Invalid coordinates for entry %s subentry %s",
                entry.entry_id,
                subentry_id,
            )
            raise ConfigEntryNotReady
        lat, lon = latlon

        coordinator = PollenDataUpdateCoordinator(
            hass=hass,
            api_key=api_key,
            lat=lat,
            lon=lon,
            hours=hours,
            language=language,
            entry_id=entry.entry_id,
            subentry_id=subentry_id,
            entry_title=title,
            legacy_entry_id=legacy_entry_id,
            forecast_days=forecast_days,
            create_d1=create_d1,
            create_d2=create_d2,
            client=client,
        )

        try:
            await coordinator.async_config_entry_first_refresh()
        except ConfigEntryAuthFailed:
            raise
        except ConfigEntryNotReady:
            raise
        except Exception as err:
            _LOGGER.exception(
                "Error during initial data refresh for entry %s subentry %s: %s",
                entry.entry_id,
                subentry_id,
                err,
            )
            raise ConfigEntryNotReady from err

        locations[subentry_id] = PollenLocationRuntime(
            subentry_id=subentry_id,
            coordinator=coordinator,
            legacy_entry_id=legacy_entry_id,
        )

    entry.runtime_data = PollenLevelsRuntimeData(client=client, locations=locations)

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except (ConfigEntryAuthFailed, ConfigEntryNotReady):
        entry.runtime_data = None
        raise
    except Exception as err:
        entry.runtime_data = None
        _LOGGER.exception("Error forwarding entry setups: %s", err)
        raise ConfigEntryNotReady from err

    _LOGGER.info("PollenLevels integration loaded successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry and remove coordinator reference."""
    _LOGGER.debug(
        "PollenLevels async_unload_entry called for entry_id=%s", entry.entry_id
    )
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data = None
    return unloaded
