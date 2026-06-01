"""Initialize Pollen Levels integration.

Notes:
- Adds a top-level DEBUG log when the force_update service is invoked to aid debugging.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
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
    api_key_unique_id,
    normalize_sensor_mode,
    redact_sensitive_values,
    safe_parse_int,
    validate_location_pair,
)

# Ensure YAML config is entry-only for this domain (no YAML schema).
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)
TARGET_ENTRY_VERSION = 5
_LEGACY_HTTP_REFERER_KEY = "http_referer"
_CONF_MERGED_INTO_ENTRY_ID = "merged_into_entry_id"
_FORCE_UPDATE_CONCURRENCY_LIMIT = 1
PLATFORMS = ["sensor", "button"]


@dataclass(frozen=True, slots=True)
class _MigrationLocation:
    """Location payload collected from a legacy config entry."""

    source_entry: ConfigEntry
    title: str
    data: dict[str, Any]
    legacy_entry_id: str | None
    unique_id: str | None


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
    except TypeError, ValueError:
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


def _entry_version(entry: ConfigEntry) -> int:
    """Return a safe integer config-entry version."""
    current_version_raw = getattr(entry, "version", 1)
    return current_version_raw if isinstance(current_version_raw, int) else 1


def _entry_api_key(entry: ConfigEntry) -> str | None:
    """Return the normalized API key stored on an entry."""
    api_key = (entry.data or {}).get(CONF_API_KEY)
    if not isinstance(api_key, str):
        return None
    api_key = api_key.strip()
    return api_key or None


def _entry_is_merged(entry: ConfigEntry) -> bool:
    """Return whether a legacy entry has already been merged into another one."""
    merged_into = (entry.data or {}).get(_CONF_MERGED_INTO_ENTRY_ID)
    return isinstance(merged_into, str) and bool(merged_into)


def _clean_parent_data(api_key: str | None) -> dict[str, Any]:
    """Return v3 parent entry data."""
    if isinstance(api_key, str) and api_key.strip():
        return {CONF_API_KEY: api_key.strip()}
    return {}


def _clean_parent_options(entry: ConfigEntry) -> dict[str, Any]:
    """Return v3 parent options migrated from legacy data/options."""
    existing_data = entry.data or {}
    existing_options = entry.options or {}
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

    new_options.pop(_LEGACY_HTTP_REFERER_KEY, None)
    return new_options


def _location_from_legacy_entry(entry: ConfigEntry) -> _MigrationLocation | None:
    """Return the location stored directly on a legacy config entry."""
    data = dict(entry.data or {})
    if CONF_LATITUDE not in data or CONF_LONGITUDE not in data:
        return None

    subentry_data = {
        CONF_LATITUDE: data.get(CONF_LATITUDE),
        CONF_LONGITUDE: data.get(CONF_LONGITUDE),
        CONF_LEGACY_ENTRY_ID: entry.entry_id,
    }
    return _MigrationLocation(
        source_entry=entry,
        title=(entry.title or "").strip() or DEFAULT_ENTRY_TITLE,
        data=subentry_data,
        legacy_entry_id=entry.entry_id,
        unique_id=_location_unique_id(
            subentry_data[CONF_LATITUDE], subentry_data[CONF_LONGITUDE]
        ),
    )


def _location_from_subentry(
    entry: ConfigEntry, subentry: ConfigSubentry
) -> _MigrationLocation | None:
    """Return a migrated legacy location stored as a subentry."""
    if getattr(subentry, "subentry_type", None) != SUBENTRY_TYPE_LOCATION:
        return None

    data = dict(getattr(subentry, "data", {}) or {})
    legacy_entry_id = data.get(CONF_LEGACY_ENTRY_ID)
    if not isinstance(legacy_entry_id, str) or not legacy_entry_id:
        return None
    if CONF_LATITUDE not in data or CONF_LONGITUDE not in data:
        return None

    subentry_data = {
        CONF_LATITUDE: data.get(CONF_LATITUDE),
        CONF_LONGITUDE: data.get(CONF_LONGITUDE),
        CONF_LEGACY_ENTRY_ID: legacy_entry_id,
    }
    unique_id = getattr(subentry, "unique_id", None) or _location_unique_id(
        subentry_data[CONF_LATITUDE], subentry_data[CONF_LONGITUDE]
    )
    return _MigrationLocation(
        source_entry=entry,
        title=(getattr(subentry, "title", "") or "").strip() or DEFAULT_ENTRY_TITLE,
        data=subentry_data,
        legacy_entry_id=legacy_entry_id,
        unique_id=unique_id,
    )


def _migration_locations(entry: ConfigEntry) -> list[_MigrationLocation]:
    """Return legacy locations to materialize as subentries."""
    locations: list[_MigrationLocation] = []
    for subentry in (getattr(entry, "subentries", {}) or {}).values():
        location = _location_from_subentry(entry, subentry)
        if location is not None:
            locations.append(location)

    if locations:
        return locations

    location = _location_from_legacy_entry(entry)
    return [location] if location is not None else []


def _has_migration_locations(entry: ConfigEntry) -> bool:
    """Return whether this entry has legacy location data."""
    return bool(_migration_locations(entry))


def _make_migrated_subentry(
    location: _MigrationLocation,
    used_unique_ids: set[str | None] | None = None,
) -> ConfigSubentry:
    """Build a location subentry for v3 migration."""
    unique_id = location.unique_id
    if used_unique_ids is not None and unique_id is not None:
        if unique_id in used_unique_ids and location.legacy_entry_id:
            unique_id = f"{unique_id}_{location.legacy_entry_id}"
        base_unique_id = unique_id
        suffix = 2
        while unique_id in used_unique_ids:
            unique_id = f"{base_unique_id}_{suffix}"
            suffix += 1
        used_unique_ids.add(unique_id)

    return ConfigSubentry(
        data=MappingProxyType(location.data),
        subentry_type=SUBENTRY_TYPE_LOCATION,
        title=location.title,
        unique_id=unique_id,
    )


def _add_migrated_subentry_for_tests(
    entry: ConfigEntry, subentry: ConfigSubentry
) -> None:
    """Fallback used by lightweight tests without Home Assistant's entry manager."""
    subentries = dict(getattr(entry, "subentries", {}) or {})
    subentries[subentry.subentry_id] = subentry
    entry.subentries = subentries


def _add_migrated_subentry(
    hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry
) -> ConfigSubentry:
    """Add a migrated subentry using HA APIs or the local test fallback."""
    if hasattr(hass.config_entries, "async_add_subentry"):
        hass.config_entries.async_add_subentry(entry, subentry)
    else:
        _add_migrated_subentry_for_tests(entry, subentry)
    return subentry


def _existing_location_indexes(
    entry: ConfigEntry,
) -> tuple[set[str | None], dict[str, ConfigSubentry]]:
    """Return existing subentry unique IDs and legacy-entry lookup."""
    unique_ids: set[str | None] = set()
    legacy_subentries: dict[str, ConfigSubentry] = {}
    for subentry in (getattr(entry, "subentries", {}) or {}).values():
        if getattr(subentry, "subentry_type", None) != SUBENTRY_TYPE_LOCATION:
            continue
        unique_ids.add(getattr(subentry, "unique_id", None))
        data = dict(getattr(subentry, "data", {}) or {})
        legacy_entry_id = data.get(CONF_LEGACY_ENTRY_ID)
        if isinstance(legacy_entry_id, str) and legacy_entry_id:
            legacy_subentries[legacy_entry_id] = subentry
    return unique_ids, legacy_subentries


def _migration_group_entries(
    hass: HomeAssistant, entry: ConfigEntry, api_key: str
) -> list[ConfigEntry]:
    """Return legacy entries sharing the same API key."""
    async_entries = getattr(hass.config_entries, "async_entries", None)
    if callable(async_entries):
        entries = list(async_entries(DOMAIN))
    else:
        entries = [entry]

    group: list[ConfigEntry] = []
    for candidate in entries:
        if _entry_is_merged(candidate):
            continue
        if _entry_api_key(candidate) != api_key:
            continue
        if candidate is entry or _has_migration_locations(candidate):
            group.append(candidate)

    if entry not in group and not _entry_is_merged(entry):
        group.append(entry)
    return group


def _select_migration_parent(
    group: list[ConfigEntry], current: ConfigEntry
) -> ConfigEntry:
    """Return the parent entry that will own the shared API-key locations."""
    for candidate in group:
        if getattr(candidate, "subentries", None):
            return candidate
    return group[0] if group else current


def _merged_entry_data(api_key: str, parent: ConfigEntry) -> dict[str, Any]:
    """Return temporary data for entries merged into another parent."""
    return {
        CONF_API_KEY: api_key,
        _CONF_MERGED_INTO_ENTRY_ID: parent.entry_id,
    }


def _entry_needs_cleanup(
    entry: ConfigEntry, current_version: int, target_version: int
) -> bool:
    """Return whether the entry still needs v3/v5 storage cleanup."""
    existing_data = entry.data or {}
    existing_options = entry.options or {}
    existing_subentries = getattr(entry, "subentries", {}) or {}
    cleanup_needed = (
        _LEGACY_HTTP_REFERER_KEY in existing_data
        or _LEGACY_HTTP_REFERER_KEY in existing_options
        or CONF_CREATE_FORECAST_SENSORS in existing_data
        or CONF_LATITUDE in existing_data
        or CONF_LONGITUDE in existing_data
        or CONF_UPDATE_INTERVAL in existing_data
        or CONF_LANGUAGE_CODE in existing_data
        or CONF_FORECAST_DAYS in existing_data
        or (
            not existing_subentries
            and not _entry_is_merged(entry)
            and current_version < target_version
        )
    )
    if not cleanup_needed and CONF_CREATE_FORECAST_SENSORS in existing_options:
        stored_mode = existing_options.get(CONF_CREATE_FORECAST_SENSORS)
        stored_mode_raw = getattr(stored_mode, "value", stored_mode)
        if stored_mode_raw is not None:
            stored_mode_raw = str(stored_mode_raw)
            cleanup_needed = (
                normalize_sensor_mode(stored_mode_raw, _LOGGER) != stored_mode_raw
            )
    return cleanup_needed


def _migrate_entity_registry_for_merged_entry(
    hass: HomeAssistant,
    source: ConfigEntry,
    parent: ConfigEntry,
    subentry: ConfigSubentry,
) -> None:
    """Attach entity-registry links from a legacy entry to the parent subentry."""
    try:
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
    except ImportError, RuntimeError, KeyError, AttributeError:
        return

    for entity in er.async_entries_for_config_entry(registry, source.entry_id):
        if getattr(entity, "platform", None) != DOMAIN:
            continue
        try:
            registry.async_update_entity(
                entity.entity_id,
                config_entry_id=parent.entry_id,
                config_subentry_id=subentry.subentry_id,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Failed to move entity %s from entry %s to parent %s",
                getattr(entity, "entity_id", "unknown"),
                source.entry_id,
                parent.entry_id,
            )


def _migrate_device_registry_for_merged_entry(
    hass: HomeAssistant,
    source: ConfigEntry,
    parent: ConfigEntry,
    subentry: ConfigSubentry,
) -> None:
    """Attach device-registry links from a legacy entry to the parent subentry."""
    try:
        from homeassistant.helpers import device_registry as dr

        registry = dr.async_get(hass)
    except ImportError, RuntimeError, KeyError, AttributeError:
        return

    for device in dr.async_entries_for_config_entry(registry, source.entry_id):
        try:
            registry.async_update_device(
                device.id,
                add_config_entry_id=parent.entry_id,
                add_config_subentry_id=subentry.subentry_id,
            )
            if source is not parent:
                registry.async_update_device(
                    device.id,
                    remove_config_entry_id=source.entry_id,
                )
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Failed to move device %s from entry %s to parent %s",
                getattr(device, "id", "unknown"),
                source.entry_id,
                parent.entry_id,
            )


def _mark_entry_merged(
    hass: HomeAssistant,
    source: ConfigEntry,
    parent: ConfigEntry,
    api_key: str,
    target_version: int,
) -> None:
    """Persist a temporary merged marker before the duplicate entry is removed."""
    hass.config_entries.async_update_entry(
        source,
        data=_merged_entry_data(api_key, parent),
        options={},
        version=max(_entry_version(source), target_version),
    )


async def _async_remove_merged_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a duplicate entry after its data has been merged."""
    async_remove = getattr(hass.config_entries, "async_remove", None)
    if async_remove is None:
        return
    result = async_remove(entry.entry_id)
    if asyncio.iscoroutine(result):
        await result


async def _remove_or_schedule_merged_entry(
    hass: HomeAssistant,
    source: ConfigEntry,
    current: ConfigEntry,
) -> None:
    """Remove merged entries, deferring the current entry until its setup lock exits."""
    if source is current:
        create_task = getattr(hass, "async_create_task", None)
        if callable(create_task):
            create_task(
                _async_remove_merged_entry(hass, source),
                name=f"remove merged {DOMAIN} entry {source.entry_id}",
            )
        return

    await _async_remove_merged_entry(hass, source)


def _update_parent_entry(
    hass: HomeAssistant,
    parent: ConfigEntry,
    api_key: str | None,
    options: dict[str, Any],
    target_version: int,
) -> None:
    """Persist cleaned parent identity, data, options, and version."""
    new_data = _clean_parent_data(api_key)
    existing_data = parent.data or {}
    existing_options = parent.options or {}
    new_version = max(_entry_version(parent), target_version)
    new_unique_id = api_key_unique_id(api_key) if api_key is not None else None
    unique_id_changed = (
        new_unique_id is not None
        and getattr(parent, "unique_id", None) != new_unique_id
    )
    if new_data != existing_data or options != existing_options or unique_id_changed:
        updates: dict[str, Any] = {
            "data": new_data,
            "options": options,
            "version": new_version,
        }
        if new_unique_id is not None:
            updates["unique_id"] = new_unique_id
        hass.config_entries.async_update_entry(parent, **updates)
    else:
        hass.config_entries.async_update_entry(parent, version=new_version)


async def _async_migrate_grouped_entries(
    hass: HomeAssistant,
    entry: ConfigEntry,
    group: list[ConfigEntry],
    api_key: str,
    target_version: int,
) -> bool:
    """Migrate all legacy entries sharing one API key into one parent."""
    parent = _select_migration_parent(group, entry)
    parent_options = _clean_parent_options(parent)
    for candidate in group:
        if candidate is parent:
            continue
        for key, value in _clean_parent_options(candidate).items():
            parent_options.setdefault(key, value)

    parent_had_subentries = bool(getattr(parent, "subentries", {}) or {})
    used_unique_ids, legacy_subentries = _existing_location_indexes(parent)

    for source in group:
        for location in _migration_locations(source):
            subentry = None
            if location.legacy_entry_id is not None:
                subentry = legacy_subentries.get(location.legacy_entry_id)
            if subentry is None:
                subentry = _make_migrated_subentry(location, used_unique_ids)
                _add_migrated_subentry(hass, parent, subentry)
                if location.legacy_entry_id is not None:
                    legacy_subentries[location.legacy_entry_id] = subentry

            if source is not parent:
                _migrate_entity_registry_for_merged_entry(
                    hass, source, parent, subentry
                )
                _migrate_device_registry_for_merged_entry(
                    hass, source, parent, subentry
                )
            elif not parent_had_subentries:
                _migrate_entity_registry_for_merged_entry(
                    hass, parent, parent, subentry
                )
                _migrate_device_registry_for_merged_entry(
                    hass, parent, parent, subentry
                )

    _update_parent_entry(hass, parent, api_key, parent_options, target_version)

    for source in group:
        if source is parent:
            continue
        _mark_entry_merged(hass, source, parent, api_key, target_version)
        await _remove_or_schedule_merged_entry(hass, source, entry)

    return True


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
    try:
        target_version = TARGET_ENTRY_VERSION
        current_version = _entry_version(entry)
        if _entry_is_merged(entry):
            hass.config_entries.async_update_entry(
                entry, version=max(current_version, target_version)
            )
            return True

        api_key = _entry_api_key(entry)
        if api_key is not None:
            group = _migration_group_entries(hass, entry, api_key)
            if len(group) > 1:
                return await _async_migrate_grouped_entries(
                    hass, entry, group, api_key, target_version
                )

        existing_subentries = getattr(entry, "subentries", {}) or {}
        existing_data = entry.data or {}
        existing_options = entry.options or {}
        cleanup_needed = _entry_needs_cleanup(entry, current_version, target_version)
        target_unique_id = api_key_unique_id(api_key) if api_key is not None else None
        unique_id_changed = (
            target_unique_id is not None
            and getattr(entry, "unique_id", None) != target_unique_id
        )
        if current_version >= target_version and not cleanup_needed:
            if not unique_id_changed:
                return True

        new_data = _clean_parent_data(api_key)
        new_options = _clean_parent_options(entry)

        if not existing_subentries:
            location = _location_from_legacy_entry(entry)
            if location is not None:
                subentry = _make_migrated_subentry(location)
                _add_migrated_subentry(hass, entry, subentry)
                _migrate_entity_registry_for_merged_entry(hass, entry, entry, subentry)
                _migrate_device_registry_for_merged_entry(hass, entry, entry, subentry)

        new_version = max(current_version, target_version)
        if (
            new_data != existing_data
            or new_options != existing_options
            or unique_id_changed
        ):
            updates: dict[str, Any] = {
                "data": new_data,
                "options": new_options,
                "version": new_version,
            }
            if target_unique_id is not None:
                updates["unique_id"] = target_unique_id
            hass.config_entries.async_update_entry(entry, **updates)
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
    if _entry_is_merged(entry):
        _LOGGER.debug(
            "Skipping setup for merged entry %s (merged into %s)",
            entry.entry_id,
            entry.data.get(_CONF_MERGED_INTO_ENTRY_ID),
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
    last_location_error: Exception | None = None
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
            last_location_error = ConfigEntryNotReady("Invalid location configuration")
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
            last_location_error = err
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
            last_location_error = err
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
        ) from last_location_error

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
