"""Tests for integration setup exception handling."""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from tests._ha_stubs import (
    clear_integration_modules,
    stub_config_entry_class,
    stub_custom_components_packages,
    stub_exceptions,
    stub_homeassistant_package,
    stub_update_coordinator_module,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

integration = None
const = None
_BaseDataUpdateCoordinator = None


class _StubConfigEntry:
    @classmethod
    def __class_getitem__(cls, _item):
        return cls


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


class _StubClientError(Exception):
    pass


class _StubClientSession:  # pragma: no cover - structure only
    pass


class _StubClientTimeout:
    def __init__(self, total: float | None = None):
        self.total = total


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


def _stub_utcnow():
    from datetime import UTC, datetime

    return datetime.now(UTC)


def _stub_parse_http_date(value: str | None):  # pragma: no cover - stub only
    from datetime import UTC, datetime
    from email.utils import parsedate_to_datetime

    try:
        parsed = parsedate_to_datetime(value) if value is not None else None
    except TypeError, ValueError, IndexError:
        return None

    if parsed is None:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)

    if isinstance(parsed, datetime):
        return parsed

    return None


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
    aiohttp_mod = types.ModuleType("aiohttp")
    aiohttp_mod.ClientError = _StubClientError
    aiohttp_mod.ClientSession = _StubClientSession
    aiohttp_mod.ClientTimeout = _StubClientTimeout
    aiohttp_mod.ContentTypeError = ValueError
    monkeypatch.setitem(sys.modules, "aiohttp", aiohttp_mod)

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
    dt_mod = types.ModuleType("homeassistant.util.dt")
    dt_mod.utcnow = _stub_utcnow
    dt_mod.parse_http_date = _stub_parse_http_date
    monkeypatch.setitem(sys.modules, "homeassistant.util.dt", dt_mod)

    util_mod = types.ModuleType("homeassistant.util")
    util_mod.dt = dt_mod
    monkeypatch.setitem(sys.modules, "homeassistant.util", util_mod)
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


@pytest.fixture(autouse=True)
def integration_modules(stub_init_ha_modules: None):
    """Import integration modules only after stubs are installed."""
    global integration, const, _BaseDataUpdateCoordinator
    integration = importlib.import_module("custom_components.pollenlevels.__init__")
    const = importlib.import_module("custom_components.pollenlevels.const")
    _BaseDataUpdateCoordinator = _StubDataUpdateCoordinator
    return integration, const


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
        self.data = data or {
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        }
        self.options = options or {}
        self.version = version
        self.runtime_data = None


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
        self.schemas: dict[tuple[str, str], Any] = {}

    def async_register(self, domain: str, service: str, handler, schema=None):
        key = (domain, service)
        self.registered[key] = handler
        self.schemas[key] = schema

    async def async_call(self, domain: str, service: str):
        handler = self.registered[(domain, service)]
        await handler(_StubServiceCall())


def test_setup_entry_propagates_auth_failed() -> None:
    """ConfigEntryAuthFailed should bubble up for reauthentication."""

    hass = _FakeHass(forward_exception=integration.ConfigEntryAuthFailed("bad key"))
    entry = _FakeEntry()

    with pytest.raises(integration.ConfigEntryAuthFailed):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_clears_runtime_data_on_forward_auth_failed() -> None:
    """runtime_data is cleared when forwarding raises ConfigEntryAuthFailed."""

    hass = _FakeHass(forward_exception=integration.ConfigEntryAuthFailed("bad key"))
    entry = _FakeEntry()

    with pytest.raises(integration.ConfigEntryAuthFailed):
        asyncio.run(integration.async_setup_entry(hass, entry))

    assert entry.runtime_data is None


def test_setup_entry_clears_runtime_data_on_forward_not_ready() -> None:
    """runtime_data is cleared when forwarding raises ConfigEntryNotReady."""

    hass = _FakeHass(forward_exception=integration.ConfigEntryNotReady("retry"))
    entry = _FakeEntry()

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))

    assert entry.runtime_data is None


def test_setup_entry_clears_runtime_data_on_forward_generic_error() -> None:
    """runtime_data is cleared when forwarding raises an unexpected exception."""

    class _Boom(Exception):
        pass

    hass = _FakeHass(forward_exception=_Boom("boom"))
    entry = _FakeEntry()

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))

    assert entry.runtime_data is None


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


def test_setup_entry_whitespace_api_key_raises_auth_failed() -> None:
    """Whitespace-only API key should trigger ConfigEntryAuthFailed."""

    hass = _FakeHass()
    entry = _FakeEntry(
        data={
            integration.CONF_API_KEY: "   ",
            integration.CONF_LATITUDE: 1.0,
            integration.CONF_LONGITUDE: 2.0,
        }
    )

    with pytest.raises(integration.ConfigEntryAuthFailed):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_invalid_coordinates_raise_not_ready() -> None:
    """Invalid coordinates should trigger ConfigEntryNotReady."""

    hass = _FakeHass()
    entry = _FakeEntry(
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: "not-a-number",
            integration.CONF_LONGITUDE: 2.0,
        }
    )

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_invalid_coordinates_do_not_log_precise_values(caplog) -> None:
    """Invalid coordinates should fail without logging precise coordinate values."""

    hass = _FakeHass()
    entry = _FakeEntry(
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: 91.123456,
            integration.CONF_LONGITUDE: 2.654321,
        }
    )

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))

    log_text = caplog.text
    assert "91.123456" not in log_text
    assert "2.654321" not in log_text


def test_setup_entry_nonfinite_or_out_of_range_coordinates_raise_not_ready() -> None:
    """Non-finite or out-of-range coordinates should trigger ConfigEntryNotReady."""

    bad_pairs = [
        (float("inf"), 2.0),
        (1.0, float("nan")),
        (91.0, 2.0),
        (1.0, 181.0),
    ]

    for lat, lon in bad_pairs:
        hass = _FakeHass()
        entry = _FakeEntry(
            data={
                integration.CONF_API_KEY: "key",
                integration.CONF_LATITUDE: lat,
                integration.CONF_LONGITUDE: lon,
            }
        )

        with pytest.raises(integration.ConfigEntryNotReady):
            asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_boolean_coordinates_raise_not_ready() -> None:
    """Boolean coordinates should trigger ConfigEntryNotReady."""

    hass = _FakeHass()
    entry = _FakeEntry(
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: True,
            integration.CONF_LONGITUDE: 2.0,
        }
    )

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_numeric_string_coordinates_are_allowed() -> None:
    """Numeric string coordinates should still set up normally."""

    hass = _FakeHass()
    entry = _FakeEntry(
        data={
            integration.CONF_API_KEY: "key",
            integration.CONF_LATITUDE: "1.5",
            integration.CONF_LONGITUDE: "2.5",
        }
    )

    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True
    assert entry.runtime_data is not None
    assert entry.runtime_data.coordinator.lat == pytest.approx(1.5)
    assert entry.runtime_data.coordinator.lon == pytest.approx(2.5)


def test_setup_entry_boundary_coordinates_are_allowed() -> None:
    """Coordinate values on valid boundaries should still set up successfully."""

    for lat, lon in [(-90.0, -180.0), (90.0, 180.0)]:
        hass = _FakeHass()
        entry = _FakeEntry(
            data={
                integration.CONF_API_KEY: "key",
                integration.CONF_LATITUDE: lat,
                integration.CONF_LONGITUDE: lon,
            }
        )

        assert asyncio.run(integration.async_setup_entry(hass, entry)) is True


def test_setup_entry_decimal_numeric_options_fallback_to_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decimal options should not be truncated silently during setup."""

    hass = _FakeHass()
    entry = _FakeEntry(
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

    class _StubCoordinator(_BaseDataUpdateCoordinator):
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


def test_setup_entry_wraps_generic_error() -> None:
    """Unexpected errors convert to ConfigEntryNotReady for retries."""

    class _Boom(Exception):
        pass

    hass = _FakeHass(forward_exception=_Boom("boom"))
    entry = _FakeEntry()

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_success_and_unload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path should forward setup and unload cleanly."""

    hass = _FakeHass()
    entry = _FakeEntry()

    class _StubClient:
        def __init__(self, _session, _api_key):
            self.session = _session
            self.api_key = _api_key

        async def async_fetch_pollen_data(self, **_kwargs):
            return {"region": {"source": "meta"}, "dailyInfo": []}

    class _StubCoordinator(_BaseDataUpdateCoordinator):
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should normalize stored forecast mode values before coordinator flags."""

    hass = _FakeHass()
    entry = _FakeEntry(options={integration.CONF_CREATE_FORECAST_SENSORS: " D+1 "})

    class _StubClient:
        def __init__(self, _session, _api_key):
            self.session = _session
            self.api_key = _api_key

        async def async_fetch_pollen_data(self, **_kwargs):
            return {"region": {"source": "meta"}, "dailyInfo": []}

    class _StubCoordinator(_BaseDataUpdateCoordinator):
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should disable D+1/D+2 creation when forecast days disallow them."""

    hass = _FakeHass()
    entry = _FakeEntry(
        options={
            integration.CONF_CREATE_FORECAST_SENSORS: "D+1+2",
            integration.CONF_FORECAST_DAYS: 1,
        }
    )

    class _StubClient:
        def __init__(self, _session, _api_key):
            self.session = _session
            self.api_key = _api_key

        async def async_fetch_pollen_data(self, **_kwargs):
            return {"region": {"source": "meta"}, "dailyInfo": []}

    class _StubCoordinator(_BaseDataUpdateCoordinator):
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async_setup should register force_update with an empty schema."""

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


def test_force_update_requests_refresh_per_entry() -> None:
    """force_update should queue refresh via runtime_data coordinators and skip missing runtime data."""

    class _StubCoordinator:
        def __init__(self):
            self.calls: list[str] = []
            self.done = asyncio.Event()

        async def _mark(self):
            self.calls.append("refresh")
            self.done.set()

        async def async_request_refresh(self):
            await self._mark()

    entry1 = _FakeEntry(entry_id="entry-1")
    entry1.runtime_data = types.SimpleNamespace(coordinator=_StubCoordinator())
    entry2 = _FakeEntry(entry_id="entry-2")
    entry2.runtime_data = types.SimpleNamespace(coordinator=_StubCoordinator())
    entry3 = _FakeEntry(entry_id="entry-3")
    entry3.runtime_data = None
    entry4 = _FakeEntry(entry_id="entry-4")
    entry4.runtime_data = types.SimpleNamespace()

    hass = _FakeHass(entries=[entry1, entry2, entry3, entry4])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    assert (integration.DOMAIN, "force_update") in hass.services.registered

    asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert entry1.runtime_data.coordinator.calls == ["refresh"]
    assert entry2.runtime_data.coordinator.calls == ["refresh"]
    assert entry1.runtime_data.coordinator.done.is_set()
    assert entry2.runtime_data.coordinator.done.is_set()


def test_force_update_continues_after_single_coordinator_failure() -> None:
    """One coordinator failure should not block refreshes for other entries."""

    class _OkCoordinator:
        def __init__(self):
            self.calls = 0

        async def async_request_refresh(self):
            self.calls += 1

    class _FailCoordinator:
        async def async_request_refresh(self):
            raise RuntimeError("boom")

    good_entry = _FakeEntry(entry_id="entry-good")
    good_entry.runtime_data = types.SimpleNamespace(coordinator=_OkCoordinator())
    bad_entry = _FakeEntry(entry_id="entry-bad")
    bad_entry.runtime_data = types.SimpleNamespace(coordinator=_FailCoordinator())

    hass = _FakeHass(entries=[bad_entry, good_entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert good_entry.runtime_data.coordinator.calls == 1


def test_force_update_handles_per_entry_cancelled_error(caplog) -> None:
    """Per-entry cancellation results should not abort the global service."""

    class _CancelledCoordinator:
        async def async_request_refresh(self):
            raise asyncio.CancelledError

    entry = _FakeEntry(entry_id="entry-cancel")
    entry.runtime_data = types.SimpleNamespace(coordinator=_CancelledCoordinator())

    hass = _FakeHass(entries=[entry])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    with caplog.at_level("DEBUG"):
        asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert "Manual refresh cancelled for entry entry-cancel" in caplog.text


def test_force_update_no_coordinators_is_noop(caplog) -> None:
    """Calling force_update with no coordinators should be a safe no-op."""

    hass = _FakeHass(entries=[])

    assert asyncio.run(integration.async_setup(hass, {})) is True
    with caplog.at_level("DEBUG"):
        asyncio.run(hass.services.async_call(integration.DOMAIN, "force_update"))

    assert "No coordinators available for force_update" in caplog.text


def test_force_update_logs_do_not_expose_secrets(caplog) -> None:
    """Failure logs should avoid exposing key material and detailed location/payload data."""

    class _FailCoordinator:
        async def async_request_refresh(self):
            raise RuntimeError(
                "api_key=secret-123 lat=12.345678 lon=-98.765432 "
                "url=https://example.test/pollen?token=secret-123 payload=line1\n"
                "token=secret-123\nlocation.latitude=12.345678\n"
                "location.longitude=-98.765432"
            )

    entry = _FakeEntry(
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
