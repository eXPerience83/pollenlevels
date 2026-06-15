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
    PollenLocationSetupFailure: type[object]
    CONF_API_KEY: str
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
        CONF_LANGUAGE_CODE as imported_conf_language_code,
        CONF_LATITUDE as imported_conf_latitude,
        CONF_LONGITUDE as imported_conf_longitude,
    )
    from custom_components.pollenlevels.runtime import (
        PollenLevelsRuntimeData as ImportedRuntimeData,
        PollenLocationRuntime as ImportedLocationRuntime,
        PollenLocationSetupFailure as ImportedLocationSetupFailure,
    )

    modules = DiagnosticsModules(
        diag=imported_diag,
        PollenLevelsRuntimeData=ImportedRuntimeData,
        PollenLocationRuntime=ImportedLocationRuntime,
        PollenLocationSetupFailure=ImportedLocationSetupFailure,
        CONF_API_KEY=imported_conf_api_key,
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
    options = {}

    entry = _ConfigEntry(data=data, options=options, entry_id="entry", title="Home")

    coordinator = SimpleNamespace(
        entry_id="entry",
        language="en",
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        data={f"type_{idx}": {} for idx in range(60)},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    location_payload = diagnostics["locations"]["entry"]
    assert location_payload["request_params_example"]["key"] == "***"
    assert diagnostics_modules.CONF_LATITUDE not in diagnostics["entry"]["data"]
    assert diagnostics_modules.CONF_LONGITUDE not in diagnostics["entry"]["data"]
    assert location_payload["request_params_example"]["location.latitude"] == 12.3
    assert location_payload["request_params_example"]["location.longitude"] == 79.0
    assert (
        location_payload["coordinator"]["forecast_days"]
        == diagnostics_modules.diag.FORECAST_DAYS
    )
    assert "create_d1" not in location_payload["coordinator"]
    assert "create_d2" not in location_payload["coordinator"]
    assert location_payload["coordinator"]["data_keys_total"] == 60
    assert len(location_payload["coordinator"]["data_keys"]) == 50
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "12.345678" not in serialized
    assert "78.987654" not in serialized


@pytest.mark.asyncio
async def test_diagnostics_includes_all_locations_without_top_level_duplicates(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics should expose all locations without legacy top-level copies."""

    data = {
        diagnostics_modules.CONF_API_KEY: "secret-token",
        diagnostics_modules.CONF_LANGUAGE_CODE: "en",
    }
    options = {}
    entry = _ConfigEntry(data=data, options=options, entry_id="entry", title="Home")
    entry.subentries = {
        "subentry-1": SimpleNamespace(
            subentry_id="subentry-1", subentry_type="location"
        ),
        "subentry-2": SimpleNamespace(
            subentry_id="subentry-2", subentry_type="location"
        ),
    }

    first_coordinator = SimpleNamespace(
        entry_id="entry",
        subentry_id="subentry-1",
        legacy_entry_id="legacy-entry",
        entity_identity_id="legacy-entry",
        language="en",
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
        language="en",
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
    assert set(diagnostics) == {
        "entry",
        "failed_locations",
        "locations",
        "runtime_summary",
        "registry_summary",
    }
    first_payload = diagnostics["locations"]["subentry-1"]
    second_payload = diagnostics["locations"]["subentry-2"]
    assert diagnostics["runtime_summary"] == {
        "stale_location_count": 0,
        "stale_location_ids": [],
        "failed_location_count": 0,
        "failed_location_ids": [],
    }
    assert "registry_summary" in diagnostics
    assert first_payload["request_params_example"]["key"] == "***"
    assert second_payload["request_params_example"]["key"] == "***"
    assert first_payload["approximate_location"]["latitude_rounded"] == 12.3
    assert first_payload["approximate_location"]["longitude_rounded"] == 79.0
    assert second_payload["approximate_location"]["latitude_rounded"] == 40.7
    assert second_payload["approximate_location"]["longitude_rounded"] == -74.0
    assert first_payload["coordinator"]["has_legacy_entry_id"] is True
    assert first_payload["coordinator"]["has_entity_identity_id"] is True
    assert second_payload["coordinator"]["has_legacy_entry_id"] is False
    assert second_payload["coordinator"]["has_entity_identity_id"] is True
    assert "legacy_entry_id" not in first_payload["coordinator"]
    assert "entity_identity_id" not in first_payload["coordinator"]
    assert second_payload["coordinator"]["subentry_id"] == "subentry-2"


@pytest.mark.asyncio
async def test_diagnostics_do_not_expose_coordinate_derived_identity_strings(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics should summarize identity presence without raw identity values."""

    coordinate_identity = "39.1234_-0.1234"
    entry = _ConfigEntry(
        data={diagnostics_modules.CONF_API_KEY: "secret-token"},
        options={},
        entry_id="entry",
        title="Home",
    )
    entry.subentries = {
        "subentry-1": SimpleNamespace(
            subentry_id="subentry-1", subentry_type="location"
        )
    }
    coordinator = SimpleNamespace(
        entry_id="entry",
        subentry_id="subentry-1",
        legacy_entry_id=coordinate_identity,
        entity_identity_id=coordinate_identity,
        language="en",
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        lat=39.1234,
        lon=-0.1234,
        entry_title="Home",
        data={},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        client=object(),
        locations={
            "subentry-1": diagnostics_modules.PollenLocationRuntime(
                subentry_id="subentry-1",
                coordinator=coordinator,
                legacy_entry_id=coordinate_identity,
            )
        },
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    coord = diagnostics["locations"]["subentry-1"]["coordinator"]
    assert coord["has_legacy_entry_id"] is True
    assert coord["has_entity_identity_id"] is True
    assert "legacy_entry_id" not in coord
    assert "entity_identity_id" not in coord
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert coordinate_identity not in serialized
    assert "39.1234" not in serialized
    assert "-0.1234" not in serialized


@pytest.mark.asyncio
async def test_diagnostics_redacts_multi_location_titles(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Multi-location title redaction should cover all runtime coordinates.

    The first coordinator's user-controlled title contains exact coordinates
    of the second runtime location. Those must be redacted even though the
    second location's payload has not been built yet.
    """
    data = {
        diagnostics_modules.CONF_API_KEY: "secret-token",
    }
    entry = _ConfigEntry(
        data=data,
        options={},
        entry_id="entry",
        title="Home secret-token 40.7128 -74.006",
    )
    entry.subentries = {
        "casa": SimpleNamespace(subentry_id="casa", subentry_type="location"),
        "trabajo": SimpleNamespace(subentry_id="trabajo", subentry_type="location"),
    }

    casa_coordinator = SimpleNamespace(
        entry_id="entry",
        subentry_id="casa",
        language=None,
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        lat=12.345678,
        lon=-98.765432,
        entry_title="Casa secret-token 40.7128 -74.006",
        data={"type_grass": {"source": "type", "code": "GRASS", "value": 2}},
    )
    trabajo_coordinator = SimpleNamespace(
        entry_id="entry",
        subentry_id="trabajo",
        language=None,
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        lat=40.7128,
        lon=-74.006,
        entry_title="Trabajo",
        data={"type_tree": {"source": "type", "code": "TREE", "value": 4}},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        client=object(),
        locations={
            "casa": diagnostics_modules.PollenLocationRuntime(
                subentry_id="casa",
                coordinator=casa_coordinator,
                legacy_entry_id=None,
            ),
            "trabajo": diagnostics_modules.PollenLocationRuntime(
                subentry_id="trabajo",
                coordinator=trabajo_coordinator,
                legacy_entry_id=None,
            ),
        },
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    assert diagnostics["locations"]["casa"]["title"] == "Casa *** *** ***"
    assert diagnostics["locations"]["trabajo"]["title"] == "Trabajo"
    assert diagnostics["entry"]["title"] == "Home *** *** ***"
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "secret-token" not in serialized
    assert "12.345678" not in serialized
    assert "-98.765432" not in serialized
    assert "40.7128" not in serialized
    assert "-74.006" not in serialized


@pytest.mark.asyncio
async def test_diagnostics_includes_fallback_location_without_subentries(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics should keep fallback runtime locations when no subentries exist."""

    data = {
        diagnostics_modules.CONF_API_KEY: "secret-token",
        diagnostics_modules.CONF_LATITUDE: 12.345678,
        diagnostics_modules.CONF_LONGITUDE: -98.765432,
    }
    entry = _ConfigEntry(
        data=data,
        options={},
        entry_id="entry",
        title="Home secret-token 12.345678",
    )
    coordinator = SimpleNamespace(
        entry_id="entry",
        subentry_id="entry",
        language=None,
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        lat=12.345678,
        lon=-98.765432,
        entry_title="Home secret-token -98.765432",
        data={},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        client=object(),
        locations={
            entry.entry_id: diagnostics_modules.PollenLocationRuntime(
                subentry_id=entry.entry_id, coordinator=coordinator
            )
        },
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    assert set(diagnostics["locations"]) == {"entry"}
    assert diagnostics["runtime_summary"]["stale_location_count"] == 0
    assert diagnostics["runtime_summary"]["stale_location_ids"] == []
    assert diagnostics["entry"]["title"] == "Home *** ***"
    assert diagnostics["locations"]["entry"]["title"] == "Home *** ***"
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "secret-token" not in serialized
    assert "12.345678" not in serialized
    assert "-98.765432" not in serialized


@pytest.mark.asyncio
async def test_diagnostics_redacts_legacy_title_without_runtime_data(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics should redact legacy title secrets before runtime exists."""
    data = {
        diagnostics_modules.CONF_API_KEY: "secret-token",
        diagnostics_modules.CONF_LATITUDE: 12.345678,
        diagnostics_modules.CONF_LONGITUDE: -98.765432,
    }
    entry = _ConfigEntry(
        data=data,
        options={},
        entry_id="entry",
        title="Home secret-token 12.345678 -98.765432",
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    assert diagnostics["entry"]["title"] == "Home *** *** ***"
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "secret-token" not in serialized
    assert "12.345678" not in serialized
    assert "-98.765432" not in serialized


@pytest.mark.asyncio
async def test_diagnostics_redacts_v3_subentry_title_without_runtime_data(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics should redact v3 title coordinates before runtime exists."""
    data = {diagnostics_modules.CONF_API_KEY: "secret-token"}
    entry = _ConfigEntry(
        data=data,
        options={},
        entry_id="entry",
        title="Home secret-token 12.345678 -98.765432",
    )
    entry.subentries = {
        "subentry-1": SimpleNamespace(
            subentry_id="subentry-1",
            subentry_type="location",
            data={
                diagnostics_modules.CONF_LATITUDE: 12.345678,
                diagnostics_modules.CONF_LONGITUDE: -98.765432,
            },
        )
    }

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    assert diagnostics["entry"]["title"] == "Home *** *** ***"
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "secret-token" not in serialized
    assert "12.345678" not in serialized
    assert "-98.765432" not in serialized


@pytest.mark.asyncio
async def test_diagnostics_summarizes_runtime_locations_when_parent_has_no_locations(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics should summarize stale v3 runtime locations after the last deletion."""

    data = {diagnostics_modules.CONF_API_KEY: "secret-token"}
    entry = _ConfigEntry(data=data, options={}, entry_id="entry", title="Home")
    entry.subentries = {}
    coordinator = SimpleNamespace(
        entry_id="entry",
        subentry_id="deleted-location",
        language=None,
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        lat=12.345678,
        lon=-98.765432,
        entry_title="Deleted",
        data={},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        client=object(),
        locations={
            "deleted-location": diagnostics_modules.PollenLocationRuntime(
                subentry_id="deleted-location", coordinator=coordinator
            )
        },
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    assert diagnostics["locations"] == {}
    assert diagnostics["runtime_summary"] == {
        "stale_location_count": 1,
        "stale_location_ids": ["deleted-location"],
        "failed_location_count": 0,
        "failed_location_ids": [],
    }
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "secret-token" not in serialized
    assert "12.345678" not in serialized
    assert "-98.765432" not in serialized


@pytest.mark.asyncio
async def test_diagnostics_summarizes_stale_runtime_locations(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics should exclude deleted runtime locations and summarize them."""

    data = {
        diagnostics_modules.CONF_API_KEY: "secret-token",
        diagnostics_modules.CONF_LANGUAGE_CODE: "en",
    }
    entry = _ConfigEntry(data=data, options={}, entry_id="entry", title="Home")
    entry.subentries = {
        "casa": SimpleNamespace(subentry_id="casa", subentry_type="location"),
        "guineta": SimpleNamespace(subentry_id="guineta", subentry_type="location"),
    }

    def _coordinator(subentry_id: str, lat: float, lon: float) -> SimpleNamespace:
        return SimpleNamespace(
            entry_id="entry",
            subentry_id=subentry_id,
            language="en",
            last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
            lat=lat,
            lon=lon,
            entry_title=subentry_id,
            data={},
        )

    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        client=object(),
        locations={
            "casa": diagnostics_modules.PollenLocationRuntime(
                subentry_id="casa",
                coordinator=_coordinator("casa", 12.345678, -98.765432),
            ),
            "trabajo": diagnostics_modules.PollenLocationRuntime(
                subentry_id="trabajo",
                coordinator=_coordinator("trabajo", 23.456789, -87.654321),
            ),
            "guineta": diagnostics_modules.PollenLocationRuntime(
                subentry_id="guineta",
                coordinator=_coordinator("guineta", 34.567891, -76.543219),
            ),
        },
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    assert set(diagnostics["locations"]) == {"casa", "guineta"}
    assert diagnostics["runtime_summary"] == {
        "stale_location_count": 1,
        "stale_location_ids": ["trabajo"],
        "failed_location_count": 0,
        "failed_location_ids": [],
    }
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "secret-token" not in serialized
    assert "12.345678" not in serialized
    assert "-98.765432" not in serialized
    assert "23.456789" not in serialized
    assert "-87.654321" not in serialized


@pytest.mark.asyncio
async def test_diagnostics_reports_failed_locations_separately_from_stale(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics should keep failed setup locations separate from stale runtime."""

    data = {
        diagnostics_modules.CONF_API_KEY: "secret-token",
        diagnostics_modules.CONF_LANGUAGE_CODE: "en",
    }
    entry = _ConfigEntry(data=data, options={}, entry_id="entry", title="Home")
    entry.subentries = {
        "loaded": SimpleNamespace(subentry_id="loaded", subentry_type="location"),
        "failed": SimpleNamespace(
            subentry_id="failed",
            subentry_type="location",
            data={
                diagnostics_modules.CONF_LATITUDE: 12.345678,
                diagnostics_modules.CONF_LONGITUDE: -98.765432,
            },
        ),
    }

    loaded_coordinator = SimpleNamespace(
        entry_id="entry",
        subentry_id="loaded",
        language="en",
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        lat=40.4168,
        lon=-3.7038,
        entry_title="Loaded",
        data={},
    )
    stale_coordinator = SimpleNamespace(
        entry_id="entry",
        subentry_id="deleted",
        language="en",
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        lat=23.456789,
        lon=-87.654321,
        entry_title="Deleted",
        data={},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        client=object(),
        locations={
            "loaded": diagnostics_modules.PollenLocationRuntime(
                subentry_id="loaded",
                coordinator=loaded_coordinator,
            ),
            "deleted": diagnostics_modules.PollenLocationRuntime(
                subentry_id="deleted",
                coordinator=stale_coordinator,
            ),
        },
        failed_locations={
            "failed": diagnostics_modules.PollenLocationSetupFailure(
                subentry_id="failed",
                title="Failed secret-token 12.345678",
                error_type="UpdateFailed",
                reason=(
                    "API response missing data for key=secret-token "
                    "location.latitude=12.345678"
                ),
            )
        },
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    assert set(diagnostics["locations"]) == {"loaded"}
    assert set(diagnostics["failed_locations"]) == {"failed"}
    assert diagnostics["runtime_summary"] == {
        "stale_location_count": 1,
        "stale_location_ids": ["deleted"],
        "failed_location_count": 1,
        "failed_location_ids": ["failed"],
    }
    failed_payload = diagnostics["failed_locations"]["failed"]
    assert failed_payload["error_type"] == "UpdateFailed"
    assert failed_payload["will_retry_on_reload"] is True
    assert failed_payload["is_auth_error"] is False
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "secret-token" not in serialized
    assert "12.345678" not in serialized
    assert "23.456789" not in serialized
    assert "-87.654321" not in serialized


@pytest.mark.asyncio
async def test_diagnostics_marks_invalid_stored_location_as_not_reload_retryable(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Invalid stored location diagnostics should not claim reload retry is enough."""

    data = {
        diagnostics_modules.CONF_API_KEY: "secret-token",
        diagnostics_modules.CONF_LANGUAGE_CODE: "en",
    }
    entry = _ConfigEntry(data=data, options={}, entry_id="entry", title="Home")
    entry.subentries = {
        "invalid": SimpleNamespace(subentry_id="invalid", subentry_type="location")
    }
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        client=object(),
        locations={},
        failed_locations={
            "invalid": diagnostics_modules.PollenLocationSetupFailure(
                subentry_id="invalid",
                title="Invalid",
                error_type="InvalidStoredLocation",
                reason="Pollen Levels location has invalid stored coordinates",
            )
        },
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    failed_payload = diagnostics["failed_locations"]["invalid"]
    assert failed_payload["error_type"] == "InvalidStoredLocation"
    assert failed_payload["will_retry_on_reload"] is False


@pytest.mark.asyncio
async def test_diagnostics_request_days_are_fixed(
    diagnostics_modules: DiagnosticsModules,
) -> None:
    """Diagnostics request params should always show the fixed Google API limit."""

    data = {
        diagnostics_modules.CONF_LATITUDE: 12.3,
        diagnostics_modules.CONF_LONGITUDE: 45.6,
        diagnostics_modules.CONF_LANGUAGE_CODE: "en",
    }
    options = {}

    entry = _ConfigEntry(data=data, options=options, entry_id="entry", title="Home")

    coordinator = SimpleNamespace(
        entry_id="entry",
        language="en",
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        data={"type_grass": {"source": "type"}},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    location_payload = diagnostics["locations"]["entry"]
    assert (
        location_payload["request_params_example"]["days"]
        == diagnostics_modules.diag.FORECAST_DAYS
    )


@pytest.mark.parametrize(
    ("stored_language", "expected_language"),
    [
        (" es ", "es"),
        ("es-ES", "es-ES"),
        ("bad code", None),
    ],
)
@pytest.mark.asyncio
async def test_diagnostics_normalizes_request_example_language_code(
    diagnostics_modules: DiagnosticsModules,
    stored_language: str,
    expected_language: str | None,
) -> None:
    """Diagnostics request params should match runtime language normalization."""

    data = {
        diagnostics_modules.CONF_API_KEY: "test-api-key",
        diagnostics_modules.CONF_LATITUDE: 12.3,
        diagnostics_modules.CONF_LONGITUDE: 45.6,
    }
    options = {diagnostics_modules.CONF_LANGUAGE_CODE: stored_language}

    entry = _ConfigEntry(data=data, options=options, entry_id="entry", title="Home")

    coordinator = SimpleNamespace(
        entry_id="entry",
        language=expected_language,
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        data={"type_grass": {"source": "type"}},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    request_params = diagnostics["locations"]["entry"]["request_params_example"]
    if expected_language is None:
        assert "languageCode" not in request_params
    else:
        assert request_params["languageCode"] == expected_language


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
    options = {}

    entry = _ConfigEntry(data=data, options=options, entry_id="entry", title="Home")
    entry.subentries = {
        "entry": SimpleNamespace(subentry_id="entry", subentry_type="location")
    }

    coordinator = SimpleNamespace(
        entry_id="entry",
        subentry_id="entry",
        language="en",
        last_updated=dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        data={"type_grass": {"source": "type"}},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    location_payload = diagnostics["locations"]["entry"]
    assert location_payload["approximate_location"]["latitude_rounded"] is None
    assert location_payload["approximate_location"]["longitude_rounded"] is None
    assert location_payload["request_params_example"]["location.latitude"] is None
    assert location_payload["request_params_example"]["location.longitude"] is None


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
    options = {}

    entry = _ConfigEntry(data=data, options=options, entry_id="entry", title="Home")

    coordinator = SimpleNamespace(
        entry_id="entry",
        language="en",
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

    daily_summary = diagnostics["locations"]["entry"]["daily_summary"]
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
    entry.subentries = {
        "entry": SimpleNamespace(subentry_id="entry", subentry_type="location")
    }
    coordinator = SimpleNamespace(
        entry_id="entry",
        subentry_id="entry",
        language=None,
        last_updated=None,
        data={},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        None, entry
    )

    daily_summary = diagnostics["locations"]["entry"]["daily_summary"]
    assert daily_summary["plants_in_season_today"]["state"] is None
    assert daily_summary["plants_in_season_today"]["total_plant_count"] == 0
    assert daily_summary["overall_pollen_risk_today"]["state"] is None
    assert daily_summary["overall_pollen_risk_today"]["tie_count"] == 0
    assert daily_summary["top_pollen_types_today"]["state"] is None
    assert daily_summary["top_pollen_types_today"]["tie_count"] == 0


@pytest.mark.asyncio
async def test_diagnostics_includes_registry_summary_without_sensitive_values(
    diagnostics_modules: DiagnosticsModules,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Diagnostics should summarize registry subentry links without IDs or secrets."""

    helpers_mod = ModuleType("homeassistant.helpers")
    entity_registry_mod = ModuleType("homeassistant.helpers.entity_registry")
    device_registry_mod = ModuleType("homeassistant.helpers.device_registry")

    entity_registry_mod.async_get = lambda _hass: object()
    entity_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: [
        SimpleNamespace(
            entity_id="sensor.secret_home_12_345678_gramineas",
            unique_id="legacy-home_type_grass",
            platform=diagnostics_modules.diag.DOMAIN,
            config_subentry_id="subentry-home",
        ),
        SimpleNamespace(
            entity_id="sensor.secret_home_12_345678_tree",
            unique_id="legacy-home_type_tree",
            platform=diagnostics_modules.diag.DOMAIN,
            config_subentry_id=None,
        ),
        SimpleNamespace(
            entity_id="sensor.other",
            unique_id="other",
            platform="other",
            config_subentry_id=None,
        ),
    ]

    device_registry_mod.async_get = lambda _hass: object()
    device_registry_mod.async_entries_for_config_entry = lambda _registry, entry_id: [
        SimpleNamespace(config_entries_subentries={entry_id: {"subentry-home"}}),
        SimpleNamespace(config_entries_subentries={entry_id: {None}}),
        SimpleNamespace(config_entries_subentries={entry_id: {"subentry-office"}}),
    ]

    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers_mod)
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.entity_registry", entity_registry_mod
    )
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry_mod
    )

    data = {
        diagnostics_modules.CONF_API_KEY: "secret-token",
        diagnostics_modules.CONF_LATITUDE: 12.345678,
        diagnostics_modules.CONF_LONGITUDE: -98.765432,
    }
    entry = _ConfigEntry(data=data, options={}, entry_id="entry", title="Home")
    coordinator = SimpleNamespace(
        entry_id="entry",
        language=None,
        last_updated=None,
        lat=12.345678,
        lon=-98.765432,
        data={},
    )
    entry.runtime_data = diagnostics_modules.PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    diagnostics = await diagnostics_modules.diag.async_get_config_entry_diagnostics(
        object(), entry
    )

    registry_summary = diagnostics["registry_summary"]
    assert registry_summary["entities"] == {
        "total": 2,
        "without_subentry": 1,
        "by_subentry_id": {"subentry-home": 1},
    }
    assert registry_summary["devices"] == {
        "total": 3,
        "without_subentry": 1,
        "by_subentry_id": {"subentry-home": 1, "subentry-office": 1},
        "with_legacy_none_association": 1,
    }
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "secret-token" not in serialized
    assert "12.345678" not in serialized
    assert "-98.765432" not in serialized
    assert "sensor.secret_home" not in serialized
