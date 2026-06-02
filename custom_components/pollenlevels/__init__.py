"""Initialize Pollen Levels integration.

Notes:
- Adds a top-level DEBUG log when the force_update service is invoked to aid debugging.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol  # Service schema validation
from homeassistant.config_entries import ConfigEntry, ConfigSubentry as ConfigSubentry
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
from .migration import (
    CONF_MERGED_INTO_ENTRY_ID,
    async_handle_entry_migration,
    is_entry_merged,
)
from .runtime import (
    PollenLevelsConfigEntry,
    PollenLevelsRuntimeData,
    PollenLocationRuntime,
)
from .sensor import ForecastSensorMode
from .util import (
    api_key_unique_id as api_key_unique_id,
    normalize_sensor_mode,
    redact_sensitive_values,
    safe_parse_int,
    validate_location_pair,
)

# Ensure YAML config is entry-only for this domain (no YAML schema).
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)
TARGET_ENTRY_VERSION = 6
_FORCE_UPDATE_CONCURRENCY_LIMIT = 1
PLATFORMS = ["sensor", "button"]


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


# ---- Service -------------------------------------------------------------


async def _refresh_force_update_target(
    entry: ConfigEntry, subentry_id: str, coordinator: Any
) -> None:
    """Refresh one force_update target and log local failures."""
    try:
        await coordinator.async_request_refresh()
    except asyncio.CancelledError:
        _LOGGER.debug(
            "Manual refresh cancelled for entry %s subentry %s",
            entry.entry_id,
            subentry_id,
        )
    except Exception as result:  # noqa: BLE001
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


async def _refresh_force_update_targets(
    targets: list[tuple[ConfigEntry, str, Any]],
) -> None:
    """Refresh force_update targets with an explicit concurrency limit."""
    semaphore = asyncio.Semaphore(_FORCE_UPDATE_CONCURRENCY_LIMIT)

    async def _refresh(target: tuple[ConfigEntry, str, Any]) -> None:
        async with semaphore:
            await _refresh_force_update_target(*target)

    await asyncio.gather(*(_refresh(target) for target in targets))


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy entries to the v3 parent/subentry storage model."""
    return await async_handle_entry_migration(hass, entry, TARGET_ENTRY_VERSION)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register force_update service."""
    _LOGGER.debug("PollenLevels async_setup called")

    async def handle_force_update_service(call: ServiceCall) -> None:
        """Refresh pollen data for all entries."""
        _LOGGER.debug("Executing force_update service for all Pollen Levels entries")
        entries = list(hass.config_entries.async_entries(DOMAIN))
        targets: list[tuple[ConfigEntry, str, Any]] = []
        for entry in entries:
            runtime = getattr(entry, "runtime_data", None)
            locations = getattr(runtime, "locations", None) or {}
            if not locations:
                coordinator = getattr(runtime, "coordinator", None)
                if coordinator:
                    targets.append((entry, entry.entry_id, coordinator))
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
                targets.append((entry, location.subentry_id, coordinator))

        if not targets:
            _LOGGER.debug("No coordinators available for force_update")
            return

        await _refresh_force_update_targets(targets)

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
    if is_entry_merged(entry):
        _LOGGER.debug(
            "Skipping setup for merged entry %s (merged into %s)",
            entry.entry_id,
            entry.data.get(CONF_MERGED_INTO_ENTRY_ID),
        )
        return True

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
    except ValueError, TypeError:
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

    location_configs = _iter_location_subentries(entry)
    locations: dict[str, PollenLocationRuntime] = {}
    for subentry_id, title, data, legacy_entry_id in location_configs:
        raw_lat = data.get(CONF_LATITUDE)
        raw_lon = data.get(CONF_LONGITUDE)
        latlon = validate_location_pair(raw_lat, raw_lon)
        if latlon is None:
            _LOGGER.warning(
                "Invalid coordinates for entry %s subentry %s",
                entry.entry_id,
                subentry_id,
            )
            continue
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
        except ConfigEntryNotReady as err:
            safe_message = redact_sensitive_values(
                err, api_key=api_key, latitude=lat, longitude=lon
            )
            _LOGGER.warning(
                "Initial data refresh failed for entry %s subentry %s (%s): %s",
                entry.entry_id,
                subentry_id,
                type(err).__name__,
                safe_message or "no error details",
            )
            continue
        except Exception as err:
            safe_message = redact_sensitive_values(
                err, api_key=api_key, latitude=lat, longitude=lon
            )
            _LOGGER.warning(
                "Initial data refresh failed for entry %s subentry %s (%s): %s",
                entry.entry_id,
                subentry_id,
                type(err).__name__,
                safe_message or "no error details",
            )
            continue

        locations[subentry_id] = PollenLocationRuntime(
            subentry_id=subentry_id,
            coordinator=coordinator,
            legacy_entry_id=legacy_entry_id,
        )

    if location_configs and not locations:
        raise ConfigEntryNotReady(
            "No Pollen Levels locations could be initialized"
        ) from None

    entry.runtime_data = PollenLevelsRuntimeData(client=client, locations=locations)

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except ConfigEntryAuthFailed, ConfigEntryNotReady:
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
