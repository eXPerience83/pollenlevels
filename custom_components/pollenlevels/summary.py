"""Pure helpers for daily pollen summary extraction."""

from __future__ import annotations

import math
from typing import Any, NamedTuple

from .forecast import attach_forecast_attributes


class SummaryEntry(NamedTuple):
    """Represent a normalized daily summary entry."""

    code: str
    name: str
    key: str
    info: dict[str, Any]


def is_finite_number(value: Any) -> bool:
    """Return whether value is a finite non-boolean number."""
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def normalize_entry_code(key: str, info: dict[str, Any], prefix: str) -> str:
    """Return a deterministic uppercase code from API metadata or the data key."""
    raw_code = info.get("code")
    if isinstance(raw_code, str) and raw_code.strip():
        return raw_code.strip().upper()

    fallback = key
    if fallback.startswith(prefix):
        fallback = fallback[len(prefix) :]
    fallback = fallback.split("_d", 1)[0]
    return fallback.upper()


def current_day_plant_entries(data_map: dict[str, Any]) -> list[SummaryEntry]:
    """Collect current-day plant entries sorted by normalized plant code."""
    entries: list[SummaryEntry] = []
    for key, info in data_map.items():
        if not isinstance(info, dict) or info.get("source") != "plant":
            continue
        code = normalize_entry_code(key, info, "plants_")
        name = info.get("displayName") or code
        entries.append(SummaryEntry(code, str(name), key, info))
    return sorted(entries, key=lambda entry: entry.code)


def current_day_type_entries(data_map: dict[str, Any]) -> list[SummaryEntry]:
    """Collect current-day pollen type entries sorted by normalized type code."""
    entries: list[SummaryEntry] = []
    for key, info in data_map.items():
        if key.endswith(("_d1", "_d2")):
            continue
        if not isinstance(info, dict) or info.get("source") != "type":
            continue
        if not is_finite_number(info.get("value")):
            continue
        code = normalize_entry_code(key, info, "type_")
        name = info.get("displayName") or code
        entries.append(SummaryEntry(code, str(name), key, info))
    return sorted(entries, key=lambda entry: entry.code)


def forecast_type_entries(data_map: dict[str, Any]) -> list[SummaryEntry]:
    """Collect all base type entries for forecast aggregation.

    Unlike current_day_type_entries, this does not require a finite
    current-day value so future-only types are included.
    """
    entries: list[SummaryEntry] = []
    for key, info in data_map.items():
        if key.endswith(("_d1", "_d2")):
            continue
        if not isinstance(info, dict) or info.get("source") != "type":
            continue
        code = normalize_entry_code(key, info, "type_")
        name = info.get("displayName") or code
        entries.append(SummaryEntry(code, str(name), key, info))
    return sorted(entries, key=lambda entry: entry.code)


def top_type_entries(
    data_map: dict[str, Any],
) -> tuple[float | int | None, list[SummaryEntry]]:
    """Return the maximum current-day type value and all entries tied for it."""
    entries = current_day_type_entries(data_map)
    if not entries:
        return None, []
    top_value = max(entry.info["value"] for entry in entries)
    top_entries = [entry for entry in entries if entry.info["value"] == top_value]
    return top_value, top_entries


def _overall_forecast_from_type_forecasts(
    type_entries: list[SummaryEntry],
) -> list[dict[str, Any]]:
    """Build aggregated forecast list from current-day type forecast attributes.

    Returns an empty list when there are no future offsets (forecast_days=1).

    For each future offset, the highest indexed value across all types is used.
    Ties are preserved with deterministic ordering by normalised type code.
    """
    offsets: dict[int, list[tuple[SummaryEntry, dict[str, Any]]]] = {}
    for entry in type_entries:
        forecast = entry.info.get("forecast")
        if not isinstance(forecast, list) or not forecast:
            continue
        for f_item in forecast:
            if not isinstance(f_item, dict):
                continue
            offset = f_item.get("offset")
            if (
                not (isinstance(offset, int) and not isinstance(offset, bool))
                or offset < 1
            ):
                continue
            offsets.setdefault(offset, []).append((entry, f_item))

    if not offsets:
        return []

    result: list[dict[str, Any]] = []
    for offset in sorted(offsets):
        pairs = offsets[offset]
        pairs.sort(key=lambda pair: pair[0].code)

        valid = [
            (entry, f)
            for entry, f in pairs
            if f.get("has_index") is True and is_finite_number(f.get("value"))
        ]

        if not valid:
            _, first_f = pairs[0]
            result.append(
                {
                    "offset": offset,
                    "date": first_f.get("date"),
                    "has_index": False,
                    "value": None,
                    "category": None,
                    "description": None,
                    "color_hex": None,
                    "color_rgb": None,
                    "top_pollen_codes": [],
                    "top_pollen_names": [],
                    "top_pollen_categories": [],
                    "tie_count": 0,
                }
            )
        else:
            max_val = max(f["value"] for _, f in valid)
            tied = [(entry, f) for entry, f in valid if f["value"] == max_val]
            tied.sort(key=lambda pair: pair[0].code)
            _, first_f = tied[0]
            result.append(
                {
                    "offset": offset,
                    "date": first_f.get("date"),
                    "has_index": True,
                    "value": max_val,
                    "category": first_f.get("category"),
                    "description": first_f.get("description"),
                    "color_hex": first_f.get("color_hex"),
                    "color_rgb": first_f.get("color_rgb"),
                    "top_pollen_codes": [entry.code for entry, _ in tied],
                    "top_pollen_names": [entry.name for entry, _ in tied],
                    "top_pollen_categories": [f.get("category") for _, f in tied],
                    "tie_count": len(tied),
                }
            )

    return result


def daily_summary(data_map: dict[str, Any]) -> dict[str, Any]:
    """Return payloads for the daily summary sensors."""
    plant_entries = current_day_plant_entries(data_map)
    in_season_entries = [
        entry for entry in plant_entries if entry.info.get("inSeason") is True
    ]
    out_of_season_count = sum(
        1 for entry in plant_entries if entry.info.get("inSeason") is False
    )
    unknown_entries = [
        entry
        for entry in plant_entries
        if not isinstance(entry.info.get("inSeason"), bool)
    ]
    in_season_count = len(in_season_entries)
    season_state = (
        in_season_count if in_season_count + out_of_season_count > 0 else None
    )

    top_value, top_entries = top_type_entries(data_map)
    top_names = [entry.name for entry in top_entries]
    first_info = top_entries[0].info if top_entries else {}

    overall: dict[str, Any] = {
        "state": top_value,
        "category": first_info.get("category"),
        "description": first_info.get("description"),
        "top_pollen_codes": [entry.code for entry in top_entries],
        "top_pollen_names": top_names,
        "top_pollen_categories": [entry.info.get("category") for entry in top_entries],
        "tie_count": len(top_entries),
    }

    # Build aggregated forecast from all type entries (including future-only).
    type_entries = forecast_type_entries(data_map)
    forecast_list = _overall_forecast_from_type_forecasts(type_entries)
    if forecast_list:
        overall = attach_forecast_attributes(
            overall, forecast_list, current_value=top_value
        )

    return {
        "plants_in_season_today": {
            "state": season_state,
            "plant_codes": [entry.code for entry in in_season_entries],
            "plant_names": [entry.name for entry in in_season_entries],
            "in_season_count": in_season_count,
            "out_of_season_count": out_of_season_count,
            "unknown_season_count": len(unknown_entries),
            "total_plant_count": len(plant_entries),
            "unknown_season_codes": [entry.code for entry in unknown_entries],
            "unknown_season_names": [entry.name for entry in unknown_entries],
        },
        "overall_pollen_risk_today": overall,
        "top_pollen_types_today": {
            "state": ", ".join(top_names) if top_names else None,
            "top_value": top_value,
            "top_pollen_codes": [entry.code for entry in top_entries],
            "top_pollen_names": top_names,
            "top_pollen_categories": [
                entry.info.get("category") for entry in top_entries
            ],
            "tie_count": len(top_entries),
        },
    }
