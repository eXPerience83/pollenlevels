"""Shared helpers for Home Assistant harness tests."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl

from aioresponses import CallbackResult, aioresponses
from homeassistant.core import HomeAssistant

from custom_components.pollenlevels.const import FORECAST_DAYS

POLLEN_API_URL_RE = re.compile(
    r"^https://pollen\.googleapis\.com/v1/forecast:lookup.*$"
)


def mock_pollen_api(
    mocked: aioresponses,
    payload: dict[str, Any],
    captured_params: list[dict[str, Any]] | None = None,
) -> None:
    """Mock Google Pollen API responses and capture request parameters."""

    def _callback(url, **kwargs):
        params = dict(kwargs.get("params") or parse_qsl(url.query_string))
        if captured_params is not None:
            captured_params.append(params)
        return CallbackResult(status=200, payload=payload)

    mocked.get(POLLEN_API_URL_RE, callback=_callback, repeat=True)


async def async_setup_config_entry(hass: HomeAssistant, config_entry: Any) -> None:
    """Set up a config entry and wait for Home Assistant tasks to settle."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


def assert_fixed_forecast_days(captured_params: list[dict[str, Any]]) -> None:
    """Assert every captured Google Pollen request used the fixed days value."""
    assert captured_params
    assert all(params["days"] == FORECAST_DAYS for params in captured_params)


def location_subentry_data(
    *,
    subentry_id: str,
    title: str,
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    """Return ConfigSubentryData-compatible location data."""
    from custom_components.pollenlevels.const import (
        CONF_LATITUDE,
        CONF_LONGITUDE,
        SUBENTRY_TYPE_LOCATION,
    )

    return {
        "subentry_id": subentry_id,
        "subentry_type": SUBENTRY_TYPE_LOCATION,
        "title": title,
        "unique_id": f"{latitude:.4f}_{longitude:.4f}",
        "data": {
            CONF_LATITUDE: latitude,
            CONF_LONGITUDE: longitude,
        },
    }
