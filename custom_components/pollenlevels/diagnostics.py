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
    DEFAULT_FORECAST_DAYS,  # use constant instead of magic number
    MAX_FORECAST_DAYS,
    MIN_FORECAST_DAYS,
)
from .runtime import PollenLevelsRuntimeData
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


def _is_finite_number(value: Any) -> bool:
    """Return whether value is a finite non-boolean number."""
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _normalize_entry_code(key: str, info: dict[str, Any], prefix: str) -> str:
    """Return a deterministic uppercase code from API metadata or the data key."""
    raw_code = info.get("code")
    if isinstance(raw_code, str) and raw_code.strip():
        return raw_code.strip().upper()

    fallback = key
    if fallback.startswith(prefix):
        fallback = fallback[len(prefix) :]
    fallback = fallback.split("_d", 1)[0]
    return fallback.upper()


def _current_day_plant_entries(
    data_map: dict[str, Any],
) -> list[tuple[str, str, str, dict[str, Any]]]:
    """Collect current-day plant entries sorted by normalized plant code."""
    entries: list[tuple[str, str, str, dict[str, Any]]] = []
    for key, info in data_map.items():
        if not isinstance(info, dict) or info.get("source") != "plant":
            continue
        code = _normalize_entry_code(key, info, "plants_")
        name = info.get("displayName") or code
        entries.append((code, str(name), key, info))
    return sorted(entries, key=lambda item: item[0])


def _current_day_type_entries(
    data_map: dict[str, Any],
) -> list[tuple[str, str, str, dict[str, Any]]]:
    """Collect current-day pollen type entries sorted by normalized type code."""
    entries: list[tuple[str, str, str, dict[str, Any]]] = []
    for key, info in data_map.items():
        if key.endswith(("_d1", "_d2")):
            continue
        if not isinstance(info, dict) or info.get("source") != "type":
            continue
        if not _is_finite_number(info.get("value")):
            continue
        code = _normalize_entry_code(key, info, "type_")
        name = info.get("displayName") or code
        entries.append((code, str(name), key, info))
    return sorted(entries, key=lambda item: item[0])


def _top_type_entries(
    data_map: dict[str, Any],
) -> tuple[float | int | None, list[tuple[str, str, str, dict[str, Any]]]]:
    """Return the maximum current-day type value and all entries tied for it."""
    entries = _current_day_type_entries(data_map)
    if not entries:
        return None, []
    top_value = max(info["value"] for _code, _name, _key, info in entries)
    top_entries = [entry for entry in entries if entry[3]["value"] == top_value]
    return top_value, top_entries


def _daily_summary(data_map: dict[str, Any]) -> dict[str, Any]:
    """Return diagnostics mirroring the three daily summary sensor payloads."""
    plant_entries = _current_day_plant_entries(data_map)
    in_season_entries = [
        (code, name)
        for code, name, _key, info in plant_entries
        if info.get("inSeason") is True
    ]
    out_of_season_count = sum(
        1 for _code, _name, _key, info in plant_entries if info.get("inSeason") is False
    )
    unknown_entries = [
        (code, name)
        for code, name, _key, info in plant_entries
        if not isinstance(info.get("inSeason"), bool)
    ]
    in_season_count = len(in_season_entries)
    season_state = (
        in_season_count if in_season_count + out_of_season_count > 0 else None
    )

    top_value, top_entries = _top_type_entries(data_map)
    top_names = [name for _code, name, _key, _info in top_entries]
    first_info = top_entries[0][3] if top_entries else {}

    return {
        "plants_in_season_today": {
            "state": season_state,
            "plant_codes": [code for code, _name in in_season_entries],
            "plant_names": [name for _code, name in in_season_entries],
            "in_season_count": in_season_count,
            "out_of_season_count": out_of_season_count,
            "unknown_season_count": len(unknown_entries),
            "total_plant_count": len(plant_entries),
            "unknown_season_codes": [code for code, _name in unknown_entries],
            "unknown_season_names": [name for _code, name in unknown_entries],
        },
        "overall_pollen_risk_today": {
            "state": top_value,
            "category": first_info.get("category"),
            "description": first_info.get("description"),
            "top_pollen_codes": [code for code, _name, _key, _info in top_entries],
            "top_pollen_names": top_names,
            "top_pollen_categories": [
                info.get("category") for _code, _name, _key, info in top_entries
            ],
            "tie_count": len(top_entries),
        },
        "top_pollen_types_today": {
            "state": ", ".join(top_names) if top_names else None,
            "top_value": top_value,
            "top_pollen_codes": [code for code, _name, _key, _info in top_entries],
            "top_pollen_names": top_names,
            "top_pollen_categories": [
                info.get("category") for _code, _name, _key, info in top_entries
            ],
            "tie_count": len(top_entries),
        },
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry with secrets redacted.

    NOTE: This function must not perform any network I/O.
    """
    runtime = cast(PollenLevelsRuntimeData | None, getattr(entry, "runtime_data", None))
    coordinator = getattr(runtime, "coordinator", None) if runtime else None
    options: dict[str, Any] = dict(entry.options or {})
    data: dict[str, Any] = dict(entry.data or {})

    # Provide an obfuscated (rounded) location for support without exposing precise
    # coordinates. This should not be redacted.
    def _rounded(value: Any) -> float | None:
        try:
            f = float(value)
        except TypeError:
            return None
        except ValueError:
            return None
        except OverflowError:
            return None
        if not math.isfinite(f):
            return None
        return round(f, 1)

    approx_location = {
        "label": "approximate_location (rounded)",
        "latitude_rounded": _rounded(data.get(CONF_LATITUDE)),
        "longitude_rounded": _rounded(data.get(CONF_LONGITUDE)),
    }

    # --- Build a safe params example (no network I/O) ----------------------
    # Use DEFAULT_FORECAST_DAYS from const.py to avoid config drift.
    days_raw = options.get(
        CONF_FORECAST_DAYS,
        data.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS),
    )
    parsed_days = safe_parse_int(days_raw)
    if parsed_days is None:
        # Defensive fallback
        days_effective = DEFAULT_FORECAST_DAYS
    else:
        days_effective = parsed_days

    days_effective = max(MIN_FORECAST_DAYS, min(MAX_FORECAST_DAYS, days_effective))

    params_example: dict[str, Any] = {
        # Explicitly mask the API key example
        "key": redact_api_key(data.get(CONF_API_KEY), data.get(CONF_API_KEY)) or "***",
        # Use rounded coordinates to avoid exposing precise location data.
        "location.latitude": _rounded(data.get(CONF_LATITUDE)),
        "location.longitude": _rounded(data.get(CONF_LONGITUDE)),
        "days": days_effective,
    }
    lang = options.get(CONF_LANGUAGE_CODE, data.get(CONF_LANGUAGE_CODE))
    if lang:
        params_example["languageCode"] = lang

    # --- Coordinator snapshot ------------------------------------------------
    coord_info: dict[str, Any] = {}
    forecast_summary: dict[str, Any] = {}
    daily_summary: dict[str, Any] = {}
    if coordinator is not None:
        # Base coordinator info
        coord_info = {
            "entry_id": getattr(coordinator, "entry_id", None),
            "forecast_days": getattr(coordinator, "forecast_days", None),
            "language": getattr(coordinator, "language", None),
            "create_d1": getattr(coordinator, "create_d1", None),
            "create_d2": getattr(coordinator, "create_d2", None),
            "last_updated": _iso_or_none(getattr(coordinator, "last_updated", None)),
            "data_keys_total": 0,
            "data_keys": [],
        }
        all_keys = list((getattr(coordinator, "data", {}) or {}).keys())
        coord_info["data_keys_total"] = len(all_keys)
        coord_info["data_keys"] = all_keys[:50]

        # ---------- Forecast summaries (TYPES & PLANTS) ----------
        data_map: dict[str, Any] = getattr(coordinator, "data", {}) or {}
        daily_summary = _daily_summary(data_map)

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
                CONF_LANGUAGE_CODE: data.get(CONF_LANGUAGE_CODE),
            },
        },
        "approximate_location": approx_location,
        "coordinator": coord_info,
        "forecast_summary": forecast_summary,
        "daily_summary": daily_summary,
        "request_params_example": params_example,
    }

    # NOTE: Home Assistant's `async_redact_data` is a synchronous callback helper
    # despite its `async_` prefix. Do not `await` it.
    # Redact secrets and return
    return async_redact_data(diag, TO_REDACT)
