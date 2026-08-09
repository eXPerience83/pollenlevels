"""Unit tests for the shared forecast attribute helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

PKG_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "pollenlevels"
FORECAST_PATH = PKG_PATH / "forecast.py"

_PKG_NAME = "custom_components.pollenlevels"
_STUB_MODULE_NAMES = (
    "custom_components",
    _PKG_NAME,
    f"{_PKG_NAME}.const",
    f"{_PKG_NAME}.util",
    f"{_PKG_NAME}.forecast",
)


def _load_forecast_module() -> ModuleType:
    """Load forecast.py with package context and without Home Assistant."""
    previous_modules = {
        name: sys.modules[name] for name in _STUB_MODULE_NAMES if name in sys.modules
    }
    try:
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

        spec = importlib.util.spec_from_file_location(
            f"{_PKG_NAME}.forecast", FORECAST_PATH
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"{_PKG_NAME}.forecast"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name in _STUB_MODULE_NAMES:
            if name in previous_modules:
                sys.modules[name] = previous_modules[name]
            else:
                sys.modules.pop(name, None)


attach_forecast_attributes = _load_forecast_module().attach_forecast_attributes


def test_forecast_module_loader_restores_sys_modules() -> None:
    """The standalone loader should not leak its package dependencies."""
    previous_modules = {
        name: sys.modules[name] for name in _STUB_MODULE_NAMES if name in sys.modules
    }

    _load_forecast_module()

    for name in _STUB_MODULE_NAMES:
        if name in previous_modules:
            assert sys.modules[name] is previous_modules[name]
        else:
            assert name not in sys.modules


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
            "value": 5,
            "category": "Very High",
            "description": "Very High",
            "color_hex": "#FF0000",
            "color_rgb": [255, 0, 0],
        },
    ]
    base = {"value": 3}
    result = attach_forecast_attributes(base, forecast)

    assert result["tomorrow_value"] == 4
    assert result["d2_value"] == 5
    assert result["d2_has_index"] is True
    assert result["d2_category"] == "Very High"
    assert result["expected_peak"] == {
        "offset": 2,
        "date": "2026-06-11",
        "value": 5,
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
            "value": 5,
            "category": "Very High",
            "description": "Very High",
            "color_hex": None,
            "color_rgb": None,
        },
    ]
    base = {"value": 1}
    result = attach_forecast_attributes(base, forecast)

    assert result["expected_peak"]["offset"] == 2
    assert result["expected_peak"]["value"] == 5


def test_zero_is_valid_for_convenience_trend_and_expected_peak() -> None:
    """A zero index remains a real value in every forecast calculation."""
    forecast = [
        {
            "offset": 1,
            "date": "2026-06-10",
            "has_index": True,
            "value": 0,
            "category": "None",
            "description": "No pollen",
            "color_hex": "#00FF00",
            "color_rgb": [0, 255, 0],
        }
    ]

    result = attach_forecast_attributes({"value": 1}, forecast)

    assert result["tomorrow_value"] == 0
    assert result["trend"] == "down"
    assert result["expected_peak"] == {
        "offset": 1,
        "date": "2026-06-10",
        "value": 0,
        "category": "None",
    }


def test_malformed_forecast_values_do_not_affect_derived_attributes() -> None:
    """Malformed future values preserve metadata but not numeric derivatives."""
    forecast = [
        {
            "offset": 1,
            "date": "2026-06-10",
            "has_index": True,
            "value": float("nan"),
            "category": "Tomorrow category",
            "description": "Tomorrow description",
            "color_hex": "#112233",
            "color_rgb": [17, 34, 51],
        },
        {
            "offset": 2,
            "date": "2026-06-11",
            "has_index": True,
            "value": "3",
            "category": "D2 category",
            "description": "D2 description",
            "color_hex": "#445566",
            "color_rgb": [68, 85, 102],
        },
        {
            "offset": 3,
            "date": "2026-06-12",
            "has_index": True,
            "value": 4,
            "category": "Valid category",
            "description": "Valid description",
            "color_hex": "#778899",
            "color_rgb": [119, 136, 153],
        },
    ]

    result = attach_forecast_attributes({"value": 2}, forecast)

    assert result["forecast"] is forecast
    assert result["tomorrow_has_index"] is True
    assert result["tomorrow_value"] is None
    assert result["tomorrow_category"] == "Tomorrow category"
    assert result["tomorrow_description"] == "Tomorrow description"
    assert result["tomorrow_color_hex"] == "#112233"
    assert result["d2_has_index"] is True
    assert result["d2_value"] is None
    assert result["d2_category"] == "D2 category"
    assert result["d2_description"] == "D2 description"
    assert result["d2_color_hex"] == "#445566"
    assert result["trend"] is None
    assert result["expected_peak"] == {
        "offset": 3,
        "date": "2026-06-12",
        "value": 4,
        "category": "Valid category",
    }


def test_invalid_current_value_override_does_not_fall_back_to_base() -> None:
    """An explicit malformed current value disables trend calculation."""
    forecast = [
        {
            "offset": 1,
            "date": "2026-06-10",
            "has_index": True,
            "value": 2,
            "category": "Low",
            "description": "Low",
            "color_hex": None,
            "color_rgb": None,
        }
    ]

    result = attach_forecast_attributes({"value": 1}, forecast, current_value=6)

    assert result["tomorrow_value"] == 2
    assert result["trend"] is None
    assert result["expected_peak"]["value"] == 2


def test_attach_current_value_overrides_base_value() -> None:
    """current_value param is used for trend when base has no 'value' key."""
    base: dict[str, Any] = {}
    forecast = [
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
    ]
    result = attach_forecast_attributes(base, forecast, current_value=3)
    assert result["trend"] == "up"
    assert "value" not in result


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
