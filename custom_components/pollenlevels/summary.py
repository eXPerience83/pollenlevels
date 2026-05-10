"""Pure helpers for daily pollen summary extraction."""

from __future__ import annotations

import math
from typing import Any, NamedTuple


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
        "overall_pollen_risk_today": {
            "state": top_value,
            "category": first_info.get("category"),
            "description": first_info.get("description"),
            "top_pollen_codes": [entry.code for entry in top_entries],
            "top_pollen_names": top_names,
            "top_pollen_categories": [
                entry.info.get("category") for entry in top_entries
            ],
            "tie_count": len(top_entries),
        },
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
