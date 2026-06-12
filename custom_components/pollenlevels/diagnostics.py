"""Diagnostics support for Pollen Levels.

This exposes non-sensitive runtime details useful for support:
- Entry data/options (with API key and location redacted)
- Coordinator snapshot (last_updated, forecast_days, language)
- Forecast summaries for TYPES & PLANTS (attributes-only for plants)
- Daily summary sensor snapshot derived from coordinator data
- A sample of the request params with the API key redacted

No network I/O is performed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, cast

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    DOMAIN,
    FORECAST_DAYS,
)
from .runtime import PollenLevelsRuntimeData
from .summary import daily_summary as _daily_summary
from .util import (
    active_location_subentry_ids,
    has_legacy_location_data,
    redact_api_key,
    redact_sensitive_values,
)

# Redact potentially sensitive values from diagnostics. Diagnostics intentionally
# expose only 1-decimal approximate coordinates in support examples so issues
# can distinguish unsupported areas from integration/API failures without
# publishing exact location data.
TO_REDACT = {
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
}


def _iso_or_none(dt_obj: Any) -> str | None:
    """Return UTC ISO8601 string for datetimes, else None."""
    try:
        return dt_obj.isoformat() if dt_obj is not None else None
    except Exception:
        return None


def _rounded(value: Any) -> float | None:
    """Return a support-safe 1-decimal coordinate for diagnostics.

    The 1-decimal precision is deliberate: it is enough to tell whether a
    reported issue is tied to an unsupported area versus an API/integration
    failure, while avoiding full-precision location disclosure.
    """
    try:
        f = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, 1)


def _redact_diagnostics_text(
    value: Any,
    api_key: str | None,
    coordinate_pairs: list[tuple[Any, Any]],
) -> str:
    """Redact secrets from user-controlled diagnostics text."""
    redacted = redact_sensitive_values(value, api_key=api_key)
    for lat, lon in coordinate_pairs:
        redacted = redact_sensitive_values(redacted, latitude=lat, longitude=lon)
    return redacted


def _coordinate_pairs_from_location_subentries(
    entry: ConfigEntry,
) -> list[tuple[Any, Any]]:
    """Return stored coordinate pairs from active location subentries."""
    subentries = getattr(entry, "subentries", {}) or {}
    coordinate_pairs: list[tuple[Any, Any]] = []
    for subentry_id in active_location_subentry_ids(entry):
        subentry = subentries.get(subentry_id)
        data = dict(getattr(subentry, "data", {}) or {})
        if CONF_LATITUDE in data or CONF_LONGITUDE in data:
            coordinate_pairs.append((data.get(CONF_LATITUDE), data.get(CONF_LONGITUDE)))
    return coordinate_pairs


def _coordinator_diagnostics(coordinator: Any) -> dict[str, Any]:
    """Return diagnostics for one location coordinator."""
    coord_info = {
        "entry_id": getattr(coordinator, "entry_id", None),
        "subentry_id": getattr(coordinator, "subentry_id", None),
        "legacy_entry_id": getattr(coordinator, "legacy_entry_id", None),
        "entity_identity_id": getattr(coordinator, "entity_identity_id", None),
        "forecast_days": FORECAST_DAYS,
        "language": getattr(coordinator, "language", None),
        "last_updated": _iso_or_none(getattr(coordinator, "last_updated", None)),
        "data_keys_total": 0,
        "data_keys": [],
    }
    data_map: dict[str, Any] = getattr(coordinator, "data", {}) or {}
    all_keys = list(data_map.keys())
    coord_info["data_keys_total"] = len(all_keys)
    coord_info["data_keys"] = all_keys[:50]

    forecast_summary: dict[str, Any] = {}
    daily_summary = _daily_summary(data_map)

    type_main_keys = [
        k
        for k, v in data_map.items()
        if isinstance(v, dict)
        and v.get("source") == "type"
        and not k.endswith(("_d1", "_d2"))
    ]
    type_codes = sorted({k.split("_", 1)[1].upper() for k in type_main_keys})
    forecast_summary["type"] = {
        "total_main": len(type_main_keys),
        "days": FORECAST_DAYS,
        "codes": type_codes,
    }

    plant_items = [
        v
        for v in data_map.values()
        if isinstance(v, dict) and v.get("source") == "plant"
    ]
    plant_codes = sorted([v.get("code") for v in plant_items if v.get("code")])
    plants_with_attr = [v for v in plant_items if "forecast" in v]
    plants_with_nonempty = [v for v in plant_items if v.get("forecast")]
    plants_with_trend = [v for v in plant_items if v.get("trend") is not None]

    forecast_summary["plant"] = {
        "enabled": FORECAST_DAYS >= 2,
        "days": FORECAST_DAYS,
        "total": len(plant_items),
        "with_attr": len(plants_with_attr),
        "with_nonempty": len(plants_with_nonempty),
        "with_trend": len(plants_with_trend),
        "codes": plant_codes,
    }

    return {
        "coordinator": coord_info,
        "forecast_summary": forecast_summary,
        "daily_summary": daily_summary,
    }


def _coordinate_from_coordinator_or_data(
    coordinator: Any, data: dict[str, Any], key: str
) -> Any:
    """Return coordinator coordinate with legacy entry-data fallback."""
    attr = "lat" if key == CONF_LATITUDE else "lon"
    value = getattr(coordinator, attr, None)
    if value is not None:
        return value
    return data.get(key)


def _normalized_subentry_ids(value: Any) -> set[str | None]:
    """Return normalized subentry ids for registry diagnostics."""
    if value is None:
        return {None}
    if isinstance(value, str):
        return {value} if value else {None}
    try:
        ids = {item if isinstance(item, str) and item else None for item in value}
    except TypeError:
        return {None}
    return ids or {None}


def _device_subentry_ids_for_entry(device: Any, entry_id: str) -> set[str | None]:
    """Return device subentry ids for one config entry."""
    for attr in ("config_entries_subentries", "config_entry_subentries"):
        mapping = getattr(device, attr, None)
        if isinstance(mapping, Mapping):
            return _normalized_subentry_ids(mapping.get(entry_id))

    for attr in ("config_subentry_ids", "config_subentries"):
        value = getattr(device, attr, None)
        if value is not None:
            return _normalized_subentry_ids(value)

    direct_subentry_id = getattr(device, "config_subentry_id", None)
    if direct_subentry_id is not None:
        return _normalized_subentry_ids(direct_subentry_id)
    return {None}


def _empty_registry_summary() -> dict[str, Any]:
    """Return an empty registry summary payload."""
    return {
        "entities": {
            "total": 0,
            "without_subentry": 0,
            "by_subentry_id": {},
        },
        "devices": {
            "total": 0,
            "without_subentry": 0,
            "by_subentry_id": {},
            "with_legacy_none_association": 0,
        },
    }


def _registry_summary(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return entity/device registry subentry association counters."""
    summary = _empty_registry_summary()

    try:
        from homeassistant.helpers import entity_registry as er

        entity_registry = er.async_get(hass)
        entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    except (ImportError, RuntimeError, KeyError, AttributeError):
        entities = []

    for entity in entities:
        if getattr(entity, "platform", None) != DOMAIN:
            continue
        summary["entities"]["total"] += 1
        subentry_id = getattr(entity, "config_subentry_id", None)
        if isinstance(subentry_id, str) and subentry_id:
            by_subentry = summary["entities"]["by_subentry_id"]
            by_subentry[subentry_id] = by_subentry.get(subentry_id, 0) + 1
        else:
            summary["entities"]["without_subentry"] += 1

    try:
        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    except (ImportError, RuntimeError, KeyError, AttributeError):
        devices = []

    for device in devices:
        summary["devices"]["total"] += 1
        subentry_ids = _device_subentry_ids_for_entry(device, entry.entry_id)
        if None in subentry_ids:
            summary["devices"]["without_subentry"] += 1
            summary["devices"]["with_legacy_none_association"] += 1
        by_subentry = summary["devices"]["by_subentry_id"]
        for subentry_id in sorted(
            subentry_id for subentry_id in subentry_ids if subentry_id is not None
        ):
            by_subentry[subentry_id] = by_subentry.get(subentry_id, 0) + 1

    return summary


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry with secrets redacted.

    NOTE: This function must not perform any network I/O.
    """
    options: dict[str, Any] = dict(entry.options or {})
    data: dict[str, Any] = dict(entry.data or {})
    runtime = cast(PollenLevelsRuntimeData | None, getattr(entry, "runtime_data", None))
    lang = options.get(CONF_LANGUAGE_CODE, data.get(CONF_LANGUAGE_CODE))
    locations: dict[str, Any] = {}
    stale_location_ids: list[str] = []
    first_location_payload: dict[str, Any] | None = None
    coordinate_pairs: list[tuple[Any, Any]] = []
    api_key = data.get(CONF_API_KEY)
    api_key_text = api_key if isinstance(api_key, str) else None
    if CONF_LATITUDE in data or CONF_LONGITUDE in data:
        coordinate_pairs.append((data.get(CONF_LATITUDE), data.get(CONF_LONGITUDE)))
    coordinate_pairs.extend(_coordinate_pairs_from_location_subentries(entry))
    if runtime is not None:
        active_subentry_ids = active_location_subentry_ids(entry)
        filter_stale_locations = bool(
            active_subentry_ids
        ) or not has_legacy_location_data(entry)
        # Pre-collect all runtime coordinate pairs before redacting any titles.
        # This ensures a user-controlled title for one location can have all
        # configured location coordinates redacted.
        runtime_coords: dict[str, tuple[Any, Any]] = {}
        for subentry_id, location in runtime.locations.items():
            if filter_stale_locations and subentry_id not in active_subentry_ids:
                continue
            coordinator = location.coordinator
            lat = _coordinate_from_coordinator_or_data(coordinator, data, CONF_LATITUDE)
            lon = _coordinate_from_coordinator_or_data(
                coordinator, data, CONF_LONGITUDE
            )
            runtime_coords[subentry_id] = (lat, lon)
            if lat is not None or lon is not None:
                coordinate_pairs.append((lat, lon))

        for subentry_id, location in runtime.locations.items():
            if filter_stale_locations and subentry_id not in active_subentry_ids:
                stale_location_ids.append(subentry_id)
                continue
            coordinator = location.coordinator
            lat, lon = runtime_coords.get(subentry_id, (None, None))
            request_params_example: dict[str, Any] = {
                "key": redact_api_key(api_key, api_key_text) or "***",
                "location.latitude": _rounded(lat),
                "location.longitude": _rounded(lon),
                "days": FORECAST_DAYS,
            }
            if lang:
                request_params_example["languageCode"] = lang
            location_payload = _coordinator_diagnostics(coordinator)
            location_payload["title"] = _redact_diagnostics_text(
                getattr(coordinator, "entry_title", DEFAULT_ENTRY_TITLE),
                api_key_text,
                coordinate_pairs,
            )
            location_payload["approximate_location"] = {
                "label": "approximate_location (rounded)",
                "latitude_rounded": _rounded(lat),
                "longitude_rounded": _rounded(lon),
            }
            location_payload["request_params_example"] = request_params_example
            locations[subentry_id] = location_payload
            if first_location_payload is None:
                first_location_payload = location_payload

    # Final diagnostics payload (with secrets redacted)
    diag: dict[str, Any] = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": _redact_diagnostics_text(
                entry.title,
                api_key_text,
                coordinate_pairs,
            ),
            "options": {
                CONF_UPDATE_INTERVAL: options.get(CONF_UPDATE_INTERVAL),
                CONF_LANGUAGE_CODE: options.get(CONF_LANGUAGE_CODE),
            },
            "data": {
                CONF_LANGUAGE_CODE: data.get(CONF_LANGUAGE_CODE),
            },
        },
        "locations": locations,
        "runtime_summary": {
            "stale_location_count": len(stale_location_ids),
            "stale_location_ids": sorted(stale_location_ids),
        },
        "registry_summary": _registry_summary(hass, entry),
    }
    if first_location_payload is not None:
        diag["approximate_location"] = first_location_payload["approximate_location"]
        diag["coordinator"] = first_location_payload["coordinator"]
        diag["forecast_summary"] = first_location_payload["forecast_summary"]
        diag["daily_summary"] = first_location_payload["daily_summary"]
        diag["request_params_example"] = first_location_payload[
            "request_params_example"
        ]

    # NOTE: Home Assistant's `async_redact_data` is a synchronous callback helper
    # despite its `async_` prefix. Do not `await` it.
    # Redact secrets and return
    return async_redact_data(diag, TO_REDACT)
