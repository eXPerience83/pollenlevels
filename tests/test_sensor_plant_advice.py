"""Regression tests for plant health advice handling."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from tests._ha_stubs import (
    clear_integration_modules,
    stub_aiohttp_module,
    stub_custom_components_packages,
    stub_exceptions,
    stub_homeassistant_package,
    stub_update_coordinator_module,
    stub_util_dt_module,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class SensorModules(NamedTuple):
    """Integration modules imported under fixture-scoped Home Assistant stubs."""

    client_mod: types.ModuleType
    coordinator_mod: types.ModuleType


def _install_coordinator_import_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install minimal Home Assistant stubs needed by coordinator imports."""

    clear_integration_modules(monkeypatch=monkeypatch)
    stub_custom_components_packages(root=ROOT, monkeypatch=monkeypatch)
    stub_homeassistant_package(monkeypatch=monkeypatch)

    class _StubConfigEntryAuthFailed(Exception):
        pass

    stub_exceptions(
        monkeypatch=monkeypatch,
        ConfigEntryAuthFailed=_StubConfigEntryAuthFailed,
    )

    class _StubUpdateFailed(Exception):
        pass

    class _StubDataUpdateCoordinator:
        def __init__(self, hass, logger, *, name: str, update_interval) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = None
            self.last_updated = None

    class _StubCoordinatorEntity:
        def __init__(self, coordinator) -> None:
            self.coordinator = coordinator

    stub_update_coordinator_module(
        update_failed=_StubUpdateFailed,
        data_update_coordinator=_StubDataUpdateCoordinator,
        coordinator_entity=_StubCoordinatorEntity,
        monkeypatch=monkeypatch,
    )
    stub_util_dt_module(monkeypatch=monkeypatch)
    stub_aiohttp_module(monkeypatch=monkeypatch)


def _load_module(
    module_name: str, relative_path: str, monkeypatch: pytest.MonkeyPatch
) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "custom_components" / "pollenlevels" / relative_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


@pytest.fixture
def sensor_modules(monkeypatch: pytest.MonkeyPatch) -> SensorModules:
    """Import coordinator dependencies with fixture-scoped Home Assistant stubs."""

    _install_coordinator_import_stubs(monkeypatch)
    modules = SensorModules(
        client_mod=_load_module(
            "custom_components.pollenlevels.client", "client.py", monkeypatch
        ),
        coordinator_mod=_load_module(
            "custom_components.pollenlevels.coordinator", "coordinator.py", monkeypatch
        ),
    )
    yield modules
    clear_integration_modules()


class DummyHass:
    """Minimal Home Assistant stub for the coordinator."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.data: dict[str, Any] = {}


class FakeResponse:
    """Async context manager returning a static payload."""

    def __init__(self, payload: dict[str, Any], *, status: int = 200) -> None:
        self._payload = payload
        self.status = status
        self.headers: dict[str, str] = {}

    async def json(self) -> dict[str, Any]:
        return self._payload

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(
        self,
        exc_type,
        exc: BaseException | None,
        tb,
    ) -> None:
        return None


class FakeSession:
    """Return a fake aiohttp-like session that yields the provided payload."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def get(self, *_args, **_kwargs) -> FakeResponse:
        return FakeResponse(self._payload)


def _make_coordinator(
    sensor_modules: SensorModules,
    loop: asyncio.AbstractEventLoop,
    client: Any,
) -> Any:
    """Build a coordinator with stable defaults for refresh tests."""

    return sensor_modules.coordinator_mod.PollenDataUpdateCoordinator(
        hass=DummyHass(loop),
        api_key="test",
        lat=1.0,
        lon=2.0,
        hours=12,
        language=None,
        entry_id="entry",
        client=client,
    )


def test_plant_sensor_does_not_inherit_type_health_recommendations(
    sensor_modules: SensorModules,
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

    fake_session = FakeSession(payload)
    client = sensor_modules.client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(sensor_modules, loop, client)

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert data["type_weed"]["advice"] == ["Keep windows closed"]
    assert data["plants_ragweed"]["advice"] is None


def test_plant_without_index_info(
    sensor_modules: SensorModules,
) -> None:
    """Plant without indexInfo is present in coordinator output with null index fields."""

    payload = {
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 7, "day": 1},
                "pollenTypeInfo": [
                    {
                        "code": "TREE",
                        "displayName": "Tree",
                        "healthRecommendations": ["Avoid outdoor activity"],
                        "indexInfo": {
                            "value": 2,
                            "category": "LOW",
                            "indexDescription": "Low",
                        },
                    }
                ],
                "plantInfo": [
                    {
                        "code": "hazel",
                        "displayName": "Hazel",
                    },
                    {
                        "code": "oak",
                        "displayName": "Oak",
                        "indexInfo": {
                            "value": 3,
                            "category": "MODERATE",
                            "indexDescription": "Moderate",
                        },
                    },
                ],
            }
        ]
    }

    fake_session = FakeSession(payload)
    client = sensor_modules.client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(sensor_modules, loop, client)

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert "plants_hazel" in data
    hazel = data["plants_hazel"]

    assert hazel["source"] == "plant"
    assert hazel["code"] == "hazel"
    assert hazel["displayName"] == "Hazel"
    assert hazel["value"] is None
    assert hazel["category"] is None
    assert hazel["description"] is None
    assert hazel["color_hex"] is None
    assert hazel["color_rgb"] is None
    assert hazel["advice"] is None

    assert "plants_oak" in data
    assert data["plants_oak"]["value"] == 3
    assert "type_tree" in data
    assert data["type_tree"]["value"] == 2
    assert data["type_tree"]["advice"] == ["Avoid outdoor activity"]


def test_plant_missing_optional_metadata(
    sensor_modules: SensorModules,
) -> None:
    """Missing optional plant metadata fields fall back safely."""

    payload = {
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 7, "day": 1},
                "plantInfo": [
                    {
                        "code": "alder",
                    },
                    {
                        "code": "birch",
                        "displayName": "Birch",
                        "inSeason": True,
                        "plantDescription": "not-a-dict",
                        "indexInfo": {
                            "value": 2,
                            "category": "LOW",
                        },
                    },
                    {
                        "code": "oak",
                        "displayName": "Oak",
                        "inSeason": True,
                        "plantDescription": {
                            "type": "TREE",
                            "family": "Fagaceae",
                            "season": "Spring",
                            "crossReaction": ["Birch"],
                            "picture": "https://example.com/oak.jpg",
                            "pictureCloseup": "https://example.com/oak-close.jpg",
                        },
                        "indexInfo": {
                            "value": 2,
                            "category": "LOW",
                        },
                    },
                ],
            }
        ]
    }

    fake_session = FakeSession(payload)
    client = sensor_modules.client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(sensor_modules, loop, client)

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    alder = data["plants_alder"]
    assert alder["displayName"] == "alder"
    assert alder["inSeason"] is None
    assert alder["type"] is None
    assert alder["family"] is None
    assert alder["season"] is None
    assert alder["cross_reaction"] is None
    assert alder["picture"] is None
    assert alder["picture_closeup"] is None

    birch = data["plants_birch"]
    assert birch["displayName"] == "Birch"
    assert birch["inSeason"] is True
    assert birch["type"] is None
    assert birch["family"] is None
    assert birch["season"] is None
    assert birch["cross_reaction"] is None
    assert birch["picture"] is None
    assert birch["picture_closeup"] is None

    oak = data["plants_oak"]
    assert oak["displayName"] == "Oak"
    assert oak["inSeason"] is True
    assert oak["type"] == "TREE"
    assert oak["family"] == "Fagaceae"
    assert oak["season"] == "Spring"
    assert oak["cross_reaction"] == ["Birch"]
    assert oak["picture"] == "https://example.com/oak.jpg"
    assert oak["picture_closeup"] == "https://example.com/oak-close.jpg"


def test_plant_missing_and_partial_colors(
    sensor_modules: SensorModules,
) -> None:
    """Missing, empty, partial, and zero-valued color structures produce correct output."""

    payload = {
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 7, "day": 1},
                "plantInfo": [
                    {
                        "code": "alder",
                        "displayName": "Alder",
                        "indexInfo": {
                            "value": 1,
                            "category": "LOW",
                        },
                    },
                    {
                        "code": "birch",
                        "displayName": "Birch",
                        "indexInfo": {
                            "value": 1,
                            "category": "LOW",
                            "color": {},
                        },
                    },
                    {
                        "code": "hazel",
                        "displayName": "Hazel",
                        "indexInfo": {
                            "value": 2,
                            "category": "MODERATE",
                            "color": {"green": 128, "blue": 64},
                        },
                    },
                    {
                        "code": "oak",
                        "displayName": "Oak",
                        "indexInfo": {
                            "value": 3,
                            "category": "HIGH",
                            "color": {"red": 0, "green": 0, "blue": 0},
                        },
                    },
                ],
            }
        ]
    }

    fake_session = FakeSession(payload)
    client = sensor_modules.client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(sensor_modules, loop, client)

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert data["plants_alder"]["color_hex"] is None
    assert data["plants_alder"]["color_rgb"] is None

    assert data["plants_birch"]["color_hex"] is None
    assert data["plants_birch"]["color_rgb"] is None

    assert data["plants_hazel"]["color_rgb"] == [0, 128, 64]
    assert data["plants_hazel"]["color_hex"] == "#008040"

    assert data["plants_oak"]["color_rgb"] == [0, 0, 0]
    assert data["plants_oak"]["color_hex"] == "#000000"
