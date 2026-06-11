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
        def __init__(self, hass, logger, *, name: str, update_interval):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = None
            self.last_updated = None

    stub_update_coordinator_module(
        update_failed=_StubUpdateFailed,
        data_update_coordinator=_StubDataUpdateCoordinator,
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
        forecast_days=1,
        create_d1=False,
        create_d2=False,
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
