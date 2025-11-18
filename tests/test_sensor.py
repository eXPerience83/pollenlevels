"""Coordinator and entity-registry tests using the HA test harness."""

from __future__ import annotations

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pollenlevels import sensor
from custom_components.pollenlevels.const import (
    CONF_FORECAST_DAYS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

API_URL = "https://pollen.googleapis.com/v1/forecast:lookup"

TYPE_FORECAST_PAYLOAD = {
    "regionCode": "test_region",
    "dailyInfo": [
        {
            "date": {"year": 2025, "month": 6, "day": 1},
            "pollenTypeInfo": [],
        },
        {
            "date": {"year": 2025, "month": 6, "day": 2},
            "pollenTypeInfo": [
                {
                    "code": "GRASS",
                    "displayName": "Grass Pollen",
                    "inSeason": True,
                    "healthRecommendations": ["Carry medication"],
                    "indexInfo": {
                        "value": 3,
                        "category": "MODERATE",
                        "indexDescription": "Moderate",
                        "color": {"red": 80, "green": 170, "blue": 60},
                    },
                }
            ],
        },
        {
            "date": {"year": 2025, "month": 6, "day": 3},
            "pollenTypeInfo": [
                {
                    "code": "GRASS",
                    "displayName": "Grass Pollen",
                    "inSeason": True,
                    "healthRecommendations": ["Monitor symptoms"],
                    "indexInfo": {
                        "value": 1,
                        "category": "LOW",
                        "indexDescription": "Low",
                        "color": {"red": 40, "green": 120, "blue": 80},
                    },
                }
            ],
        },
    ],
}

PLANT_FORECAST_PAYLOAD = {
    "regionCode": "test_region",
    "dailyInfo": [
        {
            "date": {"year": 2025, "month": 7, "day": 1},
            "plantInfo": [
                {
                    "code": "ragweed",
                    "displayName": "Ragweed",
                    "inSeason": True,
                    "healthRecommendations": ["Limit outdoor time"],
                    "indexInfo": {
                        "value": 2,
                        "category": "LOW",
                        "indexDescription": "Low",
                        "color": {"red": 50, "green": 150, "blue": 70},
                    },
                    "plantDescription": {
                        "type": "weed",
                        "family": "Asteraceae",
                        "season": "Fall",
                        "crossReaction": ["Sunflower"],
                        "picture": "https://example.com/plant.jpg",
                        "pictureCloseup": "https://example.com/plant-close.jpg",
                    },
                }
            ],
        },
        {
            "date": {"year": 2025, "month": 7, "day": 2},
            "plantInfo": [
                {
                    "code": "ragweed",
                    "displayName": "Ragweed",
                    "inSeason": True,
                    "healthRecommendations": ["Carry medication"],
                    "indexInfo": {
                        "value": 4,
                        "category": "HIGH",
                        "indexDescription": "High",
                        "color": {"red": 200, "green": 120, "blue": 40},
                    },
                }
            ],
        },
        {
            "date": {"year": 2025, "month": 7, "day": 3},
            "plantInfo": [
                {
                    "code": "ragweed",
                    "displayName": "Ragweed",
                    "inSeason": False,
                    "healthRecommendations": ["Expect relief"],
                    "indexInfo": {
                        "value": 1,
                        "category": "LOW",
                        "indexDescription": "Low",
                        "color": {"red": 40, "green": 150, "blue": 80},
                    },
                }
            ],
        },
    ],
}


def _coordinator(
    hass,
    *,
    forecast_days: int = 3,
    create_d1: bool = True,
    create_d2: bool = True,
) -> sensor.PollenDataUpdateCoordinator:
    return sensor.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="secret",
        lat=40.0,
        lon=-105.0,
        hours=24,
        language="en",
        entry_id="entry",
        forecast_days=forecast_days,
        create_d1=create_d1,
        create_d2=create_d2,
    )


@pytest.mark.asyncio
async def test_type_sensor_uses_forecast_metadata_when_today_missing(
    hass, aioclient_mock
):
    """Future days provide display/advice metadata when today lacks a type entry."""

    aioclient_mock.get(API_URL, json=TYPE_FORECAST_PAYLOAD)

    coordinator = _coordinator(hass)
    data = await coordinator._async_update_data()

    entry = data["type_grass"]
    assert entry["source"] == "type"
    assert entry["displayName"] == "Grass Pollen"
    assert entry["advice"] == ["Carry medication"]
    assert entry["forecast"][0]["offset"] == 1
    assert entry["tomorrow_value"] == 3
    assert entry["expected_peak"]["offset"] == 1


@pytest.mark.asyncio
async def test_plant_sensor_includes_forecast_attributes(hass, aioclient_mock):
    """Plant sensors retain forecast list plus derived tomorrow/d2 helpers."""

    aioclient_mock.get(API_URL, json=PLANT_FORECAST_PAYLOAD)
    coordinator = _coordinator(hass, create_d1=False, create_d2=False)
    data = await coordinator._async_update_data()

    entry = data["plants_ragweed"]
    assert entry["source"] == "plant"
    assert entry["value"] == 2
    assert entry["tomorrow_value"] == 4
    assert entry["tomorrow_category"] == "HIGH"
    assert entry["d2_value"] == 1
    assert entry["trend"] == "up"
    assert entry["expected_peak"]["offset"] == 1


@pytest.mark.asyncio
async def test_cleanup_per_day_entities_respects_allow_flags(hass):
    """Entity registry cleanup removes only the disabled per-day suffixes."""

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)

    keep = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_type_grass",
        suggested_object_id="pollen_type_grass",
        config_entry_id=entry.entry_id,
    )
    d1 = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_type_grass_d1",
        suggested_object_id="pollen_type_grass_d1",
        config_entry_id=entry.entry_id,
    )
    d2 = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_type_grass_d2",
        suggested_object_id="pollen_type_grass_d2",
        config_entry_id=entry.entry_id,
    )

    removed = await sensor._cleanup_per_day_entities(
        hass, entry.entry_id, allow_d1=False, allow_d2=True
    )
    assert removed == 1
    assert registry.async_get(d1.entity_id) is None
    assert registry.async_get(d2.entity_id) is not None
    assert registry.async_get(keep.entity_id) is not None

    removed += await sensor._cleanup_per_day_entities(
        hass, entry.entry_id, allow_d1=True, allow_d2=False
    )
    assert removed == 2
    assert registry.async_get(d2.entity_id) is None


@pytest.mark.asyncio
async def test_coordinator_raises_auth_failed_on_403(hass, aioclient_mock):
    """The coordinator bubbles ConfigEntryAuthFailed so HA can trigger reauth."""

    aioclient_mock.get(API_URL, status=403)
    coordinator = _coordinator(hass, create_d1=False, create_d2=False)

    with pytest.raises(sensor.ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_async_setup_entry_missing_api_key_triggers_reauth(hass):
    """Setup fails fast and requests reauth when the API key is missing."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LATITUDE: 40.0,
            CONF_LONGITUDE: -105.0,
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_FORECAST_DAYS: DEFAULT_FORECAST_DAYS,
        },
    )
    entry.add_to_hass(hass)

    async def _async_add_entities(entities, update_before_add: bool = False) -> None:
        return None

    with pytest.raises(sensor.ConfigEntryAuthFailed):
        await sensor.async_setup_entry(hass, entry, _async_add_entities)
