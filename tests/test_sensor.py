"""Unit tests for Pollen Levels sensor data shaping."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Ensure the custom_components namespace exists for relative imports.
custom_components_pkg = types.ModuleType("custom_components")
custom_components_pkg.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components_pkg)

pollenlevels_pkg = types.ModuleType("custom_components.pollenlevels")
pollenlevels_pkg.__path__ = [str(ROOT / "custom_components" / "pollenlevels")]
sys.modules.setdefault("custom_components.pollenlevels", pollenlevels_pkg)

# ---------------------------------------------------------------------------
# Minimal Home Assistant stubs to import the integration module under test.
# ---------------------------------------------------------------------------
ha = types.ModuleType("homeassistant")
sys.modules.setdefault("homeassistant", ha)

ha.components = types.ModuleType("homeassistant.components")
sys.modules.setdefault("homeassistant.components", ha.components)

sensor_mod = types.ModuleType("homeassistant.components.sensor")


class _StubSensorEntity:  # pragma: no cover - no runtime behavior needed
    pass


class _StubSensorDeviceClass:
    DATE = "date"
    TIMESTAMP = "timestamp"


class _StubSensorStateClass:
    MEASUREMENT = "measurement"


sensor_mod.SensorDeviceClass = _StubSensorDeviceClass
sensor_mod.SensorEntity = _StubSensorEntity
sensor_mod.SensorStateClass = _StubSensorStateClass
sys.modules.setdefault("homeassistant.components.sensor", sensor_mod)

const_mod = sys.modules.get("homeassistant.const")
if const_mod is None:
    const_mod = types.ModuleType("homeassistant.const")
    sys.modules["homeassistant.const"] = const_mod

const_mod.ATTR_ATTRIBUTION = "Attribution"
const_mod.CONF_NAME = "name"
const_mod.CONF_LOCATION = "location"
const_mod.CONF_LATITUDE = "latitude"
const_mod.CONF_LONGITUDE = "longitude"

exceptions_mod = types.ModuleType("homeassistant.exceptions")


class _StubConfigEntryNotReady(Exception):
    pass


class _StubConfigEntryAuthFailed(Exception):
    pass


exceptions_mod.ConfigEntryNotReady = _StubConfigEntryNotReady
exceptions_mod.ConfigEntryAuthFailed = _StubConfigEntryAuthFailed
sys.modules.setdefault("homeassistant.exceptions", exceptions_mod)

helpers_mod = types.ModuleType("homeassistant.helpers")
sys.modules.setdefault("homeassistant.helpers", helpers_mod)

entity_registry_mod = types.ModuleType("homeassistant.helpers.entity_registry")


def _stub_async_get(_hass):  # pragma: no cover - not exercised in tests
    class _Registry:
        @staticmethod
        def async_entries_for_config_entry(_registry, _entry_id):
            return []

    return _Registry()


entity_registry_mod.async_get = _stub_async_get
entity_registry_mod.async_entries_for_config_entry = lambda *args, **kwargs: []
sys.modules.setdefault("homeassistant.helpers.entity_registry", entity_registry_mod)

aiohttp_client_mod = types.ModuleType("homeassistant.helpers.aiohttp_client")
aiohttp_client_mod.async_get_clientsession = lambda hass: None
sys.modules.setdefault("homeassistant.helpers.aiohttp_client", aiohttp_client_mod)

entity_mod = types.ModuleType("homeassistant.helpers.entity")


class _StubEntityCategory:
    DIAGNOSTIC = "diagnostic"


entity_mod.EntityCategory = _StubEntityCategory
sys.modules.setdefault("homeassistant.helpers.entity", entity_mod)

entity_platform_mod = types.ModuleType("homeassistant.helpers.entity_platform")


def _add_entities_callback_stub(entities, update_before_add: bool = False) -> None:
    return None


entity_platform_mod.AddEntitiesCallback = _add_entities_callback_stub  # type: ignore[assignment]
sys.modules.setdefault("homeassistant.helpers.entity_platform", entity_platform_mod)

update_coordinator_mod = types.ModuleType("homeassistant.helpers.update_coordinator")


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

    async def async_config_entry_first_refresh(self):
        """Simulate a successful first refresh with minimal payload."""

        if self.data is None:
            # Provide minimal successful payload so entity setup can proceed
            self.data = {
                "date": {"source": "meta"},
                "region": {"source": "meta"},
            }
        if self.last_updated is None:
            self.last_updated = "now"

        return None


class _StubCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_unique_id = None
        self._attr_device_info = None

    @property
    def unique_id(self):  # pragma: no cover - simple data holder
        return self._attr_unique_id

    @property
    def device_info(self):  # pragma: no cover - simple data holder
        return self._attr_device_info


update_coordinator_mod.DataUpdateCoordinator = _StubDataUpdateCoordinator
update_coordinator_mod.UpdateFailed = _StubUpdateFailed
update_coordinator_mod.CoordinatorEntity = _StubCoordinatorEntity
sys.modules.setdefault(
    "homeassistant.helpers.update_coordinator", update_coordinator_mod
)

dt_mod = types.ModuleType("homeassistant.util.dt")


def _stub_utcnow():
    """Return a timezone-aware UTC datetime, similar to Home Assistant."""

    from datetime import UTC, datetime

    return datetime.now(UTC)


dt_mod.utcnow = _stub_utcnow
sys.modules.setdefault("homeassistant.util.dt", dt_mod)

util_mod = types.ModuleType("homeassistant.util")
util_mod.dt = dt_mod
sys.modules.setdefault("homeassistant.util", util_mod)

aiohttp_mod = types.ModuleType("aiohttp")


class _StubClientError(Exception):
    pass


class _StubClientTimeout:
    def __init__(self, total: float | None = None):
        self.total = total


aiohttp_mod.ClientError = _StubClientError
aiohttp_mod.ClientTimeout = _StubClientTimeout
sys.modules.setdefault("aiohttp", aiohttp_mod)


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "custom_components" / "pollenlevels" / relative_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    sys.modules[module_name] = module
    return module


_load_module("custom_components.pollenlevels.const", "const.py")
sensor = _load_module("custom_components.pollenlevels.sensor", "sensor.py")


class DummyHass:
    """Minimal Home Assistant stub for the coordinator."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.data: dict[str, Any] = {}


class FakeConfigEntry:
    """ConfigEntry stub exposing data/options/entry_id."""

    def __init__(
        self,
        *,
        data: dict[str, Any],
        options: dict[str, Any] | None = None,
        entry_id: str = "entry",
    ) -> None:
        self.data = data
        self.options = options or {}
        self.entry_id = entry_id


class FakeResponse:
    """Async context manager returning a static payload."""

    def __init__(
        self,
        payload: dict[str, Any],
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self.status = status
        self.headers: dict[str, str] = headers or {}

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

    def __init__(self, payload: dict[str, Any], *, status: int = 200) -> None:
        self._payload = payload
        self._status = status

    def get(self, *_args, **_kwargs) -> FakeResponse:
        return FakeResponse(self._payload, status=self._status)


class ResponseSpec(NamedTuple):
    """Describe a fake HTTP response to return from the coordinator session."""

    status: int
    payload: dict[str, Any]
    headers: dict[str, str] | None = None


class SequenceSession:
    """Session that returns a sequence of responses or raises exceptions."""

    def __init__(self, sequence: list[ResponseSpec | Exception]):
        self.sequence = sequence
        self.calls = 0

    def get(self, *_args, **_kwargs):
        if self.calls >= len(self.sequence):
            raise AssertionError(
                "SequenceSession exhausted; no more responses "
                f"(calls={self.calls}, sequence_len={len(self.sequence)})."
            )
        item = self.sequence[self.calls]
        self.calls += 1

        if isinstance(item, Exception):
            raise item

        return FakeResponse(
            item.payload, status=item.status, headers=item.headers or {}
        )


class RegistryEntry:
    """Simple stub representing an Entity Registry entry."""

    def __init__(self, unique_id: str, entity_id: str) -> None:
        self.unique_id = unique_id
        self.entity_id = entity_id
        self.domain = "sensor"
        self.platform = sensor.DOMAIN


class RegistryStub:
    """Minimal async Entity Registry stub capturing removals."""

    def __init__(self, entries: list[RegistryEntry]) -> None:
        self.entries = entries
        self.removals: list[str] = []

    async def async_remove(self, entity_id: str) -> None:
        self.removals.append(entity_id)


def _setup_registry_stub(
    monkeypatch: pytest.MonkeyPatch,
    entries: list[RegistryEntry],
    *,
    entry_id: str,
) -> RegistryStub:
    registry = RegistryStub(entries)

    monkeypatch.setattr(sensor.er, "async_get", lambda _hass: registry)
    monkeypatch.setattr(
        sensor.er,
        "async_entries_for_config_entry",
        lambda reg, eid: entries if reg is registry and eid == entry_id else [],
    )

    return registry


def test_type_sensor_preserves_source_with_single_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single-day payload keeps the type sensor source and exposes no forecast."""

    payload = {
        "regionCode": "us_ca_san_francisco",
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 5, "day": 9},
                "pollenTypeInfo": [
                    {
                        "code": "GRASS",
                        "displayName": "Grass",
                        "inSeason": True,
                        "healthRecommendations": ["Limit outdoor activity"],
                        "indexInfo": {
                            "value": 2,
                            "category": "LOW",
                            "indexDescription": "Low",
                            "color": {"red": 30, "green": 160, "blue": 40},
                        },
                    }
                ],
            }
        ],
    }

    fake_session = FakeSession(payload)
    monkeypatch.setattr(sensor, "async_get_clientsession", lambda _hass: fake_session)

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = sensor.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="test",
        lat=1.0,
        lon=2.0,
        hours=12,
        language=None,
        entry_id="entry",
        forecast_days=1,
        create_d1=False,
        create_d2=False,
    )

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    entry = data["type_grass"]

    assert entry["source"] == "type"
    assert entry["displayName"] == "Grass"
    assert entry["forecast"] == []
    assert entry["tomorrow_has_index"] is False
    assert entry["tomorrow_value"] is None


def test_type_sensor_uses_forecast_metadata_when_today_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When today lacks a type entry, use forecast metadata and keep type source."""

    payload = {
        "regionCode": "us_tx_austin",
        "dailyInfo": [
            {  # Today has no type index
                "date": {"year": 2025, "month": 5, "day": 9},
                "pollenTypeInfo": [],
            },
            {
                "date": {"year": 2025, "month": 5, "day": 10},
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
                            "color": {"red": 120, "green": 200, "blue": 90},
                        },
                    }
                ],
            },
            {
                "date": {"year": 2025, "month": 5, "day": 11},
                "pollenTypeInfo": [
                    {
                        "code": "GRASS",
                        "displayName": "Grass Pollen",
                        "inSeason": True,
                        "healthRecommendations": ["Expect improvement"],
                        "indexInfo": {
                            "value": 1,
                            "category": "LOW",
                            "indexDescription": "Low",
                            "color": {"red": 40, "green": 180, "blue": 60},
                        },
                    }
                ],
            },
        ],
    }

    fake_session = FakeSession(payload)
    monkeypatch.setattr(sensor, "async_get_clientsession", lambda _hass: fake_session)

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = sensor.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="test",
        lat=1.0,
        lon=2.0,
        hours=12,
        language=None,
        entry_id="entry",
        forecast_days=5,
        create_d1=False,
        create_d2=False,
    )

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    entry = data["type_grass"]

    assert entry["source"] == "type"
    assert entry["displayName"] == "Grass Pollen"
    assert entry["value"] is None
    assert entry["category"] is None
    assert entry["description"] is None
    assert entry["advice"] == ["Carry medication"]
    assert entry["forecast"][0]["offset"] == 1
    assert entry["forecast"][0]["has_index"] is True
    assert entry["tomorrow_value"] == 3
    assert entry["tomorrow_category"] == "MODERATE"
    assert entry["trend"] is None
    assert entry["expected_peak"]["offset"] == 1


def test_plant_sensor_includes_forecast_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plant sensors expose forecast attributes and derived convenience fields."""

    payload = {
        "regionCode": "us_co_denver",
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 6, "day": 1},
                "plantInfo": [
                    {
                        "code": "ragweed",
                        "displayName": "Ragweed",
                        "inSeason": True,
                        "healthRecommendations": ["Limit outdoor exposure"],
                        "indexInfo": {
                            "value": 2,
                            "category": "LOW",
                            "indexDescription": "Low",
                            "color": {"red": 80, "green": 170, "blue": 60},
                        },
                        "plantDescription": {
                            "type": "weed",
                            "family": "Asteraceae",
                            "season": "Fall",
                            "crossReaction": ["Sunflower"],
                            "picture": "https://example.com/ragweed.jpg",
                            "pictureCloseup": "https://example.com/ragweed-close.jpg",
                        },
                    }
                ],
            },
            {
                "date": {"year": 2025, "month": 6, "day": 2},
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
                "date": {"year": 2025, "month": 6, "day": 3},
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

    fake_session = FakeSession(payload)
    monkeypatch.setattr(sensor, "async_get_clientsession", lambda _hass: fake_session)

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = sensor.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="test",
        lat=1.0,
        lon=2.0,
        hours=12,
        language=None,
        entry_id="entry",
        forecast_days=5,
        create_d1=False,
        create_d2=False,
    )

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    entry = data["plants_ragweed"]

    assert entry["source"] == "plant"
    assert entry["value"] == 2
    assert len(entry["forecast"]) == 2
    assert entry["forecast"][0]["offset"] == 1
    assert entry["forecast"][0]["value"] == 4
    assert entry["forecast"][0]["has_index"] is True
    assert entry["tomorrow_has_index"] is True
    assert entry["tomorrow_value"] == 4
    assert entry["tomorrow_category"] == "HIGH"
    assert entry["tomorrow_description"] == "High"
    assert entry["tomorrow_color_hex"] == entry["forecast"][0]["color_hex"]
    assert entry["d2_has_index"] is True
    assert entry["d2_value"] == 1
    assert entry["trend"] == "up"
    assert entry["expected_peak"]["offset"] == 1
    assert entry["expected_peak"]["value"] == 4


def test_cleanup_per_day_entities_removes_disabled_d1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D+1 entries are awaited and removed when the option is disabled."""

    entries = [
        RegistryEntry("entry_type_grass", "sensor.pollen_type_grass"),
        RegistryEntry("entry_type_grass_d1", "sensor.pollen_type_grass_d1"),
        RegistryEntry("entry_type_grass_d2", "sensor.pollen_type_grass_d2"),
    ]
    registry = _setup_registry_stub(monkeypatch, entries, entry_id="entry")

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    try:
        removed = loop.run_until_complete(
            sensor._cleanup_per_day_entities(
                hass, "entry", allow_d1=False, allow_d2=True
            )
        )
    finally:
        loop.close()

    assert removed == 1
    assert registry.removals == ["sensor.pollen_type_grass_d1"]


def test_cleanup_per_day_entities_removes_disabled_d2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D+2 entries are awaited and removed when the option is disabled."""

    entries = [
        RegistryEntry("entry_type_grass", "sensor.pollen_type_grass"),
        RegistryEntry("entry_type_grass_d1", "sensor.pollen_type_grass_d1"),
        RegistryEntry("entry_type_grass_d2", "sensor.pollen_type_grass_d2"),
    ]
    registry = _setup_registry_stub(monkeypatch, entries, entry_id="entry")

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    try:
        removed = loop.run_until_complete(
            sensor._cleanup_per_day_entities(
                hass, "entry", allow_d1=True, allow_d2=False
            )
        )
    finally:
        loop.close()

    assert removed == 1
    assert registry.removals == ["sensor.pollen_type_grass_d2"]


def test_coordinator_raises_auth_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 403 response triggers ConfigEntryAuthFailed for re-auth flows."""

    fake_session = FakeSession({}, status=403)
    monkeypatch.setattr(sensor, "async_get_clientsession", lambda _hass: fake_session)

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = sensor.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="bad",
        lat=1.0,
        lon=2.0,
        hours=12,
        language=None,
        entry_id="entry",
        forecast_days=1,
        create_d1=False,
        create_d2=False,
    )

    try:
        with pytest.raises(sensor.ConfigEntryAuthFailed):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()


def test_coordinator_retries_then_raises_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """429 responses are retried once then raise UpdateFailed with quota message."""

    session = SequenceSession(
        [
            ResponseSpec(status=429, payload={}, headers={"Retry-After": "3"}),
            ResponseSpec(status=429, payload={}, headers={"Retry-After": "3"}),
        ]
    )
    delays: list[float] = []

    async def _fast_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(sensor.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(sensor.random, "uniform", lambda *_args, **_kwargs: 0.0)
    monkeypatch.setattr(sensor, "async_get_clientsession", lambda _hass: session)

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = sensor.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="test",
        lat=1.0,
        lon=2.0,
        hours=12,
        language=None,
        entry_id="entry",
        forecast_days=1,
        create_d1=False,
        create_d2=False,
    )

    try:
        with pytest.raises(sensor.UpdateFailed, match="Quota exceeded"):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert session.calls == 2
    assert delays == [3.0]


def test_coordinator_retries_then_raises_on_server_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5xx responses retry once before raising UpdateFailed with status."""

    session = SequenceSession(
        [ResponseSpec(status=500, payload={}), ResponseSpec(status=502, payload={})]
    )
    delays: list[float] = []

    async def _fast_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(sensor.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(sensor.random, "uniform", lambda *_args, **_kwargs: 0.0)
    monkeypatch.setattr(sensor, "async_get_clientsession", lambda _hass: session)

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = sensor.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="test",
        lat=1.0,
        lon=2.0,
        hours=12,
        language=None,
        entry_id="entry",
        forecast_days=1,
        create_d1=False,
        create_d2=False,
    )

    try:
        with pytest.raises(sensor.UpdateFailed, match="HTTP 502"):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert session.calls == 2
    assert delays == [0.8]


def test_coordinator_retries_then_wraps_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout errors retry once then surface as UpdateFailed with context."""

    session = SequenceSession([TimeoutError("boom"), TimeoutError("boom")])
    delays: list[float] = []

    async def _fast_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(sensor.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(sensor.random, "uniform", lambda *_args, **_kwargs: 0.0)
    monkeypatch.setattr(sensor, "async_get_clientsession", lambda _hass: session)

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = sensor.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="test",
        lat=1.0,
        lon=2.0,
        hours=12,
        language=None,
        entry_id="entry",
        forecast_days=1,
        create_d1=False,
        create_d2=False,
    )

    try:
        with pytest.raises(sensor.UpdateFailed, match="Timeout"):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert session.calls == 2
    assert delays == [0.8]


def test_coordinator_retries_then_wraps_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client errors retry once then raise UpdateFailed with redacted message."""

    session = SequenceSession(
        [sensor.aiohttp.ClientError("net down"), sensor.aiohttp.ClientError("net down")]
    )
    delays: list[float] = []

    async def _fast_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(sensor.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(sensor.random, "uniform", lambda *_args, **_kwargs: 0.0)
    monkeypatch.setattr(sensor, "async_get_clientsession", lambda _hass: session)

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = sensor.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="secret",
        lat=1.0,
        lon=2.0,
        hours=12,
        language=None,
        entry_id="entry",
        forecast_days=1,
        create_d1=False,
        create_d2=False,
    )

    try:
        with pytest.raises(sensor.UpdateFailed, match="net down"):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert session.calls == 2
    assert delays == [0.8]


def test_async_setup_entry_missing_api_key_triggers_reauth() -> None:
    """A missing API key results in ConfigEntryAuthFailed during setup."""

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    config_entry = FakeConfigEntry(
        data={
            sensor.CONF_LATITUDE: 1.0,
            sensor.CONF_LONGITUDE: 2.0,
            sensor.CONF_UPDATE_INTERVAL: sensor.DEFAULT_UPDATE_INTERVAL,
            sensor.CONF_FORECAST_DAYS: sensor.DEFAULT_FORECAST_DAYS,
        }
    )

    async def _noop_add_entities(_entities, _update_before_add=False):
        return None

    try:
        with pytest.raises(sensor.ConfigEntryAuthFailed):
            loop.run_until_complete(
                sensor.async_setup_entry(hass, config_entry, _noop_add_entities)
            )
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_device_info_uses_default_title_when_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whitespace titles fall back to the default in translation placeholders."""

    async def _stub_first_refresh(self):  # type: ignore[override]
        self.data = {"date": {"source": "meta"}, "region": {"source": "meta"}}

    monkeypatch.setattr(
        sensor.PollenDataUpdateCoordinator,
        "async_config_entry_first_refresh",
        _stub_first_refresh,
    )
    monkeypatch.setattr(sensor, "async_get_clientsession", lambda _hass: None)

    hass = DummyHass(asyncio.get_running_loop())
    config_entry = FakeConfigEntry(
        data={
            sensor.CONF_API_KEY: "key",
            sensor.CONF_LATITUDE: 1.0,
            sensor.CONF_LONGITUDE: 2.0,
            sensor.CONF_UPDATE_INTERVAL: sensor.DEFAULT_UPDATE_INTERVAL,
            sensor.CONF_FORECAST_DAYS: sensor.DEFAULT_FORECAST_DAYS,
        },
        entry_id="entry",
    )
    config_entry.title = "   "

    captured: list[Any] = []

    def _capture_entities(entities, _update_before_add=False):
        captured.extend(entities)

    await sensor.async_setup_entry(hass, config_entry, _capture_entities)

    region_sensor = next(
        entity for entity in captured if isinstance(entity, sensor.RegionSensor)
    )

    placeholders = region_sensor.device_info["translation_placeholders"]
    assert placeholders["title"] == sensor.DEFAULT_ENTRY_TITLE


@pytest.mark.asyncio
async def test_device_info_trims_custom_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom titles are trimmed before reaching translation placeholders."""

    async def _stub_first_refresh(self):  # type: ignore[override]
        self.data = {"date": {"source": "meta"}, "region": {"source": "meta"}}

    monkeypatch.setattr(
        sensor.PollenDataUpdateCoordinator,
        "async_config_entry_first_refresh",
        _stub_first_refresh,
    )
    monkeypatch.setattr(sensor, "async_get_clientsession", lambda _hass: None)

    hass = DummyHass(asyncio.get_running_loop())
    config_entry = FakeConfigEntry(
        data={
            sensor.CONF_API_KEY: "key",
            sensor.CONF_LATITUDE: 1.0,
            sensor.CONF_LONGITUDE: 2.0,
            sensor.CONF_UPDATE_INTERVAL: sensor.DEFAULT_UPDATE_INTERVAL,
            sensor.CONF_FORECAST_DAYS: sensor.DEFAULT_FORECAST_DAYS,
        },
        entry_id="entry",
    )
    config_entry.title = "  My Location  "

    captured: list[Any] = []

    def _capture_entities(entities, _update_before_add=False):
        captured.extend(entities)

    await sensor.async_setup_entry(hass, config_entry, _capture_entities)

    region_sensor = next(
        entity for entity in captured if isinstance(entity, sensor.RegionSensor)
    )

    placeholders = region_sensor.device_info["translation_placeholders"]
    assert placeholders["title"] == "My Location"
