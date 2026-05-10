"""Unit tests for shared daily summary helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

SUMMARY_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "pollenlevels"
    / "summary.py"
)


def _load_summary_module() -> ModuleType:
    """Load summary.py directly without importing the integration package."""
    spec = importlib.util.spec_from_file_location("pollenlevels_summary", SUMMARY_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


daily_summary = _load_summary_module().daily_summary


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
