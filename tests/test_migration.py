"""Tests for migration Repair issue creation for invalid stored locations."""

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
class _MigrateModules:
    integration: types.ModuleType
    const: types.ModuleType
    migration: types.ModuleType
    issue_helpers: types.ModuleType


def _stub_async_get(_hass):
    class _Registry:
        @staticmethod
        def async_entries_for_config_entry(_registry, _entry_id):
            return []

    return _Registry()


class _StubConfigEntry:
    @classmethod
    def __class_getitem__(cls, _item):
        return cls


class _StubHomeAssistant:
    pass


class _StubServiceCall:
    pass


class _StubSensorEntity:
    def __init__(self, *args, **kwargs):
        self._attr_unique_id = None
        self._attr_device_info = None

    @property
    def unique_id(self):
        return getattr(self, "_attr_unique_id", None)

    @property
    def device_info(self):
        return getattr(self, "_attr_device_info", None)


class _StubSensorDeviceClass:
    DATE = "date"
    TIMESTAMP = "timestamp"


class _StubSensorStateClass:
    MEASUREMENT = "measurement"


class _StubEntityCategory:
    DIAGNOSTIC = "diagnostic"


class _StubUpdateFailed(Exception):
    pass


class _StubCoordinatorEntity:
    pass


class _StubDataUpdateCoordinator:
    pass


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


class _StubConfigEntryNotReady(Exception):
    pass


class _StubConfigEntryAuthFailed(Exception):
    pass


def _ha_stubs_config_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install ConfigEntry and ConfigSubentry stubs."""
    stub_config_entry_class(_StubConfigEntry, monkeypatch=monkeypatch)
    config_entries_mod = sys.modules["homeassistant.config_entries"]
    config_entries_mod.ConfigSubentry = _StubConfigSubentry


class _FakeConfigEntries:
    def __init__(
        self,
        entries: list[object] | None = None,
    ):
        self.forward_calls: list[tuple[object, list[str]]] = []
        self.added_subentries: list[tuple[object, object]] = []
        self.removed_entries: list[str] = []
        self._entries = entries or []

    async def async_forward_entry_setups(self, entry, platforms):
        self.forward_calls.append((entry, platforms))

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
            e for e in self._entries if getattr(e, "entry_id", None) != entry_id
        ]
        return {"require_restart": False}

    def async_get_entry(self, entry_id: str):
        return next(
            (e for e in self._entries if getattr(e, "entry_id", None) == entry_id),
            None,
        )

    def async_entries(self, domain: str | None = None):
        if domain is None:
            return list(self._entries)
        return [e for e in self._entries if getattr(e, "domain", None) == domain]


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


class _FakeHass:
    def __init__(
        self,
        *,
        entries: list[object] | None = None,
    ):
        self.config_entries = _FakeConfigEntries(
            entries=entries,
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

    def async_register(self, domain: str, service: str, handler, schema=None):
        self.registered[(domain, service)] = handler


@pytest.fixture
def stub_migration_ha_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install HA stubs needed by migration module imports."""
    clear_integration_modules(monkeypatch=monkeypatch)
    stub_custom_components_packages(root=ROOT, monkeypatch=monkeypatch)
    stub_homeassistant_package(monkeypatch=monkeypatch)
    _ha_stubs_config_entries(monkeypatch=monkeypatch)

    core_mod = types.ModuleType("homeassistant.core")
    core_mod.HomeAssistant = _StubHomeAssistant
    core_mod.ServiceCall = _StubServiceCall
    monkeypatch.setitem(sys.modules, "homeassistant.core", core_mod)

    cv_mod = types.ModuleType("homeassistant.helpers.config_validation")
    cv_mod.config_entry_only_config_schema = lambda _domain: lambda config: config
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.config_validation", cv_mod)

    vol_mod = types.ModuleType("voluptuous")
    monkeypatch.setitem(sys.modules, "voluptuous", vol_mod)
    vol_mod.Schema = lambda *args, **kwargs: None

    stub_aiohttp_module(monkeypatch=monkeypatch)

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

    helpers_mod = types.ModuleType("homeassistant.helpers")
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers_mod)

    entity_mod = types.ModuleType("homeassistant.helpers.entity")
    entity_mod.EntityCategory = _StubEntityCategory
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.entity", entity_mod)

    entity_registry_mod = types.ModuleType("homeassistant.helpers.entity_registry")
    entity_registry_mod.async_get = _stub_async_get
    entity_registry_mod.async_entries_for_config_entry = lambda *args, **kwargs: []
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.entity_registry", entity_registry_mod
    )

    stub_update_coordinator_module(
        update_failed=_StubUpdateFailed,
        data_update_coordinator=_StubDataUpdateCoordinator,
        coordinator_entity=_StubCoordinatorEntity,
        monkeypatch=monkeypatch,
    )
    stub_util_dt_module(monkeypatch=monkeypatch)
    stub_exceptions(
        ConfigEntryNotReady=_StubConfigEntryNotReady,
        ConfigEntryAuthFailed=_StubConfigEntryAuthFailed,
        monkeypatch=monkeypatch,
    )
    stub_issue_registry_module(monkeypatch=monkeypatch)


@pytest.fixture
def migration_modules(
    monkeypatch: pytest.MonkeyPatch, stub_migration_ha_modules: None
) -> _MigrateModules:
    """Import integration modules only after stubs are installed."""
    clear_integration_modules(monkeypatch=monkeypatch)
    const = importlib.import_module("custom_components.pollenlevels.const")
    issue_helpers = importlib.import_module(
        "custom_components.pollenlevels.issue_helpers"
    )
    migration = importlib.import_module("custom_components.pollenlevels.migration")
    integration = importlib.import_module("custom_components.pollenlevels")
    return _MigrateModules(
        integration=integration,
        const=const,
        migration=migration,
        issue_helpers=issue_helpers,
    )


def test_migration_removes_forecast_days_without_repair_issue(
    migration_modules: _MigrateModules,
) -> None:
    """Legacy forecast-day storage should be removed silently."""
    integration = migration_modules.integration
    registry = sys.modules["homeassistant.helpers.issue_registry"].registry

    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            integration.CONF_FORECAST_DAYS: 3,
        },
        options={integration.CONF_FORECAST_DAYS: 3},
        version=3,
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert integration.CONF_FORECAST_DAYS not in entry.data
    assert integration.CONF_FORECAST_DAYS not in entry.options
    assert (
        migration_modules.issue_helpers.PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID
        not in registry.issues
    )


def test_migration_removes_per_day_option_and_creates_repair_issue(
    migration_modules: _MigrateModules,
) -> None:
    """Legacy per-day sensor storage should be removed with a Repair warning."""
    integration = migration_modules.integration
    registry = sys.modules["homeassistant.helpers.issue_registry"].registry

    entry = _FakeEntry(
        integration,
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
            integration.CONF_CREATE_FORECAST_SENSORS: "D+1",
        },
        options={
            integration.CONF_FORECAST_DAYS: 3,
            integration.CONF_CREATE_FORECAST_SENSORS: "D+1+2",
        },
        version=3,
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert integration.CONF_CREATE_FORECAST_SENSORS not in entry.data
    assert integration.CONF_CREATE_FORECAST_SENSORS not in entry.options
    assert integration.CONF_FORECAST_DAYS not in entry.options
    issue = registry.issues[
        migration_modules.issue_helpers.PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID
    ]
    assert issue["domain"] == integration.DOMAIN
    assert issue["translation_key"] == "per_day_forecast_sensors_removed"
    assert issue["is_fixable"] is False
    assert issue["is_persistent"] is True
    assert issue["severity"] == migration_modules.issue_helpers.ir.IssueSeverity.WARNING


def test_migration_creates_repair_issue_for_invalid_legacy_coordinates(
    migration_modules: _MigrateModules,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Legacy entry with invalid coordinates should create a Repair and abort migration."""
    integration = migration_modules.integration
    registry = sys.modules["homeassistant.helpers.issue_registry"].registry

    entry = _FakeEntry(
        integration,
        entry_id="legacy-corrupt",
        title="Corrupt Legacy",
        data={
            integration.CONF_API_KEY: "secret-key",
            integration.CONF_LATITUDE: "not-a-number",
            integration.CONF_LONGITUDE: 2.0,
        },
        options={},
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[entry])

    with caplog.at_level("ERROR", logger=integration.__name__):
        result = asyncio.run(integration.async_migrate_entry(hass, entry))

    assert result is False
    assert entry.version == 3
    assert entry.subentries == {}
    assert hass.config_entries.added_subentries == []

    expected_issue_id = integration.invalid_stored_location_issue_id(
        entry.entry_id, subentry_id=None
    )
    assert expected_issue_id in registry.issues
    issue = registry.issues[expected_issue_id]
    assert issue["domain"] == integration.DOMAIN
    assert issue["translation_key"] == "invalid_stored_location"
    assert issue["translation_placeholders"]["entry_title"] == "Corrupt Legacy"
    assert "secret-key" not in caplog.text
    assert "not-a-number" not in caplog.text


def test_migration_creates_repair_issue_for_unmigratable_location_subentries(
    migration_modules: _MigrateModules,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Corrupt location subentry should create a Repair and abort migration."""
    integration = migration_modules.integration
    registry = sys.modules["homeassistant.helpers.issue_registry"].registry

    corrupt_subentry = integration.ConfigSubentry(
        data={
            integration.CONF_LEGACY_ENTRY_ID: "legacy-corrupt",
        },
        subentry_id="corrupt-location",
        title="Corrupt Sub",
    )
    entry = _FakeEntry(
        integration,
        entry_id="legacy-corrupt",
        title="Corrupt Entry",
        data={integration.CONF_API_KEY: "secret-key"},
        options={},
        version=integration.TARGET_ENTRY_VERSION - 1,
        subentries={corrupt_subentry.subentry_id: corrupt_subentry},
        unique_id=integration.api_key_unique_id("secret-key"),
    )
    hass = _FakeHass(entries=[entry])

    with caplog.at_level("ERROR", logger=integration.__name__):
        result = asyncio.run(integration.async_migrate_entry(hass, entry))

    assert result is False
    assert entry.version == integration.TARGET_ENTRY_VERSION - 1
    assert entry.subentries == {corrupt_subentry.subentry_id: corrupt_subentry}
    assert hass.config_entries.added_subentries == []

    expected_issue_id = integration.invalid_stored_location_issue_id(
        entry.entry_id, subentry_id=None
    )
    assert expected_issue_id in registry.issues
    issue = registry.issues[expected_issue_id]
    assert issue["domain"] == integration.DOMAIN
    assert issue["translation_key"] == "invalid_stored_location"
    assert issue["translation_placeholders"]["entry_title"] == "Corrupt Entry"
    assert "secret-key" not in caplog.text


def test_migration_deletes_repair_issue_after_successful_migration(
    migration_modules: _MigrateModules,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Successful single-entry migration should delete the legacy Repair issue."""
    integration = migration_modules.integration
    registry = sys.modules["homeassistant.helpers.issue_registry"].registry

    entry = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        },
        options={},
        version=3,
        subentries={},
        unique_id="1.0000_2.0000",
    )
    hass = _FakeHass(entries=[entry])

    with caplog.at_level("INFO", logger=integration.__name__):
        result = asyncio.run(integration.async_migrate_entry(hass, entry))

    assert result is True

    expected_issue_id = integration.invalid_stored_location_issue_id(
        entry.entry_id, subentry_id=None
    )
    assert (hass, integration.DOMAIN, expected_issue_id) in registry.deleted


def test_migration_deletes_repair_issue_for_each_source_in_grouped_migration(
    migration_modules: _MigrateModules,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Successful grouped migration should delete the legacy Repair for every source."""
    integration = migration_modules.integration
    registry = sys.modules["homeassistant.helpers.issue_registry"].registry

    parent = _FakeEntry(
        integration,
        entry_id="legacy-home",
        title="Home",
        data={
            integration.CONF_API_KEY: "shared-key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
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
        },
        options={},
        version=3,
        subentries={},
    )
    hass = _FakeHass(entries=[parent, duplicate])

    with caplog.at_level("INFO", logger=integration.__name__):
        result = asyncio.run(integration.async_migrate_entry(hass, parent))

    assert result is True

    expected_parent_issue_id = integration.invalid_stored_location_issue_id(
        parent.entry_id, subentry_id=None
    )
    expected_office_issue_id = integration.invalid_stored_location_issue_id(
        duplicate.entry_id, subentry_id=None
    )
    assert (hass, integration.DOMAIN, expected_parent_issue_id) in registry.deleted
    assert (hass, integration.DOMAIN, expected_office_issue_id) in registry.deleted
    assert "shared-key" not in caplog.text
