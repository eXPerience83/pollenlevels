"""Unit tests for shared daily summary helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PKG_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "pollenlevels"

SUMMARY_PATH = PKG_PATH / "summary.py"
FORECAST_PATH = PKG_PATH / "forecast.py"

_PKG_NAME = "custom_components.pollenlevels"


def _load_summary_module() -> ModuleType:
    """Load summary.py with package context so relative imports resolve.

    Also loads forecast.py as a sibling module.  Does NOT import Home
    Assistant.
    """
    # -- create stub packages in sys.modules so relative imports work --------
    parent_name = "custom_components"
    if parent_name not in sys.modules:
        parent = ModuleType(parent_name)
        parent.__path__ = [str(PKG_PATH.parent)]
        parent.__package__ = parent_name
        sys.modules[parent_name] = parent

    if _PKG_NAME not in sys.modules:
        pkg = ModuleType(_PKG_NAME)
        pkg.__path__ = [str(PKG_PATH)]
        pkg.__package__ = _PKG_NAME
        sys.modules[_PKG_NAME] = pkg

    # -- load forecast.py first (dependency of summary.py) ------------------
    forecast_spec = importlib.util.spec_from_file_location(
        f"{_PKG_NAME}.forecast", FORECAST_PATH
    )
    assert forecast_spec is not None
    assert forecast_spec.loader is not None
    forecast_module = importlib.util.module_from_spec(forecast_spec)
    sys.modules[f"{_PKG_NAME}.forecast"] = forecast_module
    forecast_spec.loader.exec_module(forecast_module)

    # -- load summary.py ----------------------------------------------------
    summary_spec = importlib.util.spec_from_file_location(
        f"{_PKG_NAME}.summary", SUMMARY_PATH
    )
    assert summary_spec is not None
    assert summary_spec.loader is not None
    summary_module = importlib.util.module_from_spec(summary_spec)
    sys.modules[f"{_PKG_NAME}.summary"] = summary_module
    summary_spec.loader.exec_module(summary_module)

    return summary_module


_module = _load_summary_module()
daily_summary = _module.daily_summary
current_day_type_entries = _module.current_day_type_entries
forecast_type_entries = _module.forecast_type_entries
is_finite_number = _module.is_finite_number


# ── existing tests (unchanged) ─────────────────────────────────────────────


def test_daily_summary_uses_empty_states_without_data() -> None:
    """Daily summary should expose empty payloads without coordinator data."""

    summary = daily_summary({})

    assert summary["plants_in_season_today"]["state"] is None
    assert summary["plants_in_season_today"]["total_plant_count"] == 0
    assert summary["overall_pollen_risk_today"]["state"] is None
    assert summary["overall_pollen_risk_today"]["tie_count"] == 0
    assert summary["top_pollen_types_today"]["state"] is None
    assert summary["top_pollen_types_today"]["tie_count"] == 0


def test_daily_summary_preserves_ties_and_ignores_future_and_nonfinite_values() -> None:
    """Type summaries keep current-day ties and ignore D+ and non-finite values."""

    summary = daily_summary(
        {
            "type_weed": {
                "source": "type",
                "code": "WEED",
                "displayName": "Weed",
                "value": 4,
                "category": "High",
            },
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 4,
                "category": "High",
            },
            "type_tree": {
                "source": "type",
                "displayName": "Tree",
                "value": float("nan"),
                "category": "Low",
            },
            "type_grass_d1": {
                "source": "type",
                "displayName": "Grass tomorrow",
                "value": 6,
                "category": "Very High",
            },
            "type_weed_d2": {
                "source": "type",
                "displayName": "Weed D+2",
                "value": 7,
                "category": "Very High",
            },
        }
    )

    assert summary["overall_pollen_risk_today"] == {
        "state": 4,
        "category": "High",
        "description": None,
        "top_pollen_codes": ["GRASS", "WEED"],
        "top_pollen_names": ["Grass", "Weed"],
        "top_pollen_categories": ["High", "High"],
        "tie_count": 2,
    }
    assert summary["top_pollen_types_today"] == {
        "state": "Grass, Weed",
        "top_value": 4,
        "top_pollen_codes": ["GRASS", "WEED"],
        "top_pollen_names": ["Grass", "Weed"],
        "top_pollen_categories": ["High", "High"],
        "tie_count": 2,
    }


def test_daily_summary_tracks_unknown_plant_season_values() -> None:
    """Plant summaries count only boolean season values as known."""

    summary = daily_summary(
        {
            "plants_oak": {
                "source": "plant",
                "displayName": "Oak",
                "inSeason": True,
            },
            "plants_pine": {
                "source": "plant",
                "displayName": "Pine",
                "inSeason": False,
            },
            "plants_birch": {
                "source": "plant",
                "displayName": "Birch",
                "inSeason": "false",
            },
            "plants_elm": {"source": "plant", "displayName": "Elm"},
        }
    )

    assert summary["plants_in_season_today"] == {
        "state": 1,
        "plant_codes": ["OAK"],
        "plant_names": ["Oak"],
        "in_season_count": 1,
        "out_of_season_count": 1,
        "unknown_season_count": 2,
        "total_plant_count": 4,
        "unknown_season_codes": ["BIRCH", "ELM"],
        "unknown_season_names": ["Birch", "Elm"],
    }


# ── forecast attribute tests ───────────────────────────────────────────────


def test_overall_forecast_not_added_when_no_future_offsets() -> None:
    """No forecast-related attributes when type entries lack forecast data."""
    summary = daily_summary(
        {
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 3,
                "category": "Moderate",
            },
            "type_weed": {
                "source": "type",
                "code": "WEED",
                "displayName": "Weed",
                "value": 2,
                "category": "Low",
                "forecast": [],
            },
        }
    )

    overall = summary["overall_pollen_risk_today"]
    assert overall["state"] == 3
    assert "forecast" not in overall
    assert "tomorrow_has_index" not in overall
    assert "d2_has_index" not in overall
    assert "trend" not in overall
    assert "expected_peak" not in overall
    assert "value" not in overall


def test_overall_forecast_two_days() -> None:
    """A 2-day forecast (offset 1) exposes one forecast item and convenience."""
    summary = daily_summary(
        {
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 2,
                "category": "Low",
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 5,
                        "category": "High",
                        "description": "High",
                        "color_hex": "#FF0000",
                        "color_rgb": [255, 0, 0],
                    }
                ],
            }
        }
    )

    overall = summary["overall_pollen_risk_today"]
    assert overall["state"] == 2
    assert "value" not in overall
    assert len(overall["forecast"]) == 1
    assert overall["forecast"][0]["offset"] == 1
    assert overall["forecast"][0]["value"] == 5
    assert overall["forecast"][0]["has_index"] is True
    assert overall["forecast"][0]["top_pollen_codes"] == ["GRASS"]
    assert overall["forecast"][0]["top_pollen_names"] == ["Grass"]
    assert overall["forecast"][0]["tie_count"] == 1
    assert overall["tomorrow_has_index"] is True
    assert overall["tomorrow_value"] == 5
    assert overall["tomorrow_category"] == "High"
    assert overall["trend"] == "up"
    assert overall["d2_has_index"] is False
    assert overall["d2_value"] is None
    assert overall["expected_peak"] == {
        "offset": 1,
        "date": "2026-06-10",
        "value": 5,
        "category": "High",
    }


def test_overall_forecast_three_days() -> None:
    """A 3-day forecast exposes offsets 1 and 2 with correct convenience."""
    summary = daily_summary(
        {
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 1,
                "category": "Low",
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 3,
                        "category": "Moderate",
                        "description": "Moderate",
                        "color_hex": "#FFFF00",
                        "color_rgb": [255, 255, 0],
                    },
                    {
                        "offset": 2,
                        "date": "2026-06-11",
                        "has_index": True,
                        "value": 7,
                        "category": "Very High",
                        "description": "Very High",
                        "color_hex": "#FF0000",
                        "color_rgb": [255, 0, 0],
                    },
                ],
            }
        }
    )

    overall = summary["overall_pollen_risk_today"]
    assert overall["state"] == 1
    assert len(overall["forecast"]) == 2
    assert overall["forecast"][0]["offset"] == 1
    assert overall["forecast"][1]["offset"] == 2
    assert overall["tomorrow_value"] == 3
    assert overall["d2_value"] == 7
    assert overall["d2_has_index"] is True
    assert overall["expected_peak"]["offset"] == 2
    assert overall["expected_peak"]["value"] == 7


def test_overall_forecast_tie_handling() -> None:
    """Tied max future values preserve both type codes and names."""
    summary = daily_summary(
        {
            "type_weed": {
                "source": "type",
                "code": "WEED",
                "displayName": "Weed",
                "value": 2,
                "category": "Low",
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 5,
                        "category": "High",
                        "description": "High",
                        "color_hex": "#FF0000",
                        "color_rgb": [255, 0, 0],
                    }
                ],
            },
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 3,
                "category": "Moderate",
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 5,
                        "category": "High",
                        "description": "High risk",
                        "color_hex": "#FF0000",
                        "color_rgb": [255, 0, 0],
                    }
                ],
            },
        }
    )

    overall = summary["overall_pollen_risk_today"]
    forecast_item = overall["forecast"][0]
    assert forecast_item["value"] == 5
    assert forecast_item["has_index"] is True
    assert forecast_item["top_pollen_codes"] == ["GRASS", "WEED"]
    assert forecast_item["top_pollen_names"] == ["Grass", "Weed"]
    assert forecast_item["top_pollen_categories"] == ["High", "High"]
    assert forecast_item["tie_count"] == 2
    # Deterministic ordering: GRASS before WEED
    assert forecast_item["top_pollen_codes"] == ["GRASS", "WEED"]


def test_overall_forecast_missing_future_index() -> None:
    """Offset with no valid indexed value produces has_index=False and empty lists."""
    summary = daily_summary(
        {
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 2,
                "category": "Low",
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": False,
                        "value": None,
                        "category": None,
                        "description": None,
                        "color_hex": None,
                        "color_rgb": None,
                    }
                ],
            }
        }
    )

    overall = summary["overall_pollen_risk_today"]
    assert len(overall["forecast"]) == 1
    item = overall["forecast"][0]
    assert item["offset"] == 1
    assert item["has_index"] is False
    assert item["value"] is None
    assert item["category"] is None
    assert item["description"] is None
    assert item["color_hex"] is None
    assert item["color_rgb"] is None
    assert item["top_pollen_codes"] == []
    assert item["top_pollen_names"] == []
    assert item["top_pollen_categories"] == []
    assert item["tie_count"] == 0
    assert overall["tomorrow_has_index"] is False
    assert overall["tomorrow_value"] is None
    assert overall["trend"] is None


def test_overall_forecast_ignores_per_day_d1_d2_keys() -> None:
    """Per-day _d1/_d2 type entries do not contribute to the overall forecast."""
    summary = daily_summary(
        {
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 2,
                "category": "Low",
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 3,
                        "category": "Moderate",
                        "description": "Moderate",
                        "color_hex": "#FFFF00",
                        "color_rgb": [255, 255, 0],
                    }
                ],
            },
            "type_grass_d1": {
                "source": "type",
                "displayName": "Grass D+1",
                "value": 9,
                "category": "Extreme",
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 9,
                        "category": "Extreme",
                        "description": "Extreme",
                        "color_hex": "#FF0000",
                        "color_rgb": [255, 0, 0],
                    }
                ],
            },
        }
    )

    overall = summary["overall_pollen_risk_today"]
    assert len(overall["forecast"]) == 1
    assert overall["forecast"][0]["value"] == 3  # from current-day entry
    assert overall["forecast"][0]["top_pollen_codes"] == ["GRASS"]


def test_forecast_type_entries_includes_future_only_types() -> None:
    """Forecast aggregation includes types with no finite current-day value."""
    entries = forecast_type_entries(
        {
            "type_tree": {
                "source": "type",
                "code": "TREE",
                "displayName": "Tree",
                "value": None,
            },
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 3,
            },
            "type_mold_d1": {
                "source": "type",
                "displayName": "Mold tomorrow",
                "value": 5,
            },
        }
    )

    codes = {e.code for e in entries}
    assert codes == {"GRASS", "TREE"}


def test_overall_forecast_future_only_types_included() -> None:
    """A type with no current-day value can still contribute to overall forecast."""
    summary = daily_summary(
        {
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 3,
                "category": "Moderate",
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 5,
                        "category": "High",
                        "description": "High",
                        "color_hex": "#FF0000",
                        "color_rgb": [255, 0, 0],
                    }
                ],
            },
            "type_tree": {
                "source": "type",
                "code": "TREE",
                "displayName": "Tree",
                "value": None,
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 4,
                        "category": "Moderate",
                        "description": "Moderate",
                        "color_hex": "#FFFF00",
                        "color_rgb": [255, 255, 0],
                    }
                ],
            },
        }
    )

    overall = summary["overall_pollen_risk_today"]
    assert overall["state"] == 3
    assert "value" not in overall
    assert overall["forecast"][0]["value"] == 5
    assert overall["forecast"][0]["top_pollen_codes"] == ["GRASS"]


def test_overall_forecast_future_only_type_can_win_future_risk() -> None:
    """A future-only type (no value today) can dominate the aggregated forecast."""
    summary = daily_summary(
        {
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 3,
                "category": "Moderate",
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 2,
                        "category": "Low",
                        "description": "Low",
                        "color_hex": "#00FF00",
                        "color_rgb": [0, 255, 0],
                    }
                ],
            },
            "type_tree": {
                "source": "type",
                "code": "TREE",
                "displayName": "Tree",
                "value": None,
                "category": None,
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 5,
                        "category": "High",
                        "description": "High",
                        "color_hex": "#FF0000",
                        "color_rgb": [255, 0, 0],
                    }
                ],
            },
        }
    )

    overall = summary["overall_pollen_risk_today"]
    assert overall["state"] == 3
    assert "value" not in overall
    assert len(overall["forecast"]) == 1
    assert overall["forecast"][0]["offset"] == 1
    assert overall["forecast"][0]["date"] == "2026-06-10"
    assert overall["forecast"][0]["has_index"] is True
    assert overall["forecast"][0]["value"] == 5
    assert overall["forecast"][0]["category"] == "High"
    assert overall["forecast"][0]["description"] == "High"
    assert overall["forecast"][0]["color_hex"] == "#FF0000"
    assert overall["forecast"][0]["color_rgb"] == [255, 0, 0]
    assert overall["forecast"][0]["top_pollen_codes"] == ["TREE"]
    assert overall["forecast"][0]["top_pollen_names"] == ["Tree"]
    assert overall["forecast"][0]["top_pollen_categories"] == ["High"]
    assert overall["forecast"][0]["tie_count"] == 1
    assert overall["tomorrow_has_index"] is True
    assert overall["tomorrow_value"] == 5
    assert overall["tomorrow_category"] == "High"
    assert overall["trend"] == "up"
    assert overall["expected_peak"] == {
        "offset": 1,
        "date": "2026-06-10",
        "value": 5,
        "category": "High",
    }


def test_overall_forecast_all_current_values_missing_with_future() -> None:
    """Overall can still produce forecast when no type has a finite current-day value."""
    summary = daily_summary(
        {
            "type_tree": {
                "source": "type",
                "code": "TREE",
                "displayName": "Tree",
                "value": None,
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 4,
                        "category": "Moderate",
                        "description": "Moderate",
                        "color_hex": "#FFFF00",
                        "color_rgb": [255, 255, 0],
                    }
                ],
            },
        }
    )

    overall = summary["overall_pollen_risk_today"]
    assert overall["state"] is None
    assert "value" not in overall
    assert len(overall["forecast"]) == 1
    assert overall["forecast"][0]["value"] == 4


def test_overall_forecast_bool_offset_ignored() -> None:
    """Forecast entries with bool offsets are not treated as valid offsets."""
    summary = daily_summary(
        {
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 3,
                "forecast": [
                    {
                        "offset": True,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 5,
                        "category": "High",
                        "description": "High",
                        "color_hex": "#FF0000",
                        "color_rgb": [255, 0, 0],
                    },
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": True,
                        "value": 4,
                        "category": "Moderate",
                        "description": "Moderate",
                        "color_hex": "#FFFF00",
                        "color_rgb": [255, 255, 0],
                    },
                ],
            },
        }
    )

    overall = summary["overall_pollen_risk_today"]
    assert len(overall["forecast"]) == 1
    assert overall["forecast"][0]["value"] == 4


def test_overall_forecast_has_index_must_be_true_explicit() -> None:
    """Only has_index=True (not truthy 1) is accepted as indexed for overall."""
    summary = daily_summary(
        {
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 3,
                "forecast": [
                    {
                        "offset": 1,
                        "date": "2026-06-10",
                        "has_index": 1,
                        "value": 5,
                        "category": "High",
                        "description": "High",
                        "color_hex": "#FF0000",
                        "color_rgb": [255, 0, 0],
                    },
                ],
            },
        }
    )

    overall = summary["overall_pollen_risk_today"]
    assert len(overall["forecast"]) == 1
    item = overall["forecast"][0]
    assert item["has_index"] is False
    assert item["value"] is None
