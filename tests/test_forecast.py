"""Unit tests for the shared forecast attribute helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

FORECAST_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "pollenlevels"
    / "forecast.py"
)


def _load_forecast_module() -> ModuleType:
    """Load forecast.py directly (pure module, no HA imports)."""
    spec = importlib.util.spec_from_file_location(
        "pollenlevels_forecast", FORECAST_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


attach_forecast_attributes = _load_forecast_module().attach_forecast_attributes


def test_attach_empty_forecast() -> None:
    """An empty forecast list sets forecast to [] and convenience defaults."""
    base = {"value": 3}
    result = attach_forecast_attributes(base, [])

    assert result is base
    assert result["forecast"] == []
    assert result["tomorrow_has_index"] is False
    assert result["tomorrow_value"] is None
    assert result["tomorrow_category"] is None
    assert result["tomorrow_description"] is None
    assert result["tomorrow_color_hex"] is None
    assert result["d2_has_index"] is False
    assert result["d2_value"] is None
    assert result["trend"] is None
    assert result["expected_peak"] is None


def test_attach_single_offset() -> None:
    """A single offset-1 entry populates tomorrow_* fields and trend."""
    forecast = [
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
    ]
    base = {"value": 2}
    result = attach_forecast_attributes(base, forecast)

    assert result["forecast"] == forecast
    assert result["tomorrow_has_index"] is True
    assert result["tomorrow_value"] == 5
    assert result["tomorrow_category"] == "High"
    assert result["tomorrow_description"] == "High risk"
    assert result["tomorrow_color_hex"] == "#FF0000"
    assert result["d2_has_index"] is False
    assert result["d2_value"] is None
    assert result["trend"] == "up"
    assert result["expected_peak"] == {
        "offset": 1,
        "date": "2026-06-10",
        "value": 5,
        "category": "High",
    }


def test_attach_two_offsets() -> None:
    """Offsets 1 and 2 populate tomorrow_* and d2_* fields."""
    forecast = [
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
        {
            "offset": 2,
            "date": "2026-06-11",
            "has_index": True,
            "value": 6,
            "category": "Very High",
            "description": "Very High",
            "color_hex": "#FF0000",
            "color_rgb": [255, 0, 0],
        },
    ]
    base = {"value": 3}
    result = attach_forecast_attributes(base, forecast)

    assert result["tomorrow_value"] == 4
    assert result["d2_value"] == 6
    assert result["d2_has_index"] is True
    assert result["d2_category"] == "Very High"
    assert result["expected_peak"] == {
        "offset": 2,
        "date": "2026-06-11",
        "value": 6,
        "category": "Very High",
    }


def test_trend_flat() -> None:
    """Equal today and tomorrow values produce trend 'flat'."""
    forecast = [
        {
            "offset": 1,
            "date": "2026-06-10",
            "has_index": True,
            "value": 3,
            "category": "Moderate",
            "description": "Moderate",
            "color_hex": None,
            "color_rgb": None,
        }
    ]
    base = {"value": 3}
    result = attach_forecast_attributes(base, forecast)

    assert result["trend"] == "flat"


def test_trend_down() -> None:
    """Tomorrow value lower than today produces trend 'down'."""
    forecast = [
        {
            "offset": 1,
            "date": "2026-06-10",
            "has_index": True,
            "value": 1,
            "category": "Low",
            "description": "Low",
            "color_hex": None,
            "color_rgb": None,
        }
    ]
    base = {"value": 4}
    result = attach_forecast_attributes(base, forecast)

    assert result["trend"] == "down"


def test_trend_none_when_missing_value() -> None:
    """Trend is None when today or tomorrow value is missing."""
    forecast = [
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
    ]
    base = {"value": 3}
    result = attach_forecast_attributes(base, forecast)

    assert result["trend"] is None


def test_expected_peak_picks_highest() -> None:
    """Expected peak selects the highest future indexed value."""
    forecast = [
        {
            "offset": 1,
            "date": "2026-06-10",
            "has_index": True,
            "value": 3,
            "category": "Moderate",
            "description": "Moderate",
            "color_hex": None,
            "color_rgb": None,
        },
        {
            "offset": 2,
            "date": "2026-06-11",
            "has_index": True,
            "value": 7,
            "category": "Very High",
            "description": "Very High",
            "color_hex": None,
            "color_rgb": None,
        },
    ]
    base = {"value": 1}
    result = attach_forecast_attributes(base, forecast)

    assert result["expected_peak"]["offset"] == 2
    assert result["expected_peak"]["value"] == 7


def test_expected_peak_none_when_all_missing() -> None:
    """Expected peak is None when no forecast entry has a valid index."""
    forecast = [
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
    ]
    base = {"value": 2}
    result = attach_forecast_attributes(base, forecast)

    assert result["expected_peak"] is None
