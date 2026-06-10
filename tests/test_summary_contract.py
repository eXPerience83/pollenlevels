"""Contract tests for public daily summary attributes."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

PKG_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "pollenlevels"

SUMMARY_PATH = PKG_PATH / "summary.py"
FORECAST_PATH = PKG_PATH / "forecast.py"

_PKG_NAME = "custom_components.pollenlevels"
_MODULE_NAMES = (
    "custom_components",
    _PKG_NAME,
    f"{_PKG_NAME}.forecast",
    f"{_PKG_NAME}.summary",
)

DailySummaryCallable = Callable[
    [dict[str, dict[str, object]]], dict[str, dict[str, object]]
]


def _load_summary_module() -> ModuleType:
    """Load summary.py with package context so relative imports resolve."""
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


@pytest.fixture
def daily_summary_callable() -> Iterator[DailySummaryCallable]:
    """Load daily_summary and restore pre-existing module state after the test."""
    missing = object()
    original_modules = {name: sys.modules.get(name, missing) for name in _MODULE_NAMES}

    module = _load_summary_module()
    try:
        yield module.daily_summary
    finally:
        for name, original_module in original_modules.items():
            if original_module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original_module


def test_summary_sensor_attribute_contract_distinguishes_summary_sensors(
    daily_summary_callable: DailySummaryCallable,
) -> None:
    """Lock the public attribute contract of the three daily summary sensors."""
    data_map: dict[str, dict[str, object]] = {
        "type_grass": {
            "source": "type",
            "code": "GRASS",
            "displayName": "Grass",
            "value": 3,
            "category": "Moderate",
            "description": "Moderate pollen risk",
        },
        "type_tree": {
            "source": "type",
            "code": "TREE",
            "displayName": "Tree",
            "value": 1,
            "category": "Very low",
            "description": "Very low pollen risk",
        },
        "plants_grasses": {
            "source": "plant",
            "code": "GRAMINALES",
            "displayName": "Grasses",
            "inSeason": True,
        },
        "plants_birch": {
            "source": "plant",
            "code": "BIRCH",
            "displayName": "Birch",
            "inSeason": False,
        },
    }

    summary = daily_summary_callable(data_map)

    overall = summary["overall_pollen_risk_today"]
    top_types = summary["top_pollen_types_today"]
    plants = summary["plants_in_season_today"]

    # -- state sanity --------------------------------------------------------
    overall_state = overall["state"]
    assert isinstance(overall_state, int), "overall state must be numeric"
    assert not isinstance(overall_state, bool), "overall state must not be boolean"
    assert overall_state == 3

    top_types_state = top_types["state"]
    assert isinstance(top_types_state, str), "top_types state must be textual"
    assert top_types_state == "Grass"

    plants_state = plants["state"]
    assert isinstance(plants_state, int), "plants state must be numeric"
    assert not isinstance(plants_state, bool), "plants state must not be boolean"
    assert plants_state == 1

    # -- top_pollen_codes contract ------------------------------------------
    assert "top_pollen_codes" in overall
    assert overall["top_pollen_codes"] == ["GRASS"]

    assert "top_pollen_codes" in top_types
    assert top_types["top_pollen_codes"] == ["GRASS"]

    assert "top_pollen_codes" not in plants

    # -- top_value contract --------------------------------------------------
    assert "top_value" not in overall

    assert "top_value" in top_types
    assert top_types["top_value"] == 3

    assert "top_value" not in plants

    # -- plant_codes contract ------------------------------------------------
    assert "plant_codes" not in overall
    assert "plant_codes" not in top_types

    assert "plant_codes" in plants
    assert plants["plant_codes"] == ["GRAMINALES"]
