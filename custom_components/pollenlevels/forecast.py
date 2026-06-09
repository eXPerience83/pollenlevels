"""Shared forecast attribute helper for pollen sensors.

This module provides the pure ``attach_forecast_attributes`` function used
by both the coordinator (TYPE and PLANT sensors) and the daily summary
(overall_pollen_risk_today sensor).
"""

from __future__ import annotations

from typing import Any


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
        base[f"{prefix}_value"] = f.get("value") if f and f.get("has_index") else None
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
    now_val = current_value if current_value is not None else base.get("value")
    tomorrow_val = base.get("tomorrow_value")
    if isinstance(now_val, (int, float)) and isinstance(tomorrow_val, (int, float)):
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
    for f in forecast_list:
        if f.get("has_index") and isinstance(f.get("value"), (int, float)):
            if peak is None or f["value"] > peak["value"]:
                peak = f
    base["expected_peak"] = (
        {
            "offset": peak["offset"],
            "date": peak["date"],
            "value": peak["value"],
            "category": peak["category"],
        }
        if peak
        else None
    )
    return base
