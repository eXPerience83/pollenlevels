"""Migration helpers for the Pollen Levels integration."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant

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
    DOMAIN,
    SUBENTRY_TYPE_LOCATION,
)
from .util import api_key_unique_id, normalize_sensor_mode, validate_location_pair

_LOGGER = logging.getLogger(__name__)
LEGACY_HTTP_REFERER_KEY = "http_referer"
CONF_MERGED_INTO_ENTRY_ID = "merged_into_entry_id"


@dataclass(frozen=True, slots=True)
class _MigrationLocation:
    """Location payload collected from a legacy config entry."""

    source_entry: ConfigEntry
    title: str
    data: dict[str, Any]
    legacy_entry_id: str | None
    unique_id: str | None
    source_subentry_id: str | None = None


@dataclass(slots=True)
class _RegistryMigrationStats:
    """Registry migration counters for migration logs."""

    entities_moved: int = 0
    devices_moved: int = 0
    legacy_device_associations_removed: int = 0


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


def _has_invalid_legacy_coordinates(entry: ConfigEntry) -> bool:
    """Return whether legacy entry data contains unusable stored coordinates."""
    data = entry.data or {}
    if not _has_any_legacy_coordinate_key(entry):
        return False
    if not _has_legacy_coordinate_pair(entry):
        return True

    return (
        validate_location_pair(data.get(CONF_LATITUDE), data.get(CONF_LONGITUDE))
        is None
    )


def _has_any_legacy_coordinate_key(entry: ConfigEntry) -> bool:
    """Return whether legacy entry data contains any stored coordinate key."""
    data = entry.data or {}
    return CONF_LATITUDE in data or CONF_LONGITUDE in data


def _has_legacy_coordinate_pair(entry: ConfigEntry) -> bool:
    """Return whether legacy entry data contains a stored coordinate pair."""
    data = entry.data or {}
    return CONF_LATITUDE in data and CONF_LONGITUDE in data


def _log_invalid_legacy_coordinates(entry: ConfigEntry) -> None:
    """Log an actionable migration failure for corrupt legacy coordinates."""
    _LOGGER.error(
        "Cannot migrate Pollen Levels entry %s because it contains invalid stored "
        "coordinates. The entry was left unchanged. Remove and recreate this "
        "location or fix the configuration before retrying the migration.",
        entry.entry_id,
    )


def _log_unmigratable_location_subentries(entry: ConfigEntry) -> None:
    """Log an actionable migration failure for corrupt location subentries."""
    _LOGGER.error(
        "Cannot migrate Pollen Levels entry %s because it has location subentries "
        "with invalid stored migration data. The entry was left unchanged. Remove "
        "and recreate the affected location or fix the configuration before "
        "retrying the migration.",
        entry.entry_id,
    )


def _invalid_legacy_coordinate_entry(
    entries: list[ConfigEntry],
) -> ConfigEntry | None:
    """Return the first entry with corrupt legacy coordinates, if any."""
    return next(
        (
            candidate
            for candidate in entries
            if _has_invalid_legacy_coordinates(candidate)
        ),
        None,
    )


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


def is_entry_merged(entry: ConfigEntry) -> bool:
    """Return whether a legacy entry has already been merged into another one."""
    merged_into = (entry.data or {}).get(CONF_MERGED_INTO_ENTRY_ID)
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

    new_options.pop(LEGACY_HTTP_REFERER_KEY, None)
    return new_options


def _location_from_legacy_entry(entry: ConfigEntry) -> _MigrationLocation | None:
    """Return the location stored directly on a legacy config entry."""
    data = dict(entry.data or {})
    if CONF_LATITUDE not in data or CONF_LONGITUDE not in data:
        return None
    if (
        validate_location_pair(data.get(CONF_LATITUDE), data.get(CONF_LONGITUDE))
        is None
    ):
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
    if (
        validate_location_pair(data.get(CONF_LATITUDE), data.get(CONF_LONGITUDE))
        is None
    ):
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
        source_subentry_id=subentry.subentry_id,
    )


def _migration_locations(entry: ConfigEntry) -> list[_MigrationLocation]:
    """Return legacy locations to materialize as subentries."""
    locations: list[_MigrationLocation] = []
    for subentry in (getattr(entry, "subentries", {}) or {}).values():
        location = _location_from_subentry(entry, subentry)
        if location is not None:
            locations.append(location)

    location = _location_from_legacy_entry(entry)
    if location is not None:
        # Keep direct legacy data as a migration source while entry.data still
        # contains coordinates. This lets retries finish registry migration
        # after a previous attempt already created the location subentry.
        locations.append(location)
    return locations


def _has_migration_locations(entry: ConfigEntry) -> bool:
    """Return whether this entry has legacy location data."""
    return bool(_migration_locations(entry))


def _has_location_subentries(entry: ConfigEntry) -> bool:
    """Return whether this entry already stores v3 location subentries."""
    return any(
        getattr(subentry, "subentry_type", None) == SUBENTRY_TYPE_LOCATION
        for subentry in (getattr(entry, "subentries", {}) or {}).values()
    )


def _has_invalid_legacy_location_subentry(entry: ConfigEntry) -> bool:
    """Return whether a legacy location subentry has unusable coordinates."""
    for subentry in (getattr(entry, "subentries", {}) or {}).values():
        if getattr(subentry, "subentry_type", None) != SUBENTRY_TYPE_LOCATION:
            continue
        data = dict(getattr(subentry, "data", {}) or {})
        legacy_entry_id = data.get(CONF_LEGACY_ENTRY_ID)
        if not isinstance(legacy_entry_id, str) or not legacy_entry_id:
            continue
        if CONF_LATITUDE not in data or CONF_LONGITUDE not in data:
            return True
        if (
            validate_location_pair(data.get(CONF_LATITUDE), data.get(CONF_LONGITUDE))
            is None
        ):
            return True
    return False


def _has_unmigratable_location_subentries(entry: ConfigEntry) -> bool:
    """Return whether location subentries cannot be safely auto-merged."""
    for subentry in (getattr(entry, "subentries", {}) or {}).values():
        data = dict(getattr(subentry, "data", {}) or {})
        subentry_type = getattr(subentry, "subentry_type", None)
        looks_like_location = subentry_type == SUBENTRY_TYPE_LOCATION or (
            subentry_type is None
            and (
                CONF_LATITUDE in data
                or CONF_LONGITUDE in data
                or CONF_LEGACY_ENTRY_ID in data
            )
        )
        if not looks_like_location:
            continue
        if CONF_LATITUDE not in data or CONF_LONGITUDE not in data:
            return True
        if (
            validate_location_pair(data.get(CONF_LATITUDE), data.get(CONF_LONGITUDE))
            is None
        ):
            return True
        legacy_entry_id = data.get(CONF_LEGACY_ENTRY_ID)
        if not isinstance(legacy_entry_id, str) or not legacy_entry_id:
            return True
    return False


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
    target_unique_id = api_key_unique_id(api_key)
    for candidate in entries:
        if is_entry_merged(candidate):
            continue
        if _entry_api_key(candidate) != api_key:
            continue
        if (
            candidate is entry
            or _has_any_legacy_coordinate_key(candidate)
            or _has_migration_locations(candidate)
            or _has_location_subentries(candidate)
            or getattr(candidate, "unique_id", None) == target_unique_id
        ):
            group.append(candidate)

    if entry not in group and not is_entry_merged(entry):
        group.append(entry)
    return group


def _select_migration_parent(
    group: list[ConfigEntry], current: ConfigEntry, api_key: str
) -> ConfigEntry:
    """Return the parent entry that will own the shared API-key locations."""
    for candidate in group:
        if getattr(candidate, "subentries", None):
            return candidate
    target_unique_id = api_key_unique_id(api_key)
    for candidate in group:
        if getattr(candidate, "unique_id", None) == target_unique_id:
            return candidate
    return group[0] if group else current


def _merged_entry_data(api_key: str, parent: ConfigEntry) -> dict[str, Any]:
    """Return temporary data for entries merged into another parent."""
    return {
        CONF_API_KEY: api_key,
        CONF_MERGED_INTO_ENTRY_ID: parent.entry_id,
    }


def _entry_needs_cleanup(
    entry: ConfigEntry, current_version: int, target_version: int
) -> bool:
    """Return whether the entry still needs v3/v5 storage cleanup."""
    existing_data = entry.data or {}
    existing_options = entry.options or {}
    existing_subentries = getattr(entry, "subentries", {}) or {}
    cleanup_needed = (
        LEGACY_HTTP_REFERER_KEY in existing_data
        or LEGACY_HTTP_REFERER_KEY in existing_options
        or CONF_CREATE_FORECAST_SENSORS in existing_data
        or CONF_LATITUDE in existing_data
        or CONF_LONGITUDE in existing_data
        or CONF_UPDATE_INTERVAL in existing_data
        or CONF_LANGUAGE_CODE in existing_data
        or CONF_FORECAST_DAYS in existing_data
        or (
            not existing_subentries
            and not is_entry_merged(entry)
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


def _target_subentries_by_source_subentry(
    location_targets: list[tuple[_MigrationLocation, ConfigSubentry]],
) -> dict[str | None, ConfigSubentry]:
    """Return target subentries keyed by their source subentry identity."""
    return {
        location.source_subentry_id: subentry for location, subentry in location_targets
    }


def _parent_legacy_location_target(
    source: ConfigEntry, location: _MigrationLocation, subentry: ConfigSubentry
) -> tuple[_MigrationLocation, ConfigSubentry] | None:
    """Return a registry target for the parent's legacy main-entry association."""
    if location.legacy_entry_id != source.entry_id:
        return None
    return (
        _MigrationLocation(
            source_entry=location.source_entry,
            title=location.title,
            data=location.data,
            legacy_entry_id=location.legacy_entry_id,
            unique_id=location.unique_id,
            source_subentry_id=None,
        ),
        subentry,
    )


def _normalize_subentry_ids(value: Any) -> set[str | None]:
    """Return a normalized subentry-id set while preserving legacy None links."""
    if value is None:
        return {None}
    if isinstance(value, str):
        return {value} if value else {None}
    try:
        ids: set[str | None] = set()
        for item in value:
            if item is None:
                ids.add(None)
            elif isinstance(item, str) and item:
                ids.add(item)
        return ids or {None}
    except TypeError:
        return {None}


def _device_source_subentry_ids(
    device: Any, source_entry_id: str
) -> set[str | None] | None:
    """Return known source subentry IDs for a device, or None if unavailable."""
    for attr in ("config_entries_subentries", "config_entry_subentries"):
        mapping = getattr(device, attr, None)
        if isinstance(mapping, Mapping):
            return _normalize_subentry_ids(mapping.get(source_entry_id))

    for attr in ("config_subentry_ids", "config_subentries"):
        value = getattr(device, attr, None)
        if value is not None:
            return _normalize_subentry_ids(value)

    direct_subentry_id = getattr(device, "config_subentry_id", None)
    if direct_subentry_id is not None:
        return _normalize_subentry_ids(direct_subentry_id)
    return None


def _migrate_entity_registry_for_merged_entry(
    hass: HomeAssistant,
    source: ConfigEntry,
    parent: ConfigEntry,
    location_targets: list[tuple[_MigrationLocation, ConfigSubentry]],
) -> tuple[bool, int]:
    """Attach entity-registry links and report whether every move succeeded."""
    try:
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
    except ImportError, RuntimeError, KeyError, AttributeError:
        return True, 0

    migrated = True
    moved = 0
    targets_by_source_subentry = _target_subentries_by_source_subentry(location_targets)
    for entity in er.async_entries_for_config_entry(registry, source.entry_id):
        if getattr(entity, "platform", None) != DOMAIN:
            continue

        source_subentry_id = getattr(entity, "config_subentry_id", None)
        if not isinstance(source_subentry_id, str) or not source_subentry_id:
            source_subentry_id = None
        if source_subentry_id not in targets_by_source_subentry:
            if source is parent:
                continue
            _LOGGER.error(
                "Cannot move entity %s from entry %s to parent %s: no target "
                "subentry for source subentry %s",
                getattr(entity, "entity_id", "unknown"),
                source.entry_id,
                parent.entry_id,
                source_subentry_id or "legacy-entry",
            )
            migrated = False
            continue

        subentry = targets_by_source_subentry[source_subentry_id]
        if getattr(entity, "config_subentry_id", None) == subentry.subentry_id:
            continue
        try:
            registry.async_update_entity(
                entity.entity_id,
                config_entry_id=parent.entry_id,
                config_subentry_id=subentry.subentry_id,
            )
            moved += 1
        except Exception:  # noqa: BLE001
            migrated = False
            _LOGGER.exception(
                "Failed to move entity %s from entry %s to parent %s",
                getattr(entity, "entity_id", "unknown"),
                source.entry_id,
                parent.entry_id,
            )
    return migrated, moved


def _migrate_device_registry_for_merged_entry(
    hass: HomeAssistant,
    source: ConfigEntry,
    parent: ConfigEntry,
    location_targets: list[tuple[_MigrationLocation, ConfigSubentry]],
) -> tuple[bool, int, int]:
    """Attach device-registry links and report whether every move succeeded."""
    try:
        from homeassistant.helpers import device_registry as dr

        registry = dr.async_get(hass)
    except ImportError, RuntimeError, KeyError, AttributeError:
        return True, 0, 0

    migrated = True
    moved = 0
    legacy_associations_removed = 0
    targets_by_source_subentry = _target_subentries_by_source_subentry(location_targets)
    has_source_subentry_targets = any(
        source_subentry_id is not None
        for source_subentry_id in targets_by_source_subentry
    )
    for device in dr.async_entries_for_config_entry(registry, source.entry_id):
        source_subentry_ids = _device_source_subentry_ids(device, source.entry_id)
        if source_subentry_ids is None:
            if has_source_subentry_targets:
                _LOGGER.error(
                    "Cannot move device %s from entry %s to parent %s: source "
                    "subentry association is unavailable",
                    getattr(device, "id", "unknown"),
                    source.entry_id,
                    parent.entry_id,
                )
                migrated = False
                continue
            source_subentry_ids = {None}
        elif not source_subentry_ids:
            source_subentry_ids = {None}

        valid_source_subentry_ids = {
            subentry_id
            for subentry_id in source_subentry_ids
            if subentry_id in targets_by_source_subentry
        }
        target_subentries: list[ConfigSubentry] = []
        for source_subentry_id in sorted(
            source_subentry_ids, key=lambda item: item or ""
        ):
            if source_subentry_id not in targets_by_source_subentry:
                if source is parent:
                    continue
                if source_subentry_id is None and valid_source_subentry_ids:
                    continue
                _LOGGER.error(
                    "Cannot move device %s from entry %s to parent %s: no target "
                    "subentry for source subentry %s",
                    getattr(device, "id", "unknown"),
                    source.entry_id,
                    parent.entry_id,
                    source_subentry_id or "legacy-entry",
                )
                migrated = False
                continue
            target_subentries.append(targets_by_source_subentry[source_subentry_id])

        if not target_subentries:
            continue

        try:
            for subentry in target_subentries:
                registry.async_update_device(
                    device.id,
                    add_config_entry_id=parent.entry_id,
                    add_config_subentry_id=subentry.subentry_id,
                )
                moved += 1
            if source is not parent:
                registry.async_update_device(
                    device.id,
                    remove_config_entry_id=source.entry_id,
                )
            elif None in source_subentry_ids:
                registry.async_update_device(
                    device.id,
                    remove_config_entry_id=source.entry_id,
                    remove_config_subentry_id=None,
                )
                legacy_associations_removed += 1
        except Exception:  # noqa: BLE001
            migrated = False
            _LOGGER.exception(
                "Failed to move device %s from entry %s to parent %s",
                getattr(device, "id", "unknown"),
                source.entry_id,
                parent.entry_id,
            )
    return migrated, moved, legacy_associations_removed


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
    if (invalid_entry := _invalid_legacy_coordinate_entry(group)) is not None:
        _log_invalid_legacy_coordinates(invalid_entry)
        _LOGGER.error(
            "Aborted Pollen Levels API-key migration group because entry %s "
            "contains invalid stored coordinates. The group was left unchanged.",
            invalid_entry.entry_id,
        )
        return False

    parent = _select_migration_parent(group, entry, api_key)
    _LOGGER.info(
        "Selected parent entry %s for API-key migration group with %d entries",
        parent.entry_id,
        len(group),
    )
    for source in group:
        if source is parent:
            if _has_invalid_legacy_location_subentry(source):
                _log_unmigratable_location_subentries(source)
                return False
            continue
        if _has_unmigratable_location_subentries(source):
            _log_unmigratable_location_subentries(source)
            return False

    parent_options = _clean_parent_options(parent)
    for candidate in group:
        if candidate is parent:
            continue
        for key, value in _clean_parent_options(candidate).items():
            parent_options.setdefault(key, value)

    used_unique_ids, legacy_subentries = _existing_location_indexes(parent)
    registry_targets: dict[
        ConfigEntry, list[tuple[_MigrationLocation, ConfigSubentry]]
    ] = {}

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
                _LOGGER.info(
                    "Created location subentry %s for legacy entry %s",
                    subentry.subentry_id,
                    location.legacy_entry_id or source.entry_id,
                )
            else:
                _LOGGER.info(
                    "Reused location subentry %s for legacy entry %s",
                    subentry.subentry_id,
                    location.legacy_entry_id or source.entry_id,
                )

            if source is not parent or location.source_subentry_id is None:
                registry_targets.setdefault(source, []).append((location, subentry))
            elif (
                parent_target := _parent_legacy_location_target(
                    source, location, subentry
                )
            ) is not None:
                registry_targets.setdefault(source, []).append(parent_target)

    stats = _RegistryMigrationStats()
    for source, location_targets in registry_targets.items():
        entity_registry_migrated, moved_entities = (
            _migrate_entity_registry_for_merged_entry(
                hass, source, parent, location_targets
            )
        )
        device_registry_migrated, moved_devices, removed_legacy_associations = (
            _migrate_device_registry_for_merged_entry(
                hass, source, parent, location_targets
            )
        )
        stats.entities_moved += moved_entities
        stats.devices_moved += moved_devices
        stats.legacy_device_associations_removed += removed_legacy_associations
        _LOGGER.info(
            "Moved %d entity registry entries from entry %s to parent %s",
            moved_entities,
            source.entry_id,
            parent.entry_id,
        )
        _LOGGER.info(
            "Moved %d device registry entries from entry %s to parent %s",
            moved_devices,
            source.entry_id,
            parent.entry_id,
        )
        if removed_legacy_associations:
            _LOGGER.info(
                "Removed %d legacy non-subentry device associations from entry %s",
                removed_legacy_associations,
                source.entry_id,
            )
        if not entity_registry_migrated or not device_registry_migrated:
            _LOGGER.warning(
                "Registry migration incomplete; migration state will be reused on retry"
            )
            return False

    _update_parent_entry(hass, parent, api_key, parent_options, target_version)

    for source in group:
        if source is parent:
            continue
        _mark_entry_merged(hass, source, parent, api_key, target_version)
        await _remove_or_schedule_merged_entry(hass, source, entry)

    _LOGGER.info(
        "Completed Pollen Levels v3 migration for parent %s "
        "(entities=%d devices=%d legacy_device_associations_removed=%d)",
        parent.entry_id,
        stats.entities_moved,
        stats.devices_moved,
        stats.legacy_device_associations_removed,
    )
    return True


def _existing_parent_legacy_registry_targets(
    entry: ConfigEntry,
) -> list[tuple[_MigrationLocation, ConfigSubentry]]:
    """Return repair targets for legacy parent registry entries without subentry."""
    targets: list[tuple[_MigrationLocation, ConfigSubentry]] = []
    for subentry in (getattr(entry, "subentries", {}) or {}).values():
        location = _location_from_subentry(entry, subentry)
        if location is None:
            continue
        target = _parent_legacy_location_target(entry, location, subentry)
        if target is not None:
            targets.append(target)
    return targets


def _repair_existing_parent_registry_links(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Repair parent registry links left without subentry by older alpha builds."""
    registry_targets = _existing_parent_legacy_registry_targets(entry)
    if not registry_targets:
        return True

    entity_registry_migrated, moved_entities = (
        _migrate_entity_registry_for_merged_entry(hass, entry, entry, registry_targets)
    )
    device_registry_migrated, moved_devices, removed_legacy_associations = (
        _migrate_device_registry_for_merged_entry(hass, entry, entry, registry_targets)
    )
    _LOGGER.info(
        "Moved %d entity registry entries from entry %s to parent %s",
        moved_entities,
        entry.entry_id,
        entry.entry_id,
    )
    _LOGGER.info(
        "Moved %d device registry entries from entry %s to parent %s",
        moved_devices,
        entry.entry_id,
        entry.entry_id,
    )
    if removed_legacy_associations:
        _LOGGER.info(
            "Removed %d legacy non-subentry device associations from entry %s",
            removed_legacy_associations,
            entry.entry_id,
        )
    if not entity_registry_migrated or not device_registry_migrated:
        _LOGGER.warning(
            "Registry migration incomplete; migration state will be reused on retry"
        )
        return False
    return True


async def async_handle_entry_migration(
    hass: HomeAssistant, entry: ConfigEntry, target_version: int
) -> bool:
    """Migrate legacy entries to the v3 parent/subentry storage model."""
    try:
        _LOGGER.info("Starting Pollen Levels v3 migration for entry %s", entry.entry_id)
        current_version = _entry_version(entry)
        if is_entry_merged(entry):
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

        if _has_invalid_legacy_coordinates(entry):
            _log_invalid_legacy_coordinates(entry)
            return False
        if _has_invalid_legacy_location_subentry(entry):
            _log_unmigratable_location_subentries(entry)
            return False

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
                return _repair_existing_parent_registry_links(hass, entry)

        new_data = _clean_parent_data(api_key)
        new_options = _clean_parent_options(entry)

        used_unique_ids, legacy_subentries = _existing_location_indexes(entry)
        registry_targets: list[tuple[_MigrationLocation, ConfigSubentry]] = []
        for location in _migration_locations(entry):
            subentry = None
            if location.legacy_entry_id is not None:
                subentry = legacy_subentries.get(location.legacy_entry_id)
            if subentry is None:
                subentry = _make_migrated_subentry(location, used_unique_ids)
                _add_migrated_subentry(hass, entry, subentry)
                if location.legacy_entry_id is not None:
                    legacy_subentries[location.legacy_entry_id] = subentry
                _LOGGER.info(
                    "Created location subentry %s for legacy entry %s",
                    subentry.subentry_id,
                    location.legacy_entry_id or entry.entry_id,
                )
            else:
                _LOGGER.info(
                    "Reused location subentry %s for legacy entry %s",
                    subentry.subentry_id,
                    location.legacy_entry_id or entry.entry_id,
                )

            if location.source_subentry_id is None:
                registry_targets.append((location, subentry))
            elif (
                parent_target := _parent_legacy_location_target(
                    entry, location, subentry
                )
            ) is not None:
                registry_targets.append(parent_target)

        stats = _RegistryMigrationStats()
        if registry_targets:
            entity_registry_migrated, moved_entities = (
                _migrate_entity_registry_for_merged_entry(
                    hass, entry, entry, registry_targets
                )
            )
            device_registry_migrated, moved_devices, removed_legacy_associations = (
                _migrate_device_registry_for_merged_entry(
                    hass, entry, entry, registry_targets
                )
            )
            stats.entities_moved += moved_entities
            stats.devices_moved += moved_devices
            stats.legacy_device_associations_removed += removed_legacy_associations
            _LOGGER.info(
                "Moved %d entity registry entries from entry %s to parent %s",
                moved_entities,
                entry.entry_id,
                entry.entry_id,
            )
            _LOGGER.info(
                "Moved %d device registry entries from entry %s to parent %s",
                moved_devices,
                entry.entry_id,
                entry.entry_id,
            )
            if removed_legacy_associations:
                _LOGGER.info(
                    "Removed %d legacy non-subentry device associations from entry %s",
                    removed_legacy_associations,
                    entry.entry_id,
                )
            if not entity_registry_migrated or not device_registry_migrated:
                _LOGGER.warning(
                    "Registry migration incomplete; migration state will be reused on retry"
                )
                return False

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
        _LOGGER.info(
            "Completed Pollen Levels v3 migration for parent %s "
            "(entities=%d devices=%d legacy_device_associations_removed=%d)",
            entry.entry_id,
            stats.entities_moved,
            stats.devices_moved,
            stats.legacy_device_associations_removed,
        )
        return True
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        _LOGGER.exception(
            "Failed to migrate Pollen Levels config entry storage for entry %s "
            "(version=%s)",
            entry.entry_id,
            getattr(entry, "version", None),
        )
        return False
