"""Diagnostics support for Pollen Levels.

This exposes non-sensitive runtime details useful for support:
- Entry data/options (with API key and location redacted)
- Coordinator snapshot (last_updated, forecast_days, language, flags)
- Forecast summaries for TYPES & PLANTS (attributes-only for plants)
- Daily summary sensor snapshot derived from coordinator data
- A sample of the request params with the API key redacted

No network I/O is performed.
"""

from __future__ import annotations

import math
from typing import Any, cast

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    DEFAULT_FORECAST_DAYS,  # use constant instead of magic number
    MAX_FORECAST_DAYS,
    MIN_FORECAST_DAYS,
)
from .runtime import PollenLevelsRuntimeData
from .summary import daily_summary as _daily_summary
from .util import redact_api_key, safe_parse_int

# Redact potentially sensitive values from diagnostics.
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
    """Return a rounded coordinate for diagnostics."""
    try:
        f = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, 1)


def _effective_days(options: dict[str, Any], data: dict[str, Any]) -> int:
    """Return sanitized forecast days for diagnostics examples."""
    days_raw = options.get(
        CONF_FORECAST_DAYS,
        data.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS),
    )
    parsed_days = safe_parse_int(days_raw)
    days_effective = DEFAULT_FORECAST_DAYS if parsed_days is None else parsed_days
    return max(MIN_FORECAST_DAYS, min(MAX_FORECAST_DAYS, days_effective))


def _coordinator_diagnostics(coordinator: Any) -> dict[str, Any]:
    """Return diagnostics for one location coordinator."""
    coord_info = {
        "entry_id": getattr(coordinator, "entry_id", None),
        "subentry_id": getattr(coordinator, "subentry_id", None),
        "legacy_entry_id": getattr(coordinator, "legacy_entry_id", None),
        "entity_identity_id": getattr(coordinator, "entity_identity_id", None),
        "forecast_days": getattr(coordinator, "forecast_days", None),
        "language": getattr(coordinator, "language", None),
        "create_d1": getattr(coordinator, "create_d1", None),
        "create_d2": getattr(coordinator, "create_d2", None),
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
    type_perday_keys = [
        k
        for k, v in data_map.items()
        if isinstance(v, dict)
        and v.get("source") == "type"
        and k.endswith(("_d1", "_d2"))
    ]
    type_codes = sorted(
        {k.split("_", 1)[1].split("_d", 1)[0].upper() for k in type_main_keys}
    )
    forecast_summary["type"] = {
        "total_main": len(type_main_keys),
        "total_per_day": len(type_perday_keys),
        "create_d1": getattr(coordinator, "create_d1", None),
        "create_d2": getattr(coordinator, "create_d2", None),
        "days": getattr(coordinator, "forecast_days", None),
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
        "enabled": bool(getattr(coordinator, "forecast_days", 1) >= 2),
        "days": getattr(coordinator, "forecast_days", None),
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


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry with secrets redacted.

    NOTE: This function must not perform any network I/O.
    """
    options: dict[str, Any] = dict(entry.options or {})
    data: dict[str, Any] = dict(entry.data or {})
    runtime = cast(PollenLevelsRuntimeData | None, getattr(entry, "runtime_data", None))
    days_effective = _effective_days(options, data)
    lang = options.get(CONF_LANGUAGE_CODE, data.get(CONF_LANGUAGE_CODE))
    locations: dict[str, Any] = {}
    first_location_payload: dict[str, Any] | None = None
    if runtime is not None:
        for subentry_id, location in runtime.locations.items():
            coordinator = location.coordinator
            lat = _coordinate_from_coordinator_or_data(coordinator, data, CONF_LATITUDE)
            lon = _coordinate_from_coordinator_or_data(
                coordinator, data, CONF_LONGITUDE
            )
            request_params_example: dict[str, Any] = {
                "key": redact_api_key(data.get(CONF_API_KEY), data.get(CONF_API_KEY))
                or "***",
                "location.latitude": _rounded(lat),
                "location.longitude": _rounded(lon),
                "days": days_effective,
            }
            if lang:
                request_params_example["languageCode"] = lang
            location_payload = _coordinator_diagnostics(coordinator)
            location_payload["title"] = getattr(
                coordinator, "entry_title", DEFAULT_ENTRY_TITLE
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
            "title": entry.title,
            "options": {
                CONF_UPDATE_INTERVAL: options.get(CONF_UPDATE_INTERVAL),
                CONF_LANGUAGE_CODE: options.get(CONF_LANGUAGE_CODE),
                CONF_FORECAST_DAYS: options.get(CONF_FORECAST_DAYS),
                CONF_CREATE_FORECAST_SENSORS: options.get(CONF_CREATE_FORECAST_SENSORS),
            },
            "data": {
                CONF_LANGUAGE_CODE: data.get(CONF_LANGUAGE_CODE),
            },
        },
        "locations": locations,
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
