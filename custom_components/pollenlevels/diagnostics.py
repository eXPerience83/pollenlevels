"""Diagnostics support for Pollen Levels.

This exposes non-sensitive runtime details useful for support:
- Entry data/options (with API key and location redacted)
- Coordinator snapshot (last_updated, forecast_days, language, flags)
- Forecast summaries for TYPES & PLANTS (attributes-only for plants)
- A sample of the request params with the API key redacted

No network I/O is performed.
"""

from __future__ import annotations

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
    DEFAULT_FORECAST_DAYS,  # use constant instead of magic number
)
from .runtime import PollenLevelsRuntimeData
from .util import redact_api_key

# Redact potentially sensitive values from diagnostics.
# NOTE: Also redact the "location.*" variants used in the request example to avoid
# leaking coordinates in exported diagnostics.
TO_REDACT = {
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    "location.latitude",
    "location.longitude",
}


def _iso_or_none(dt_obj) -> str | None:
    """Return UTC ISO8601 string for datetimes, else None."""
    try:
        return dt_obj.isoformat() if dt_obj is not None else None
    except Exception:
        return None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry with secrets redacted.

    NOTE: This function must not perform any network I/O.
    """
    runtime = cast(PollenLevelsRuntimeData | None, getattr(entry, "runtime_data", None))
    coordinator = getattr(runtime, "coordinator", None)
    options: dict[str, Any] = dict(entry.options or {})
    data: dict[str, Any] = dict(entry.data or {})

    # Provide an obfuscated (rounded) location for support without exposing precise
    # coordinates. This should not be redacted.
    def _rounded(value: Any) -> float | None:
        try:
            return round(float(value), 1)
        except (TypeError, ValueError):
            return None

    approx_location = {
        "label": "approximate_location (rounded)",
        "latitude_rounded": _rounded(data.get(CONF_LATITUDE)),
        "longitude_rounded": _rounded(data.get(CONF_LONGITUDE)),
    }

    # --- Build a safe params example (no network I/O) ----------------------
    # Use DEFAULT_FORECAST_DAYS from const.py to avoid config drift.
    try:
        days_effective = int(
            options.get(
                CONF_FORECAST_DAYS,
                data.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS),
            )
        )
    except Exception:
        # Defensive fallback
        days_effective = DEFAULT_FORECAST_DAYS

    # Clamp days to a sensible minimum (avoid 0 or negative in diagnostics)
    if days_effective < 1:
        days_effective = 1

    params_example: dict[str, Any] = {
        # Explicitly mask the API key example
        "key": redact_api_key(data.get(CONF_API_KEY), data.get(CONF_API_KEY)) or "***",
        "location.latitude": data.get(CONF_LATITUDE),
        "location.longitude": data.get(CONF_LONGITUDE),
        "days": days_effective,
    }
    lang = options.get(CONF_LANGUAGE_CODE, data.get(CONF_LANGUAGE_CODE))
    if lang:
        params_example["languageCode"] = lang

    # --- Coordinator snapshot ------------------------------------------------
    coord_info: dict[str, Any] = {}
    forecast_summary: dict[str, Any] = {}
    if coordinator is not None:
        # Base coordinator info
        coord_info = {
            "entry_id": getattr(coordinator, "entry_id", None),
            "forecast_days": getattr(coordinator, "forecast_days", None),
            "language": getattr(coordinator, "language", None),
            "create_d1": getattr(coordinator, "create_d1", None),
            "create_d2": getattr(coordinator, "create_d2", None),
            "last_updated": _iso_or_none(getattr(coordinator, "last_updated", None)),
            "data_keys": list((getattr(coordinator, "data", {}) or {}).keys()),
        }

        # ---------- Forecast summaries (TYPES & PLANTS) ----------
        data_map: dict[str, Any] = getattr(coordinator, "data", {}) or {}

        # TYPES (main vs per-day)
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
            "days": getattr(coordinator, "forecast_days", None),  # symmetry with plant
            "codes": type_codes,
        }

        # PLANTS (attributes-only)
        plant_items = [
            v
            for v in data_map.values()
            if isinstance(v, dict) and v.get("source") == "plant"
        ]
        plant_codes = sorted([v.get("code") for v in plant_items if v.get("code")])
        plants_with_attr = [v for v in plant_items if "forecast" in v]
        # Readability: include items only when forecast is present and non-empty
        plants_with_nonempty = [v for v in plant_items if v.get("forecast")]
        plants_with_trend = [v for v in plant_items if v.get("trend") is not None]

        forecast_summary["plant"] = {
            # Enabled if at least tomorrow is requested (2+ days)
            "enabled": bool(getattr(coordinator, "forecast_days", 1) >= 2),
            "days": getattr(coordinator, "forecast_days", None),
            "total": len(plant_items),
            "with_attr": len(plants_with_attr),
            "with_nonempty": len(plants_with_nonempty),
            "with_trend": len(plants_with_trend),
            "codes": plant_codes,
        }

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
                CONF_LATITUDE: data.get(CONF_LATITUDE),
                CONF_LONGITUDE: data.get(CONF_LONGITUDE),
                CONF_LANGUAGE_CODE: data.get(CONF_LANGUAGE_CODE),
            },
        },
        "approximate_location": approx_location,
        "coordinator": coord_info,
        "forecast_summary": forecast_summary,
        "request_params_example": params_example,
    }

    # Redact secrets and return
    return async_redact_data(diag, TO_REDACT)
