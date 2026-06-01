"""Diagnostics tests for privacy and payload sizing."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, NamedTuple

import pytest

from tests._ha_stubs import (
    clear_integration_modules,
    stub_config_entry_class,
    stub_custom_components_packages,
)


class DiagnosticsModules(NamedTuple):
    """Diagnostics modules/constants imported under fixture-scoped HA stubs."""

    diag: ModuleType
    PollenLevelsRuntimeData: type[object]
    PollenLocationRuntime: type[object]
    CONF_API_KEY: str
    CONF_FORECAST_DAYS: str
    CONF_LANGUAGE_CODE: str
    CONF_LATITUDE: str
    CONF_LONGITUDE: str


class _ConfigEntry:
    def __init__(
        self,
        *,
        data: dict[str, Any],
        options: dict[str, Any],
        entry_id: str,
        title: str,
    ) -> None:
        self.data = data
        self.options = options
        self.entry_id = entry_id
        self.title = title
        self.runtime_data = None


def _install_diagnostics_import_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install minimal Home Assistant stubs needed by diagnostics imports."""

    components_mod = ModuleType("homeassistant.components")
    diagnostics_mod = ModuleType("homeassistant.components.diagnostics")

    def _async_redact_data(data: dict[str, Any], _redact: set[str]) -> dict[str, Any]:
        def _walk(value):
            if isinstance(value, dict):
                return {
                    k: ("**REDACTED**" if k in _redact else _walk(v))
                    for k, v in value.items()
                }
            if isinstance(value, list):
                return [_walk(v) for v in value]
            return value

        return _walk(data)

    diagnostics_mod.async_redact_data = _async_redact_data
    monkeypatch.setitem(sys.modules, "homeassistant.components", components_mod)
    monkeypatch.setitem(
        sys.modules, "homeassistant.components.diagnostics", diagnostics_mod
    )

    stub_config_entry_class(_ConfigEntry, monkeypatch=monkeypatch)

    core_mod = ModuleType("homeassistant.core")

    class _HomeAssistant:
        pass

    core_mod.HomeAssistant = _HomeAssistant
    monkeypatch.setitem(sys.modules, "homeassistant.core", core_mod)

    clear_integration_modules(monkeypatch=monkeypatch)
    stub_custom_components_packages(
        root=Path(__file__).resolve().parents[1], monkeypatch=monkeypatch
    )


@pytest.fixture
def diagnostics_modules(monkeypatch: pytest.MonkeyPatch) -> DiagnosticsModules:
    """Import diagnostics with fixture-scoped Home Assistant stubs."""

    _install_diagnostics_import_stubs(monkeypatch)

    from custom_components.pollenlevels import diagnostics as imported_diag
    from custom_components.pollenlevels.const import (
        CONF_API_KEY as imported_conf_api_key,
        CONF_FORECAST_DAYS as imported_conf_forecast_days,
        CONF_LANGUAGE_CODE as imported_conf_language_code,
        CONF_LATITUDE as imported_conf_latitude,
        CONF_LONGITUDE as imported_conf_longitude,
    )
    from custom_components.pollenlevels.runtime import (
        PollenLevelsRuntimeData as ImportedRuntimeData,
        PollenLocationRuntime as ImportedLocationRuntime,
    )

    modules = DiagnosticsModules(
        diag=imported_diag,
        PollenLevelsRuntimeData=ImportedRuntimeData,
        PollenLocationRuntime=ImportedLocationRuntime,
        CONF_API_KEY=imported_conf_api_key,
        CONF_FORECAST_DAYS=imported_conf_forecast_days,
        CONF_LANGUAGE_CODE=imported_conf_language_code,
        CONF_LATITUDE=imported_conf_latitude,
        CONF_LONGITUDE=imported_conf_longitude,
    )
    yield modules
    # Remove imported integration modules directly so pytest does not restore
    # modules that were imported against these Home Assistant stubs.
    clear_integration_modules()


@pytest.mark.asyncio
async def test_diagnostics_rounds_coordinates_and_truncates_keys(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics should use rounded coordinates and limit data_keys length."""

    data = {
        diagnostics_modules.CONF_API_KEY: "secret-token",
        diagnostics_modules.CONF_LATITUDE: 12.345678,
        diagnostics_modules.CONF_LONGITUDE: 78.987654,
        diagnostics_modules.CONF_LANGUAGE_CODE: "en",
    }
    options = {diagnostics_modules.CONF_FORECAST_DAYS: 3}

    entry = _ConfigEntry(data=data, options=options, entry_id="entry", title="Home")

    coordinator = SimpleNamespace(
        entry_id="entry",
        forecast_days=3,
        language="en",
        create_d1=True,
        create_d2=False,
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        data={f"type_{idx}": {} for idx in range(60)},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    assert diagnostics["request_params_example"]["key"] == "***"
    assert diagnostics_modules.CONF_LATITUDE not in diagnostics["entry"]["data"]
    assert diagnostics_modules.CONF_LONGITUDE not in diagnostics["entry"]["data"]
    assert diagnostics["request_params_example"]["location.latitude"] == 12.3
    assert diagnostics["request_params_example"]["location.longitude"] == 79.0
    assert diagnostics["coordinator"]["data_keys_total"] == 60
    assert len(diagnostics["coordinator"]["data_keys"]) == 50
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "12.345678" not in serialized
    assert "78.987654" not in serialized


@pytest.mark.asyncio
async def test_diagnostics_includes_all_locations_with_top_level_first_location(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics should expose all locations and keep top-level compatibility."""

    data = {
        diagnostics_modules.CONF_API_KEY: "secret-token",
        diagnostics_modules.CONF_LANGUAGE_CODE: "en",
    }
    options = {diagnostics_modules.CONF_FORECAST_DAYS: 3}
    entry = _ConfigEntry(data=data, options=options, entry_id="entry", title="Home")

    first_coordinator = SimpleNamespace(
        entry_id="entry",
        subentry_id="subentry-1",
        legacy_entry_id="legacy-entry",
        entity_identity_id="legacy-entry",
        forecast_days=3,
        language="en",
        create_d1=True,
        create_d2=False,
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        lat=12.3456,
        lon=78.9876,
        entry_title="Home",
        data={"type_grass": {"source": "type", "code": "GRASS", "value": 2}},
    )
    second_coordinator = SimpleNamespace(
        entry_id="entry",
        subentry_id="subentry-2",
        legacy_entry_id=None,
        entity_identity_id="entry_subentry-2",
        forecast_days=3,
        language="en",
        create_d1=True,
        create_d2=False,
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        lat=40.7128,
        lon=-74.0060,
        entry_title="Office",
        data={"type_tree": {"source": "type", "code": "TREE", "value": 4}},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        client=object(),
        locations={
            "subentry-1": diagnostics_modules.PollenLocationRuntime(
                subentry_id="subentry-1",
                coordinator=first_coordinator,
                legacy_entry_id="legacy-entry",
            ),
            "subentry-2": diagnostics_modules.PollenLocationRuntime(
                subentry_id="subentry-2",
                coordinator=second_coordinator,
                legacy_entry_id=None,
            ),
        },
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    assert set(diagnostics["locations"]) == {"subentry-1", "subentry-2"}
    first_payload = diagnostics["locations"]["subentry-1"]
    second_payload = diagnostics["locations"]["subentry-2"]
    assert diagnostics["coordinator"] == first_payload["coordinator"]
    assert diagnostics["forecast_summary"] == first_payload["forecast_summary"]
    assert diagnostics["daily_summary"] == first_payload["daily_summary"]
    assert (
        diagnostics["request_params_example"] == first_payload["request_params_example"]
    )
    assert first_payload["request_params_example"]["key"] == "***"
    assert second_payload["request_params_example"]["key"] == "***"
    assert first_payload["approximate_location"]["latitude_rounded"] == 12.3
    assert first_payload["approximate_location"]["longitude_rounded"] == 79.0
    assert second_payload["approximate_location"]["latitude_rounded"] == 40.7
    assert second_payload["approximate_location"]["longitude_rounded"] == -74.0
    assert first_payload["coordinator"]["legacy_entry_id"] == "legacy-entry"
    assert second_payload["coordinator"]["subentry_id"] == "subentry-2"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_days", "expected_days"),
    [
        (999, 5),
        (-3, 1),
        ("nan", 2),
    ],
)
async def test_diagnostics_clamps_request_days(
    diagnostics_modules: DiagnosticsModules, raw_days: Any, expected_days: int
) -> None:
    """Diagnostics request params should always show a supported day count."""

    data = {
        diagnostics_modules.CONF_LATITUDE: 12.3,
        diagnostics_modules.CONF_LONGITUDE: 45.6,
        diagnostics_modules.CONF_LANGUAGE_CODE: "en",
    }
    options = {diagnostics_modules.CONF_FORECAST_DAYS: raw_days}

    entry = _ConfigEntry(data=data, options=options, entry_id="entry", title="Home")

    coordinator = SimpleNamespace(
        entry_id="entry",
        forecast_days=3,
        language="en",
        create_d1=True,
        create_d2=False,
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        data={"type_grass": {"source": "type"}},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    assert diagnostics["request_params_example"]["days"] == expected_days


@pytest.mark.asyncio
async def test_diagnostics_nonfinite_coordinates_are_omitted_in_examples(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Rounded coordinate helpers should drop non-finite values."""

    data = {
        diagnostics_modules.CONF_LATITUDE: "nan",
        diagnostics_modules.CONF_LONGITUDE: float("inf"),
        diagnostics_modules.CONF_LANGUAGE_CODE: "en",
    }
    options = {diagnostics_modules.CONF_FORECAST_DAYS: 2}

    entry = _ConfigEntry(data=data, options=options, entry_id="entry", title="Home")

    coordinator = SimpleNamespace(
        entry_id="entry",
        forecast_days=2,
        language="en",
        create_d1=True,
        create_d2=False,
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        data={"type_grass": {"source": "type"}},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    assert diagnostics["approximate_location"]["latitude_rounded"] is None
    assert diagnostics["approximate_location"]["longitude_rounded"] is None
    assert diagnostics["request_params_example"]["location.latitude"] is None
    assert diagnostics["request_params_example"]["location.longitude"] is None


@pytest.mark.asyncio
async def test_diagnostics_includes_daily_summary_sensor_snapshot(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics should summarize the daily summary sensors from coordinator data."""

    data = {
        diagnostics_modules.CONF_LATITUDE: 12.3,
        diagnostics_modules.CONF_LONGITUDE: 45.6,
        diagnostics_modules.CONF_LANGUAGE_CODE: "en",
    }
    options = {diagnostics_modules.CONF_FORECAST_DAYS: 3}

    entry = _ConfigEntry(data=data, options=options, entry_id="entry", title="Home")

    coordinator = SimpleNamespace(
        entry_id="entry",
        forecast_days=3,
        language="en",
        create_d1=True,
        create_d2=True,
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        data={
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
            "plants_birch": {"source": "plant", "displayName": "Birch"},
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
                "value": 5,
                "category": "High",
            },
            "type_tree": {
                "source": "type",
                "displayName": "Tree",
                "value": 2,
                "category": "Low",
            },
            "type_grass_d1": {
                "source": "type",
                "displayName": "Grass tomorrow",
                "value": 6,
                "category": "Very High",
            },
            "type_mold": {
                "source": "type",
                "displayName": "Mold",
                "value": float("nan"),
            },
        },
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    daily_summary = diagnostics["daily_summary"]
    assert daily_summary["plants_in_season_today"] == {
        "state": 1,
        "plant_codes": ["OAK"],
        "plant_names": ["Oak"],
        "in_season_count": 1,
        "out_of_season_count": 1,
        "unknown_season_count": 1,
        "total_plant_count": 3,
        "unknown_season_codes": ["BIRCH"],
        "unknown_season_names": ["Birch"],
    }
    assert daily_summary["overall_pollen_risk_today"] == {
        "state": 5,
        "category": "High",
        "description": "High risk",
        "top_pollen_codes": ["GRASS", "WEED"],
        "top_pollen_names": ["Grass", "Weed"],
        "top_pollen_categories": ["High", "High"],
        "tie_count": 2,
    }
    assert daily_summary["top_pollen_types_today"] == {
        "state": "Grass, Weed",
        "top_value": 5,
        "top_pollen_codes": ["GRASS", "WEED"],
        "top_pollen_names": ["Grass", "Weed"],
        "top_pollen_categories": ["High", "High"],
        "tie_count": 2,
    }


@pytest.mark.asyncio
async def test_diagnostics_daily_summary_uses_empty_states_without_data(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics daily summary should be present even without coordinator data."""

    entry = _ConfigEntry(data={}, options={}, entry_id="entry", title="Home")
    coordinator = SimpleNamespace(
        entry_id="entry",
        forecast_days=1,
        language=None,
        create_d1=False,
        create_d2=False,
        last_updated=None,
        data={},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    daily_summary = diagnostics["daily_summary"]
    assert daily_summary["plants_in_season_today"]["state"] is None
    assert daily_summary["plants_in_season_today"]["total_plant_count"] == 0
    assert daily_summary["overall_pollen_risk_today"]["state"] is None
    assert daily_summary["overall_pollen_risk_today"]["tie_count"] == 0
    assert daily_summary["top_pollen_types_today"]["state"] is None
    assert daily_summary["top_pollen_types_today"]["tie_count"] == 0
