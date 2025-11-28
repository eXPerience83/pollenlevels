"""Options flow validation tests for Pollen Levels."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.pollenlevels.const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
)
from tests import test_config_flow as base

PollenLevelsOptionsFlow = base.cf.PollenLevelsOptionsFlow
_StubConfigEntry = base._StubConfigEntry


def _flow(entry_data: dict | None = None, options: dict | None = None):
    entry = _StubConfigEntry(
        data=entry_data
        or {
            CONF_API_KEY: "key",
            CONF_LATITUDE: 1.0,
            CONF_LONGITUDE: 2.0,
            CONF_LANGUAGE_CODE: "en",
            CONF_UPDATE_INTERVAL: 6,
            CONF_FORECAST_DAYS: 2,
            CONF_CREATE_FORECAST_SENSORS: "none",
        },
        options=options,
    )
    flow = PollenLevelsOptionsFlow(entry)
    flow.hass = SimpleNamespace(config=SimpleNamespace(language="en"))
    flow.async_show_form = lambda **kwargs: kwargs
    flow.async_create_entry = lambda *, title, data: {"title": title, "data": data}
    return flow


def test_options_flow_invalid_language_sets_error() -> None:
    """Invalid language in options should map to invalid_language_format."""

    flow = _flow()

    result = asyncio.run(
        flow.async_step_init(
            {
                CONF_LANGUAGE_CODE: "bad code",
                CONF_FORECAST_DAYS: 2,
                CONF_CREATE_FORECAST_SENSORS: "none",
                CONF_UPDATE_INTERVAL: 6,
            }
        )
    )

    assert result["errors"] == {CONF_LANGUAGE_CODE: "invalid_language_format"}


def test_options_flow_forecast_days_below_min_sets_error() -> None:
    """Forecast days below allowed range should error."""

    flow = _flow()

    result = asyncio.run(
        flow.async_step_init(
            {
                CONF_LANGUAGE_CODE: "en",
                CONF_FORECAST_DAYS: 0,
                CONF_CREATE_FORECAST_SENSORS: "none",
                CONF_UPDATE_INTERVAL: 6,
            }
        )
    )

    assert result["errors"] == {
        CONF_FORECAST_DAYS: "invalid_option_combo",
        CONF_CREATE_FORECAST_SENSORS: "invalid_option_combo",
    }


@pytest.mark.parametrize(
    "mode,days",
    [("D+1", 1), ("D+1+2", 2)],
)
def test_options_flow_per_day_sensor_requires_enough_days(mode: str, days: int) -> None:
    """Per-day sensor modes should enforce minimum forecast days."""

    flow = _flow()

    result = asyncio.run(
        flow.async_step_init(
            {
                CONF_LANGUAGE_CODE: "en",
                CONF_FORECAST_DAYS: days,
                CONF_CREATE_FORECAST_SENSORS: mode,
                CONF_UPDATE_INTERVAL: 6,
            }
        )
    )

    assert result["errors"] == {CONF_CREATE_FORECAST_SENSORS: "invalid_option_combo"}


def test_options_flow_valid_submission_returns_entry_data() -> None:
    """A valid options submission should return the data unchanged."""

    flow = _flow()

    user_input = {
        CONF_LANGUAGE_CODE: " es ",
        CONF_FORECAST_DAYS: 3,
        CONF_CREATE_FORECAST_SENSORS: "D+1",
        CONF_UPDATE_INTERVAL: 8,
    }

    result = asyncio.run(flow.async_step_init(dict(user_input)))

    assert result == {
        "title": "",
        "data": {
            **user_input,
            CONF_LANGUAGE_CODE: "es",
        },
    }
