"""Shared pytest fixtures and configuration for Pollen Levels tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.pollenlevels.const import (
    CONF_API_KEY,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SUBENTRY_TYPE_LOCATION,
)
from custom_components.pollenlevels.util import (
    api_key_unique_id,
    format_location_unique_id,
)

TESTS_DIR = Path(__file__).resolve().parent


@pytest.fixture
def fake_api_key() -> str:
    """Return a fake Google Pollen API key for harness tests."""
    return "test-api-key"


@pytest.fixture
def sample_location() -> dict[str, Any]:
    """Return a sample location using public integration constants."""
    return {
        "title": "Madrid",
        CONF_LATITUDE: 40.4168,
        CONF_LONGITUDE: -3.7038,
        "subentry_id": "location-madrid",
    }


@pytest.fixture
def sample_location_subentry_data(sample_location: dict[str, Any]) -> dict[str, Any]:
    """Return ConfigSubentryData-compatible location data."""
    latitude = sample_location[CONF_LATITUDE]
    longitude = sample_location[CONF_LONGITUDE]
    return {
        "subentry_id": sample_location["subentry_id"],
        "subentry_type": SUBENTRY_TYPE_LOCATION,
        "title": sample_location["title"],
        "unique_id": f"{latitude:.4f}_{longitude:.4f}",
        "data": {
            CONF_LATITUDE: latitude,
            CONF_LONGITUDE: longitude,
        },
    }


@pytest.fixture
def ha_config_entry(
    fake_api_key: str,
    sample_location_subentry_data: dict[str, Any],
):
    """Return a parent MockConfigEntry with one location subentry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="pollenlevels-entry",
        title="Pollen Levels",
        unique_id=api_key_unique_id(fake_api_key),
        data={CONF_API_KEY: fake_api_key},
        options={
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_LANGUAGE_CODE: "es",
        },
        subentries_data=[sample_location_subentry_data],
        version=6,
    )


@pytest.fixture
def ha_two_location_config_entry(fake_api_key: str):
    """Return a parent MockConfigEntry with Madrid and Barcelona locations."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    madrid_latitude = 40.4168
    madrid_longitude = -3.7038
    barcelona_latitude = 41.3874
    barcelona_longitude = 2.1686

    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="pollenlevels-entry",
        title="Pollen Levels",
        unique_id=api_key_unique_id(fake_api_key),
        data={CONF_API_KEY: fake_api_key},
        options={
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_LANGUAGE_CODE: "es",
        },
        subentries_data=[
            {
                "subentry_id": "location-madrid",
                "subentry_type": SUBENTRY_TYPE_LOCATION,
                "title": "Madrid",
                "unique_id": format_location_unique_id(
                    madrid_latitude, madrid_longitude
                ),
                "data": {
                    CONF_LATITUDE: madrid_latitude,
                    CONF_LONGITUDE: madrid_longitude,
                },
            },
            {
                "subentry_id": "location-barcelona",
                "subentry_type": SUBENTRY_TYPE_LOCATION,
                "title": "Barcelona",
                "unique_id": format_location_unique_id(
                    barcelona_latitude, barcelona_longitude
                ),
                "data": {
                    CONF_LATITUDE: barcelona_latitude,
                    CONF_LONGITUDE: barcelona_longitude,
                },
            },
        ],
        version=6,
    )


@pytest.fixture
def google_pollen_5_day_payload() -> dict[str, Any]:
    """Return the sanitized real 5-day Google Pollen fixture."""
    fixture_path = TESTS_DIR / "fixtures" / "google_pollen_forecast_5_days.json"
    return json.loads(fixture_path.read_text(encoding="ascii"))
