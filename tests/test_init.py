"""Tests for integration setup exception handling."""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import config_flow test module to reuse its Home Assistant stubs.
import tests.test_config_flow  # noqa: E402,F401  # pylint: disable=unused-import

# Provide the additional stubs required by __init__.
sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))

core_mod = types.ModuleType("homeassistant.core")


class _StubHomeAssistant:  # pragma: no cover - structure only
    pass


class _StubServiceCall:  # pragma: no cover - structure only
    pass


core_mod.HomeAssistant = _StubHomeAssistant
core_mod.ServiceCall = _StubServiceCall
sys.modules.setdefault("homeassistant.core", core_mod)

ha_components_mod = sys.modules.get("homeassistant.components") or types.ModuleType(
    "homeassistant.components"
)
sys.modules["homeassistant.components"] = ha_components_mod

sensor_mod = types.ModuleType("homeassistant.components.sensor")


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


sensor_mod.SensorEntity = _StubSensorEntity
sensor_mod.SensorDeviceClass = _StubSensorDeviceClass
sensor_mod.SensorStateClass = _StubSensorStateClass
sys.modules.setdefault("homeassistant.components.sensor", sensor_mod)

const_mod = sys.modules.get("homeassistant.const") or types.ModuleType(
    "homeassistant.const"
)
const_mod.ATTR_ATTRIBUTION = "Attribution"
sys.modules["homeassistant.const"] = const_mod

aiohttp_client_mod = types.ModuleType("homeassistant.helpers.aiohttp_client")
aiohttp_client_mod.async_get_clientsession = lambda _hass: None
sys.modules.setdefault("homeassistant.helpers.aiohttp_client", aiohttp_client_mod)

aiohttp_mod = sys.modules.get("aiohttp") or types.ModuleType("aiohttp")


class _StubClientError(Exception):
    pass


class _StubClientSession:  # pragma: no cover - structure only
    pass


class _StubClientTimeout:
    def __init__(self, total: float | None = None):
        self.total = total


aiohttp_mod.ClientError = _StubClientError
aiohttp_mod.ClientSession = _StubClientSession
aiohttp_mod.ClientTimeout = _StubClientTimeout
sys.modules["aiohttp"] = aiohttp_mod

cv_mod = sys.modules["homeassistant.helpers.config_validation"]
cv_mod.config_entry_only_config_schema = lambda _domain: lambda config: config

vol_mod = sys.modules["voluptuous"]
if not hasattr(vol_mod, "Schema"):
    vol_mod.Schema = lambda *args, **kwargs: None

helpers_mod = sys.modules.get("homeassistant.helpers") or types.ModuleType(
    "homeassistant.helpers"
)
sys.modules["homeassistant.helpers"] = helpers_mod

entity_registry_mod = types.ModuleType("homeassistant.helpers.entity_registry")


def _stub_async_get(_hass):  # pragma: no cover - structure only
    class _Registry:
        @staticmethod
        def async_entries_for_config_entry(_registry, _entry_id):
            return []

    return _Registry()


entity_registry_mod.async_get = _stub_async_get
entity_registry_mod.async_entries_for_config_entry = lambda *args, **kwargs: []
sys.modules.setdefault("homeassistant.helpers.entity_registry", entity_registry_mod)

entity_mod = types.ModuleType("homeassistant.helpers.entity")


class _StubEntityCategory:
    DIAGNOSTIC = "diagnostic"


entity_mod.EntityCategory = _StubEntityCategory
sys.modules.setdefault("homeassistant.helpers.entity", entity_mod)

dt_mod = types.ModuleType("homeassistant.util.dt")


def _stub_utcnow():
    from datetime import UTC, datetime

    return datetime.now(UTC)


dt_mod.utcnow = _stub_utcnow


def _stub_parse_http_date(value: str | None):  # pragma: no cover - stub only
    from datetime import UTC, datetime
    from email.utils import parsedate_to_datetime

    try:
        parsed = parsedate_to_datetime(value) if value is not None else None
    except (TypeError, ValueError, IndexError):
        return None

    if parsed is None:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)

    if isinstance(parsed, datetime):
        return parsed

    return None


dt_mod.parse_http_date = _stub_parse_http_date
sys.modules.setdefault("homeassistant.util.dt", dt_mod)

util_mod = types.ModuleType("homeassistant.util")
util_mod.dt = dt_mod
sys.modules.setdefault("homeassistant.util", util_mod)

exceptions_mod = sys.modules.setdefault(
    "homeassistant.exceptions", types.ModuleType("homeassistant.exceptions")
)
if not hasattr(exceptions_mod, "ConfigEntryNotReady"):

    class _StubConfigEntryNotReady(Exception):
        pass

    exceptions_mod.ConfigEntryNotReady = _StubConfigEntryNotReady
if not hasattr(exceptions_mod, "ConfigEntryAuthFailed"):

    class _StubConfigEntryAuthFailed(Exception):
        pass

    exceptions_mod.ConfigEntryAuthFailed = _StubConfigEntryAuthFailed

update_coordinator_mod = types.ModuleType("homeassistant.helpers.update_coordinator")


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


update_coordinator_mod.DataUpdateCoordinator = _StubDataUpdateCoordinator
update_coordinator_mod.UpdateFailed = _StubUpdateFailed
update_coordinator_mod.CoordinatorEntity = _StubCoordinatorEntity
sys.modules.setdefault(
    "homeassistant.helpers.update_coordinator", update_coordinator_mod
)

integration = importlib.import_module(
    "custom_components.pollenlevels.__init__"
)  # noqa: E402
const = importlib.import_module("custom_components.pollenlevels.const")  # noqa: E402


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

    async def async_reload(self, entry_id: str):  # pragma: no cover - used in tests
        self.reload_calls.append(entry_id)

    def async_entries(self, domain: str | None = None):
        if domain is None:
            return list(self._entries)
        return [
            entry for entry in self._entries if getattr(entry, "domain", None) == domain
        ]


class _FakeEntry:
    def __init__(
        self,
        *,
        entry_id: str = "entry-1",
        title: str = "Pollen Levels",
        data: dict | None = None,
        options: dict | None = None,
        version: int = 1,
    ):
        self.entry_id = entry_id
        self.title = title
        self.domain = integration.DOMAIN
        self._update_listener = None
        self.data = data or {
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        }
        self.options = options or {}
        self.version = version
        self.runtime_data = None

    def add_update_listener(self, listener):
        self._update_listener = listener
        return listener

    def async_on_unload(self, callback):
        # Store callbacks to mirror Home Assistant behavior during tests.
        self._on_unload = callback  # pragma: no cover - stored for completeness
        return callback


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


class _ServiceRegistry:
    def __init__(self):
        self.registered: dict[tuple[str, str], Any] = {}

    def async_register(self, domain: str, service: str, handler, schema=None):
        self.registered[(domain, service)] = handler

    async def async_call(self, domain: str, service: str):
        handler = self.registered[(domain, service)]
        await handler(_StubServiceCall())


def test_setup_entry_propagates_auth_failed() -> None:
    """ConfigEntryAuthFailed should bubble up for reauthentication."""

    hass = _FakeHass(forward_exception=integration.ConfigEntryAuthFailed("bad key"))
    entry = _FakeEntry()

    with pytest.raises(integration.ConfigEntryAuthFailed):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_missing_api_key_raises_auth_failed() -> None:
    """Missing API key should trigger ConfigEntryAuthFailed."""

    hass = _FakeHass()
    entry = _FakeEntry(
        data={
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        }
    )

    with pytest.raises(integration.ConfigEntryAuthFailed):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_wraps_generic_error() -> None:
    """Unexpected errors convert to ConfigEntryNotReady for retries."""

    class _Boom(Exception):
        pass

    hass = _FakeHass(forward_exception=_Boom("boom"))
    entry = _FakeEntry()

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_success_and_unload() -> None:
    """Happy path should forward setup, register listener, and unload cleanly."""

    hass = _FakeHass()
    entry = _FakeEntry()

    class _StubClient:
        def __init__(self, _session, _api_key):
            self.session = _session
            self.api_key = _api_key

        async def async_fetch_pollen_data(self, **_kwargs):
            return {"region": {"source": "meta"}, "dailyInfo": []}

    class _StubCoordinator(update_coordinator_mod.DataUpdateCoordinator):
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

    integration.GooglePollenApiClient = _StubClient
    integration.PollenDataUpdateCoordinator = _StubCoordinator

    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True

    assert hass.config_entries.forward_calls == [(entry, ["sensor"])]
    assert entry._update_listener is integration._update_listener  # noqa: SLF001
    assert entry._on_unload is entry._update_listener  # noqa: SLF001

    assert entry.runtime_data is not None
    assert entry.runtime_data.coordinator.entry_id == entry.entry_id

    asyncio.run(entry._update_listener(hass, entry))  # noqa: SLF001
    assert hass.config_entries.reload_calls == [entry.entry_id]

    assert asyncio.run(integration.async_unload_entry(hass, entry)) is True
    assert hass.config_entries.unload_calls == [(entry, ["sensor"])]
    assert entry.runtime_data is None


def test_force_update_requests_refresh_per_entry() -> None:
    """force_update should queue refresh via runtime_data coordinators and skip missing runtime data."""

    class _StubCoordinator:
        def __init__(self):
            self.calls: list[str] = []

        async def _mark(self):
            self.calls.append("refresh")

        async def async_refresh(self):
            await self._mark()

        def async_request_refresh(self):
            return asyncio.create_task(self._mark())

    entry1 = _FakeEntry(entry_id="entry-1")
    entry1.runtime_data = types.SimpleNamespace(coordinator=_StubCoordinator())
    entry2 = _FakeEntry(entry_id="entry-2")
    entry2.runtime_data = types.SimpleNamespace(coordinator=_StubCoordinator())
    entry3 = _FakeEntry(entry_id="entry-3")
    entry3.runtime_data = None

    hass = _FakeHass(entries=[entry1, entry2, entry3])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    assert (integration.DOMAIN, "force_update") in hass.services.registered

    asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert entry1.runtime_data.coordinator.calls == ["refresh"]
    assert entry2.runtime_data.coordinator.calls == ["refresh"]


def test_migrate_entry_moves_mode_to_options() -> None:
    """Migration should copy per-day sensor mode from data to options."""
    entry = _FakeEntry(
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
    assert entry.version == 3


def test_migrate_entry_normalizes_invalid_mode() -> None:
    """Migration should normalize invalid per-day sensor mode values."""
    entry = _FakeEntry(
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
    assert entry.version == 3


def test_migrate_entry_normalizes_invalid_mode_in_options() -> None:
    """Migration should normalize invalid per-day sensor mode values in options."""
    entry = _FakeEntry(
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
    assert entry.version == 3


def test_migrate_entry_normalizes_invalid_mode_in_options_when_version_current() -> (
    None
):
    """Migration should normalize invalid mode values even at the target version."""
    entry = _FakeEntry(
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


def test_migrate_entry_marks_version_when_no_changes() -> None:
    """Migration should still bump the version when no changes are needed."""
    entry = _FakeEntry(
        options={integration.CONF_CREATE_FORECAST_SENSORS: "D+1"},
        version=1,
    )
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert entry.version == 3


def test_migrate_entry_cleans_legacy_keys_when_version_current() -> None:
    """Migration should remove legacy keys even if already at target version."""
    entry = _FakeEntry(
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


def test_migrate_entry_does_not_downgrade_version() -> None:
    """Migration should preserve versions newer than the target."""
    entry = _FakeEntry(
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


def test_migrate_entry_removes_mode_from_data_when_in_options() -> None:
    """Migration should remove per-day sensor mode from data when already in options."""
    entry = _FakeEntry(
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
def test_migrate_entry_handles_non_int_version(version: object) -> None:
    """Migration should normalize non-integer versions before bumping."""
    entry = _FakeEntry(options={}, version=version)
    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_migrate_entry(hass, entry)) is True
    assert entry.version == 3
