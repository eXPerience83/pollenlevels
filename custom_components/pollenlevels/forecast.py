"""Shared forecast attribute helper for pollen sensors.

This module provides the pure ``attach_forecast_attributes`` function used
by both the coordinator (TYPE and PLANT sensors) and the daily summary
(overall_pollen_risk_today sensor).
"""

from __future__ import annotations

from typing import Any

from .util import normalize_pollen_index_value


def attach_forecast_attributes(
    base: dict[str, Any],
    forecast_list: list[dict[str, Any]],
    current_value: Any = None,
) -> dict[str, Any]:
    """Attach common forecast attributes to *base* in-place and return it.

    Adds:
      * ``forecast`` list
      * tomorrow convenience fields (tomorrow_has_index, tomorrow_value, …)
      * d2 convenience fields (d2_has_index, d2_value, …)
      * ``trend`` (up / down / flat / None)
      * ``expected_peak`` (offset, date, value, category / None)

    Behaviour mirrors the original ``_process_forecast_attributes`` method on
    the coordinator so TYPE and PLANT sensor output stays unchanged.
    """
    base["forecast"] = forecast_list
    forecast_by_offset = {item.get("offset"): item for item in forecast_list}

    def _set_convenience(prefix: str, off: int) -> None:
        f = forecast_by_offset.get(off)
        base[f"{prefix}_has_index"] = f.get("has_index") if f else False
        base[f"{prefix}_value"] = (
            normalize_pollen_index_value(f.get("value"))
            if f and f.get("has_index")
            else None
        )
        base[f"{prefix}_category"] = (
            f.get("category") if f and f.get("has_index") else None
        )
        base[f"{prefix}_description"] = (
            f.get("description") if f and f.get("has_index") else None
        )
        base[f"{prefix}_color_hex"] = (
            f.get("color_hex") if f and f.get("has_index") else None
        )

    _set_convenience("tomorrow", 1)
    _set_convenience("d2", 2)

    # Trend (today vs tomorrow)
    selected_current = current_value if current_value is not None else base.get("value")
    now_val = normalize_pollen_index_value(selected_current)
    tomorrow_val = base.get("tomorrow_value")
    if now_val is not None and tomorrow_val is not None:
        if tomorrow_val > now_val:
            base["trend"] = "up"
        elif tomorrow_val < now_val:
            base["trend"] = "down"
        else:
            base["trend"] = "flat"
    else:
        base["trend"] = None

    # Expected peak (excluding today)
    peak = None
    peak_value = None
    for f in forecast_list:
        value = (
            normalize_pollen_index_value(f.get("value")) if f.get("has_index") else None
        )
        if value is not None and (peak_value is None or value > peak_value):
            peak = f
            peak_value = value
    base["expected_peak"] = (
        {
            "offset": peak["offset"],
            "date": peak["date"],
            "value": peak_value,
            "category": peak["category"],
        }
        if peak
        else None
    )
    return base
