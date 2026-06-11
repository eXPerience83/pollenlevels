"""Regression tests for plant health advice handling."""

from __future__ import annotations

import asyncio

import pytest

from tests import test_sensor as sensor_helpers


@pytest.fixture
def sensor_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> sensor_helpers.SensorModules:
    """Import sensor dependencies with fixture-scoped Home Assistant stubs."""

    sensor_helpers._install_sensor_import_stubs(monkeypatch)
    modules = sensor_helpers.SensorModules(
        const=sensor_helpers._load_module(
            "custom_components.pollenlevels.const", "const.py", monkeypatch
        ),
        client_mod=sensor_helpers._load_module(
            "custom_components.pollenlevels.client", "client.py", monkeypatch
        ),
        coordinator_mod=sensor_helpers._load_module(
            "custom_components.pollenlevels.coordinator", "coordinator.py", monkeypatch
        ),
        sensor=sensor_helpers._load_module(
            "custom_components.pollenlevels.sensor", "sensor.py", monkeypatch
        ),
    )
    yield modules
    sensor_helpers.clear_integration_modules()


def test_plant_sensor_does_not_inherit_type_health_recommendations(
    sensor_modules: sensor_helpers.SensorModules,
) -> None:
    """Plant advice is not derived from same-family pollen type advice."""

    payload = {
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 6, "day": 1},
                "pollenTypeInfo": [
                    {
                        "code": "WEED",
                        "displayName": "Weed",
                        "healthRecommendations": ["Keep windows closed"],
                        "indexInfo": {
                            "value": 3,
                            "category": "MODERATE",
                            "indexDescription": "Moderate",
                        },
                    }
                ],
                "plantInfo": [
                    {
                        "code": "ragweed",
                        "displayName": "Ragweed",
                        "indexInfo": {
                            "value": 2,
                            "category": "LOW",
                            "indexDescription": "Low",
                        },
                        "plantDescription": {"type": "WEED"},
                    }
                ],
            }
        ]
    }

    fake_session = sensor_helpers.FakeSession(payload)
    client = sensor_modules.client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    coordinator = sensor_helpers._make_coordinator(sensor_modules, loop, client)

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert data["type_weed"]["advice"] == ["Keep windows closed"]
    assert data["plants_ragweed"]["advice"] is None
