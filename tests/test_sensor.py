"""Unit tests for Pollen Levels sensor data shaping."""

from __future__ import annotations

import asyncio
import datetime
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
    def __init__(self, *args, **kwargs):
        self._attr_unique_id = None
        self._attr_device_info: dict[str, Any] | None = None

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

config_entries_mod = types.ModuleType("homeassistant.config_entries")


class _StubConfigEntry:
    @classmethod
    def __class_getitem__(cls, _item):
        return cls


config_entries_mod.ConfigEntry = _StubConfigEntry
sys.modules.setdefault("homeassistant.config_entries", config_entries_mod)

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


dt_mod.parse_http_date = _stub_parse_http_date
sys.modules.setdefault("homeassistant.util.dt", dt_mod)

util_mod = types.ModuleType("homeassistant.util")
util_mod.dt = dt_mod
sys.modules.setdefault("homeassistant.util", util_mod)

aiohttp_existing = sys.modules.get("aiohttp")
aiohttp_mod = aiohttp_existing or types.ModuleType("aiohttp")


class _StubClientError(Exception):
    pass


class _StubClientSession:  # pragma: no cover - structure only
    pass


class _StubClientTimeout:
    def __init__(self, total: float | None = None):
        self.total = total


if not hasattr(aiohttp_mod, "ClientError"):
    aiohttp_mod.ClientError = _StubClientError
if not hasattr(aiohttp_mod, "ClientSession"):
    aiohttp_mod.ClientSession = _StubClientSession
if not hasattr(aiohttp_mod, "ClientTimeout"):
    aiohttp_mod.ClientTimeout = _StubClientTimeout
if aiohttp_existing is None:
    sys.modules["aiohttp"] = aiohttp_mod


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "custom_components" / "pollenlevels" / relative_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    sys.modules[module_name] = module
    return module


const = _load_module("custom_components.pollenlevels.const", "const.py")
coordinator_mod = _load_module(
    "custom_components.pollenlevels.coordinator", "coordinator.py"
)
sensor = _load_module("custom_components.pollenlevels.sensor", "sensor.py")
client_mod = importlib.import_module("custom_components.pollenlevels.client")


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
        self.runtime_data = None


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
        """Return the next fake response in the sequence."""

        if self.calls >= len(self.sequence):
            raise AssertionError(
                "SequenceSession exhausted; no more responses configured"
            )

        item = self.sequence[self.calls]
        self.calls += 1

        if isinstance(item, Exception):
            raise item

        return FakeResponse(item.payload, status=item.status, headers=item.headers)


def _minimal_valid_payload(value: int = 2) -> dict[str, Any]:
    """Return a minimal valid pollen payload for coordinator refresh tests."""

    return {
        "regionCode": "us_ca_san_francisco",
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 5, "day": 9},
                "pollenTypeInfo": [
                    {
                        "code": "GRASS",
                        "displayName": "Grass",
                        "indexInfo": {
                            "value": value,
                            "category": "LOW",
                            "indexDescription": "Low",
                        },
                    }
                ],
            }
        ],
    }


def _make_coordinator(
    loop: asyncio.AbstractEventLoop,
    client: client_mod.GooglePollenApiClient,
    *,
    hours: int = 12,
    forecast_days: int = 1,
    create_d1: bool = False,
    create_d2: bool = False,
) -> coordinator_mod.PollenDataUpdateCoordinator:
    """Build a coordinator with stable defaults for refresh tests."""

    return coordinator_mod.PollenDataUpdateCoordinator(
        hass=DummyHass(loop),
        api_key="test",
        lat=1.0,
        lon=2.0,
        hours=hours,
        language=None,
        entry_id="entry",
        forecast_days=forecast_days,
        create_d1=create_d1,
        create_d2=create_d2,
        client=client,
    )


class RegistryEntry(NamedTuple):
    """Entity registry entry stub."""

    entity_id: str
    unique_id: str
    domain: str
    platform: str


class RegistryStub:
    """Stubbed entity registry that records removals."""

    def __init__(self, entries: list[RegistryEntry], entry_id: str) -> None:
        self._entries = entries
        self._entry_id = entry_id
        self.removals: list[str] = []

    def async_entries_for_config_entry(self, _registry, entry_id: str):
        assert entry_id == self._entry_id
        return [
            types.SimpleNamespace(
                entity_id=e.entity_id,
                unique_id=e.unique_id,
                domain=e.domain,
                platform=e.platform,
            )
            for e in self._entries
        ]

    def async_remove(self, entity_id: str) -> None:
        self.removals.append(entity_id)


def _setup_registry_stub(
    monkeypatch: pytest.MonkeyPatch,
    entries: list[RegistryEntry],
    *,
    entry_id: str,
) -> RegistryStub:
    """Patch the sensor module's entity registry helpers for cleanup tests."""

    registry = RegistryStub(entries, entry_id=entry_id)

    # In Home Assistant, `async_remove()` is a method of the registry object returned by
    # `entity_registry.async_get(hass)`, not a module-level function.
    monkeypatch.setattr(sensor.er, "async_get", lambda hass: registry)
    monkeypatch.setattr(
        sensor.er,
        "async_entries_for_config_entry",
        registry.async_entries_for_config_entry,
    )

    return registry


def _summary_coordinator(data: dict[str, Any]):
    """Build a minimal coordinator-like object for summary sensor tests."""
    return types.SimpleNamespace(
        data=data,
        entry_id="entry",
        entry_title="Home",
        lat=1.0,
        lon=2.0,
    )


def test_plants_in_season_counts_mixed_boolean_and_unknown_values() -> None:
    """Plants in season counts True/False and treats missing/non-boolean as unknown."""

    coordinator = _summary_coordinator(
        {
            "plants_oak": {
                "source": "plant",
                "displayName": "Oak",
                "inSeason": True,
            },
            "plants_pine": {
                "source": "plant",
                "code": "PINE",
                "displayName": "Pine",
                "inSeason": False,
            },
            "plants_birch": {
                "source": "plant",
                "displayName": "Birch",
            },
            "plants_elm": {
                "source": "plant",
                "displayName": "Elm",
                "inSeason": "yes",
            },
        }
    )

    entity = sensor.PlantsInSeasonTodaySensor(coordinator)
    attrs = entity.extra_state_attributes

    assert entity.native_value == 1
    assert attrs["plant_codes"] == ["OAK"]
    assert attrs["plant_names"] == ["Oak"]
    assert attrs["in_season_count"] == 1
    assert attrs["out_of_season_count"] == 1
    assert attrs["unknown_season_count"] == 2
    assert attrs["total_plant_count"] == 4
    assert attrs["unknown_season_codes"] == ["BIRCH", "ELM"]
    assert attrs["unknown_season_names"] == ["Birch", "Elm"]


def test_plants_in_season_returns_none_without_boolean_season_data() -> None:
    """Plants in season returns None when plant entries lack explicit booleans."""

    coordinator = _summary_coordinator(
        {
            "plants_oak": {"source": "plant", "displayName": "Oak"},
            "plants_pine": {
                "source": "plant",
                "displayName": "Pine",
                "inSeason": "false",
            },
        }
    )

    entity = sensor.PlantsInSeasonTodaySensor(coordinator)

    assert entity.native_value is None
    assert entity.extra_state_attributes["unknown_season_count"] == 2


def test_plants_in_season_returns_none_without_plant_entries() -> None:
    """Plants in season returns None when coordinator data has no plant entries."""

    coordinator = _summary_coordinator(
        {"type_grass": {"source": "type", "displayName": "Grass", "value": 2}}
    )

    entity = sensor.PlantsInSeasonTodaySensor(coordinator)

    assert entity.native_value is None
    assert entity.extra_state_attributes["total_plant_count"] == 0


def test_summary_sensor_caches_payload_for_current_data_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Summary computation is cached per sensor while coordinator data is unchanged."""

    calls: list[dict[str, Any]] = []

    def fake_daily_summary(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        calls.append(data)
        call_count = len(calls)
        return {
            "plants_in_season_today": {
                "state": call_count,
                "plant_names": [f"Plant {call_count}"],
            }
        }

    monkeypatch.setattr(sensor, "_daily_summary", fake_daily_summary)
    initial_data = {"plants_oak": {"source": "plant", "inSeason": True}}
    coordinator = _summary_coordinator(initial_data)
    entity = sensor.PlantsInSeasonTodaySensor(coordinator)

    assert entity.native_value == 1
    assert entity.extra_state_attributes["plant_names"] == ["Plant 1"]
    assert calls == [initial_data]

    updated_data = {"plants_pine": {"source": "plant", "inSeason": True}}
    coordinator.data = updated_data

    assert entity.native_value == 2
    assert entity.extra_state_attributes["plant_names"] == ["Plant 2"]
    assert calls == [initial_data, updated_data]


def test_overall_pollen_risk_returns_max_current_day_type_value() -> None:
    """Overall pollen risk returns the maximum valid current-day type index."""

    coordinator = _summary_coordinator(
        {
            "type_tree": {
                "source": "type",
                "code": "TREE",
                "displayName": "Tree",
                "value": 3,
                "category": "Moderate",
                "description": "Moderate risk",
            },
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 5,
                "category": "High",
                "description": "High risk",
            },
            "type_weed": {
                "source": "type",
                "code": "WEED",
                "displayName": "Weed",
                "value": None,
            },
        }
    )

    entity = sensor.OverallPollenRiskTodaySensor(coordinator)
    attrs = entity.extra_state_attributes

    assert entity.native_value == 5
    assert attrs["category"] == "High"
    assert attrs["description"] == "High risk"
    assert attrs["top_pollen_codes"] == ["GRASS"]
    assert attrs["top_pollen_names"] == ["Grass"]
    assert attrs["tie_count"] == 1


def test_top_pollen_types_returns_single_winner_name() -> None:
    """Top pollen types returns one display name when there is a single winner."""

    coordinator = _summary_coordinator(
        {
            "type_tree": {"source": "type", "displayName": "Tree", "value": 2},
            "type_grass": {"source": "type", "displayName": "Grass", "value": 4},
        }
    )

    entity = sensor.TopPollenTypesTodaySensor(coordinator)

    assert entity.native_value == "Grass"
    assert entity.extra_state_attributes["top_value"] == 4


def test_top_pollen_types_returns_tied_names_and_attributes() -> None:
    """Top pollen types preserves all tied top values in state and attributes."""

    coordinator = _summary_coordinator(
        {
            "type_weed": {
                "source": "type",
                "code": "WEED",
                "displayName": "Weed",
                "value": 4,
                "category": "High",
            },
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 4,
                "category": "High",
            },
            "type_tree": {
                "source": "type",
                "code": "TREE",
                "displayName": "Tree",
                "value": 1,
                "category": "Low",
            },
        }
    )

    entity = sensor.TopPollenTypesTodaySensor(coordinator)
    attrs = entity.extra_state_attributes

    assert entity.native_value == "Grass, Weed"
    assert attrs["top_value"] == 4
    assert attrs["top_pollen_codes"] == ["GRASS", "WEED"]
    assert attrs["top_pollen_names"] == ["Grass", "Weed"]
    assert attrs["top_pollen_categories"] == ["High", "High"]
    assert attrs["tie_count"] == 2


def test_type_summary_sensors_ignore_per_day_d1_d2_values() -> None:
    """Summary sensors ignore D+1 and D+2 per-day type sensors."""

    coordinator = _summary_coordinator(
        {
            "type_grass": {"source": "type", "displayName": "Grass", "value": 2},
            "type_grass_d1": {
                "source": "type",
                "displayName": "Grass D+1",
                "value": 5,
            },
            "type_grass_d2": {
                "source": "type",
                "displayName": "Grass D+2",
                "value": 6,
            },
        }
    )

    risk = sensor.OverallPollenRiskTodaySensor(coordinator)
    top = sensor.TopPollenTypesTodaySensor(coordinator)

    assert risk.native_value == 2
    assert risk.extra_state_attributes["top_pollen_names"] == ["Grass"]
    assert top.native_value == "Grass"


def test_summary_fallback_codes_are_uppercase_from_data_keys() -> None:
    """Fallback summary codes from type_/plants_ keys are exposed uppercase."""

    coordinator = _summary_coordinator(
        {
            "type_grass": {"source": "type", "displayName": "Grass", "value": 3},
            "plants_oak": {
                "source": "plant",
                "displayName": "Oak",
                "inSeason": True,
            },
        }
    )

    risk = sensor.OverallPollenRiskTodaySensor(coordinator)
    plants = sensor.PlantsInSeasonTodaySensor(coordinator)

    assert risk.extra_state_attributes["top_pollen_codes"] == ["GRASS"]
    assert plants.extra_state_attributes["plant_codes"] == ["OAK"]


def test_summary_sensors_expose_attribution() -> None:
    """Summary sensors expose attribution attributes."""

    coordinator = _summary_coordinator(
        {
            "type_grass": {"source": "type", "displayName": "Grass", "value": 3},
            "plants_oak": {
                "source": "plant",
                "displayName": "Oak",
                "inSeason": True,
            },
        }
    )

    entities = [
        sensor.PlantsInSeasonTodaySensor(coordinator),
        sensor.OverallPollenRiskTodaySensor(coordinator),
        sensor.TopPollenTypesTodaySensor(coordinator),
    ]

    assert all(
        entity.extra_state_attributes["Attribution"] == sensor.ATTRIBUTION
        for entity in entities
    )


def test_pollen_sensor_device_info_rounds_coordinates_for_placeholders() -> None:
    """Pollen sensor placeholders show rounded coordinates without unique_id changes."""

    coordinator = _summary_coordinator(
        {
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 2,
            }
        }
    )
    coordinator.lat = 39.123456
    coordinator.lon = -0.123456

    entity = sensor.PollenSensor(coordinator, "type_grass")
    placeholders = entity.device_info["translation_placeholders"]

    assert placeholders["latitude"] == "39.12"
    assert placeholders["longitude"] == "-0.12"
    assert entity.unique_id == "entry_type_grass"


def test_daily_summary_device_info_rounds_coordinates_for_placeholders() -> None:
    """Daily summary placeholders show rounded coordinates without unique_id changes."""

    coordinator = _summary_coordinator({})
    coordinator.lat = 39.123456
    coordinator.lon = -0.123456

    entity = sensor.OverallPollenRiskTodaySensor(coordinator)
    placeholders = entity.device_info["translation_placeholders"]

    assert placeholders["latitude"] == "39.12"
    assert placeholders["longitude"] == "-0.12"
    assert entity.unique_id == "entry_overall_pollen_risk_today"


def test_metadata_device_info_rounds_coordinates_for_placeholders() -> None:
    """Metadata placeholders show rounded coordinates without unique_id changes."""

    coordinator = _summary_coordinator({"region": {"source": "meta", "code": "ES"}})
    coordinator.lat = 39.123456
    coordinator.lon = -0.123456

    entity = sensor.RegionSensor(coordinator)
    placeholders = entity.device_info["translation_placeholders"]

    assert placeholders["latitude"] == "39.12"
    assert placeholders["longitude"] == "-0.12"
    assert entity.unique_id == "entry_region"


def test_top_pollen_types_today_does_not_expose_measurement_state_class() -> None:
    """Top pollen types summary is textual and does not expose measurement state."""

    entity = sensor.TopPollenTypesTodaySensor(_summary_coordinator({}))

    assert (
        getattr(entity, "_attr_state_class", None)
        != sensor.SensorStateClass.MEASUREMENT
    )


def test_plants_in_season_today_does_not_expose_measurement_state_class() -> None:
    """Plants in season summary count does not expose measurement state."""

    entity = sensor.PlantsInSeasonTodaySensor(_summary_coordinator({}))

    assert (
        getattr(entity, "_attr_state_class", None)
        != sensor.SensorStateClass.MEASUREMENT
    )


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
    client = client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

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
    assert "color_raw" not in entry


def test_coordinator_preserves_last_data_when_dailyinfo_missing() -> None:
    """Missing dailyInfo keeps the last successful data instead of clearing."""

    payload = {
        "regionCode": "us_ca_san_francisco",
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 5, "day": 9},
                "pollenTypeInfo": [
                    {
                        "code": "GRASS",
                        "displayName": "Grass",
                        "indexInfo": {
                            "value": 2,
                            "category": "LOW",
                            "indexDescription": "Low",
                        },
                    }
                ],
            }
        ],
    }

    session = SequenceSession(
        [
            ResponseSpec(status=200, payload=payload),
            ResponseSpec(status=200, payload={}),
        ]
    )
    client = client_mod.GooglePollenApiClient(session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        first_data = loop.run_until_complete(coordinator._async_update_data())
        coordinator.data = first_data
        second_data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert first_data["type_grass"]["value"] == 2
    assert second_data == first_data
    assert second_data == coordinator.data


def test_coordinator_clamps_forecast_days_low() -> None:
    """Forecast days are clamped to minimum for legacy or invalid values."""

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    client = client_mod.GooglePollenApiClient(FakeSession({}), "test")

    try:
        coordinator = coordinator_mod.PollenDataUpdateCoordinator(
            hass=hass,
            api_key="test",
            lat=1.0,
            lon=2.0,
            hours=12,
            language=None,
            entry_id="entry",
            forecast_days=0,
            create_d1=False,
            create_d2=False,
            client=client,
        )
    finally:
        loop.close()

    assert coordinator.forecast_days == const.MIN_FORECAST_DAYS


def test_coordinator_first_refresh_missing_dailyinfo_raises() -> None:
    """Missing dailyInfo on the first refresh should raise UpdateFailed."""

    session = SequenceSession([ResponseSpec(status=200, payload={})])
    client = client_mod.GooglePollenApiClient(session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        with pytest.raises(client_mod.UpdateFailed, match="dailyInfo"):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert coordinator.data == {}


def test_coordinator_first_refresh_invalid_dailyinfo_type_raises() -> None:
    """Non-list dailyInfo payload should raise UpdateFailed on first refresh."""

    session = SequenceSession([ResponseSpec(status=200, payload={"dailyInfo": {}})])
    client = client_mod.GooglePollenApiClient(session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        with pytest.raises(client_mod.UpdateFailed, match="dailyInfo"):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()


def test_coordinator_invalid_dailyinfo_items_keep_last_data() -> None:
    """Invalid dailyInfo items should preserve previous successful coordinator data."""

    session = SequenceSession(
        [
            ResponseSpec(
                status=200,
                payload={
                    "dailyInfo": [
                        {
                            "date": {"year": 2025, "month": 5, "day": 9},
                            "pollenTypeInfo": [
                                {
                                    "code": "GRASS",
                                    "displayName": "Grass",
                                    "indexInfo": {"value": 2, "category": "LOW"},
                                }
                            ],
                        }
                    ]
                },
            ),
            ResponseSpec(status=200, payload={"dailyInfo": ["bad-item"]}),
        ]
    )
    client = client_mod.GooglePollenApiClient(session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        first_data = loop.run_until_complete(coordinator._async_update_data())
        coordinator.data = first_data
        second_data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert first_data["type_grass"]["value"] == 2
    assert second_data == first_data


def test_coordinator_mixed_dailyinfo_items_keep_last_data() -> None:
    """Mixed valid/invalid dailyInfo items are treated as invalid payload."""

    session = SequenceSession(
        [
            ResponseSpec(
                status=200,
                payload={
                    "dailyInfo": [
                        {
                            "date": {"year": 2025, "month": 5, "day": 9},
                            "pollenTypeInfo": [
                                {
                                    "code": "GRASS",
                                    "displayName": "Grass",
                                    "indexInfo": {"value": 2, "category": "LOW"},
                                }
                            ],
                        }
                    ]
                },
            ),
            ResponseSpec(
                status=200,
                payload={
                    "dailyInfo": [
                        {
                            "date": {"year": 2025, "month": 5, "day": 10},
                            "pollenTypeInfo": [],
                        },
                        "bad-item",
                    ]
                },
            ),
        ]
    )
    client = client_mod.GooglePollenApiClient(session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client, forecast_days=2)

    try:
        first_data = loop.run_until_complete(coordinator._async_update_data())
        coordinator.data = first_data
        second_data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert second_data == first_data


def test_coordinator_stale_cached_data_raises_after_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed dailyInfo raises once cached data is older than the TTL."""

    start = datetime.datetime(2025, 5, 9, 12, tzinfo=datetime.UTC)
    now = start
    session = SequenceSession(
        [
            ResponseSpec(status=200, payload=_minimal_valid_payload()),
            ResponseSpec(status=200, payload={}),
        ]
    )
    client = client_mod.GooglePollenApiClient(session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client, hours=6)
    monkeypatch.setattr(coordinator, "_utcnow", lambda: now)

    try:
        first_data = loop.run_until_complete(coordinator._async_update_data())
        now = start + datetime.timedelta(hours=24, seconds=1)
        with pytest.raises(client_mod.UpdateFailed, match="cached data expired"):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert coordinator.data == first_data


def test_coordinator_stale_data_ttl_accounts_for_update_interval() -> None:
    """Effective stale-data TTL uses the larger of 24h and twice the interval."""

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    client = client_mod.GooglePollenApiClient(FakeSession({}), "test")

    try:
        six_hour = coordinator_mod.PollenDataUpdateCoordinator(
            hass=hass,
            api_key="test",
            lat=1.0,
            lon=2.0,
            hours=6,
            language=None,
            entry_id="entry-6h",
            forecast_days=1,
            create_d1=False,
            create_d2=False,
            client=client,
        )
        twenty_four_hour = coordinator_mod.PollenDataUpdateCoordinator(
            hass=hass,
            api_key="test",
            lat=1.0,
            lon=2.0,
            hours=24,
            language=None,
            entry_id="entry-24h",
            forecast_days=1,
            create_d1=False,
            create_d2=False,
            client=client,
        )
    finally:
        loop.close()

    assert six_hour._stale_data_ttl() == datetime.timedelta(hours=24)
    assert twenty_four_hour._stale_data_ttl() == datetime.timedelta(hours=48)


def test_coordinator_success_after_malformed_response_updates_last_updated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later successful refresh updates last_updated after malformed dailyInfo."""

    first_refresh = datetime.datetime(2025, 5, 9, 12, tzinfo=datetime.UTC)
    malformed_refresh = first_refresh + datetime.timedelta(hours=1)
    second_refresh = first_refresh + datetime.timedelta(hours=2)
    now = first_refresh
    session = SequenceSession(
        [
            ResponseSpec(status=200, payload=_minimal_valid_payload(value=2)),
            ResponseSpec(status=200, payload={}),
            ResponseSpec(status=200, payload=_minimal_valid_payload(value=4)),
        ]
    )
    client = client_mod.GooglePollenApiClient(session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client, hours=6)
    monkeypatch.setattr(coordinator, "_utcnow", lambda: now)

    try:
        first_data = loop.run_until_complete(coordinator._async_update_data())
        assert coordinator.last_updated == first_refresh

        now = malformed_refresh
        cached_data = loop.run_until_complete(coordinator._async_update_data())
        assert cached_data == first_data
        assert coordinator.last_updated == first_refresh

        now = second_refresh
        second_data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert second_data["type_grass"]["value"] == 4
    assert coordinator.last_updated == second_refresh


def test_coordinator_clamps_forecast_days_negative() -> None:
    """Negative forecast days are clamped to minimum."""

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    client = client_mod.GooglePollenApiClient(FakeSession({}), "test")

    try:
        coordinator = coordinator_mod.PollenDataUpdateCoordinator(
            hass=hass,
            api_key="test",
            lat=1.0,
            lon=2.0,
            hours=12,
            language=None,
            entry_id="entry",
            forecast_days=-5,
            create_d1=False,
            create_d2=False,
            client=client,
        )
    finally:
        loop.close()

    assert coordinator.forecast_days == const.MIN_FORECAST_DAYS


def test_coordinator_clamps_forecast_days_high() -> None:
    """Forecast days are clamped to maximum for legacy or invalid values."""

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    client = client_mod.GooglePollenApiClient(FakeSession({}), "test")

    try:
        coordinator = coordinator_mod.PollenDataUpdateCoordinator(
            hass=hass,
            api_key="test",
            lat=1.0,
            lon=2.0,
            hours=12,
            language=None,
            entry_id="entry",
            forecast_days=10,
            create_d1=False,
            create_d2=False,
            client=client,
        )
    finally:
        loop.close()

    assert coordinator.forecast_days == const.MAX_FORECAST_DAYS


def test_coordinator_keeps_forecast_days_within_range() -> None:
    """Valid forecast days remain unchanged after initialization."""

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    client = client_mod.GooglePollenApiClient(FakeSession({}), "test")

    try:
        coordinator = coordinator_mod.PollenDataUpdateCoordinator(
            hass=hass,
            api_key="test",
            lat=1.0,
            lon=2.0,
            hours=12,
            language=None,
            entry_id="entry",
            forecast_days=3,
            create_d1=False,
            create_d2=False,
            client=client,
        )
    finally:
        loop.close()

    assert coordinator.forecast_days == 3


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
    client = client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = coordinator_mod.PollenDataUpdateCoordinator(
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
        client=client,
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
    client = client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = coordinator_mod.PollenDataUpdateCoordinator(
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
        client=client,
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


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        ({"date": {"year": 2025, "month": 6, "day": 1}}, "2025-06-01"),
        ({"date": {"year": "2025", "month": "6", "day": "1"}}, "2025-06-01"),
        ({}, None),
        ({"date": None}, None),
        ({"date": {"year": 2025, "month": 6}}, None),
        ({"date": {"year": 2025, "month": None, "day": 1}}, None),
        ({"date": "bad-date"}, None),
        ({"date": {"year": "bad", "month": 6, "day": 1}}, None),
        ({"date": {"year": 2025.5, "month": 6, "day": 1}}, None),
        ({"date": {"year": True, "month": 6, "day": 1}}, None),
    ],
)
def test_extract_api_date_parses_integer_like_values(
    day: dict[str, Any], expected: str | None
) -> None:
    """API date extraction accepts integer-like values and rejects malformed ones."""

    assert coordinator_mod._extract_api_date(day) == expected


def test_forecast_extraction_preserves_missing_index_and_date_behavior() -> None:
    """Forecast entries preserve missing index and missing API date output."""

    payload = {
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 6, "day": 1},
                "pollenTypeInfo": [
                    {
                        "code": "GRASS",
                        "displayName": "Grass",
                        "inSeason": True,
                        "healthRecommendations": ["Today advice"],
                        "indexInfo": {
                            "value": 2,
                            "category": "LOW",
                            "indexDescription": "Low",
                        },
                    }
                ],
                "plantInfo": [
                    {
                        "code": "oak",
                        "displayName": "Oak",
                        "indexInfo": {
                            "value": 3,
                            "category": "MODERATE",
                            "indexDescription": "Moderate",
                        },
                    }
                ],
            },
            {
                "date": {"year": 2025, "month": 6, "day": 2},
                "pollenTypeInfo": [
                    {
                        "code": "GRASS",
                        "displayName": "Grass",
                        "inSeason": False,
                        "healthRecommendations": ["Tomorrow advice"],
                    }
                ],
                "plantInfo": [
                    {
                        "code": "oak",
                        "displayName": "Oak",
                        "indexInfo": {},
                    }
                ],
            },
            {
                "date": {"year": 2025, "month": None, "day": 3},
                "pollenTypeInfo": [
                    {
                        "code": "GRASS",
                        "displayName": "Grass",
                        "inSeason": True,
                        "healthRecommendations": ["D2 advice"],
                        "indexInfo": {
                            "value": 5,
                            "category": "HIGH",
                            "indexDescription": "High",
                            "color": {"red": 255, "green": 100, "blue": 50},
                        },
                    }
                ],
                "plantInfo": [
                    {
                        "code": "oak",
                        "displayName": "Oak",
                        "indexInfo": {
                            "value": 1,
                            "category": "LOW",
                            "indexDescription": "Low",
                            "color": {"red": 0, "green": 1, "blue": 0},
                        },
                    }
                ],
            },
        ]
    }

    fake_session = FakeSession(payload)
    client = client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(
        loop, client, forecast_days=3, create_d1=True, create_d2=True
    )

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    type_entry = data["type_grass"]
    assert type_entry["forecast"][0] == {
        "offset": 1,
        "date": "2025-06-02",
        "has_index": False,
        "value": None,
        "category": None,
        "description": None,
        "color_hex": None,
        "color_rgb": None,
    }
    assert type_entry["forecast"][1]["date"] is None
    assert type_entry["forecast"][1]["has_index"] is True
    assert type_entry["forecast"][1]["color_hex"] == "#FF6432"
    d1_entry = data["type_grass_d1"]
    assert d1_entry["value"] is None
    assert d1_entry["category"] is None
    assert d1_entry["description"] is None
    assert d1_entry["date"] == "2025-06-02"
    assert d1_entry["has_index"] is False
    assert d1_entry["inSeason"] is False
    assert d1_entry["advice"] == ["Tomorrow advice"]

    d2_entry = data["type_grass_d2"]
    assert d2_entry["value"] == 5
    assert d2_entry["date"] is None
    assert d2_entry["has_index"] is True

    plant_entry = data["plants_oak"]
    assert plant_entry["forecast"][0] == {
        "offset": 1,
        "date": "2025-06-02",
        "has_index": False,
        "value": None,
        "category": None,
        "description": None,
        "color_hex": None,
        "color_rgb": None,
    }
    assert plant_entry["forecast"][1]["date"] is None
    assert plant_entry["forecast"][1]["color_hex"] == "#00FF00"


def test_plant_forecast_matches_codes_case_insensitively() -> None:
    """Plant forecast should match even when code casing varies by day."""

    payload = {
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 6, "day": 1},
                "plantInfo": [
                    {
                        "code": "ragweed",
                        "displayName": "Ragweed",
                        "indexInfo": {"value": 2, "category": "LOW"},
                    }
                ],
            },
            {
                "date": {"year": 2025, "month": 6, "day": 2},
                "plantInfo": [
                    {
                        "code": "RAGWEED",
                        "displayName": "Ragweed",
                        "indexInfo": {"value": 4, "category": "HIGH"},
                    }
                ],
            },
        ]
    }

    fake_session = FakeSession(payload)
    client = client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = coordinator_mod.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="test",
        lat=1.0,
        lon=2.0,
        hours=12,
        language=None,
        entry_id="entry",
        forecast_days=3,
        create_d1=False,
        create_d2=False,
        client=client,
    )

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    entry = data["plants_ragweed"]
    assert entry["code"] == "ragweed"
    assert entry["tomorrow_has_index"] is True
    assert entry["tomorrow_value"] == 4


def test_coordinator_accepts_numeric_string_color_channels() -> None:
    """Numeric string channels should be normalized into RGB/hex values."""

    payload = {
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 7, "day": 1},
                "pollenTypeInfo": [
                    {
                        "code": "GRASS",
                        "displayName": "Grass",
                        "indexInfo": {
                            "value": 1,
                            "category": "LOW",
                            "color": {"red": "1", "green": "0", "blue": "0"},
                        },
                    }
                ],
            }
        ]
    }

    fake_session = FakeSession(payload)
    client = client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert data["type_grass"]["color_hex"] == "#FF0000"
    assert data["type_grass"]["color_rgb"] == [255, 0, 0]


def test_coordinator_ignores_invalid_string_color_channels() -> None:
    """Non-numeric string channels should not emit RGB/hex values."""

    payload = {
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 7, "day": 1},
                "pollenTypeInfo": [
                    {
                        "code": "GRASS",
                        "displayName": "Grass",
                        "indexInfo": {
                            "value": 1,
                            "category": "LOW",
                            "color": {"red": "foo"},
                        },
                    }
                ],
            }
        ]
    }

    fake_session = FakeSession(payload)
    client = client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert data["type_grass"]["color_hex"] is None
    assert data["type_grass"]["color_rgb"] is None


def test_coordinator_ignores_nonfinite_color_channels() -> None:
    """Non-finite color channel values should not crash or emit invalid colors."""

    payload = {
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 7, "day": 1},
                "pollenTypeInfo": [
                    {
                        "code": "GRASS",
                        "displayName": "Grass",
                        "indexInfo": {
                            "value": 1,
                            "category": "LOW",
                            "color": {"red": float("inf"), "green": float("nan")},
                        },
                    }
                ],
            }
        ]
    }

    fake_session = FakeSession(payload)
    client = client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert data["type_grass"]["color_hex"] is None
    assert data["type_grass"]["color_rgb"] is None


def test_coordinator_type_keys_are_deterministic_sorted() -> None:
    """Type sensor keys are emitted in stable sorted order."""

    payload = {
        "dailyInfo": [
            {
                "date": {"year": 2025, "month": 7, "day": 1},
                "pollenTypeInfo": [
                    {
                        "code": "WEED",
                        "displayName": "Weed",
                        "indexInfo": {"value": 2, "category": "LOW"},
                    },
                    {
                        "code": "GRASS",
                        "displayName": "Grass",
                        "indexInfo": {"value": 1, "category": "LOW"},
                    },
                ],
            }
        ]
    }

    fake_session = FakeSession(payload)
    client = client_mod.GooglePollenApiClient(fake_session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        data = loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    type_keys = [
        k
        for k, v in data.items()
        if isinstance(v, dict)
        and v.get("source") == "type"
        and not k.endswith(("_d1", "_d2"))
    ]
    assert type_keys == sorted(type_keys)


@pytest.mark.parametrize(
    (
        "allow_d1",
        "allow_d2",
        "expected_removed",
        "expected_entities",
    ),
    [
        (False, True, 1, ["sensor.pollen_type_grass_d1"]),
        (True, False, 1, ["sensor.pollen_type_grass_d2"]),
    ],
)
def test_cleanup_per_day_entities_removes_disabled_days(
    monkeypatch: pytest.MonkeyPatch,
    allow_d1: bool,
    allow_d2: bool,
    expected_removed: int,
    expected_entities: list[str],
) -> None:
    """D+1/D+2 entities are awaited and removed when disabled."""

    entries = [
        RegistryEntry(
            "sensor.pollen_type_grass",
            "entry_type_grass",
            "sensor",
            sensor.DOMAIN,
        ),
        RegistryEntry(
            "sensor.pollen_type_grass_d1",
            "entry_type_grass_d1",
            "sensor",
            sensor.DOMAIN,
        ),
        RegistryEntry(
            "sensor.pollen_type_grass_d2",
            "entry_type_grass_d2",
            "sensor",
            sensor.DOMAIN,
        ),
    ]
    registry = _setup_registry_stub(monkeypatch, entries, entry_id="entry")

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    try:
        removed = loop.run_until_complete(
            sensor._cleanup_per_day_entities(
                hass, "entry", allow_d1=allow_d1, allow_d2=allow_d2
            )
        )
    finally:
        loop.close()

    assert removed == expected_removed
    assert registry.removals == expected_entities


def test_coordinator_raises_auth_failed() -> None:
    """401 responses trigger ConfigEntryAuthFailed for re-auth flows."""

    fake_session = FakeSession({}, status=401)
    client = client_mod.GooglePollenApiClient(fake_session, "bad")

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = coordinator_mod.PollenDataUpdateCoordinator(
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
        client=client,
    )

    try:
        with pytest.raises(client_mod.ConfigEntryAuthFailed):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()


def test_coordinator_handles_forbidden() -> None:
    """403 responses raise UpdateFailed without triggering re-auth."""

    fake_session = FakeSession({"error": {"message": "Forbidden"}}, status=403)
    client = client_mod.GooglePollenApiClient(fake_session, "bad")

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = coordinator_mod.PollenDataUpdateCoordinator(
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
        client=client,
    )

    try:
        with pytest.raises(client_mod.UpdateFailed):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()


def test_coordinator_invalid_key_message_triggers_reauth() -> None:
    """403 invalid API key messages should raise ConfigEntryAuthFailed."""

    payload = {"error": {"message": "API key not valid. Please pass a valid API key."}}
    fake_session = FakeSession(payload, status=403)
    client = client_mod.GooglePollenApiClient(fake_session, "bad")

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = coordinator_mod.PollenDataUpdateCoordinator(
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
        client=client,
    )

    try:
        with pytest.raises(client_mod.ConfigEntryAuthFailed):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()


def test_format_http_message_ignores_whitespace_only_message() -> None:
    """Whitespace-only raw messages should not add a trailing HTTP suffix."""

    assert client_mod._format_http_message(429, "   ") == "HTTP 429"


def test_client_raises_dedicated_quota_error_after_terminal_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Terminal HTTP 429 responses raise the dedicated quota exception."""

    session = SequenceSession(
        [
            ResponseSpec(
                status=429,
                payload={"error": {"message": "Quota exceeded"}},
                headers={"Retry-After": "2"},
            ),
            ResponseSpec(
                status=429,
                payload={"error": {"message": "Quota exceeded"}},
                headers={"Retry-After": "2"},
            ),
        ]
    )

    async def _fast_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(client_mod.random, "uniform", lambda *_args, **_kwargs: 0.0)

    client = client_mod.GooglePollenApiClient(session, "test")

    async def _run() -> None:
        await client.async_fetch_pollen_data(
            latitude=1.0,
            longitude=2.0,
            days=1,
            language_code=None,
        )

    with pytest.raises(client_mod.PollenQuotaExceededError, match="Quota exceeded"):
        asyncio.run(_run())

    assert session.calls == 2


def test_coordinator_retries_then_raises_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """429 responses are retried once then raise UpdateFailed with quota message."""

    session = SequenceSession(
        [
            ResponseSpec(
                status=429,
                payload={"error": {"message": "Quota exceeded"}},
                headers={"Retry-After": "3"},
            ),
            ResponseSpec(
                status=429,
                payload={"error": {"message": "Quota exceeded"}},
                headers={"Retry-After": "3"},
            ),
        ]
    )
    delays: list[float] = []

    async def _fast_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(client_mod.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(client_mod.random, "uniform", lambda *_args, **_kwargs: 0.0)

    client = client_mod.GooglePollenApiClient(session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        with pytest.raises(client_mod.UpdateFailed, match="Quota exceeded"):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert session.calls == 2
    assert delays == [3.0]


def test_coordinator_retry_after_http_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry-After as HTTP-date is converted to a delay before retry."""

    retry_after = "Wed, 10 Dec 2025 12:00:05 GMT"
    session = SequenceSession(
        [
            ResponseSpec(
                status=429,
                payload={"error": {"message": "Quota exceeded"}},
                headers={"Retry-After": retry_after},
            ),
            ResponseSpec(
                status=429,
                payload={"error": {"message": "Quota exceeded"}},
                headers={"Retry-After": retry_after},
            ),
        ]
    )
    delays: list[float] = []

    async def _fast_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(client_mod.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(client_mod.random, "uniform", lambda *_args, **_kwargs: 0.0)
    monkeypatch.setattr(
        client_mod.dt_util,
        "utcnow",
        lambda: datetime.datetime(2025, 12, 10, 12, 0, 0, tzinfo=datetime.UTC),
    )

    client = client_mod.GooglePollenApiClient(session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        with pytest.raises(client_mod.UpdateFailed, match="Quota exceeded"):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert session.calls == 2
    assert delays == [5.0]


@pytest.mark.parametrize(
    ("retry_after", "now"),
    [
        ("-10", None),
        ("nan", None),
        ("inf", None),
        (
            "Wed, 10 Dec 2025 12:00:00 GMT",
            datetime.datetime(2025, 12, 10, 12, 0, 5, tzinfo=datetime.UTC),
        ),
    ],
)
def test_coordinator_retry_after_invalid_values_use_safe_default(
    monkeypatch: pytest.MonkeyPatch,
    retry_after: str,
    now: datetime.datetime | None,
) -> None:
    """Invalid Retry-After values should fall back to a safe finite delay."""

    session = SequenceSession(
        [
            ResponseSpec(
                status=429,
                payload={"error": {"message": "Quota exceeded"}},
                headers={"Retry-After": retry_after},
            ),
            ResponseSpec(
                status=429,
                payload={"error": {"message": "Quota exceeded"}},
                headers={"Retry-After": retry_after},
            ),
        ]
    )
    delays: list[float] = []

    async def _fast_sleep(delay: float) -> None:
        assert isinstance(delay, float)
        assert delay == delay
        assert delay != float("inf")
        assert delay != float("-inf")
        delays.append(delay)

    monkeypatch.setattr(client_mod.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(client_mod.random, "uniform", lambda *_args, **_kwargs: 0.0)
    if now is not None:
        monkeypatch.setattr(client_mod.dt_util, "utcnow", lambda: now)

    client = client_mod.GooglePollenApiClient(session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        with pytest.raises(client_mod.UpdateFailed, match="Quota exceeded"):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert session.calls == 2
    assert delays == [2.0]


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

    monkeypatch.setattr(client_mod.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(client_mod.random, "uniform", lambda *_args, **_kwargs: 0.0)

    client = client_mod.GooglePollenApiClient(session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        with pytest.raises(client_mod.UpdateFailed, match="HTTP 502"):
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

    monkeypatch.setattr(client_mod.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(client_mod.random, "uniform", lambda *_args, **_kwargs: 0.0)

    client = client_mod.GooglePollenApiClient(session, "test")

    loop = asyncio.new_event_loop()
    coordinator = _make_coordinator(loop, client)

    try:
        with pytest.raises(client_mod.UpdateFailed, match="Timeout"):
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
        [
            client_mod.ClientError("net down"),
            client_mod.ClientError("net down"),
        ]
    )
    delays: list[float] = []

    async def _fast_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(client_mod.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(client_mod.random, "uniform", lambda *_args, **_kwargs: 0.0)

    client = client_mod.GooglePollenApiClient(session, "secret")

    loop = asyncio.new_event_loop()
    hass = DummyHass(loop)
    coordinator = coordinator_mod.PollenDataUpdateCoordinator(
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
        client=client,
    )

    try:
        with pytest.raises(client_mod.UpdateFailed, match="net down"):
            loop.run_until_complete(coordinator._async_update_data())
    finally:
        loop.close()

    assert session.calls == 2
    assert delays == [0.8]


def test_async_setup_entry_raises_not_ready_if_runtime_data_missing() -> None:
    """Missing runtime data causes setup to raise ConfigEntryNotReady."""

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
        with pytest.raises(sensor.ConfigEntryNotReady):
            loop.run_until_complete(
                sensor.async_setup_entry(hass, config_entry, _noop_add_entities)
            )
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_async_setup_entry_skips_disabled_d1_d2_sensors() -> None:
    """Setup does not recreate D+1/D+2 sensors when forecast days disable them."""

    hass = DummyHass(asyncio.get_running_loop())
    config_entry = FakeConfigEntry(
        data={
            sensor.CONF_API_KEY: "key",
            sensor.CONF_LATITUDE: 1.0,
            sensor.CONF_LONGITUDE: 2.0,
            sensor.CONF_UPDATE_INTERVAL: sensor.DEFAULT_UPDATE_INTERVAL,
            sensor.CONF_FORECAST_DAYS: sensor.DEFAULT_FORECAST_DAYS,
        },
        options={sensor.CONF_FORECAST_DAYS: 1},
        entry_id="entry",
    )

    client = client_mod.GooglePollenApiClient(FakeSession({}), "key")
    coordinator = coordinator_mod.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="key",
        lat=1.0,
        lon=2.0,
        hours=sensor.DEFAULT_UPDATE_INTERVAL,
        language=None,
        entry_id="entry",
        entry_title=sensor.DEFAULT_ENTRY_TITLE,
        forecast_days=3,
        create_d1=True,
        create_d2=True,
        client=client,
    )
    coordinator.data = {
        "date": {"source": "meta"},
        "region": {"source": "meta"},
        "type_grass": {"source": "type", "name": "Grass"},
        "type_grass_d1": {"source": "type", "name": "Grass D+1"},
        "type_grass_d2": {"source": "type", "name": "Grass D+2"},
    }
    config_entry.runtime_data = sensor.PollenLevelsRuntimeData(
        coordinator=coordinator, client=client
    )

    captured: list[Any] = []

    def _capture_entities(entities, _update_before_add=False):
        captured.extend(entities)

    await sensor.async_setup_entry(hass, config_entry, _capture_entities)

    unique_ids = {
        entity.unique_id
        for entity in captured
        if getattr(entity, "unique_id", None) is not None
    }

    assert "entry_type_grass" in unique_ids
    assert all(not uid.endswith("_d1") for uid in unique_ids)
    assert all(not uid.endswith("_d2") for uid in unique_ids)


@pytest.mark.asyncio
async def test_async_setup_entry_uses_refreshed_coordinator_data_without_forced_update() -> (
    None
):
    """Setup uses first-refresh coordinator data and does not force entity update."""

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
    coordinator = types.SimpleNamespace(
        data={
            "date": {"source": "meta", "value": "2026-05-08"},
            "region": {"source": "meta", "value": "us_ca_san_francisco"},
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 3,
                "category": "Moderate",
            },
        },
        entry_id="entry",
        entry_title="Home",
        lat=1.0,
        lon=2.0,
        forecast_days=sensor.DEFAULT_FORECAST_DAYS,
        create_d1=False,
        create_d2=False,
        last_updated=None,
    )
    config_entry.runtime_data = sensor.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    captured: list[Any] = []
    update_before_add_value: bool | None = None

    def _capture_entities(entities, _update_before_add=False):
        nonlocal update_before_add_value
        captured.extend(entities)
        update_before_add_value = _update_before_add

    await sensor.async_setup_entry(hass, config_entry, _capture_entities)

    assert update_before_add_value is False

    grass_sensor = next(
        entity
        for entity in captured
        if getattr(entity, "unique_id", "") == "entry_type_grass"
    )
    assert grass_sensor.native_value == 3


@pytest.mark.asyncio
async def test_async_setup_entry_adds_daily_summary_sensors() -> None:
    """Setup creates the three daily summary sensors."""

    entry_id = "summary_entry"
    hass = DummyHass(asyncio.get_running_loop())
    config_entry = FakeConfigEntry(
        data={
            sensor.CONF_API_KEY: "key",
            sensor.CONF_LATITUDE: 1.0,
            sensor.CONF_LONGITUDE: 2.0,
            sensor.CONF_UPDATE_INTERVAL: sensor.DEFAULT_UPDATE_INTERVAL,
            sensor.CONF_FORECAST_DAYS: sensor.DEFAULT_FORECAST_DAYS,
        },
        entry_id=entry_id,
    )
    coordinator = types.SimpleNamespace(
        data={
            "date": {"source": "meta", "value": "2026-05-08"},
            "region": {"source": "meta", "value": "us_ca_san_francisco"},
            "type_grass": {
                "source": "type",
                "code": "GRASS",
                "displayName": "Grass",
                "value": 3,
                "category": "Moderate",
            },
            "plants_oak": {
                "source": "plant",
                "code": "OAK",
                "displayName": "Oak",
                "inSeason": True,
            },
        },
        entry_id=entry_id,
        entry_title="Home",
        lat=1.0,
        lon=2.0,
        forecast_days=sensor.DEFAULT_FORECAST_DAYS,
        create_d1=False,
        create_d2=False,
        last_updated=None,
    )
    config_entry.runtime_data = sensor.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    captured: list[Any] = []

    def _capture_entities(entities, _update_before_add=False):
        captured.extend(entities)

    await sensor.async_setup_entry(hass, config_entry, _capture_entities)

    unique_ids = {
        entity.unique_id
        for entity in captured
        if getattr(entity, "unique_id", None) is not None
    }

    assert {
        f"{entry_id}_plants_in_season_today",
        f"{entry_id}_overall_pollen_risk_today",
        f"{entry_id}_top_pollen_types_today",
    }.issubset(unique_ids)


@pytest.mark.asyncio
async def test_device_info_uses_default_title_when_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whitespace titles fall back to the default in translation placeholders."""

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

    client = client_mod.GooglePollenApiClient(FakeSession({}), "key")
    clean_title = sensor.DEFAULT_ENTRY_TITLE
    coordinator = coordinator_mod.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="key",
        lat=1.0,
        lon=2.0,
        hours=sensor.DEFAULT_UPDATE_INTERVAL,
        language=None,
        entry_id="entry",
        entry_title=clean_title,
        forecast_days=sensor.DEFAULT_FORECAST_DAYS,
        create_d1=False,
        create_d2=False,
        client=client,
    )
    coordinator.data = {"date": {"source": "meta"}, "region": {"source": "meta"}}
    config_entry.runtime_data = sensor.PollenLevelsRuntimeData(
        coordinator=coordinator, client=client
    )

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

    client = client_mod.GooglePollenApiClient(FakeSession({}), "key")
    clean_title = config_entry.title.strip()
    coordinator = coordinator_mod.PollenDataUpdateCoordinator(
        hass=hass,
        api_key="key",
        lat=1.0,
        lon=2.0,
        hours=sensor.DEFAULT_UPDATE_INTERVAL,
        language=None,
        entry_id="entry",
        entry_title=clean_title,
        forecast_days=sensor.DEFAULT_FORECAST_DAYS,
        create_d1=False,
        create_d2=False,
        client=client,
    )
    coordinator.data = {"date": {"source": "meta"}, "region": {"source": "meta"}}
    config_entry.runtime_data = sensor.PollenLevelsRuntimeData(
        coordinator=coordinator, client=client
    )

    captured: list[Any] = []

    def _capture_entities(entities, _update_before_add=False):
        captured.extend(entities)

    await sensor.async_setup_entry(hass, config_entry, _capture_entities)

    region_sensor = next(
        entity for entity in captured if isinstance(entity, sensor.RegionSensor)
    )

    placeholders = region_sensor.device_info["translation_placeholders"]
    assert placeholders["title"] == "My Location"
