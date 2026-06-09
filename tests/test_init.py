"""Tests for integration setup exception handling."""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests._ha_stubs import (
    clear_integration_modules,
    stub_aiohttp_module,
    stub_config_entry_class,
    stub_custom_components_packages,
    stub_exceptions,
    stub_homeassistant_package,
    stub_issue_registry_module,
    stub_update_coordinator_module,
    stub_util_dt_module,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class _InitModules:
    integration: types.ModuleType
    const: types.ModuleType
    base_data_update_coordinator: type[_StubDataUpdateCoordinator]


class _StubConfigEntry:
    @classmethod
    def __class_getitem__(cls, _item):
        return cls


class _StubConfigSubentry:
    _next_id = 1

    def __init__(
        self,
        *,
        data=None,
        subentry_type="location",
        title="Location",
        unique_id=None,
        subentry_id=None,
    ):
        if subentry_id is None:
            subentry_id = f"subentry-{self.__class__._next_id}"
            self.__class__._next_id += 1
        self.data = data or {}
        self.subentry_type = subentry_type
        self.title = title
        self.unique_id = unique_id
        self.subentry_id = subentry_id


class _StubHomeAssistant:  # pragma: no cover - structure only
    pass


class _StubServiceCall:  # pragma: no cover - structure only
    pass


class _StubSensorEntity:  # pragma: no cover - structure only
    def __init__(self, *args, **kwargs):
        self._attr_unique_id = None
        self._attr_device_info = None

    @property
    def unique_id(self):
        return getattr(self, "_attr_unique_id", None)

    @property
    def device_info(self):
        return getattr(self, "_attr_device_info", None)


class _StubSensorDeviceClass:  # pragma: no cover - structure only
    DATE = "date"
    TIMESTAMP = "timestamp"


class _StubSensorStateClass:  # pragma: no cover - structure only
    MEASUREMENT = "measurement"


class _StubEntityCategory:
    DIAGNOSTIC = "diagnostic"


class _StubConfigEntryNotReady(Exception):
    pass


class _StubConfigEntryAuthFailed(Exception):
    pass


class _StubUpdateFailed(Exception):
    pass


class _StubCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator


class _StubDataUpdateCoordinator:
    def __init__(self, hass, logger, *, name: str, update_interval):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data = {"date": {}, "region": {}}
        self.last_updated = None

    async def async_config_entry_first_refresh(self):
        self.last_updated = "now"
        return None

    async def async_refresh(self):
        return None

    def async_request_refresh(self):  # pragma: no cover - scheduling helper
        return asyncio.create_task(self.async_refresh())


def _stub_async_get(_hass):  # pragma: no cover - structure only
    class _Registry:
        @staticmethod
        def async_entries_for_config_entry(_registry, _entry_id):
            return []

    return _Registry()


@pytest.fixture
def stub_init_ha_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install only the Home Assistant stubs needed by ``__init__`` imports."""
    clear_integration_modules(monkeypatch=monkeypatch)
    stub_custom_components_packages(root=ROOT, monkeypatch=monkeypatch)
    stub_homeassistant_package(monkeypatch=monkeypatch)
    stub_config_entry_class(_StubConfigEntry, monkeypatch=monkeypatch)
    config_entries_mod = sys.modules["homeassistant.config_entries"]
    config_entries_mod.ConfigSubentry = _StubConfigSubentry
    core_mod = types.ModuleType("homeassistant.core")
    core_mod.HomeAssistant = _StubHomeAssistant
    core_mod.ServiceCall = _StubServiceCall
    monkeypatch.setitem(sys.modules, "homeassistant.core", core_mod)

    ha_components_mod = types.ModuleType("homeassistant.components")
    monkeypatch.setitem(sys.modules, "homeassistant.components", ha_components_mod)

    sensor_mod = types.ModuleType("homeassistant.components.sensor")
    sensor_mod.SensorEntity = _StubSensorEntity
    sensor_mod.SensorDeviceClass = _StubSensorDeviceClass
    sensor_mod.SensorStateClass = _StubSensorStateClass
    monkeypatch.setitem(sys.modules, "homeassistant.components.sensor", sensor_mod)

    const_mod = types.ModuleType("homeassistant.const")
    const_mod.ATTR_ATTRIBUTION = "Attribution"
    monkeypatch.setitem(sys.modules, "homeassistant.const", const_mod)

    aiohttp_client_mod = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client_mod.async_get_clientsession = lambda _hass: None
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.aiohttp_client", aiohttp_client_mod
    )
    stub_aiohttp_module(monkeypatch=monkeypatch)

    cv_mod = types.ModuleType("homeassistant.helpers.config_validation")
    cv_mod.config_entry_only_config_schema = lambda _domain: lambda config: config
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.config_validation", cv_mod)

    vol_mod = types.ModuleType("voluptuous")
    monkeypatch.setitem(sys.modules, "voluptuous", vol_mod)
    vol_mod.Schema = lambda *args, **kwargs: None

    helpers_mod = types.ModuleType("homeassistant.helpers")
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers_mod)
    entity_registry_mod = types.ModuleType("homeassistant.helpers.entity_registry")
    entity_registry_mod.async_get = _stub_async_get
    entity_registry_mod.async_entries_for_config_entry = lambda *args, **kwargs: []
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.entity_registry", entity_registry_mod
    )

    entity_mod = types.ModuleType("homeassistant.helpers.entity")
    entity_mod.EntityCategory = _StubEntityCategory
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.entity", entity_mod)
    stub_util_dt_module(monkeypatch=monkeypatch)
    stub_exceptions(
        ConfigEntryNotReady=_StubConfigEntryNotReady,
        ConfigEntryAuthFailed=_StubConfigEntryAuthFailed,
        monkeypatch=monkeypatch,
    )
    stub_update_coordinator_module(
        update_failed=_StubUpdateFailed,
        data_update_coordinator=_StubDataUpdateCoordinator,
        coordinator_entity=_StubCoordinatorEntity,
        monkeypatch=monkeypatch,
    )
    stub_issue_registry_module(monkeypatch=monkeypatch)


@pytest.fixture
def integration_modules(
    monkeypatch: pytest.MonkeyPatch, stub_init_ha_modules: None
) -> _InitModules:
    """Import integration modules only after stubs are installed."""
    # Remove the package stub installed by stub_custom_components_packages so
    # importing custom_components.pollenlevels executes the real __init__.py.
    clear_integration_modules(monkeypatch=monkeypatch)
    const = importlib.import_module("custom_components.pollenlevels.const")
    integration = importlib.import_module("custom_components.pollenlevels")
    return _InitModules(
        integration=integration,
        const=const,
        base_data_update_coordinator=_StubDataUpdateCoordinator,
    )


class _FakeConfigEntries:
    def __init__(
        self,
        forward_exception: Exception | None = None,
        unload_result: bool = True,
        entries: list[object] | None = None,
    ):
        self._forward_exception = forward_exception
        self._unload_result = unload_result
        self.forward_calls: list[tuple[object, list[str]]] = []
        self.unload_calls: list[tuple[object, list[str]]] = []
        self.reload_calls: list[str] = []
        self.added_subentries: list[tuple[object, object]] = []
        self.removed_entries: list[str] = []
        self._entries = entries or []

    async def async_forward_entry_setups(self, entry, platforms):
        self.forward_calls.append((entry, platforms))
        if self._forward_exception is not None:
            raise self._forward_exception

    async def async_unload_platforms(self, entry, platforms):
        self.unload_calls.append((entry, platforms))
        return self._unload_result

    def async_update_entry(self, entry, **kwargs):
        if "data" in kwargs:
            entry.data = kwargs["data"]
        if "options" in kwargs:
            entry.options = kwargs["options"]
        if "version" in kwargs:
            entry.version = kwargs["version"]
        if "unique_id" in kwargs:
            entry.unique_id = kwargs["unique_id"]

    def async_add_subentry(self, entry, subentry):
        self.added_subentries.append((entry, subentry))
        subentries = dict(getattr(entry, "subentries", {}) or {})
        subentries[subentry.subentry_id] = subentry
        entry.subentries = subentries

    async def async_remove(self, entry_id: str):
        self.removed_entries.append(entry_id)
        self._entries = [
            entry
            for entry in self._entries
            if getattr(entry, "entry_id", None) != entry_id
        ]
        return {"require_restart": False}

    async def async_reload(self, entry_id: str):  # pragma: no cover - used in tests
        self.reload_calls.append(entry_id)

    def async_get_entry(self, entry_id: str):
        return next(
            (
                entry
                for entry in self._entries
                if getattr(entry, "entry_id", None) == entry_id
            ),
            None,
        )

    def async_entries(self, domain: str | None = None):
        if domain is None:
            return list(self._entries)
        return [
            entry for entry in self._entries if getattr(entry, "domain", None) == domain
        ]


class _FakeEntry:
    def __init__(
        self,
        integration: types.ModuleType,
        *,
        entry_id: str = "entry-1",
        title: str = "Pollen Levels",
        data: dict | None = None,
        options: dict | None = None,
        version: int = 1,
        subentries: dict | None = None,
        unique_id: str | None = None,
    ):
        self.entry_id = entry_id
        self.title = title
        self.domain = integration.DOMAIN
        self.data = data or {
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        }
        self.options = options or {}
        self.version = version
        self.subentries = subentries or {}
        self.unique_id = unique_id
        self.runtime_data = None


def _location_subentries(
    integration: types.ModuleType, *subentry_ids: str
) -> dict[str, Any]:
    """Return active location subentries keyed by subentry id."""
    return {
        subentry_id: integration.ConfigSubentry(
            data={integration.CONF_LATITUDE: 1.0, integration.CONF_LONGITUDE: 2.0},
            subentry_id=subentry_id,
            title=subentry_id,
        )
        for subentry_id in subentry_ids
    }


class _FakeHass:
    def __init__(
        self,
        *,
        forward_exception: Exception | None = None,
        entries: list[object] | None = None,
    ):
        self.config_entries = _FakeConfigEntries(
            forward_exception=forward_exception, unload_result=True, entries=entries
        )
        self.data = {}
        self.services = _ServiceRegistry()
        self.created_tasks = []

    def async_create_task(self, coro, *, name=None):
        task = asyncio.create_task(coro, name=name)
        self.created_tasks.append(task)
        return task


class _ServiceRegistry:
    def __init__(self):
        self.registered: dict[tuple[str, str], Any] = {}
        self.schemas: dict[tuple[str, str], Any] = {}

    def async_register(self, domain: str, service: str, handler, schema=None):
        key = (domain, service)
        self.registered[key] = handler
        self.schemas[key] = schema

    async def async_call(self, domain: str, service: str):
        handler = self.registered[(domain, service)]
        await handler(_StubServiceCall())


def test_setup_entry_propagates_auth_failed(integration_modules: _InitModules) -> None:
    """ConfigEntryAuthFailed should bubble up for reauthentication."""
    integration = integration_modules.integration

    hass = _FakeHass(forward_exception=integration.ConfigEntryAuthFailed("bad key"))
    entry = _FakeEntry(integration)

    with pytest.raises(integration.ConfigEntryAuthFailed):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_clears_runtime_data_on_forward_auth_failed(
    integration_modules: _InitModules,
) -> None:
    """runtime_data is cleared when forwarding raises ConfigEntryAuthFailed."""
    integration = integration_modules.integration

    hass = _FakeHass(forward_exception=integration.ConfigEntryAuthFailed("bad key"))
    entry = _FakeEntry(integration)

    with pytest.raises(integration.ConfigEntryAuthFailed):
        asyncio.run(integration.async_setup_entry(hass, entry))

    assert entry.runtime_data is None


def test_setup_entry_clears_runtime_data_on_forward_not_ready(
    integration_modules: _InitModules,
) -> None:
    """runtime_data is cleared when forwarding raises ConfigEntryNotReady."""
    integration = integration_modules.integration

    hass = _FakeHass(forward_exception=integration.ConfigEntryNotReady("retry"))
    entry = _FakeEntry(integration)

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))

    assert entry.runtime_data is None


def test_setup_entry_clears_runtime_data_on_forward_generic_error(
    integration_modules: _InitModules,
) -> None:
    """runtime_data is cleared when forwarding raises an unexpected exception."""
    integration = integration_modules.integration

    class _Boom(Exception):
        pass

    hass = _FakeHass(forward_exception=_Boom("boom"))
    entry = _FakeEntry(integration)

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))

    assert entry.runtime_data is None


def test_setup_entry_missing_api_key_raises_auth_failed(
    integration_modules: _InitModules,
) -> None:
    """Missing API key should trigger ConfigEntryAuthFailed."""
    integration = integration_modules.integration

    hass = _FakeHass()
    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
    )

    with pytest.raises(integration.ConfigEntryAuthFailed):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_whitespace_api_key_raises_auth_failed(
    integration_modules: _InitModules,
) -> None:
    """Whitespace-only API key should trigger ConfigEntryAuthFailed."""
    integration = integration_modules.integration

    hass = _FakeHass()
    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "   ",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
    )

    with pytest.raises(integration.ConfigEntryAuthFailed):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_without_location_subentries_loads_empty_runtime(
    integration_modules: _InitModules,
) -> None:
    """A parent entry with no locations should load and forward platforms."""
    integration = integration_modules.integration

    hass = _FakeHass()
    entry = _FakeEntry(
        integration,
        data={integration.CONF_API_KEY: "key"},
        subentries={},
    )

    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True

    assert entry.runtime_data is not None
    assert entry.runtime_data.locations == {}
    assert entry.runtime_data.coordinator is None
    assert hass.config_entries.forward_calls == [(entry, ["sensor", "button"])]


def test_setup_entry_debug_log_does_not_include_entry_title(
    integration_modules: _InitModules, caplog
) -> None:
    """async_setup_entry debug log should include entry_id but not entry.title."""
    integration = integration_modules.integration

    hass = _FakeHass()
    entry = _FakeEntry(
        integration,
        entry_id="test-entry",
        title="secret-api-key-abc-123",
        data={integration.CONF_API_KEY: "actual-key"},
        subentries={},
    )

    with caplog.at_level("DEBUG"):
        assert asyncio.run(integration.async_setup_entry(hass, entry)) is True

    log_text = caplog.text
    assert "entry_id=test-entry" in log_text
    assert "secret-api-key-abc-123" not in log_text
    assert "actual-key" not in log_text


def test_setup_entry_invalid_coordinates_raise_not_ready(
    integration_modules: _InitModules,
) -> None:
    """Invalid coordinates should trigger ConfigEntryNotReady."""
    integration = integration_modules.integration

    hass = _FakeHass()
    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: "not-a-number",
            integration.CONF_LONGITUDE: 2.0,
        },
    )

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_invalid_coordinates_do_not_log_precise_values(
    integration_modules: _InitModules, caplog
) -> None:
    """Invalid coordinates should fail without logging precise coordinate values."""
    integration = integration_modules.integration

    hass = _FakeHass()
    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 91.123456,
            integration.CONF_LONGITUDE: 2.654321,
        },
    )

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))

    log_text = caplog.text
    assert "91.123456" not in log_text
    assert "2.654321" not in log_text


def test_setup_entry_nonfinite_or_out_of_range_coordinates_raise_not_ready(
    integration_modules: _InitModules,
) -> None:
    """Non-finite or out-of-range coordinates should trigger ConfigEntryNotReady."""
    integration = integration_modules.integration

    bad_pairs = [
        (float("inf"), 2.0),
        (1.0, float("nan")),
        (91.0, 2.0),
        (1.0, 181.0),
    ]

    for lat, lon in bad_pairs:
        hass = _FakeHass()
        entry = _FakeEntry(
            integration,
            data={
                integration.CONF_API_KEY: "key",
                integration.CONF_LATITUDE: lat,
                integration.CONF_LONGITUDE: lon,
            },
        )

        with pytest.raises(integration.ConfigEntryNotReady):
            asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_boolean_coordinates_raise_not_ready(
    integration_modules: _InitModules,
) -> None:
    """Boolean coordinates should trigger ConfigEntryNotReady."""
    integration = integration_modules.integration

    hass = _FakeHass()
    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: True,
            integration.CONF_LONGITUDE: 2.0,
        },
    )

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_numeric_string_coordinates_are_allowed(
    integration_modules: _InitModules,
) -> None:
    """Numeric string coordinates should still set up normally."""
    integration = integration_modules.integration

    hass = _FakeHass()
    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: "1.5",
            integration.CONF_LONGITUDE: "2.5",
        },
    )

    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True
    assert entry.runtime_data is not None
    assert entry.runtime_data.coordinator.lat == pytest.approx(1.5)
    assert entry.runtime_data.coordinator.lon == pytest.approx(2.5)


def test_setup_entry_boundary_coordinates_are_allowed(
    integration_modules: _InitModules,
) -> None:
    """Coordinate values on valid boundaries should still set up successfully."""
    integration = integration_modules.integration

    for lat, lon in [(-90.0, -180.0), (90.0, 180.0)]:
        hass = _FakeHass()
        entry = _FakeEntry(
            integration,
            data={
                integration.CONF_API_KEY: "key",
                integration.CONF_LATITUDE: lat,
                integration.CONF_LONGITUDE: lon,
            },
        )

        assert asyncio.run(integration.async_setup_entry(hass, entry)) is True


def test_setup_entry_raises_not_ready_when_one_subentry_fails(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A local refresh failure should retry the whole parent entry."""
    integration = integration_modules.integration

    bad_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LATITUDE: 3.123456,
            integration.CONF_LONGITUDE: -4.654321,
        },
        subentry_id="bad-location",
        title="Bad",
    )
    good_subentry = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 1.0, integration.CONF_LONGITUDE: 2.0},
        subentry_id="good-location",
        title="Good",
    )
    entry = _FakeEntry(
        integration,
        data={integration.CONF_API_KEY: "secret-key"},
        subentries={
            bad_subentry.subentry_id: bad_subentry,
            good_subentry.subentry_id: good_subentry,
        },
    )
    hass = _FakeHass()

    class _StubCoordinator:
        def __init__(self, *args, **kwargs):
            self.api_key = kwargs["api_key"]
            self.lat = kwargs["lat"]
            self.lon = kwargs["lon"]
            self.subentry_id = kwargs["subentry_id"]
            self.legacy_entry_id = kwargs.get("legacy_entry_id")
            self.data = {"region": {"source": "meta"}, "date": {"source": "meta"}}

        async def async_config_entry_first_refresh(self):
            if self.subentry_id == "bad-location":
                raise RuntimeError(
                    "boom secret-key at 3.123456,-4.654321 "
                    "location.latitude=3.123456"
                )
            return None

    monkeypatch.setattr(integration, "PollenDataUpdateCoordinator", _StubCoordinator)

    with caplog.at_level("WARNING", logger=integration.__name__):
        with pytest.raises(integration.ConfigEntryNotReady) as exc_info:
            asyncio.run(integration.async_setup_entry(hass, entry))

    assert exc_info.value.__cause__ is None
    assert entry.runtime_data is None
    assert hass.config_entries.forward_calls == []
    log_text = caplog.text
    assert "Initial data refresh failed for entry entry-1 subentry bad-location" in (
        log_text
    )
    assert "secret-key" not in log_text
    assert "3.123456" not in log_text
    assert "-4.654321" not in log_text


def test_setup_entry_raises_not_ready_when_subentry_coordinates_are_invalid(
    integration_modules: _InitModules,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid subentry coordinates should retry without partial runtime data."""
    integration = integration_modules.integration

    bad_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LATITUDE: 91.123456,
            integration.CONF_LONGITUDE: 2.654321,
        },
        subentry_id="bad-location",
        title="Bad",
    )
    good_subentry = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 1.0, integration.CONF_LONGITUDE: 2.0},
        subentry_id="good-location",
        title="Good",
    )
    entry = _FakeEntry(
        integration,
        data={integration.CONF_API_KEY: "secret-key"},
        subentries={
            good_subentry.subentry_id: good_subentry,
            bad_subentry.subentry_id: bad_subentry,
        },
    )
    hass = _FakeHass()

    with caplog.at_level("WARNING", logger=integration.__name__):
        with pytest.raises(integration.ConfigEntryNotReady) as exc_info:
            asyncio.run(integration.async_setup_entry(hass, entry))

    assert exc_info.value.__cause__ is None
    assert entry.runtime_data is None
    assert hass.config_entries.forward_calls == []
    log_text = caplog.text
    assert (
        "Invalid coordinates for Pollen Levels entry entry-1 subentry bad-location"
        in (log_text)
    )
    assert "secret-key" not in log_text
    assert "91.123456" not in log_text
    assert "2.654321" not in log_text


def test_setup_entry_raises_not_ready_when_later_subentry_is_not_ready(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later not-ready location should discard earlier successful setup work."""
    integration = integration_modules.integration

    first = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 1.0, integration.CONF_LONGITUDE: 2.0},
        subentry_id="first-location",
    )
    second = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 3.0, integration.CONF_LONGITUDE: 4.0},
        subentry_id="second-location",
    )
    entry = _FakeEntry(
        integration,
        data={integration.CONF_API_KEY: "key"},
        subentries={first.subentry_id: first, second.subentry_id: second},
    )
    hass = _FakeHass()
    refreshed: list[str] = []

    class _PartiallyReadyCoordinator:
        def __init__(self, *args, **kwargs):
            self.subentry_id = kwargs["subentry_id"]

        async def async_config_entry_first_refresh(self):
            refreshed.append(self.subentry_id)
            if self.subentry_id == "second-location":
                raise integration.ConfigEntryNotReady("retry later")

    monkeypatch.setattr(
        integration, "PollenDataUpdateCoordinator", _PartiallyReadyCoordinator
    )

    with pytest.raises(integration.ConfigEntryNotReady) as exc_info:
        asyncio.run(integration.async_setup_entry(hass, entry))

    assert exc_info.value.__cause__ is None
    assert refreshed == ["first-location", "second-location"]
    assert entry.runtime_data is None
    assert hass.config_entries.forward_calls == []


def test_setup_entry_raises_not_ready_when_all_subentries_fail(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parent should retry when no configured location can initialize."""
    integration = integration_modules.integration

    first = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 1.0, integration.CONF_LONGITUDE: 2.0},
        subentry_id="first-location",
    )
    second = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 3.0, integration.CONF_LONGITUDE: 4.0},
        subentry_id="second-location",
    )
    entry = _FakeEntry(
        integration,
        data={integration.CONF_API_KEY: "key"},
        subentries={first.subentry_id: first, second.subentry_id: second},
    )
    hass = _FakeHass()

    class _FailingCoordinator:
        def __init__(self, *args, **kwargs):
            self.lat = kwargs["lat"]
            self.lon = kwargs["lon"]

        async def async_config_entry_first_refresh(self):
            raise RuntimeError("service unavailable")

    monkeypatch.setattr(integration, "PollenDataUpdateCoordinator", _FailingCoordinator)

    with pytest.raises(integration.ConfigEntryNotReady) as exc_info:
        asyncio.run(integration.async_setup_entry(hass, entry))

    assert exc_info.value.__cause__ is None
    assert entry.runtime_data is None
    assert hass.config_entries.forward_calls == []


def test_setup_entry_auth_failure_still_fails_parent(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared credential failures should keep failing the whole parent entry."""
    integration = integration_modules.integration

    first = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 1.0, integration.CONF_LONGITUDE: 2.0},
        subentry_id="first-location",
    )
    second = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 3.0, integration.CONF_LONGITUDE: 4.0},
        subentry_id="second-location",
    )
    entry = _FakeEntry(
        integration,
        data={integration.CONF_API_KEY: "bad-key"},
        subentries={first.subentry_id: first, second.subentry_id: second},
    )
    hass = _FakeHass()

    class _AuthFailingCoordinator:
        def __init__(self, *args, **kwargs):
            self.lat = kwargs["lat"]
            self.lon = kwargs["lon"]

        async def async_config_entry_first_refresh(self):
            raise integration.ConfigEntryAuthFailed("invalid key")

    monkeypatch.setattr(
        integration, "PollenDataUpdateCoordinator", _AuthFailingCoordinator
    )

    with pytest.raises(integration.ConfigEntryAuthFailed):
        asyncio.run(integration.async_setup_entry(hass, entry))

    assert entry.runtime_data is None
    assert hass.config_entries.forward_calls == []


def test_setup_entry_decimal_numeric_options_fallback_to_defaults(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decimal options should not be truncated silently during setup."""
    integration = integration_modules.integration
    base_data_update_coordinator = integration_modules.base_data_update_coordinator

    hass = _FakeHass()
    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        options={
            integration.CONF_UPDATE_INTERVAL: 2.5,
            integration.CONF_FORECAST_DAYS: 3.1,
        },
    )

    seen: dict[str, int] = {}

    class _StubCoordinator(base_data_update_coordinator):
        def __init__(self, *args, **kwargs):
            seen["hours"] = kwargs["hours"]
            seen["forecast_days"] = kwargs["forecast_days"]
            self.data = {"region": {"source": "meta"}, "date": {"source": "meta"}}

        async def async_config_entry_first_refresh(self):
            return None

    monkeypatch.setattr(integration, "PollenDataUpdateCoordinator", _StubCoordinator)

    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True
    assert seen["hours"] == integration.DEFAULT_UPDATE_INTERVAL
    assert seen["forecast_days"] == integration.DEFAULT_FORECAST_DAYS


def test_setup_entry_wraps_generic_error(integration_modules: _InitModules) -> None:
    """Unexpected errors convert to ConfigEntryNotReady for retries."""
    integration = integration_modules.integration

    class _Boom(Exception):
        pass

    hass = _FakeHass(forward_exception=_Boom("boom"))
    entry = _FakeEntry(integration)

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_success_and_unload(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path should forward setup and unload cleanly."""
    integration = integration_modules.integration
    base_data_update_coordinator = integration_modules.base_data_update_coordinator

    hass = _FakeHass()
    entry = _FakeEntry(integration)

    class _StubClient:
        def __init__(self, _session, _api_key):
            self.session = _session
            self.api_key = _api_key

        async def async_fetch_pollen_data(self, **_kwargs):
            return {"region": {"source": "meta"}, "dailyInfo": []}

    class _StubCoordinator(base_data_update_coordinator):
        def __init__(self, *args, **kwargs):
            self.api_key = kwargs["api_key"]
            self.lat = kwargs["lat"]
            self.lon = kwargs["lon"]
            self.forecast_days = kwargs["forecast_days"]
            self.language = kwargs["language"]
            self.create_d1 = kwargs["create_d1"]
            self.create_d2 = kwargs["create_d2"]
            self.entry_id = kwargs["entry_id"]
            self.entry_title = kwargs.get("entry_title")
            self.last_updated = None
            self.data = {"region": {"source": "meta"}, "date": {"source": "meta"}}

        async def async_config_entry_first_refresh(self):
            return None

        async def async_refresh(self):
            return None

    monkeypatch.setattr(integration, "GooglePollenApiClient", _StubClient)
    monkeypatch.setattr(integration, "PollenDataUpdateCoordinator", _StubCoordinator)

    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True

    assert hass.config_entries.forward_calls == [(entry, ["sensor", "button"])]

    assert entry.runtime_data is not None
    assert entry.runtime_data.coordinator.entry_id == entry.entry_id

    assert asyncio.run(integration.async_unload_entry(hass, entry)) is True
    assert hass.config_entries.unload_calls == [(entry, ["sensor", "button"])]
    assert entry.runtime_data is None


def test_setup_entry_normalizes_forecast_sensor_mode(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should normalize stored forecast mode values before coordinator flags."""
    integration = integration_modules.integration
    base_data_update_coordinator = integration_modules.base_data_update_coordinator

    hass = _FakeHass()
    entry = _FakeEntry(
        integration, options={integration.CONF_CREATE_FORECAST_SENSORS: " D+1 "}
    )

    class _StubClient:
        def __init__(self, _session, _api_key):
            self.session = _session
            self.api_key = _api_key

        async def async_fetch_pollen_data(self, **_kwargs):
            return {"region": {"source": "meta"}, "dailyInfo": []}

    class _StubCoordinator(base_data_update_coordinator):
        def __init__(self, *args, **kwargs):
            self.create_d1 = kwargs["create_d1"]
            self.create_d2 = kwargs["create_d2"]
            self.entry_id = kwargs["entry_id"]
            self.entry_title = kwargs.get("entry_title")
            self.lat = kwargs["lat"]
            self.lon = kwargs["lon"]
            self.last_updated = None
            self.data = {"region": {"source": "meta"}, "date": {"source": "meta"}}

        async def async_config_entry_first_refresh(self):
            return None

    monkeypatch.setattr(integration, "GooglePollenApiClient", _StubClient)
    monkeypatch.setattr(integration, "PollenDataUpdateCoordinator", _StubCoordinator)

    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True
    assert entry.runtime_data is not None
    assert entry.runtime_data.coordinator.create_d1 is True
    assert entry.runtime_data.coordinator.create_d2 is False


def test_setup_entry_disables_d1_when_forecast_days_is_one(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should disable D+1/D+2 creation when forecast days disallow them."""
    integration = integration_modules.integration
    base_data_update_coordinator = integration_modules.base_data_update_coordinator

    hass = _FakeHass()
    entry = _FakeEntry(
        integration,
        options={
            integration.CONF_CREATE_FORECAST_SENSORS: "D+1+2",
            integration.CONF_FORECAST_DAYS: 1,
        },
    )

    class _StubClient:
        def __init__(self, _session, _api_key):
            self.session = _session
            self.api_key = _api_key

        async def async_fetch_pollen_data(self, **_kwargs):
            return {"region": {"source": "meta"}, "dailyInfo": []}

    class _StubCoordinator(base_data_update_coordinator):
        def __init__(self, *args, **kwargs):
            self.create_d1 = kwargs["create_d1"]
            self.create_d2 = kwargs["create_d2"]
            self.entry_id = kwargs["entry_id"]
            self.entry_title = kwargs.get("entry_title")
            self.lat = kwargs["lat"]
            self.lon = kwargs["lon"]
            self.last_updated = None
            self.data = {"region": {"source": "meta"}, "date": {"source": "meta"}}

        async def async_config_entry_first_refresh(self):
            return None

    monkeypatch.setattr(integration, "GooglePollenApiClient", _StubClient)
    monkeypatch.setattr(integration, "PollenDataUpdateCoordinator", _StubCoordinator)

    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True
    assert entry.runtime_data is not None
    assert entry.runtime_data.coordinator.create_d1 is False
    assert entry.runtime_data.coordinator.create_d2 is False


def test_force_update_service_is_registered_with_empty_schema(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async_setup should register force_update with an empty schema."""
    integration = integration_modules.integration

    marker = object()

    def _schema(value):
        assert value == {}
        return marker

    monkeypatch.setattr(integration.vol, "Schema", _schema)

    hass = _FakeHass()
    assert asyncio.run(integration.async_setup(hass, {})) is True

    key = (integration.DOMAIN, "force_update")
    assert key in hass.services.registered
    assert hass.services.schemas[key] is marker


def test_force_update_requests_refresh_per_entry(
    integration_modules: _InitModules,
) -> None:
    """force_update should queue refresh via runtime_data coordinators and skip missing runtime data."""
    integration = integration_modules.integration

    class _StubCoordinator:
        def __init__(self):
            self.calls: list[str] = []
            self.done = asyncio.Event()

        async def _mark(self):
            self.calls.append("refresh")
            self.done.set()

        async def async_request_refresh(self):
            await self._mark()

    entry1 = _FakeEntry(integration, entry_id="entry-1")
    entry1.runtime_data = types.SimpleNamespace(coordinator=_StubCoordinator())
    entry2 = _FakeEntry(integration, entry_id="entry-2")
    entry2.runtime_data = types.SimpleNamespace(coordinator=_StubCoordinator())
    entry3 = _FakeEntry(integration, entry_id="entry-3")
    entry3.runtime_data = None
    entry4 = _FakeEntry(integration, entry_id="entry-4")
    entry4.runtime_data = types.SimpleNamespace()

    hass = _FakeHass(entries=[entry1, entry2, entry3, entry4])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    assert (integration.DOMAIN, "force_update") in hass.services.registered

    asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert entry1.runtime_data.coordinator.calls == ["refresh"]
    assert entry2.runtime_data.coordinator.calls == ["refresh"]
    assert entry1.runtime_data.coordinator.done.is_set()
    assert entry2.runtime_data.coordinator.done.is_set()


def test_force_update_continues_after_single_coordinator_failure(
    integration_modules: _InitModules,
) -> None:
    """One coordinator failure should not block refreshes for other entries."""
    integration = integration_modules.integration

    class _OkCoordinator:
        def __init__(self):
            self.calls = 0

        async def async_request_refresh(self):
            self.calls += 1

    class _FailCoordinator:
        async def async_request_refresh(self):
            raise RuntimeError("boom")

    good_entry = _FakeEntry(integration, entry_id="entry-good")
    good_entry.runtime_data = types.SimpleNamespace(coordinator=_OkCoordinator())
    bad_entry = _FakeEntry(integration, entry_id="entry-bad")
    bad_entry.runtime_data = types.SimpleNamespace(coordinator=_FailCoordinator())

    hass = _FakeHass(entries=[bad_entry, good_entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert good_entry.runtime_data.coordinator.calls == 1


def test_force_update_propagates_per_entry_cancelled_error(
    integration_modules: _InitModules, caplog
) -> None:
    """Per-entry cancellation must propagate through the global service."""
    integration = integration_modules.integration

    class _CancelledCoordinator:
        async def async_request_refresh(self):
            raise asyncio.CancelledError

    entry = _FakeEntry(integration, entry_id="entry-cancel")
    entry.runtime_data = types.SimpleNamespace(coordinator=_CancelledCoordinator())

    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    with caplog.at_level("DEBUG"):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert "Manual refresh cancelled for entry entry-cancel" in caplog.text


def test_force_update_no_coordinators_is_noop(
    integration_modules: _InitModules, caplog
) -> None:
    """Calling force_update with no coordinators should be a safe no-op."""
    integration = integration_modules.integration

    hass = _FakeHass(entries=[])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    with caplog.at_level("DEBUG"):
        asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert "No coordinators available for force_update" in caplog.text


def test_force_update_logs_do_not_expose_secrets(
    integration_modules: _InitModules, caplog
) -> None:
    """Failure logs should avoid exposing key material and detailed location/payload data."""
    integration = integration_modules.integration

    class _FailCoordinator:
        async def async_request_refresh(self):
            raise RuntimeError(
                "api_key=secret-123 lat=12.345678 lon=-98.765432 "
                "url=https://example.test/pollen?token=secret-123 payload=line1\n"
                "token=secret-123\nlocation.latitude=12.345678\n"
                "location.longitude=-98.765432"
            )

    entry = _FakeEntry(
        integration,
        entry_id="entry-secrets",
        data={
            integration.CONF_API_KEY: "secret-123",
            integration.CONF_LATITUDE: 12.345678,
            integration.CONF_LONGITUDE: -98.765432,
        },
    )
    entry.runtime_data = types.SimpleNamespace(coordinator=_FailCoordinator())

    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    text = caplog.text
    assert "secret-123" not in text
    assert "12.345678" not in text
    assert "-98.765432" not in text
    assert "https://example.test/pollen?token=secret-123" not in text
    assert "payload=line1" not in text
    assert "location.latitude=12.345678" not in text
    assert "location.longitude=-98.765432" not in text
    assert "payload=***" in text
    assert "token=***" in text
    assert "location.latitude=***" in text
    assert "location.longitude=***" in text
    assert "Manual refresh failed for entry entry-secrets (RuntimeError):" in text


def test_force_update_refreshes_all_location_subentries(
    integration_modules: _InitModules,
) -> None:
    """force_update should refresh every configured location coordinator."""
    integration = integration_modules.integration

    class _Coordinator:
        def __init__(self) -> None:
            self.calls = 0

        async def async_request_refresh(self):
            self.calls += 1

    coordinator_1 = _Coordinator()
    coordinator_2 = _Coordinator()
    entry = _FakeEntry(
        integration,
        entry_id="entry-parent",
        data={integration.CONF_API_KEY: "key"},
        subentries=_location_subentries(integration, "loc-1", "loc-2"),
    )
    entry.runtime_data = types.SimpleNamespace(
        locations={
            "loc-1": types.SimpleNamespace(
                subentry_id="loc-1", coordinator=coordinator_1
            ),
            "loc-2": types.SimpleNamespace(
                subentry_id="loc-2", coordinator=coordinator_2
            ),
        }
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert coordinator_1.calls == 1
    assert coordinator_2.calls == 1


def test_force_update_refreshes_location_subentries_sequentially(
    integration_modules: _InitModules,
) -> None:
    """force_update should limit location refresh concurrency to one."""
    integration = integration_modules.integration

    active = 0
    max_active = 0
    order: list[str] = []

    class _Coordinator:
        def __init__(self, name: str) -> None:
            self.name = name

        async def async_request_refresh(self):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            order.append(f"{self.name}:start")
            await asyncio.sleep(0)
            order.append(f"{self.name}:end")
            active -= 1

    entry = _FakeEntry(
        integration,
        entry_id="entry-parent",
        data={integration.CONF_API_KEY: "key"},
        subentries=_location_subentries(integration, "loc-1", "loc-2"),
    )
    entry.runtime_data = types.SimpleNamespace(
        locations={
            "loc-1": types.SimpleNamespace(
                subentry_id="loc-1", coordinator=_Coordinator("loc-1")
            ),
            "loc-2": types.SimpleNamespace(
                subentry_id="loc-2", coordinator=_Coordinator("loc-2")
            ),
        }
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert max_active == 1
    assert order == ["loc-1:start", "loc-1:end", "loc-2:start", "loc-2:end"]


def test_force_update_refreshes_fallback_location_without_subentries(
    integration_modules: _InitModules, caplog
) -> None:
    """force_update should still refresh legacy fallback runtime locations."""
    integration = integration_modules.integration

    class _Coordinator:
        def __init__(self) -> None:
            self.calls = 0

        async def async_request_refresh(self):
            self.calls += 1

    coordinator = _Coordinator()
    entry = _FakeEntry(
        integration,
        entry_id="entry-legacy",
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        subentries={},
    )
    entry.runtime_data = types.SimpleNamespace(
        locations={
            entry.entry_id: types.SimpleNamespace(
                subentry_id=entry.entry_id, coordinator=coordinator
            )
        }
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    with caplog.at_level("DEBUG"):
        asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert coordinator.calls == 1
    assert "Skipping stale Pollen Levels runtime location" not in caplog.text


def test_force_update_skips_runtime_locations_when_parent_has_no_locations(
    integration_modules: _InitModules, caplog
) -> None:
    """force_update should skip stale v3 runtime locations after deleting the last subentry."""
    integration = integration_modules.integration

    class _Coordinator:
        def __init__(self) -> None:
            self.calls = 0

        async def async_request_refresh(self):
            self.calls += 1

    coordinator = _Coordinator()
    entry = _FakeEntry(
        integration,
        entry_id="entry-parent",
        data={integration.CONF_API_KEY: "key"},
        subentries={},
    )
    entry.runtime_data = types.SimpleNamespace(
        locations={
            "deleted-location": types.SimpleNamespace(
                subentry_id="deleted-location", coordinator=coordinator
            )
        }
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    with caplog.at_level("DEBUG"):
        asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert coordinator.calls == 0
    assert (
        "Skipping stale Pollen Levels runtime location deleted-location "
        "for entry entry-parent"
    ) in caplog.text


def test_force_update_skips_stale_location_subentries(
    integration_modules: _InitModules, caplog
) -> None:
    """force_update should not refresh runtime locations removed from entry.subentries."""
    integration = integration_modules.integration

    class _Coordinator:
        def __init__(self) -> None:
            self.calls = 0

        async def async_request_refresh(self):
            self.calls += 1

    casa = _Coordinator()
    trabajo = _Coordinator()
    guineta = _Coordinator()
    entry = _FakeEntry(
        integration,
        entry_id="entry-parent",
        data={integration.CONF_API_KEY: "key"},
        subentries=_location_subentries(integration, "casa", "guineta"),
    )
    entry.runtime_data = types.SimpleNamespace(
        locations={
            "casa": types.SimpleNamespace(subentry_id="casa", coordinator=casa),
            "trabajo": types.SimpleNamespace(
                subentry_id="trabajo", coordinator=trabajo
            ),
            "guineta": types.SimpleNamespace(
                subentry_id="guineta", coordinator=guineta
            ),
        }
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    with caplog.at_level("DEBUG"):
        asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert casa.calls == 1
    assert guineta.calls == 1
    assert trabajo.calls == 0
    assert (
        "Skipping stale Pollen Levels runtime location trabajo for entry entry-parent"
        in caplog.text
    )


def test_force_update_continues_after_one_location_failure(
    integration_modules: _InitModules, caplog
) -> None:
    """One location failure should not prevent another location refresh."""
    integration = integration_modules.integration

    class _OkCoordinator:
        def __init__(self) -> None:
            self.calls = 0

        async def async_request_refresh(self):
            self.calls += 1

    class _FailCoordinator:
        lat = 12.345678
        lon = -98.765432

        async def async_request_refresh(self):
            raise RuntimeError(
                "api_key=secret-123 location.latitude=12.345678 "
                "location.longitude=-98.765432"
            )

    ok = _OkCoordinator()
    entry = _FakeEntry(
        integration,
        entry_id="entry-parent",
        data={integration.CONF_API_KEY: "secret-123"},
        subentries=_location_subentries(integration, "loc-bad", "loc-good"),
    )
    entry.runtime_data = types.SimpleNamespace(
        locations={
            "loc-bad": types.SimpleNamespace(
                subentry_id="loc-bad", coordinator=_FailCoordinator()
            ),
            "loc-good": types.SimpleNamespace(subentry_id="loc-good", coordinator=ok),
        }
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    text = caplog.text
    assert ok.calls == 1
    assert "Manual refresh failed for entry entry-parent subentry loc-bad" in text
    assert "secret-123" not in text
    assert "12.345678" not in text
    assert "-98.765432" not in text
    assert "location.latitude=***" in text
    assert "location.longitude=***" in text


def test_force_update_propagates_location_cancelled_error(
    integration_modules: _InitModules, caplog
) -> None:
    """A cancelled location refresh must propagate through the global service."""
    integration = integration_modules.integration

    class _CancelledCoordinator:
        async def async_request_refresh(self):
            raise asyncio.CancelledError

    entry = _FakeEntry(
        integration,
        entry_id="entry-parent",
        data={integration.CONF_API_KEY: "key"},
        subentries=_location_subentries(integration, "loc-cancel"),
    )
    entry.runtime_data = types.SimpleNamespace(
        locations={
            "loc-cancel": types.SimpleNamespace(
                subentry_id="loc-cancel", coordinator=_CancelledCoordinator()
            ),
        }
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    with caplog.at_level("DEBUG"):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert (
        "Manual refresh cancelled for entry entry-parent subentry loc-cancel"
        in caplog.text
    )


def test_force_update_parent_without_locations_is_noop(
    integration_modules: _InitModules, caplog
) -> None:
    """A loaded parent entry with no locations should be a safe no-op."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        entry_id="entry-empty",
        data={integration.CONF_API_KEY: "key"},
    )
    entry.runtime_data = types.SimpleNamespace(locations={})
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    with caplog.at_level("DEBUG"):
        asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert "Skipping force_update for entry entry-empty" in caplog.text
    assert "No coordinators available for force_update" in caplog.text


def test_migrate_entry_moves_mode_to_options(integration_modules: _InitModules) -> None:
    """Migration should copy per-day sensor mode from data to options."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            integration.CONF_CREATE_FORECAST_SENSORS: "D+1",
            "http_referer": "https://legacy.example.com",
        },
        options={"http_referer": "https://legacy.example.com"},
        version=1,
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert entry.options[integration.CONF_CREATE_FORECAST_SENSORS] == "D+1"
    assert integration.CONF_CREATE_FORECAST_SENSORS not in entry.data
    assert "http_referer" not in entry.data
    assert "http_referer" not in entry.options
    assert entry.version == integration.TARGET_ENTRY_VERSION


def test_migrate_entry_v3_legacy_creates_location_subentry(
    integration_modules: _InitModules,
) -> None:
    """A 2.3.0-style version-3 entry should migrate into one location subentry."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        entry_id="legacy-entry",
        title="Legacy Home",
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 12.34567,
            integration.CONF_LONGITUDE: -98.76543,
            integration.CONF_UPDATE_INTERVAL: 12,
            integration.CONF_LANGUAGE_CODE: "en",
            integration.CONF_FORECAST_DAYS: 3,
            integration.CONF_CREATE_FORECAST_SENSORS: "D+1",
        },
        options={},
        version=3,
        subentries={},
        unique_id="12.3457_-98.7654",
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True

    assert entry.version == integration.TARGET_ENTRY_VERSION
    assert entry.data == {integration.CONF_API_KEY: "key"}
    assert entry.unique_id == integration.api_key_unique_id("key")
    assert entry.options == {
        integration.CONF_UPDATE_INTERVAL: 12,
        integration.CONF_LANGUAGE_CODE: "en",
        integration.CONF_FORECAST_DAYS: 3,
        integration.CONF_CREATE_FORECAST_SENSORS: "D+1",
    }
    assert len(entry.subentries) == 1
    subentry = next(iter(entry.subentries.values()))
    assert subentry.subentry_type == integration.SUBENTRY_TYPE_LOCATION
    assert subentry.title == "Legacy Home"
    assert subentry.unique_id == "12.3457_-98.7654"
    assert subentry.data == {
        integration.CONF_LATITUDE: 12.34567,
        integration.CONF_LONGITUDE: -98.76543,
        integration.CONF_LEGACY_ENTRY_ID: "legacy-entry",
    }
    assert hass.config_entries.added_subentries == [(entry, subentry)]


def test_migrate_single_legacy_entry_attaches_registries_to_created_subentry(
    integration_modules: _InitModules, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A surviving single legacy entry should attach registries to its subentry."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        entry_id="legacy-entry",
        title="Legacy Home",
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 12.34567,
            integration.CONF_LONGITUDE: -98.76543,
        },
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[entry])

    entity_updates: list[tuple[str, dict[str, str]]] = []

    class _EntityRegistry:
        def async_update_entity(self, entity_id: str, **kwargs: str) -> None:
            entity_updates.append((entity_id, kwargs))

    entity_registry = _EntityRegistry()
    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(entity_registry_mod, "async_get", lambda _hass: entity_registry)
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda _registry, entry_id: (
            [
                types.SimpleNamespace(
                    entity_id="sensor.legacy_home_grass", platform=integration.DOMAIN
                ),
                types.SimpleNamespace(
                    entity_id="sensor.other_domain", platform="other"
                ),
            ]
            if entry_id == "legacy-entry"
            else []
        ),
    )

    device_updates: list[tuple[str, dict[str, str]]] = []

    class _DeviceRegistry:
        def async_update_device(self, device_id: str, **kwargs: str) -> None:
            device_updates.append((device_id, kwargs))

    device_registry = _DeviceRegistry()
    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_mod.async_get = lambda _hass: device_registry
    device_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: (
        [types.SimpleNamespace(id="device-home")] if entry_id == "legacy-entry" else []
    )
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True

    subentry = next(iter(entry.subentries.values()))
    assert entity_updates == [
        (
            "sensor.legacy_home_grass",
            {
                "config_entry_id": "legacy-entry",
                "config_subentry_id": subentry.subentry_id,
            },
        )
    ]
    assert device_updates == [
        (
            "device-home",
            {
                "add_config_entry_id": "legacy-entry",
                "add_config_subentry_id": subentry.subentry_id,
            },
        ),
        (
            "device-home",
            {
                "remove_config_entry_id": "legacy-entry",
                "remove_config_subentry_id": None,
            },
        ),
    ]


def test_migrate_single_entry_retry_after_parent_registry_failure_is_idempotent(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry should reuse the parent subentry and finish registry migration."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Legacy Home",
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 12.34567,
            integration.CONF_LONGITUDE: -98.76543,
        },
        version=3,
        subentries={},
        unique_id="12.3457_-98.7654",
    )
    hass = _FakeHass(entries=[entry])
    should_fail = True
    entity_updates: list[tuple[str, dict[str, str]]] = []

    class _EntityRegistry:
        def async_update_entity(self, entity_id: str, **kwargs: str) -> None:
            if should_fail:
                raise RuntimeError("registry boom")
            entity_updates.append((entity_id, kwargs))

    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(
        entity_registry_mod,
        "async_get",
        lambda _hass: _EntityRegistry(),
    )
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda _registry, entry_id: (
            [
                types.SimpleNamespace(
                    entity_id="sensor.legacy_home_grass", platform=integration.DOMAIN
                )
            ]
            if entry_id == "legacy-home"
            else []
        ),
    )

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is False

    assert entry.data == {
        integration.CONF_API_KEY: "key",
        integration.CONF_LATITUDE: 12.34567,
        integration.CONF_LONGITUDE: -98.76543,
    }
    assert entry.version == 3
    assert len(entry.subentries) == 1
    added_subentries = list(hass.config_entries.added_subentries)

    should_fail = False

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True

    subentry = next(iter(entry.subentries.values()))
    assert hass.config_entries.added_subentries == added_subentries
    assert len(entry.subentries) == 1
    assert entry.data == {integration.CONF_API_KEY: "key"}
    assert entry.unique_id == integration.api_key_unique_id("key")
    assert entry.version == integration.TARGET_ENTRY_VERSION
    assert entity_updates == [
        (
            "sensor.legacy_home_grass",
            {
                "config_entry_id": "legacy-home",
                "config_subentry_id": subentry.subentry_id,
            },
        )
    ]


def test_migrate_mixed_parent_direct_legacy_location_attaches_registries(
    integration_modules: _InitModules, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct legacy data should migrate even when the parent already has subentries."""
    integration = integration_modules.integration

    existing_subentry = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 10.0, integration.CONF_LONGITUDE: 20.0},
        subentry_id="existing-location",
        title="Existing",
        unique_id="10.0000_20.0000",
    )
    entry = _FakeEntry(
        integration,
        entry_id="mixed-parent",
        title="Legacy Home",
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 12.34567,
            integration.CONF_LONGITUDE: -98.76543,
        },
        version=3,
        subentries={existing_subentry.subentry_id: existing_subentry},
    )
    hass = _FakeHass(entries=[entry])

    entity_updates: list[tuple[str, dict[str, str]]] = []

    class _EntityRegistry:
        def async_update_entity(self, entity_id: str, **kwargs: str) -> None:
            entity_updates.append((entity_id, kwargs))

    entity_registry = _EntityRegistry()
    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(entity_registry_mod, "async_get", lambda _hass: entity_registry)
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda _registry, entry_id: (
            [
                types.SimpleNamespace(
                    entity_id="sensor.legacy_home_grass", platform=integration.DOMAIN
                ),
                types.SimpleNamespace(
                    entity_id="sensor.existing_grass",
                    platform=integration.DOMAIN,
                    config_subentry_id="existing-location",
                ),
            ]
            if entry_id == "mixed-parent"
            else []
        ),
    )

    device_updates: list[tuple[str, dict[str, str]]] = []

    class _DeviceRegistry:
        def async_update_device(self, device_id: str, **kwargs: str) -> None:
            device_updates.append((device_id, kwargs))

    device_registry = _DeviceRegistry()
    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_mod.async_get = lambda _hass: device_registry
    device_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: (
        [
            types.SimpleNamespace(id="device-home"),
            types.SimpleNamespace(
                id="device-existing",
                config_entries_subentries={"mixed-parent": {"existing-location"}},
            ),
        ]
        if entry_id == "mixed-parent"
        else []
    )
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True

    assert existing_subentry.subentry_id in entry.subentries
    created_subentry = next(
        subentry
        for subentry in entry.subentries.values()
        if subentry.data.get(integration.CONF_LEGACY_ENTRY_ID) == "mixed-parent"
    )
    assert created_subentry.title == "Legacy Home"
    assert created_subentry.unique_id == "12.3457_-98.7654"
    assert entry.data == {integration.CONF_API_KEY: "key"}
    assert entity_updates == [
        (
            "sensor.legacy_home_grass",
            {
                "config_entry_id": "mixed-parent",
                "config_subentry_id": created_subentry.subentry_id,
            },
        )
    ]
    assert device_updates == [
        (
            "device-home",
            {
                "add_config_entry_id": "mixed-parent",
                "add_config_subentry_id": created_subentry.subentry_id,
            },
        ),
        (
            "device-home",
            {
                "remove_config_entry_id": "mixed-parent",
                "remove_config_subentry_id": None,
            },
        ),
    ]


def test_migrate_legacy_entries_with_same_api_key_group_under_one_parent(
    integration_modules: _InitModules,
) -> None:
    """Legacy entries sharing one API key should become one parent with locations."""
    integration = integration_modules.integration

    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            integration.CONF_UPDATE_INTERVAL: 12,
        },
        options={},
        version=3,
        subentries={},
        unique_id="1.0000_2.0000",
    )
    duplicate = _FakeEntry(
        integration,
        entry_id="legacy-office",
        title="Office",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
            integration.CONF_UPDATE_INTERVAL: 8,
            integration.CONF_LANGUAGE_CODE: "en",
            integration.CONF_FORECAST_DAYS: 3,
        },
        options={},
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[parent, duplicate])

    assert asyncio.run(integration.async_migrate_entry(hass, parent)) is True

    assert parent.version == integration.TARGET_ENTRY_VERSION
    assert parent.data == {integration.CONF_API_KEY: "shared-key"}
    assert parent.unique_id == integration.api_key_unique_id("shared-key")
    assert parent.options == {
        integration.CONF_UPDATE_INTERVAL: 12,
        integration.CONF_LANGUAGE_CODE: "en",
        integration.CONF_FORECAST_DAYS: 3,
    }
    assert len(parent.subentries) == 2
    subentries_by_legacy_id = {
        subentry.data[integration.CONF_LEGACY_ENTRY_ID]: subentry
        for subentry in parent.subentries.values()
    }
    assert set(subentries_by_legacy_id) == {"legacy-home", "legacy-office"}
    assert subentries_by_legacy_id["legacy-home"].title == "Home"
    assert subentries_by_legacy_id["legacy-home"].unique_id == "1.0000_2.0000"
    assert subentries_by_legacy_id["legacy-office"].title == "Office"
    assert subentries_by_legacy_id["legacy-office"].unique_id == "3.0000_4.0000"
    assert duplicate.data == {
        integration.CONF_API_KEY: "shared-key",
        "merged_into_entry_id": "legacy-home",
    }
    assert duplicate.options == {}
    assert duplicate.version == integration.TARGET_ENTRY_VERSION
    assert hass.config_entries.removed_entries == ["legacy-office"]
    assert [entry.entry_id for entry in hass.config_entries.async_entries()] == [
        "legacy-home"
    ]
    added_subentries = list(hass.config_entries.added_subentries)

    assert asyncio.run(integration.async_migrate_entry(hass, parent)) is True

    assert len(parent.subentries) == 2
    assert parent.options[integration.CONF_UPDATE_INTERVAL] == 12
    assert hass.config_entries.added_subentries == added_subentries
    assert hass.config_entries.removed_entries == ["legacy-office"]


def test_migrate_group_with_invalid_legacy_coordinates_is_left_unchanged(
    integration_modules: _InitModules,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Grouped migration should abort if any legacy entry has corrupt coordinates."""
    integration = integration_modules.integration
    parent_data = {
        integration.CONF_API_KEY: "shared-secret",
        integration.CONF_LATITUDE: 1.0,
        integration.CONF_LONGITUDE: 2.0,
        integration.CONF_UPDATE_INTERVAL: 12,
    }
    invalid_data = {
        integration.CONF_API_KEY: "shared-secret",
        integration.CONF_LATITUDE: "123.456789",
        integration.CONF_LONGITUDE: "-222.987654",
        integration.CONF_LANGUAGE_CODE: "en",
    }
    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data=dict(parent_data),
        options={},
        version=3,
        subentries={},
        unique_id="1.0000_2.0000",
    )
    duplicate = _FakeEntry(
        integration,
        entry_id="legacy-corrupt",
        title="Corrupt",
        data=dict(invalid_data),
        options={},
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[parent, duplicate])

    with caplog.at_level("ERROR"):
        assert asyncio.run(integration.async_migrate_entry(hass, parent)) is False

    assert parent.data == parent_data
    assert parent.options == {}
    assert parent.version == 3
    assert parent.subentries == {}
    assert duplicate.data == invalid_data
    assert duplicate.options == {}
    assert duplicate.version == 3
    assert duplicate.subentries == {}
    assert "merged_into_entry_id" not in parent.data
    assert "merged_into_entry_id" not in duplicate.data
    assert hass.config_entries.added_subentries == []
    assert hass.config_entries.removed_entries == []
    assert [entry.entry_id for entry in hass.config_entries.async_entries()] == [
        "legacy-home",
        "legacy-corrupt",
    ]
    assert (
        "Cannot migrate Pollen Levels entry legacy-corrupt because it contains "
        "invalid stored coordinates"
    ) in caplog.text
    assert (
        "Aborted Pollen Levels API-key migration group because entry legacy-corrupt "
        "contains invalid stored coordinates. The group was left unchanged."
    ) in caplog.text
    assert "shared-secret" not in caplog.text
    assert "123.456789" not in caplog.text
    assert "-222.987654" not in caplog.text


def test_migrate_group_with_partial_legacy_coordinates_is_left_unchanged(
    integration_modules: _InitModules,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Grouped migration should abort if a legacy entry has partial coordinates."""
    integration = integration_modules.integration
    parent_data = {
        integration.CONF_API_KEY: "shared-secret",
        integration.CONF_LATITUDE: 1.0,
        integration.CONF_LONGITUDE: 2.0,
        integration.CONF_UPDATE_INTERVAL: 12,
    }
    partial_data = {
        integration.CONF_API_KEY: "shared-secret",
        integration.CONF_LATITUDE: "45.123456",
        integration.CONF_LANGUAGE_CODE: "en",
    }
    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data=dict(parent_data),
        options={},
        version=3,
        subentries={},
        unique_id="1.0000_2.0000",
    )
    duplicate = _FakeEntry(
        integration,
        entry_id="legacy-partial",
        title="Partial",
        data=dict(partial_data),
        options={},
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[parent, duplicate])

    with caplog.at_level("ERROR"):
        assert asyncio.run(integration.async_migrate_entry(hass, parent)) is False

    assert parent.data == parent_data
    assert parent.options == {}
    assert parent.version == 3
    assert parent.subentries == {}
    assert duplicate.data == partial_data
    assert duplicate.options == {}
    assert duplicate.version == 3
    assert duplicate.subentries == {}
    assert "merged_into_entry_id" not in parent.data
    assert "merged_into_entry_id" not in duplicate.data
    assert hass.config_entries.added_subentries == []
    assert hass.config_entries.removed_entries == []
    assert [entry.entry_id for entry in hass.config_entries.async_entries()] == [
        "legacy-home",
        "legacy-partial",
    ]
    assert (
        "Cannot migrate Pollen Levels entry legacy-partial because it contains "
        "invalid stored coordinates"
    ) in caplog.text
    assert (
        "Aborted Pollen Levels API-key migration group because entry legacy-partial "
        "contains invalid stored coordinates. The group was left unchanged."
    ) in caplog.text
    assert "shared-secret" not in caplog.text
    assert "45.123456" not in caplog.text


def test_migrate_legacy_entry_into_existing_clean_v3_parent(
    integration_modules: _InitModules,
) -> None:
    """A residual legacy entry should merge into an existing clean API-key parent."""
    integration = integration_modules.integration

    existing_subentry = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 10.0, integration.CONF_LONGITUDE: 20.0},
        subentry_id="existing-location",
        title="Existing",
        unique_id="10.0000_20.0000",
    )
    clean_parent = _FakeEntry(
        integration,
        entry_id="clean-parent",
        title="Pollen Levels",
        data={integration.CONF_API_KEY: "shared-key"},
        options={integration.CONF_LANGUAGE_CODE: "en"},
        version=integration.TARGET_ENTRY_VERSION,
        subentries={existing_subentry.subentry_id: existing_subentry},
        unique_id=integration.api_key_unique_id("shared-key"),
    )
    legacy = _FakeEntry(
        integration,
        entry_id="legacy-office",
        title="Office",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
        },
        options={integration.CONF_UPDATE_INTERVAL: 8},
        version=3,
        subentries={},
        unique_id="3.0000_4.0000",
    )
    hass = _FakeHass(entries=[legacy, clean_parent])

    assert asyncio.run(integration.async_migrate_entry(hass, legacy)) is True

    assert clean_parent.data == {integration.CONF_API_KEY: "shared-key"}
    assert clean_parent.unique_id == integration.api_key_unique_id("shared-key")
    assert clean_parent.options == {
        integration.CONF_LANGUAGE_CODE: "en",
        integration.CONF_UPDATE_INTERVAL: 8,
    }
    assert existing_subentry.subentry_id in clean_parent.subentries
    subentries_by_legacy_id = {
        subentry.data.get(integration.CONF_LEGACY_ENTRY_ID): subentry
        for subentry in clean_parent.subentries.values()
    }
    assert subentries_by_legacy_id["legacy-office"].title == "Office"
    assert subentries_by_legacy_id["legacy-office"].unique_id == "3.0000_4.0000"
    assert legacy.data == {
        integration.CONF_API_KEY: "shared-key",
        "merged_into_entry_id": "clean-parent",
    }
    assert legacy.version == integration.TARGET_ENTRY_VERSION
    assert len(hass.created_tasks) == 1
    assert hass.created_tasks[0].get_name() == (
        "remove merged pollenlevels entry legacy-office"
    )


def test_migrate_legacy_entries_with_different_api_keys_stay_separate(
    integration_modules: _InitModules,
) -> None:
    """Legacy entries with different API keys should not be merged together."""
    integration = integration_modules.integration

    first = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "key-one",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        version=3,
        subentries={},
    )
    second = _FakeEntry(
        integration,
        entry_id="legacy-office",
        title="Office",
        data={
            integration.CONF_API_KEY: "key-two",
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
        },
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[first, second])

    assert asyncio.run(integration.async_migrate_entry(hass, first)) is True

    assert first.data == {integration.CONF_API_KEY: "key-one"}
    assert second.data[integration.CONF_API_KEY] == "key-two"
    assert len(first.subentries) == 1
    assert second.subentries == {}
    assert hass.config_entries.removed_entries == []
    assert [entry.entry_id for entry in hass.config_entries.async_entries()] == [
        "legacy-home",
        "legacy-office",
    ]


def test_migrate_entry_without_location_does_not_create_corrupt_subentry(
    integration_modules: _InitModules,
) -> None:
    """Entries without coordinates should be cleaned without fake locations."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        entry_id="legacy-empty",
        data={integration.CONF_API_KEY: "key"},
        options={},
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True

    assert entry.data == {integration.CONF_API_KEY: "key"}
    assert entry.options == {}
    assert entry.subentries == {}
    assert entry.version == integration.TARGET_ENTRY_VERSION
    assert hass.config_entries.added_subentries == []


@pytest.mark.parametrize(
    ("coordinate_data", "precise_coordinate"),
    [
        (
            {
                "latitude": "123.456789",
                "longitude": "-222.987654",
            },
            "123.456789",
        ),
        ({"latitude": "45.123456"}, "45.123456"),
        ({"longitude": "-3.987654"}, "-3.987654"),
    ],
)
def test_migrate_entry_with_invalid_legacy_coordinates_is_left_unchanged(
    integration_modules: _InitModules,
    caplog: pytest.LogCaptureFixture,
    coordinate_data: dict[str, str],
    precise_coordinate: str,
) -> None:
    """Legacy entries with corrupt coordinates should fail without side effects."""
    integration = integration_modules.integration
    original_data = {
        integration.CONF_API_KEY: "secret-api-key",
        integration.CONF_UPDATE_INTERVAL: 12,
        **{
            getattr(integration, f"CONF_{key.upper()}"): value
            for key, value in coordinate_data.items()
        },
    }
    entry = _FakeEntry(
        integration,
        entry_id="legacy-corrupt",
        title="Corrupt Legacy",
        data=dict(original_data),
        options={},
        version=3,
        subentries={},
        unique_id="legacy-corrupt-id",
    )
    hass = _FakeHass(entries=[entry])

    with caplog.at_level("ERROR"):
        assert asyncio.run(integration.async_migrate_entry(hass, entry)) is False

    assert entry.data == original_data
    assert entry.options == {}
    assert entry.version == 3
    assert entry.subentries == {}
    assert hass.config_entries.added_subentries == []
    assert hass.config_entries.removed_entries == []
    assert "merged_into_entry_id" not in entry.data
    assert (
        "Cannot migrate Pollen Levels entry legacy-corrupt because it contains "
        "invalid stored coordinates. The entry was left unchanged. Remove and "
        "recreate this location or fix the configuration before retrying the "
        "migration."
    ) in caplog.text
    assert "secret-api-key" not in caplog.text
    assert precise_coordinate not in caplog.text


def test_migrate_entry_with_invalid_legacy_subentry_is_left_unchanged(
    integration_modules: _InitModules,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Alpha-state location subentries with corrupt coordinates should fail safely."""
    integration = integration_modules.integration

    existing_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LATITUDE: "123.456789",
            integration.CONF_LONGITUDE: "-222.987654",
            integration.CONF_LEGACY_ENTRY_ID: "legacy-corrupt",
        },
        subentry_id="existing-corrupt",
        title="Corrupt Home",
        unique_id=None,
    )
    entry = _FakeEntry(
        integration,
        entry_id="legacy-corrupt",
        title="Corrupt Legacy",
        data={integration.CONF_API_KEY: "secret-api-key"},
        options={},
        version=integration.TARGET_ENTRY_VERSION - 1,
        subentries={existing_subentry.subentry_id: existing_subentry},
        unique_id=integration.api_key_unique_id("secret-api-key"),
    )
    hass = _FakeHass(entries=[entry])

    with caplog.at_level("ERROR"):
        assert asyncio.run(integration.async_migrate_entry(hass, entry)) is False

    assert entry.data == {integration.CONF_API_KEY: "secret-api-key"}
    assert entry.options == {}
    assert entry.version == integration.TARGET_ENTRY_VERSION - 1
    assert entry.subentries == {existing_subentry.subentry_id: existing_subentry}
    assert hass.config_entries.added_subentries == []
    assert hass.config_entries.removed_entries == []
    assert (
        "Cannot migrate Pollen Levels entry legacy-corrupt because it has location "
        "subentries with invalid stored migration data. The entry was left "
        "unchanged. Remove and recreate the affected location or fix the "
        "configuration before retrying the migration."
    ) in caplog.text
    assert "secret-api-key" not in caplog.text
    assert "123.456789" not in caplog.text
    assert "-222.987654" not in caplog.text


def test_migrate_current_entry_updates_parent_unique_id_to_api_key_identity(
    integration_modules: _InitModules,
) -> None:
    """Already-clean parents should still migrate legacy coordinate unique IDs."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        entry_id="parent-entry",
        data={integration.CONF_API_KEY: "key"},
        options={},
        version=integration.TARGET_ENTRY_VERSION,
        subentries={},
        unique_id="1.0000_2.0000",
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True

    assert entry.data == {integration.CONF_API_KEY: "key"}
    assert entry.options == {}
    assert entry.version == integration.TARGET_ENTRY_VERSION
    assert entry.unique_id == integration.api_key_unique_id("key")


def test_migrate_grouped_entries_moves_registries_to_parent_subentry(
    integration_modules: _InitModules, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Merged entity/device registry links should point at the parent subentry."""
    integration = integration_modules.integration

    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        version=3,
        subentries={},
    )
    duplicate = _FakeEntry(
        integration,
        entry_id="legacy-office",
        title="Office",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
        },
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[parent, duplicate])

    entity_updates: list[tuple[str, dict[str, str]]] = []

    class _EntityRegistry:
        def async_update_entity(self, entity_id: str, **kwargs: str) -> None:
            entity_updates.append((entity_id, kwargs))

    entity_registry = _EntityRegistry()
    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(entity_registry_mod, "async_get", lambda _hass: entity_registry)
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda _registry, entry_id: (
            [
                types.SimpleNamespace(
                    entity_id="sensor.legacy_office_grass", platform=integration.DOMAIN
                ),
                types.SimpleNamespace(
                    entity_id="sensor.other_domain", platform="other"
                ),
            ]
            if entry_id == "legacy-office"
            else []
        ),
    )

    device_updates: list[tuple[str, dict[str, str]]] = []

    class _DeviceRegistry:
        def async_update_device(self, device_id: str, **kwargs: str) -> None:
            device_updates.append((device_id, kwargs))

    device_registry = _DeviceRegistry()
    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_mod.async_get = lambda _hass: device_registry
    device_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: (
        [types.SimpleNamespace(id="device-office")]
        if entry_id == "legacy-office"
        else []
    )
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    assert asyncio.run(integration.async_migrate_entry(hass, parent)) is True

    office_subentry = next(
        subentry
        for subentry in parent.subentries.values()
        if subentry.data[integration.CONF_LEGACY_ENTRY_ID] == "legacy-office"
    )
    assert entity_updates == [
        (
            "sensor.legacy_office_grass",
            {
                "config_entry_id": "legacy-home",
                "config_subentry_id": office_subentry.subentry_id,
            },
        )
    ]
    assert device_updates == [
        (
            "device-office",
            {
                "add_config_entry_id": "legacy-home",
                "add_config_subentry_id": office_subentry.subentry_id,
            },
        ),
        ("device-office", {"remove_config_entry_id": "legacy-office"}),
    ]


def test_migrate_grouped_multi_subentry_source_moves_registries_by_location(
    integration_modules: _InitModules, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source with several subentries should move each registry link by subentry."""
    integration = integration_modules.integration

    existing_subentry = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 10.0, integration.CONF_LONGITUDE: 20.0},
        subentry_id="existing-location",
        title="Existing",
        unique_id="10.0000_20.0000",
    )
    parent = _FakeEntry(
        integration,
        entry_id="clean-parent",
        data={integration.CONF_API_KEY: "shared-key"},
        version=integration.TARGET_ENTRY_VERSION,
        subentries={existing_subentry.subentry_id: existing_subentry},
        unique_id=integration.api_key_unique_id("shared-key"),
    )
    home_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            integration.CONF_LEGACY_ENTRY_ID: "legacy-home",
        },
        subentry_id="source-home",
        title="Home",
        unique_id="1.0000_2.0000",
    )
    office_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
            integration.CONF_LEGACY_ENTRY_ID: "legacy-office",
        },
        subentry_id="source-office",
        title="Office",
        unique_id="3.0000_4.0000",
    )
    source = _FakeEntry(
        integration,
        entry_id="legacy-source",
        data={integration.CONF_API_KEY: "shared-key"},
        version=integration.TARGET_ENTRY_VERSION,
        subentries={
            home_subentry.subentry_id: home_subentry,
            office_subentry.subentry_id: office_subentry,
        },
    )
    hass = _FakeHass(entries=[parent, source])

    entity_updates: list[tuple[str, dict[str, str]]] = []

    class _EntityRegistry:
        def async_update_entity(self, entity_id: str, **kwargs: str) -> None:
            entity_updates.append((entity_id, kwargs))

    entity_registry = _EntityRegistry()
    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(entity_registry_mod, "async_get", lambda _hass: entity_registry)
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda _registry, entry_id: (
            [
                types.SimpleNamespace(
                    entity_id="sensor.home_grass",
                    platform=integration.DOMAIN,
                    config_subentry_id="source-home",
                ),
                types.SimpleNamespace(
                    entity_id="sensor.office_grass",
                    platform=integration.DOMAIN,
                    config_subentry_id="source-office",
                ),
            ]
            if entry_id == "legacy-source"
            else []
        ),
    )

    device_updates: list[tuple[str, dict[str, str]]] = []

    class _DeviceRegistry:
        def async_update_device(self, device_id: str, **kwargs: str) -> None:
            device_updates.append((device_id, kwargs))

    device_registry = _DeviceRegistry()
    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_mod.async_get = lambda _hass: device_registry
    device_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: (
        [
            types.SimpleNamespace(
                id="device-home",
                config_entries_subentries={"legacy-source": {"source-home"}},
            ),
            types.SimpleNamespace(
                id="device-office",
                config_entries_subentries={"legacy-source": {"source-office"}},
            ),
        ]
        if entry_id == "legacy-source"
        else []
    )
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    assert asyncio.run(integration.async_migrate_entry(hass, source)) is True

    target_subentries = {
        subentry.data.get(integration.CONF_LEGACY_ENTRY_ID): subentry
        for subentry in parent.subentries.values()
    }
    target_home = target_subentries["legacy-home"]
    target_office = target_subentries["legacy-office"]

    assert entity_updates == [
        (
            "sensor.home_grass",
            {
                "config_entry_id": "clean-parent",
                "config_subentry_id": target_home.subentry_id,
            },
        ),
        (
            "sensor.office_grass",
            {
                "config_entry_id": "clean-parent",
                "config_subentry_id": target_office.subentry_id,
            },
        ),
    ]
    assert device_updates == [
        (
            "device-home",
            {
                "add_config_entry_id": "clean-parent",
                "add_config_subentry_id": target_home.subentry_id,
            },
        ),
        ("device-home", {"remove_config_entry_id": "legacy-source"}),
        (
            "device-office",
            {
                "add_config_entry_id": "clean-parent",
                "add_config_subentry_id": target_office.subentry_id,
            },
        ),
        ("device-office", {"remove_config_entry_id": "legacy-source"}),
    ]
    assert source.data == {
        integration.CONF_API_KEY: "shared-key",
        "merged_into_entry_id": "clean-parent",
    }
    assert hass.config_entries.removed_entries == ["legacy-source"]


def test_migrate_grouped_source_mixed_none_and_subentry_skips_leftover_none(
    integration_modules: _InitModules, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A grouped source device should ignore stale None if a valid subentry exists."""
    integration = integration_modules.integration

    parent_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            integration.CONF_LEGACY_ENTRY_ID: "legacy-home",
        },
        subentry_id="parent-location",
        title="Home",
        unique_id="1.0000_2.0000",
    )
    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        data={integration.CONF_API_KEY: "shared-key"},
        version=integration.TARGET_ENTRY_VERSION,
        subentries={parent_subentry.subentry_id: parent_subentry},
        unique_id=integration.api_key_unique_id("shared-key"),
    )
    source_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
            integration.CONF_LEGACY_ENTRY_ID: "legacy-office",
        },
        subentry_id="source-location",
        title="Office",
        unique_id="3.0000_4.0000",
    )
    source = _FakeEntry(
        integration,
        entry_id="legacy-office",
        data={integration.CONF_API_KEY: "shared-key"},
        version=integration.TARGET_ENTRY_VERSION,
        subentries={source_subentry.subentry_id: source_subentry},
    )
    hass = _FakeHass(entries=[parent, source])

    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda *_args, **_kwargs: [],
    )

    device_updates: list[tuple[str, dict[str, Any]]] = []

    class _DeviceRegistry:
        def async_update_device(self, device_id: str, **kwargs: Any) -> None:
            device_updates.append((device_id, kwargs))

    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_mod.async_get = lambda _hass: _DeviceRegistry()
    device_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: (
        [
            types.SimpleNamespace(
                id="device-office",
                config_entries={"legacy-office"},
                config_entries_subentries={"legacy-office": {None, "source-location"}},
            )
        ]
        if entry_id == "legacy-office"
        else []
    )
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    assert asyncio.run(integration.async_migrate_entry(hass, parent)) is True

    office_subentry = next(
        subentry
        for subentry in parent.subentries.values()
        if subentry.data[integration.CONF_LEGACY_ENTRY_ID] == "legacy-office"
    )
    assert device_updates == [
        (
            "device-office",
            {
                "add_config_entry_id": "legacy-home",
                "add_config_subentry_id": office_subentry.subentry_id,
            },
        ),
        ("device-office", {"remove_config_entry_id": "legacy-office"}),
    ]
    assert source.data == {
        integration.CONF_API_KEY: "shared-key",
        "merged_into_entry_id": "legacy-home",
    }
    assert hass.config_entries.removed_entries == ["legacy-office"]


def test_migrate_grouped_source_only_none_device_association_keeps_source(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A grouped source with only an unmapped None device link stays retryable."""
    integration = integration_modules.integration

    parent_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            integration.CONF_LEGACY_ENTRY_ID: "legacy-home",
        },
        subentry_id="parent-location",
        title="Home",
        unique_id="1.0000_2.0000",
    )
    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        data={integration.CONF_API_KEY: "shared-key"},
        version=integration.TARGET_ENTRY_VERSION,
        subentries={parent_subentry.subentry_id: parent_subentry},
        unique_id=integration.api_key_unique_id("shared-key"),
    )
    source_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
            integration.CONF_LEGACY_ENTRY_ID: "legacy-office",
        },
        subentry_id="source-location",
        title="Office",
        unique_id="3.0000_4.0000",
    )
    source = _FakeEntry(
        integration,
        entry_id="legacy-office",
        data={integration.CONF_API_KEY: "shared-key"},
        version=integration.TARGET_ENTRY_VERSION,
        subentries={source_subentry.subentry_id: source_subentry},
    )
    hass = _FakeHass(entries=[parent, source])

    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda *_args, **_kwargs: [],
    )

    device_updates: list[tuple[str, dict[str, Any]]] = []

    class _DeviceRegistry:
        def async_update_device(self, device_id: str, **kwargs: Any) -> None:
            device_updates.append((device_id, kwargs))

    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_mod.async_get = lambda _hass: _DeviceRegistry()
    device_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: (
        [
            types.SimpleNamespace(
                id="device-office",
                config_entries={"legacy-office"},
                config_entries_subentries={"legacy-office": {None}},
            )
        ]
        if entry_id == "legacy-office"
        else []
    )
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    with caplog.at_level("ERROR", logger=integration.__name__):
        assert asyncio.run(integration.async_migrate_entry(hass, parent)) is False

    assert device_updates == []
    assert source.data == {integration.CONF_API_KEY: "shared-key"}
    assert hass.config_entries.removed_entries == []
    assert "no target subentry for source subentry legacy-entry" in caplog.text


def test_migrate_grouped_entry_keeps_clean_v3_source_with_unmigratable_subentry(
    integration_modules: _InitModules,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A clean v3 source subentry without legacy identity must not be removed."""
    integration = integration_modules.integration

    parent_subentry = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 10.0, integration.CONF_LONGITUDE: 20.0},
        subentry_id="parent-location",
        title="Parent",
        unique_id="10.0000_20.0000",
    )
    parent = _FakeEntry(
        integration,
        entry_id="clean-parent",
        data={integration.CONF_API_KEY: "shared-key"},
        version=integration.TARGET_ENTRY_VERSION,
        subentries={parent_subentry.subentry_id: parent_subentry},
        unique_id=integration.api_key_unique_id("shared-key"),
    )
    source_subentry = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 1.0, integration.CONF_LONGITUDE: 2.0},
        subentry_id="clean-source-location",
        title="Clean source",
        unique_id="1.0000_2.0000",
    )
    source = _FakeEntry(
        integration,
        entry_id="clean-source",
        data={integration.CONF_API_KEY: "shared-key"},
        version=integration.TARGET_ENTRY_VERSION,
        subentries={source_subentry.subentry_id: source_subentry},
        unique_id="other-parent-id",
    )
    hass = _FakeHass(entries=[parent, source])

    with caplog.at_level("ERROR", logger=integration.__name__):
        assert asyncio.run(integration.async_migrate_entry(hass, parent)) is False

    assert source.data == {integration.CONF_API_KEY: "shared-key"}
    assert source.version == integration.TARGET_ENTRY_VERSION
    assert source.subentries == {source_subentry.subentry_id: source_subentry}
    assert parent.subentries == {parent_subentry.subentry_id: parent_subentry}
    assert hass.config_entries.added_subentries == []
    assert hass.config_entries.removed_entries == []
    assert "location subentries with invalid stored migration data" in caplog.text


def test_migrate_grouped_entry_keeps_source_with_corrupt_location_subentry(
    integration_modules: _InitModules,
) -> None:
    """A source with incomplete location subentry data must not be removed."""
    integration = integration_modules.integration

    parent = _FakeEntry(
        integration,
        entry_id="clean-parent",
        data={integration.CONF_API_KEY: "shared-key"},
        version=integration.TARGET_ENTRY_VERSION,
        subentries={
            "parent-location": integration.ConfigSubentry(
                data={
                    integration.CONF_LATITUDE: 10.0,
                    integration.CONF_LONGITUDE: 20.0,
                },
                subentry_id="parent-location",
                title="Parent",
                unique_id="10.0000_20.0000",
            )
        },
        unique_id=integration.api_key_unique_id("shared-key"),
    )
    corrupt_subentry = integration.ConfigSubentry(
        data={integration.CONF_LEGACY_ENTRY_ID: "legacy-source"},
        subentry_id="corrupt-location",
        title="Corrupt source",
        unique_id="corrupt",
    )
    source = _FakeEntry(
        integration,
        entry_id="legacy-source",
        data={integration.CONF_API_KEY: "shared-key"},
        version=integration.TARGET_ENTRY_VERSION,
        subentries={corrupt_subentry.subentry_id: corrupt_subentry},
    )
    hass = _FakeHass(entries=[parent, source])

    assert asyncio.run(integration.async_migrate_entry(hass, parent)) is False

    assert source.data == {integration.CONF_API_KEY: "shared-key"}
    assert source.subentries == {corrupt_subentry.subentry_id: corrupt_subentry}
    assert hass.config_entries.added_subentries == []
    assert hass.config_entries.removed_entries == []


def test_migrate_grouped_entries_attaches_parent_registries_to_parent_subentry(
    integration_modules: _InitModules, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The surviving legacy parent should also get config_subentry registry links."""
    integration = integration_modules.integration

    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        version=3,
        subentries={},
    )
    duplicate = _FakeEntry(
        integration,
        entry_id="legacy-office",
        title="Office",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
        },
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[parent, duplicate])

    entity_updates: list[tuple[str, dict[str, str]]] = []

    class _EntityRegistry:
        def async_update_entity(self, entity_id: str, **kwargs: str) -> None:
            entity_updates.append((entity_id, kwargs))

    entity_registry = _EntityRegistry()
    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(entity_registry_mod, "async_get", lambda _hass: entity_registry)
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda _registry, entry_id: {
            "legacy-home": [
                types.SimpleNamespace(
                    entity_id="sensor.legacy_home_grass", platform=integration.DOMAIN
                )
            ],
            "legacy-office": [
                types.SimpleNamespace(
                    entity_id="sensor.legacy_office_grass", platform=integration.DOMAIN
                )
            ],
        }.get(entry_id, []),
    )

    device_updates: list[tuple[str, dict[str, str]]] = []

    class _DeviceRegistry:
        def async_update_device(self, device_id: str, **kwargs: str) -> None:
            device_updates.append((device_id, kwargs))

    device_registry = _DeviceRegistry()
    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_mod.async_get = lambda _hass: device_registry
    device_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: {
        "legacy-home": [types.SimpleNamespace(id="device-home")],
        "legacy-office": [types.SimpleNamespace(id="device-office")],
    }.get(entry_id, [])
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    assert asyncio.run(integration.async_migrate_entry(hass, parent)) is True

    subentries_by_legacy_id = {
        subentry.data[integration.CONF_LEGACY_ENTRY_ID]: subentry
        for subentry in parent.subentries.values()
    }
    home_subentry = subentries_by_legacy_id["legacy-home"]
    office_subentry = subentries_by_legacy_id["legacy-office"]

    assert entity_updates == [
        (
            "sensor.legacy_home_grass",
            {
                "config_entry_id": "legacy-home",
                "config_subentry_id": home_subentry.subentry_id,
            },
        ),
        (
            "sensor.legacy_office_grass",
            {
                "config_entry_id": "legacy-home",
                "config_subentry_id": office_subentry.subentry_id,
            },
        ),
    ]
    assert device_updates == [
        (
            "device-home",
            {
                "add_config_entry_id": "legacy-home",
                "add_config_subentry_id": home_subentry.subentry_id,
            },
        ),
        (
            "device-home",
            {
                "remove_config_entry_id": "legacy-home",
                "remove_config_subentry_id": None,
            },
        ),
        (
            "device-office",
            {
                "add_config_entry_id": "legacy-home",
                "add_config_subentry_id": office_subentry.subentry_id,
            },
        ),
        ("device-office", {"remove_config_entry_id": "legacy-office"}),
    ]


def test_migrate_parent_surviving_entities_attach_to_location_subentry(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Surviving parent entities should keep IDs and gain the location subentry."""
    integration = integration_modules.integration

    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        version=3,
        subentries={},
    )
    duplicate = _FakeEntry(
        integration,
        entry_id="legacy-office",
        title="Office",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
        },
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[parent, duplicate])

    parent_entity = types.SimpleNamespace(
        entity_id="sensor.legacy_home_grass",
        unique_id="legacy-home_type_grass",
        platform=integration.DOMAIN,
        config_subentry_id=None,
    )
    duplicate_entity = types.SimpleNamespace(
        entity_id="sensor.legacy_office_grass",
        unique_id="legacy-office_type_grass",
        platform=integration.DOMAIN,
        config_subentry_id=None,
    )
    registry_entities = {
        "legacy-home": [parent_entity],
        "legacy-office": [duplicate_entity],
    }
    created_entities: list[object] = []

    class _EntityRegistry:
        def async_update_entity(self, entity_id: str, **kwargs: str) -> None:
            for entities in registry_entities.values():
                for entity in entities:
                    if entity.entity_id == entity_id:
                        entity.config_subentry_id = kwargs["config_subentry_id"]
                        entity.config_entry_id = kwargs["config_entry_id"]
                        return
            created_entities.append(kwargs)

    entity_registry = _EntityRegistry()
    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(entity_registry_mod, "async_get", lambda _hass: entity_registry)
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda _registry, entry_id: registry_entities.get(entry_id, []),
    )

    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_mod.async_get = lambda _hass: types.SimpleNamespace(
        async_update_device=lambda *_args, **_kwargs: None
    )
    device_registry_mod.async_entries_for_config_entry = lambda *_args: []
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    with caplog.at_level("INFO", logger=integration.__name__):
        assert asyncio.run(integration.async_migrate_entry(hass, parent)) is True

    home_subentry = next(
        subentry
        for subentry in parent.subentries.values()
        if subentry.data[integration.CONF_LEGACY_ENTRY_ID] == "legacy-home"
    )
    office_subentry = next(
        subentry
        for subentry in parent.subentries.values()
        if subentry.data[integration.CONF_LEGACY_ENTRY_ID] == "legacy-office"
    )

    assert parent_entity.entity_id == "sensor.legacy_home_grass"
    assert parent_entity.unique_id == "legacy-home_type_grass"
    assert parent_entity.config_entry_id == "legacy-home"
    assert parent_entity.config_subentry_id == home_subentry.subentry_id
    assert duplicate_entity.entity_id == "sensor.legacy_office_grass"
    assert duplicate_entity.unique_id == "legacy-office_type_grass"
    assert duplicate_entity.config_entry_id == "legacy-home"
    assert duplicate_entity.config_subentry_id == office_subentry.subentry_id
    assert created_entities == []
    assert "Selected parent entry legacy-home" in caplog.text
    assert "Moved 1 entity registry entries from entry legacy-home" in caplog.text
    assert "shared-key" not in caplog.text
    assert "1.0" not in caplog.text


def test_migrate_parent_surviving_devices_move_from_main_entry_to_location_subentry(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Surviving parent devices should move from main entry to its subentry."""
    integration = integration_modules.integration

    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        version=3,
        subentries={},
    )
    duplicate = _FakeEntry(
        integration,
        entry_id="legacy-office",
        title="Office",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
        },
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[parent, duplicate])

    parent_device = types.SimpleNamespace(
        id="device-home",
        config_entries={"legacy-home"},
        config_entries_subentries={"legacy-home": {None}},
    )
    duplicate_device = types.SimpleNamespace(
        id="device-office",
        config_entries={"legacy-office"},
        config_entries_subentries={"legacy-office": {None}},
    )
    devices = [parent_device, duplicate_device]
    removed_devices: list[str] = []

    class _DeviceRegistry:
        def async_update_device(self, device_id: str, **kwargs: str) -> None:
            device = next(device for device in devices if device.id == device_id)
            if add_entry := kwargs.get("add_config_entry_id"):
                device.config_entries.add(add_entry)
                device.config_entries_subentries.setdefault(add_entry, set()).add(
                    kwargs.get("add_config_subentry_id")
                )
            if remove_entry := kwargs.get("remove_config_entry_id"):
                if "remove_config_subentry_id" in kwargs:
                    subentries = device.config_entries_subentries.setdefault(
                        remove_entry, set()
                    )
                    subentries.discard(kwargs["remove_config_subentry_id"])
                    if not subentries:
                        device.config_entries.discard(remove_entry)
                else:
                    device.config_entries.discard(remove_entry)
                    device.config_entries_subentries.pop(remove_entry, None)

    device_registry = _DeviceRegistry()
    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_mod.async_get = lambda _hass: device_registry
    device_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: [
        device for device in devices if entry_id in device.config_entries
    ]
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda *_args, **_kwargs: [],
    )

    assert asyncio.run(integration.async_migrate_entry(hass, parent)) is True

    home_subentry = next(
        subentry
        for subentry in parent.subentries.values()
        if subentry.data[integration.CONF_LEGACY_ENTRY_ID] == "legacy-home"
    )
    office_subentry = next(
        subentry
        for subentry in parent.subentries.values()
        if subentry.data[integration.CONF_LEGACY_ENTRY_ID] == "legacy-office"
    )

    assert parent_device in devices
    assert duplicate_device in devices
    assert removed_devices == []
    assert parent_device.config_entries == {"legacy-home"}
    assert parent_device.config_entries_subentries == {
        "legacy-home": {home_subentry.subentry_id}
    }
    assert duplicate_device.config_entries == {"legacy-home"}
    assert duplicate_device.config_entries_subentries == {
        "legacy-home": {office_subentry.subentry_id}
    }


def test_migrate_a1_state_repairs_registry_without_duplicate_subentries(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A previous alpha state should repair registry links without duplicates."""
    integration = integration_modules.integration

    existing_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            integration.CONF_LEGACY_ENTRY_ID: "legacy-home",
        },
        subentry_id="existing-home",
        title="Home",
        unique_id="1.0000_2.0000",
    )
    entry = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={integration.CONF_API_KEY: "shared-key"},
        version=integration.TARGET_ENTRY_VERSION - 1,
        subentries={existing_subentry.subentry_id: existing_subentry},
        unique_id=integration.api_key_unique_id("shared-key"),
    )
    hass = _FakeHass(entries=[entry])

    entity = types.SimpleNamespace(
        entity_id="sensor.legacy_home_grass",
        unique_id="legacy-home_type_grass",
        platform=integration.DOMAIN,
        config_subentry_id=None,
    )

    class _EntityRegistry:
        def async_update_entity(self, entity_id: str, **kwargs: str) -> None:
            assert entity_id == entity.entity_id
            entity.config_entry_id = kwargs["config_entry_id"]
            entity.config_subentry_id = kwargs["config_subentry_id"]

    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(
        entity_registry_mod, "async_get", lambda _hass: _EntityRegistry()
    )
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda _registry, entry_id: [entity] if entry_id == "legacy-home" else [],
    )

    device = types.SimpleNamespace(
        id="device-home",
        config_entries={"legacy-home"},
        config_entries_subentries={"legacy-home": {None}},
    )

    class _DeviceRegistry:
        def async_update_device(self, device_id: str, **kwargs: str) -> None:
            assert device_id == device.id
            if add_entry := kwargs.get("add_config_entry_id"):
                device.config_entries.add(add_entry)
                device.config_entries_subentries.setdefault(add_entry, set()).add(
                    kwargs.get("add_config_subentry_id")
                )
            if remove_entry := kwargs.get("remove_config_entry_id"):
                subentries = device.config_entries_subentries.setdefault(
                    remove_entry, set()
                )
                subentries.discard(kwargs.get("remove_config_subentry_id"))

    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_mod.async_get = lambda _hass: _DeviceRegistry()
    device_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: (
        [device] if entry_id == "legacy-home" else []
    )
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True

    assert entry.version == integration.TARGET_ENTRY_VERSION
    assert entry.subentries == {existing_subentry.subentry_id: existing_subentry}
    assert hass.config_entries.added_subentries == []
    assert entity.entity_id == "sensor.legacy_home_grass"
    assert entity.unique_id == "legacy-home_type_grass"
    assert entity.config_subentry_id == existing_subentry.subentry_id
    assert device.config_entries_subentries == {
        "legacy-home": {existing_subentry.subentry_id}
    }


def test_migrate_mixed_device_registry_state_removes_leftover_none_association(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migration should remove stale legacy main-entry device links."""
    integration = integration_modules.integration

    existing_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            integration.CONF_LEGACY_ENTRY_ID: "legacy-home",
        },
        subentry_id="existing-home",
        title="Home",
        unique_id="1.0000_2.0000",
    )
    entry = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={integration.CONF_API_KEY: "shared-key"},
        version=integration.TARGET_ENTRY_VERSION - 1,
        subentries={existing_subentry.subentry_id: existing_subentry},
        unique_id=integration.api_key_unique_id("shared-key"),
    )
    hass = _FakeHass(entries=[entry])

    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda *_args, **_kwargs: [],
    )

    device = types.SimpleNamespace(
        id="device-home",
        config_entries={"legacy-home"},
        config_entries_subentries={"legacy-home": {None, "existing-home"}},
    )
    devices = [device]
    removed_devices: list[str] = []
    device_updates: list[tuple[str, dict[str, Any]]] = []

    class _DeviceRegistry:
        def async_update_device(self, device_id: str, **kwargs: Any) -> None:
            device_updates.append((device_id, kwargs))
            assert device_id == device.id
            if add_entry := kwargs.get("add_config_entry_id"):
                device.config_entries.add(add_entry)
                device.config_entries_subentries.setdefault(add_entry, set()).add(
                    kwargs.get("add_config_subentry_id")
                )
            if remove_entry := kwargs.get("remove_config_entry_id"):
                if "remove_config_subentry_id" in kwargs:
                    subentries = device.config_entries_subentries.setdefault(
                        remove_entry, set()
                    )
                    subentries.discard(kwargs["remove_config_subentry_id"])
                    if not subentries:
                        device.config_entries.discard(remove_entry)
                else:
                    device.config_entries.discard(remove_entry)
                    device.config_entries_subentries.pop(remove_entry, None)

    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_mod.async_get = lambda _hass: _DeviceRegistry()
    device_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: [
        device for device in devices if entry_id in device.config_entries
    ]
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True

    assert entry.version == integration.TARGET_ENTRY_VERSION
    assert entry.subentries == {existing_subentry.subentry_id: existing_subentry}
    assert hass.config_entries.added_subentries == []
    assert device in devices
    assert removed_devices == []
    assert device.config_entries_subentries == {"legacy-home": {"existing-home"}}
    assert (
        "device-home",
        {
            "remove_config_entry_id": "legacy-home",
            "remove_config_subentry_id": None,
        },
    ) in device_updates


def test_migrate_grouped_parent_retry_after_parent_registry_failure_is_idempotent(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A grouped retry should reuse parent subentries before completing merge."""
    integration = integration_modules.integration

    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        version=3,
        subentries={},
        unique_id="1.0000_2.0000",
    )
    duplicate = _FakeEntry(
        integration,
        entry_id="legacy-office",
        title="Office",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
        },
        version=3,
        subentries={},
        unique_id="3.0000_4.0000",
    )
    hass = _FakeHass(entries=[parent, duplicate])
    should_fail_parent = True
    entity_updates: list[tuple[str, dict[str, str]]] = []

    class _EntityRegistry:
        def async_update_entity(self, entity_id: str, **kwargs: str) -> None:
            if should_fail_parent and entity_id == "sensor.legacy_home_grass":
                raise RuntimeError("registry boom")
            entity_updates.append((entity_id, kwargs))

    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(
        entity_registry_mod,
        "async_get",
        lambda _hass: _EntityRegistry(),
    )
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda _registry, entry_id: {
            "legacy-home": [
                types.SimpleNamespace(
                    entity_id="sensor.legacy_home_grass", platform=integration.DOMAIN
                )
            ],
            "legacy-office": [
                types.SimpleNamespace(
                    entity_id="sensor.legacy_office_grass", platform=integration.DOMAIN
                )
            ],
        }.get(entry_id, []),
    )

    assert asyncio.run(integration.async_migrate_entry(hass, parent)) is False

    assert parent.data == {
        integration.CONF_API_KEY: "shared-key",
        integration.CONF_LATITUDE: 1.0,
        integration.CONF_LONGITUDE: 2.0,
    }
    assert parent.version == 3
    assert duplicate.data[integration.CONF_LATITUDE] == 3.0
    assert hass.config_entries.removed_entries == []
    assert len(parent.subentries) == 2
    added_subentries = list(hass.config_entries.added_subentries)

    should_fail_parent = False
    entity_updates.clear()

    assert asyncio.run(integration.async_migrate_entry(hass, parent)) is True

    subentries_by_legacy_id = {
        subentry.data[integration.CONF_LEGACY_ENTRY_ID]: subentry
        for subentry in parent.subentries.values()
    }
    home_subentry = subentries_by_legacy_id["legacy-home"]
    office_subentry = subentries_by_legacy_id["legacy-office"]
    assert hass.config_entries.added_subentries == added_subentries
    assert len(parent.subentries) == 2
    assert parent.data == {integration.CONF_API_KEY: "shared-key"}
    assert parent.unique_id == integration.api_key_unique_id("shared-key")
    assert parent.version == integration.TARGET_ENTRY_VERSION
    assert duplicate.data == {
        integration.CONF_API_KEY: "shared-key",
        "merged_into_entry_id": "legacy-home",
    }
    assert hass.config_entries.removed_entries == ["legacy-office"]
    assert entity_updates == [
        (
            "sensor.legacy_home_grass",
            {
                "config_entry_id": "legacy-home",
                "config_subentry_id": home_subentry.subentry_id,
            },
        ),
        (
            "sensor.legacy_office_grass",
            {
                "config_entry_id": "legacy-home",
                "config_subentry_id": office_subentry.subentry_id,
            },
        ),
    ]


def test_migrate_grouped_entries_keeps_duplicate_when_entity_registry_update_fails(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Entity registry failures should keep the source entry retryable."""
    integration = integration_modules.integration

    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        version=3,
        subentries={},
    )
    duplicate = _FakeEntry(
        integration,
        entry_id="legacy-office",
        title="Office",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
        },
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[parent, duplicate])

    entity_attempts: list[str] = []

    class _EntityRegistry:
        def async_update_entity(self, entity_id: str, **_kwargs: str) -> None:
            entity_attempts.append(entity_id)
            raise RuntimeError("registry boom")

    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(
        entity_registry_mod,
        "async_get",
        lambda _hass: _EntityRegistry(),
    )
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda _registry, entry_id: (
            [
                types.SimpleNamespace(
                    entity_id="sensor.legacy_office_grass", platform=integration.DOMAIN
                ),
                types.SimpleNamespace(
                    entity_id="sensor.other_domain", platform="other"
                ),
            ]
            if entry_id == "legacy-office"
            else []
        ),
    )

    with caplog.at_level("ERROR", logger=integration.__name__):
        assert asyncio.run(integration.async_migrate_entry(hass, parent)) is False

    office_subentry = next(
        subentry
        for subentry in parent.subentries.values()
        if subentry.data[integration.CONF_LEGACY_ENTRY_ID] == "legacy-office"
    )
    assert office_subentry.title == "Office"
    assert duplicate.data == {
        integration.CONF_API_KEY: "shared-key",
        integration.CONF_LATITUDE: 3.0,
        integration.CONF_LONGITUDE: 4.0,
    }
    assert duplicate.version == 3
    assert hass.config_entries.removed_entries == []
    assert entity_attempts == ["sensor.legacy_office_grass"]
    assert "Failed to move entity sensor.legacy_office_grass" in caplog.text


def test_migrate_grouped_entries_retry_after_registry_failure_is_idempotent(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retrying after a registry failure should reuse already-created subentries."""
    integration = integration_modules.integration

    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        version=3,
        subentries={},
    )
    duplicate = _FakeEntry(
        integration,
        entry_id="legacy-office",
        title="Office",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
        },
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[parent, duplicate])
    should_fail = True
    entity_updates: list[tuple[str, dict[str, str]]] = []

    class _EntityRegistry:
        def async_update_entity(self, entity_id: str, **kwargs: str) -> None:
            if should_fail:
                raise RuntimeError("registry boom")
            entity_updates.append((entity_id, kwargs))

    entity_registry_mod = sys.modules["homeassistant.helpers.entity_registry"]
    monkeypatch.setattr(
        entity_registry_mod,
        "async_get",
        lambda _hass: _EntityRegistry(),
    )
    monkeypatch.setattr(
        entity_registry_mod,
        "async_entries_for_config_entry",
        lambda _registry, entry_id: (
            [
                types.SimpleNamespace(
                    entity_id="sensor.legacy_office_grass", platform=integration.DOMAIN
                )
            ]
            if entry_id == "legacy-office"
            else []
        ),
    )

    assert asyncio.run(integration.async_migrate_entry(hass, parent)) is False
    added_subentries = list(hass.config_entries.added_subentries)
    assert len(parent.subentries) == 2
    assert duplicate.data[integration.CONF_LATITUDE] == 3.0
    assert hass.config_entries.removed_entries == []

    should_fail = False

    assert asyncio.run(integration.async_migrate_entry(hass, parent)) is True

    office_subentry = next(
        subentry
        for subentry in parent.subentries.values()
        if subentry.data[integration.CONF_LEGACY_ENTRY_ID] == "legacy-office"
    )
    assert hass.config_entries.added_subentries == added_subentries
    assert len(parent.subentries) == 2
    assert duplicate.data == {
        integration.CONF_API_KEY: "shared-key",
        "merged_into_entry_id": "legacy-home",
    }
    assert hass.config_entries.removed_entries == ["legacy-office"]
    assert entity_updates == [
        (
            "sensor.legacy_office_grass",
            {
                "config_entry_id": "legacy-home",
                "config_subentry_id": office_subentry.subentry_id,
            },
        )
    ]


def test_migrate_grouped_entries_keeps_duplicate_when_device_registry_update_fails(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Device registry failures should keep the source entry retryable."""
    integration = integration_modules.integration

    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        version=3,
        subentries={},
    )
    duplicate = _FakeEntry(
        integration,
        entry_id="legacy-office",
        title="Office",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
        },
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[parent, duplicate])

    device_attempts: list[tuple[str, dict[str, str]]] = []

    class _DeviceRegistry:
        def async_update_device(self, device_id: str, **kwargs: str) -> None:
            device_attempts.append((device_id, kwargs))
            raise RuntimeError("registry boom")

    device_registry_mod = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry_mod.async_get = lambda _hass: _DeviceRegistry()
    device_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: (
        [types.SimpleNamespace(id="device-office")]
        if entry_id == "legacy-office"
        else []
    )
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    with caplog.at_level("ERROR", logger=integration.__name__):
        assert asyncio.run(integration.async_migrate_entry(hass, parent)) is False

    office_subentry = next(
        subentry
        for subentry in parent.subentries.values()
        if subentry.data[integration.CONF_LEGACY_ENTRY_ID] == "legacy-office"
    )
    assert office_subentry.title == "Office"
    assert duplicate.data == {
        integration.CONF_API_KEY: "shared-key",
        integration.CONF_LATITUDE: 3.0,
        integration.CONF_LONGITUDE: 4.0,
    }
    assert duplicate.version == 3
    assert hass.config_entries.removed_entries == []
    assert device_attempts == [
        (
            "device-office",
            {
                "add_config_entry_id": "legacy-home",
                "add_config_subentry_id": office_subentry.subentry_id,
            },
        )
    ]
    assert "Failed to move device device-office" in caplog.text


def test_migrate_current_duplicate_entry_is_marked_and_removed_later(
    integration_modules: _InitModules,
) -> None:
    """When the current entry is merged away, removal should be deferred."""
    integration = integration_modules.integration

    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        version=3,
        subentries={},
    )
    duplicate = _FakeEntry(
        integration,
        entry_id="legacy-office",
        title="Office",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 3.0,
            integration.CONF_LONGITUDE: 4.0,
        },
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[parent, duplicate])

    assert asyncio.run(integration.async_migrate_entry(hass, duplicate)) is True

    assert duplicate.data == {
        integration.CONF_API_KEY: "shared-key",
        "merged_into_entry_id": "legacy-home",
    }
    assert duplicate.version == integration.TARGET_ENTRY_VERSION
    assert len(hass.created_tasks) == 1
    assert hass.created_tasks[0].get_name() == (
        "remove merged pollenlevels entry legacy-office"
    )


def test_setup_entry_skips_entries_already_marked_as_merged(
    integration_modules: _InitModules,
) -> None:
    """Merged entries should not continue normal setup after migration."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        entry_id="legacy-office",
        data={
            integration.CONF_API_KEY: "shared-key",
            "merged_into_entry_id": "legacy-home",
        },
        version=integration.TARGET_ENTRY_VERSION,
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True
    assert hass.config_entries.forward_calls == []


def test_migrate_entry_normalizes_invalid_mode(
    integration_modules: _InitModules,
) -> None:
    """Migration should normalize invalid per-day sensor mode values."""
    integration = integration_modules.integration
    const = integration_modules.const

    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            integration.CONF_CREATE_FORECAST_SENSORS: "bad-value",
        },
        options={},
        version=1,
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert (
        entry.options[integration.CONF_CREATE_FORECAST_SENSORS]
        == const.FORECAST_SENSORS_CHOICES[0]
    )
    assert entry.version == integration.TARGET_ENTRY_VERSION


def test_migrate_entry_normalizes_invalid_mode_in_options(
    integration_modules: _InitModules,
) -> None:
    """Migration should normalize invalid per-day sensor mode values in options."""
    integration = integration_modules.integration
    const = integration_modules.const

    entry = _FakeEntry(
        integration,
        data={},
        options={integration.CONF_CREATE_FORECAST_SENSORS: "bad-value"},
        version=1,
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert (
        entry.options[integration.CONF_CREATE_FORECAST_SENSORS]
        == const.FORECAST_SENSORS_CHOICES[0]
    )
    assert entry.version == integration.TARGET_ENTRY_VERSION


def test_migrate_entry_normalizes_invalid_mode_in_options_when_version_current(
    integration_modules: _InitModules,
) -> None:
    """Migration should normalize invalid mode values even at the target version."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        options={integration.CONF_CREATE_FORECAST_SENSORS: "invalid-value"},
        version=integration.TARGET_ENTRY_VERSION,
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert entry.options[integration.CONF_CREATE_FORECAST_SENSORS] == "none"
    assert entry.version == integration.TARGET_ENTRY_VERSION


def test_migrate_entry_marks_version_when_no_changes(
    integration_modules: _InitModules,
) -> None:
    """Migration should still bump the version when no changes are needed."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        options={integration.CONF_CREATE_FORECAST_SENSORS: "D+1"},
        version=1,
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert entry.version == integration.TARGET_ENTRY_VERSION


def test_migrate_entry_cleans_legacy_keys_when_version_current(
    integration_modules: _InitModules,
) -> None:
    """Migration should remove legacy keys even if already at target version."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            integration.CONF_CREATE_FORECAST_SENSORS: "D+1",
            "http_referer": "https://legacy.example.com",
        },
        options={"http_referer": "https://legacy.example.com"},
        version=integration.TARGET_ENTRY_VERSION,
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert "http_referer" not in entry.data
    assert "http_referer" not in entry.options
    assert integration.CONF_CREATE_FORECAST_SENSORS not in entry.data
    assert entry.version == integration.TARGET_ENTRY_VERSION


def test_migrate_entry_does_not_downgrade_version(
    integration_modules: _InitModules,
) -> None:
    """Migration should preserve versions newer than the target."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            "http_referer": "https://legacy.example.com",
        },
        options={"http_referer": "https://legacy.example.com"},
        version=integration.TARGET_ENTRY_VERSION + 1,
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert "http_referer" not in entry.data
    assert "http_referer" not in entry.options
    assert entry.version == integration.TARGET_ENTRY_VERSION + 1


def test_migrate_entry_removes_mode_from_data_when_in_options(
    integration_modules: _InitModules,
) -> None:
    """Migration should remove per-day sensor mode from data when already in options."""
    integration = integration_modules.integration

    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            integration.CONF_CREATE_FORECAST_SENSORS: "D+1",
        },
        options={integration.CONF_CREATE_FORECAST_SENSORS: "D+1"},
        version=1,
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert integration.CONF_CREATE_FORECAST_SENSORS not in entry.data
    assert entry.options[integration.CONF_CREATE_FORECAST_SENSORS] == "D+1"


@pytest.mark.parametrize("version", [None, "x"])
def test_migrate_entry_handles_non_int_version(
    integration_modules: _InitModules, version: object
) -> None:
    """Migration should normalize non-integer versions before bumping."""
    integration = integration_modules.integration

    entry = _FakeEntry(integration, options={}, version=version)
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert entry.version == integration.TARGET_ENTRY_VERSION


def test_setup_entry_creates_repair_issue_for_invalid_location_coordinates(
    integration_modules: _InitModules,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid subentry coordinates should create a Repair issue before ConfigEntryNotReady."""
    import sys

    integration = integration_modules.integration
    registry = sys.modules["homeassistant.helpers.issue_registry"].registry

    bad_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LATITUDE: 91.123456,
            integration.CONF_LONGITUDE: 2.654321,
        },
        subentry_id="bad-location",
        title="Bad Location",
    )
    entry = _FakeEntry(
        integration,
        entry_id="entry-invalid",
        title="My Home",
        data={integration.CONF_API_KEY: "secret-key"},
        subentries={bad_subentry.subentry_id: bad_subentry},
    )
    hass = _FakeHass()

    with caplog.at_level("WARNING", logger=integration.__name__):
        with pytest.raises(integration.ConfigEntryNotReady) as exc_info:
            asyncio.run(integration.async_setup_entry(hass, entry))

    assert exc_info.value.__cause__ is None
    assert entry.runtime_data is None
    assert hass.config_entries.forward_calls == []

    expected_issue_id = integration.invalid_stored_location_issue_id(
        entry.entry_id, subentry_id=None
    )
    assert expected_issue_id in registry.issues
    issue = registry.issues[expected_issue_id]
    assert issue["domain"] == integration.DOMAIN
    assert issue["translation_key"] == "invalid_stored_location"
    assert (
        issue["severity"]
        == sys.modules["homeassistant.helpers.issue_registry"].IssueSeverity.ERROR
    )
    assert issue["is_fixable"] is False
    assert issue["is_persistent"] is False
    assert issue["translation_placeholders"]["entry_title"] == "My Home"
    assert issue["translation_placeholders"]["location_title"] == "Bad Location"
    assert "secret-key" not in caplog.text
    assert "91.123456" not in caplog.text


def test_setup_entry_creates_repair_for_later_invalid_subentry_before_refresh(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later invalid subentry should create the Repair before any coordinator is created."""
    import sys

    integration = integration_modules.integration
    registry = sys.modules["homeassistant.helpers.issue_registry"].registry

    first_subentry = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 1.0, integration.CONF_LONGITUDE: 2.0},
        subentry_id="first-location",
        title="First",
    )
    bad_subentry = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 91.0, integration.CONF_LONGITUDE: 2.0},
        subentry_id="bad-location",
        title="Bad",
    )
    entry = _FakeEntry(
        integration,
        entry_id="entry-multi",
        title="Multi Home",
        data={integration.CONF_API_KEY: "key"},
        subentries={
            first_subentry.subentry_id: first_subentry,
            bad_subentry.subentry_id: bad_subentry,
        },
    )
    hass = _FakeHass()

    def _fail_coordinator(*_args, **_kwargs):
        pytest.fail(
            "Coordinator should not be instantiated before all coordinates are validated"
        )

    monkeypatch.setattr(integration, "PollenDataUpdateCoordinator", _fail_coordinator)

    class _StubClient:
        def __init__(self, _session, _api_key):
            self.session = _session
            self.api_key = _api_key

    monkeypatch.setattr(integration, "GooglePollenApiClient", _StubClient)

    with pytest.raises(integration.ConfigEntryNotReady) as exc_info:
        asyncio.run(integration.async_setup_entry(hass, entry))

    assert exc_info.value.__cause__ is None

    expected_issue_id = integration.invalid_stored_location_issue_id(
        entry.entry_id, subentry_id=None
    )
    assert expected_issue_id in registry.issues
    assert (hass, integration.DOMAIN, expected_issue_id) not in registry.deleted
    assert entry.runtime_data is None
    assert hass.config_entries.forward_calls == []


def test_setup_entry_deletes_invalid_location_repair_issue_after_coordinates_are_valid(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid subentry coordinates should delete any prior Repair issue for that subentry."""
    import sys

    integration = integration_modules.integration
    registry = sys.modules["homeassistant.helpers.issue_registry"].registry

    good_subentry = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 1.0, integration.CONF_LONGITUDE: 2.0},
        subentry_id="good-location",
        title="Good",
    )
    entry = _FakeEntry(
        integration,
        entry_id="entry-valid",
        title="Valid Home",
        data={integration.CONF_API_KEY: "key"},
        subentries={good_subentry.subentry_id: good_subentry},
    )
    hass = _FakeHass()

    class _StubCoordinator:
        def __init__(self, *args, **kwargs):
            self.api_key = kwargs["api_key"]
            self.lat = kwargs["lat"]
            self.lon = kwargs["lon"]
            self.entry_id = kwargs["entry_id"]
            self.entry_title = kwargs.get("entry_title")
            self.data = {"region": {"source": "meta"}, "date": {"source": "meta"}}
            self.last_updated = None

        async def async_config_entry_first_refresh(self):
            return None

    monkeypatch.setattr(integration, "PollenDataUpdateCoordinator", _StubCoordinator)

    class _StubClient:
        def __init__(self, _session, _api_key):
            self.session = _session
            self.api_key = _api_key

        async def async_fetch_pollen_data(self, **_kwargs):
            return {"region": {"source": "meta"}, "dailyInfo": []}

    monkeypatch.setattr(integration, "GooglePollenApiClient", _StubClient)

    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True

    expected_issue_id = integration.invalid_stored_location_issue_id(
        entry.entry_id, subentry_id=None
    )
    assert (hass, integration.DOMAIN, expected_issue_id) in registry.deleted


def test_setup_entry_removes_entry_level_repair_issue_when_no_invalid_subentries(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-existing entry-level Repair should be cleaned up when setup runs with valid subentries."""
    import sys

    integration = integration_modules.integration
    registry = sys.modules["homeassistant.helpers.issue_registry"].registry

    existing_issue_id = integration.invalid_stored_location_issue_id(
        "entry-clean", subentry_id=None
    )
    registry.async_create_issue(
        None,
        integration.DOMAIN,
        existing_issue_id,
        is_fixable=False,
        is_persistent=False,
        severity="error",
        translation_key="invalid_stored_location",
        translation_placeholders={"entry_title": "Old", "location_title": "Old"},
    )
    assert existing_issue_id in registry.issues

    good_subentry = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 1.0, integration.CONF_LONGITUDE: 2.0},
        subentry_id="good-location",
        title="Good",
    )
    entry = _FakeEntry(
        integration,
        entry_id="entry-clean",
        title="Clean Home",
        data={integration.CONF_API_KEY: "key"},
        subentries={good_subentry.subentry_id: good_subentry},
    )
    hass = _FakeHass()

    class _StubCoordinator:
        def __init__(self, *args, **kwargs):
            self.api_key = kwargs["api_key"]
            self.lat = kwargs["lat"]
            self.lon = kwargs["lon"]
            self.entry_id = kwargs["entry_id"]
            self.entry_title = kwargs.get("entry_title")
            self.data = {"region": {"source": "meta"}, "date": {"source": "meta"}}
            self.last_updated = None

        async def async_config_entry_first_refresh(self):
            return None

    monkeypatch.setattr(integration, "PollenDataUpdateCoordinator", _StubCoordinator)

    class _StubClient:
        def __init__(self, _session, _api_key):
            self.session = _session
            self.api_key = _api_key

        async def async_fetch_pollen_data(self, **_kwargs):
            return {"region": {"source": "meta"}, "dailyInfo": []}

    monkeypatch.setattr(integration, "GooglePollenApiClient", _StubClient)

    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True
    assert (hass, integration.DOMAIN, existing_issue_id) in registry.deleted
    assert existing_issue_id not in registry.issues


def test_setup_entry_does_not_create_repair_issue_for_temporal_refresh_failure(
    integration_modules: _InitModules,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A temporal ConfigEntryNotReady from refresh should NOT create a Repair issue."""
    import sys

    integration = integration_modules.integration
    registry = sys.modules["homeassistant.helpers.issue_registry"].registry

    good_subentry = integration.ConfigSubentry(
        data={integration.CONF_LATITUDE: 1.0, integration.CONF_LONGITUDE: 2.0},
        subentry_id="temp-location",
        title="Temp",
    )
    entry = _FakeEntry(
        integration,
        entry_id="entry-temp",
        title="Temp Home",
        data={integration.CONF_API_KEY: "key"},
        subentries={good_subentry.subentry_id: good_subentry},
    )
    hass = _FakeHass()

    class _FailingCoordinator:
        def __init__(self, *args, **kwargs):
            self.api_key = kwargs["api_key"]
            self.lat = kwargs["lat"]
            self.lon = kwargs["lon"]
            self.entry_id = kwargs["entry_id"]
            self.entry_title = kwargs.get("entry_title")
            self.data = {"region": {"source": "meta"}, "date": {"source": "meta"}}
            self.last_updated = None

        async def async_config_entry_first_refresh(self):
            raise integration.ConfigEntryNotReady("temporal API failure")

    monkeypatch.setattr(integration, "PollenDataUpdateCoordinator", _FailingCoordinator)

    class _StubClient:
        def __init__(self, _session, _api_key):
            self.session = _session
            self.api_key = _api_key

    monkeypatch.setattr(integration, "GooglePollenApiClient", _StubClient)

    with caplog.at_level("WARNING", logger=integration.__name__):
        with pytest.raises(integration.ConfigEntryNotReady) as exc_info:
            asyncio.run(integration.async_setup_entry(hass, entry))

    assert exc_info.value.__cause__ is None
    assert entry.runtime_data is None
    assert registry.issues == {}
    assert "Invalid coordinates" not in caplog.text
