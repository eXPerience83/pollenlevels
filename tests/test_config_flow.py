"""Tests for the Pollen Levels config flow language validation."""

# ruff: noqa: E402

from __future__ import annotations

import ast
import asyncio
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from tests._ha_stubs import (
    clear_integration_modules,
    stub_aiohttp_module,
    stub_custom_components_packages,
    stub_exceptions,
    stub_homeassistant_package,
    stub_selector_module,
    stub_update_coordinator_module,
    stub_util_dt_module,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Minimal package and dependency stubs installed by fixtures before imports.
# ---------------------------------------------------------------------------


class _StubConfigFlow:
    def __init_subclass__(cls, **_kwargs):
        return super().__init_subclass__()

    async def async_set_unique_id(self, *_args, **_kwargs):
        return None

    def _abort_if_unique_id_configured(self):
        return None

    def async_abort(self, *, reason=None):
        return {"type": "abort", "reason": reason}

    def async_show_form(self, *args, **kwargs):  # pragma: no cover - not used
        return {"step_id": kwargs.get("step_id") or (args[0] if args else None)}

    def async_create_entry(self, *args, **kwargs):  # pragma: no cover - not used
        return {
            "title": kwargs.get("title"),
            "data": kwargs.get("data"),
            "options": kwargs.get("options"),
            "subentries": kwargs.get("subentries"),
        }

    def add_suggested_values_to_schema(self, schema, suggested_values):
        return schema

    def _get_reauth_entry(self):
        entry_id = self.context.get("entry_id")
        return self.hass.config_entries.async_get_entry(entry_id)

    def _get_reconfigure_entry(self):
        entry_id = self.context.get("entry_id")
        return self.hass.config_entries.async_get_entry(entry_id)

    def async_update_reload_and_abort(
        self, entry, *, data_updates=None, reason=None, **kwargs
    ):
        new_data = dict(entry.data)
        if data_updates:
            new_data.update(data_updates)
        self.hass.config_entries.async_update_entry(entry, data=new_data)
        if "unique_id" in kwargs:
            entry.unique_id = kwargs["unique_id"]
        self.hass.config_entries.async_reload(entry.entry_id)
        return self.async_abort(reason=reason)


class _StubOptionsFlow:
    pass


class _StubOptionsFlowWithReload(_StubOptionsFlow):
    pass


class _StubAbortFlow(Exception):
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


class _StubConfigSubentryFlow:
    def async_create_entry(
        self,
        *,
        title=None,
        data=None,
        description=None,
        description_placeholders=None,
        unique_id=None,
    ):
        return {
            "type": "create_entry",
            "title": title,
            "data": data,
            "description": description,
            "description_placeholders": description_placeholders,
            "unique_id": unique_id,
        }

    def async_show_form(self, *args, **kwargs):
        result = {
            "type": "form",
            "step_id": kwargs.get("step_id") or (args[0] if args else None),
            "errors": kwargs.get("errors") or {},
        }
        if "description_placeholders" in kwargs:
            result["description_placeholders"] = kwargs["description_placeholders"]
        return result

    def async_abort(self, *, reason=None, description_placeholders=None):
        return {
            "type": "abort",
            "reason": reason,
            "description_placeholders": description_placeholders,
        }

    def async_update_and_abort(
        self,
        entry,
        subentry,
        *,
        unique_id=None,
        title=None,
        data=None,
        data_updates=None,
    ):
        if unique_id is not None:
            subentry.unique_id = unique_id
        if title is not None:
            subentry.title = title
        if data_updates is not None:
            data = {**subentry.data, **data_updates}
        if data is not None:
            subentry.data = data
        return self.async_abort(reason="reconfigure_successful")

    def async_update_reload_and_abort(self, entry, subentry, **kwargs):
        result = self.async_update_and_abort(entry, subentry, **kwargs)
        self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return result

    def _get_entry(self):
        return self.hass.config_entries.async_get_entry(self.handler[0])

    def _get_reconfigure_subentry(self):
        entry = self._get_entry()
        return entry.subentries[self.context["subentry_id"]]


class _StubConfigEntry:
    def __init__(
        self,
        data=None,
        options=None,
        entry_id="stub-entry",
        subentries=None,
        unique_id=None,
    ):
        self.data = data or {}
        self.options = options or {}
        self.entry_id = entry_id
        self.subentries = subentries or {}
        self.unique_id = unique_id
        raw = self.data.get("name", "Pollen Levels") or ""
        self.title = raw.strip() or "Pollen Levels"


class _StubConfigEntryAuthFailed(Exception):
    pass


class _StubUpdateFailed(Exception):
    pass


class _StubDataUpdateCoordinator:
    def __init__(self, *args, **kwargs):
        self.hass = args[0] if args else None
        self.data = None
        self.update_interval = kwargs.get("update_interval")

    async def async_refresh(self):
        return None

    async def async_request_refresh(self):
        return None

    async def async_config_entry_first_refresh(self):
        return None


class _StubCoordinatorEntity:
    def __init__(self, coordinator=None):
        self.coordinator = coordinator


class _StubInvalid(Exception):
    def __init__(self, error_message=""):
        super().__init__(error_message)
        self.error_message = error_message


class _StubSchema:
    def __init__(self, schema):
        self.schema = schema


def _latitude(value=None):
    try:
        lat = float(value)
    except TypeError, ValueError:
        # Mirror Home Assistant's cv.latitude behavior for invalid types.
        raise _StubInvalid("latitude_type") from None
    if lat < -90 or lat > 90:
        raise _StubInvalid("latitude_range")
    return lat


def _longitude(value=None):
    try:
        lon = float(value)
    except TypeError, ValueError:
        # Mirror Home Assistant's cv.longitude behavior for invalid types.
        raise _StubInvalid("longitude_type") from None

    if lon < -180 or lon > 180:
        raise _StubInvalid("longitude_range")

    return lon


class _StubSession:
    """Async session stub exposing a get() method."""

    def __init__(self, *, status: int = 200, body: bytes = b"{}") -> None:
        self._status = status
        self._body = body

    def get(self, *args, **kwargs) -> _StubResponse:
        """Return an async context manager response stub."""

        return _StubResponse(self._status, body=self._body)


def _install_homeassistant_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_integration_modules(monkeypatch=monkeypatch)
    stub_custom_components_packages(root=ROOT, monkeypatch=monkeypatch)

    ha_mod = stub_homeassistant_package(monkeypatch=monkeypatch)

    config_entries_mod = ModuleType("homeassistant.config_entries")
    config_entries_mod.ConfigFlow = _StubConfigFlow
    config_entries_mod.OptionsFlow = _StubOptionsFlow
    config_entries_mod.OptionsFlowWithReload = _StubOptionsFlowWithReload
    config_entries_mod.ConfigEntry = _StubConfigEntry
    config_entries_mod.AbortFlow = _StubAbortFlow
    config_entries_mod.ConfigSubentry = _StubConfigSubentry
    config_entries_mod.ConfigSubentryFlow = _StubConfigSubentryFlow
    config_entries_mod.ConfigSubentryData = dict
    config_entries_mod.ConfigFlowResult = dict
    config_entries_mod.SubentryFlowResult = dict
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries_mod)

    stub_exceptions(
        ConfigEntryAuthFailed=_StubConfigEntryAuthFailed, monkeypatch=monkeypatch
    )

    const_mod = ModuleType("homeassistant.const")
    const_mod.CONF_LATITUDE = "latitude"
    const_mod.CONF_LOCATION = "location"
    const_mod.CONF_LONGITUDE = "longitude"
    const_mod.CONF_NAME = "name"
    monkeypatch.setitem(sys.modules, "homeassistant.const", const_mod)

    helpers_mod = ModuleType("homeassistant.helpers")
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers_mod)

    config_validation_mod = ModuleType("homeassistant.helpers.config_validation")
    config_validation_mod.latitude = _latitude
    config_validation_mod.longitude = _longitude
    config_validation_mod.string = lambda value=None: value
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.config_validation", config_validation_mod
    )

    aiohttp_client_mod = ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client_mod.async_get_clientsession = lambda hass: _StubSession()
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.aiohttp_client", aiohttp_client_mod
    )

    stub_update_coordinator_module(
        update_failed=_StubUpdateFailed,
        data_update_coordinator=_StubDataUpdateCoordinator,
        coordinator_entity=_StubCoordinatorEntity,
        monkeypatch=monkeypatch,
    )

    stub_util_dt_module(monkeypatch=monkeypatch)

    stub_selector_module(monkeypatch=monkeypatch, include_section=True)

    ha_mod.helpers = helpers_mod
    ha_mod.config_entries = config_entries_mod

    stub_aiohttp_module(monkeypatch=monkeypatch)

    vol_mod = ModuleType("voluptuous")
    vol_mod.Invalid = _StubInvalid
    vol_mod.Schema = lambda schema, **kwargs: _StubSchema(schema)
    vol_mod.Optional = lambda key, **kwargs: key
    vol_mod.Required = lambda key, **kwargs: key
    vol_mod.All = lambda *args, **kwargs: None
    vol_mod.Coerce = lambda *args, **kwargs: None
    vol_mod.Range = lambda *args, **kwargs: None
    vol_mod.In = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "voluptuous", vol_mod)


@dataclass(frozen=True)
class ConfigFlowStubs:
    """Fixture-provided config flow imports and Home Assistant stubs."""

    config_flow: ModuleType
    PollenLevelsConfigFlow: type[object]
    PollenLevelsOptionsFlow: type[object]
    StubConfigEntry: type[_StubConfigEntry]
    ConfigEntryAuthFailed: type[Exception]
    UpdateFailed: type[Exception]
    CONF_LATITUDE: str
    CONF_LOCATION: str
    CONF_LONGITUDE: str
    CONF_NAME: str
    CONF_API_KEY: str
    CONF_CREATE_FORECAST_SENSORS: str
    CONF_FORECAST_DAYS: str
    CONF_LANGUAGE_CODE: str
    CONF_UPDATE_INTERVAL: str
    DEFAULT_ENTRY_TITLE: str
    DEFAULT_UPDATE_INTERVAL: int
    MAX_UPDATE_INTERVAL_HOURS: int
    FORECAST_DAYS: int


@pytest.fixture(name="config_flow_stubs", autouse=True)
def config_flow_stubs_fixture(monkeypatch: pytest.MonkeyPatch) -> ConfigFlowStubs:
    """Install scoped stubs and import the config flow under those stubs."""

    _install_homeassistant_stubs(monkeypatch)

    ha_const = importlib.import_module("homeassistant.const")
    ha_exceptions = importlib.import_module("homeassistant.exceptions")
    ha_update_coordinator = importlib.import_module(
        "homeassistant.helpers.update_coordinator"
    )
    cf_module = importlib.import_module("custom_components.pollenlevels.config_flow")
    const = importlib.import_module("custom_components.pollenlevels.const")

    stubs = ConfigFlowStubs(
        config_flow=cf_module,
        PollenLevelsConfigFlow=cf_module.PollenLevelsConfigFlow,
        PollenLevelsOptionsFlow=cf_module.PollenLevelsOptionsFlow,
        StubConfigEntry=_StubConfigEntry,
        ConfigEntryAuthFailed=ha_exceptions.ConfigEntryAuthFailed,
        UpdateFailed=ha_update_coordinator.UpdateFailed,
        CONF_LATITUDE=ha_const.CONF_LATITUDE,
        CONF_LOCATION=ha_const.CONF_LOCATION,
        CONF_LONGITUDE=ha_const.CONF_LONGITUDE,
        CONF_NAME=ha_const.CONF_NAME,
        CONF_API_KEY=const.CONF_API_KEY,
        CONF_CREATE_FORECAST_SENSORS=const.CONF_CREATE_FORECAST_SENSORS,
        CONF_FORECAST_DAYS=const.CONF_FORECAST_DAYS,
        CONF_LANGUAGE_CODE=const.CONF_LANGUAGE_CODE,
        CONF_UPDATE_INTERVAL=const.CONF_UPDATE_INTERVAL,
        DEFAULT_ENTRY_TITLE=const.DEFAULT_ENTRY_TITLE,
        DEFAULT_UPDATE_INTERVAL=const.DEFAULT_UPDATE_INTERVAL,
        MAX_UPDATE_INTERVAL_HOURS=const.MAX_UPDATE_INTERVAL_HOURS,
        FORECAST_DAYS=const.FORECAST_DAYS,
    )

    return stubs


class _StubResponse:
    def __init__(self, status: int, body: bytes | None = None) -> None:
        self.status = status
        self._body = body or b"{}"

    async def __aenter__(self):  # pragma: no cover - trivial
        return self

    async def __aexit__(self, exc_type, exc, tb):  # pragma: no cover - trivial
        return None

    async def read(self) -> bytes:
        return self._body

    async def json(self):
        import json as _json

        return _json.loads(self._body.decode())

    async def text(self) -> str:
        return self._body.decode()


class _SequenceSession:
    def __init__(self, responses: list[_StubResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[tuple, dict]] = []

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def _collect_error_keys_from_config_flow() -> set[str]:
    """Parse the config flow to extract all error keys used in forms."""

    source = (ROOT / "custom_components" / "pollenlevels" / "config_flow.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    language_error_returns: set[str] = set()

    class _LanguageErrorVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if node.name == "_language_error_to_form_key":
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Return)
                        and isinstance(child.value, ast.Constant)
                        and isinstance(child.value.value, str)
                    ):
                        language_error_returns.add(child.value.value)

    _LanguageErrorVisitor().visit(tree)

    error_keys: set[str] = set()

    def _extract_error_values(value: ast.AST) -> set[str]:
        values: set[str] = set()
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.add(value.value)
        elif (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "_language_error_to_form_key"
        ):
            values.update(language_error_returns)
        return values

    class _ErrorsVisitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
            for target in node.targets:
                self._record_errors(target, node.value)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
            self._record_errors(node.target, node.value)
            self.generic_visit(node)

        def _record_errors(self, target: ast.AST, value: ast.AST | None) -> None:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "errors"
                and value is not None
            ):
                error_keys.update(_extract_error_values(value))

    _ErrorsVisitor().visit(tree)
    return error_keys


def test_validate_input_invalid_language_key_mapping(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """Invalid language formats should surface the translation key."""

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                config_flow_stubs.CONF_API_KEY: "test-key",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: "1",
                    config_flow_stubs.CONF_LONGITUDE: "2",
                },
                config_flow_stubs.CONF_LANGUAGE_CODE: "bad code",
            },
            check_unique_id=False,
        )
    )

    assert errors == {config_flow_stubs.CONF_LANGUAGE_CODE: "invalid_language_format"}
    assert normalized is None


def test_validate_input_invalid_language_code_not_logged_raw(
    config_flow_stubs: ConfigFlowStubs, caplog
) -> None:
    """Invalid language code should not log the raw user-provided value."""
    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    with caplog.at_level("WARNING", logger=config_flow_stubs.config_flow.__name__):
        errors, normalized = asyncio.run(
            flow._async_validate_input(
                {
                    config_flow_stubs.CONF_API_KEY: "test-key",
                    config_flow_stubs.CONF_LOCATION: {
                        config_flow_stubs.CONF_LATITUDE: "1",
                        config_flow_stubs.CONF_LONGITUDE: "2",
                    },
                    config_flow_stubs.CONF_LANGUAGE_CODE: "bad code",
                },
                check_unique_id=False,
            )
        )

    assert "bad code" not in caplog.text
    assert errors == {config_flow_stubs.CONF_LANGUAGE_CODE: "invalid_language_format"}


def test_validate_input_empty_api_key(
    config_flow_stubs: ConfigFlowStubs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Blank or whitespace API keys should be rejected without HTTP calls."""

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    session_called = False

    def _raise_session(hass):
        nonlocal session_called
        session_called = True
        raise AssertionError("async_get_clientsession should not be called")

    monkeypatch.setattr(
        config_flow_stubs.config_flow, "async_get_clientsession", _raise_session
    )

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                config_flow_stubs.CONF_API_KEY: "   ",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: 1.0,
                    config_flow_stubs.CONF_LONGITUDE: 2.0,
                },
            },
            check_unique_id=False,
        )
    )

    assert errors == {config_flow_stubs.CONF_API_KEY: "empty"}
    assert normalized is None
    assert session_called is False


def test_language_error_to_form_key_mapping(config_flow_stubs: ConfigFlowStubs) -> None:
    """voluptuous error messages map to localized form keys."""

    assert (
        config_flow_stubs.config_flow._language_error_to_form_key(
            config_flow_stubs.config_flow.vol.Invalid("empty")
        )
        == "invalid_language_format"
    )
    assert (
        config_flow_stubs.config_flow._language_error_to_form_key(
            config_flow_stubs.config_flow.vol.Invalid("invalid_language")
        )
        == "invalid_language_format"
    )


def test_validate_input_invalid_coordinates(config_flow_stubs: ConfigFlowStubs) -> None:
    """Non-numeric coordinates should surface a dedicated error."""

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                config_flow_stubs.CONF_API_KEY: "test-key",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: "north",
                    config_flow_stubs.CONF_LONGITUDE: "west",
                },
            },
            check_unique_id=False,
        )
    )

    assert errors == {config_flow_stubs.CONF_LOCATION: "invalid_coordinates"}
    assert normalized is None


def test_validate_input_out_of_range_coordinates(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """Coordinates outside valid ranges should be rejected."""

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                config_flow_stubs.CONF_API_KEY: "test-key",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: "200",
                    config_flow_stubs.CONF_LONGITUDE: "-300",
                },
            },
            check_unique_id=False,
        )
    )

    assert errors == {config_flow_stubs.CONF_LOCATION: "invalid_coordinates"}
    assert normalized is None


def test_validate_input_missing_longitude(config_flow_stubs: ConfigFlowStubs) -> None:
    """Missing longitude should trigger an invalid_coordinates error."""

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                config_flow_stubs.CONF_API_KEY: "test-key",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: 10.0
                },
            },
            check_unique_id=False,
        )
    )

    assert errors == {config_flow_stubs.CONF_LOCATION: "invalid_coordinates"}
    assert normalized is None


def test_validate_input_non_dict_location(config_flow_stubs: ConfigFlowStubs) -> None:
    """Non-dictionary location payloads are invalid."""

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                config_flow_stubs.CONF_API_KEY: "test-key",
                config_flow_stubs.CONF_LOCATION: "not-a-dict",
            },
            check_unique_id=False,
        )
    )

    assert errors == {config_flow_stubs.CONF_LOCATION: "invalid_coordinates"}
    assert normalized is None


def _patch_client_fetch(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: dict | None = None,
    error: Exception | None = None,
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    async def _fake_fetch(self, **kwargs):
        calls.append(kwargs)
        if error is not None:
            raise error
        return result or _valid_daily_info_payload()

    monkeypatch.setattr(
        config_flow_stubs.config_flow.GooglePollenApiClient,
        "async_fetch_pollen_data",
        _fake_fetch,
    )
    return calls


def _valid_daily_info_payload() -> dict[str, list[dict[str, dict[str, int]]]]:
    return {"dailyInfo": [{"date": {"year": 2026, "month": 6, "day": 3}}]}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"dailyInfo": None},
        {"dailyInfo": []},
        {"dailyInfo": "invalid"},
        {"dailyInfo": [{}]},
        {"dailyInfo": [{"day": "D0"}]},
        {"dailyInfo": [{"indexInfo": []}]},
        {"dailyInfo": ["bad"]},
        {"dailyInfo": [{"pollenTypeInfo": []}]},
        {"dailyInfo": [{"pollenTypeInfo": ["bad"]}]},
        {"dailyInfo": [{"pollenTypeInfo": [{}]}]},
        {"dailyInfo": [{"pollenTypeInfo": [{"displayName": "Grass"}]}]},
        {"dailyInfo": [{"pollenTypeInfo": [{"code": ""}]}]},
        {"dailyInfo": [{"pollenTypeInfo": [{"code": "   "}]}]},
        {"dailyInfo": [{"plantInfo": []}]},
        {"dailyInfo": [{"plantInfo": ["bad"]}]},
        {"dailyInfo": [{"plantInfo": [{}]}]},
        {"dailyInfo": [{"plantInfo": [{"displayName": "Olive"}]}]},
        {"dailyInfo": [{"plantInfo": [{"code": ""}]}]},
        {"dailyInfo": [{"plantInfo": [{"code": "   "}]}]},
    ],
)
def test_daily_info_is_valid_rejects_structurally_empty_payloads(
    config_flow_stubs: ConfigFlowStubs,
    payload: object,
) -> None:
    """Structurally empty validation responses should not pass the flow."""

    assert not config_flow_stubs.config_flow._daily_info_is_valid(payload)


@pytest.mark.parametrize(
    "payload",
    [
        _valid_daily_info_payload(),
        {"dailyInfo": [{"pollenTypeInfo": [{"code": "GRASS"}]}]},
        {"dailyInfo": [{"pollenTypeInfo": [{}, {"code": "GRASS"}]}]},
        {"dailyInfo": [{"plantInfo": [{"code": "OLIVE"}]}]},
    ],
)
def test_daily_info_is_valid_accepts_structurally_useful_payloads(
    config_flow_stubs: ConfigFlowStubs,
    payload: object,
) -> None:
    """Validation accepts forecast data that can seed setup sensors."""

    assert config_flow_stubs.config_flow._daily_info_is_valid(payload)


def _base_user_input(config_flow_stubs) -> dict:
    return {
        config_flow_stubs.CONF_API_KEY: "test-key",
        config_flow_stubs.CONF_NAME: "Test Location",
        config_flow_stubs.CONF_LOCATION: {
            config_flow_stubs.CONF_LATITUDE: "1.0",
            config_flow_stubs.CONF_LONGITUDE: "2.0",
        },
    }


@pytest.mark.parametrize(
    "data",
    [
        {"latitude": 1.0},
        {"longitude": 2.0},
    ],
)
def test_location_data_for_validation_ignores_partial_legacy_coordinates(
    config_flow_stubs: ConfigFlowStubs,
    data: dict[str, float],
) -> None:
    """Partial legacy coordinates should not be used for API-key validation."""

    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(data=data)

    assert config_flow_stubs.config_flow._location_data_for_validation(entry) == []


def _build_options_flow(
    config_flow_stubs: ConfigFlowStubs, data: dict | None = None
) -> object:
    """Build an options flow with simple form/create-entry callbacks."""

    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data=data or {config_flow_stubs.CONF_LANGUAGE_CODE: "en"}
    )
    flow = config_flow_stubs.config_flow.PollenLevelsOptionsFlow()
    flow.config_entry = entry
    flow.hass = SimpleNamespace(config=SimpleNamespace(language="en"))
    flow.async_show_form = lambda **kwargs: {  # type: ignore[method-assign]
        "type": "form",
        **kwargs,
    }
    flow.async_create_entry = lambda **kwargs: {  # type: ignore[method-assign]
        "type": "create_entry",
        **kwargs,
    }
    return flow


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("not-a-number", 6),
        (0, 1),
        (999, 24),
    ],
)
def test_setup_schema_update_interval_default_is_sanitized(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
    raw_value: object,
    expected: int,
) -> None:
    """Update interval defaults should be sanitized for form rendering."""

    captured_defaults: list[int | None] = []

    def _capture_optional(key, **kwargs):
        if key == config_flow_stubs.CONF_UPDATE_INTERVAL:
            captured_defaults.append(kwargs.get("default"))
        return key

    monkeypatch.setattr(
        config_flow_stubs.config_flow.vol, "Optional", _capture_optional
    )

    hass = SimpleNamespace(
        config=SimpleNamespace(latitude=1.0, longitude=2.0, language="en")
    )
    config_flow_stubs.config_flow._build_step_user_schema(
        hass, {config_flow_stubs.CONF_UPDATE_INTERVAL: raw_value}
    )

    assert captured_defaults == [expected]


def test_setup_schema_omits_removed_forecast_options(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """Initial setup no longer exposes forecast days or per-day sensors."""

    hass = SimpleNamespace(
        config=SimpleNamespace(latitude=1.0, longitude=2.0, language="en")
    )
    schema = config_flow_stubs.config_flow._build_step_user_schema(hass, {})
    keys = {str(getattr(key, "schema", key)) for key in schema.schema}

    assert config_flow_stubs.CONF_FORECAST_DAYS not in keys
    assert config_flow_stubs.CONF_CREATE_FORECAST_SENSORS not in keys


def test_step_user_schema_masks_api_key_field(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """Initial setup form should render API key as a password selector."""

    hass = SimpleNamespace(
        config=SimpleNamespace(latitude=1.0, longitude=2.0, language="en")
    )

    schema = config_flow_stubs.config_flow._build_step_user_schema(hass, {})
    api_selector = schema.schema[config_flow_stubs.CONF_API_KEY]

    assert isinstance(api_selector, config_flow_stubs.config_flow.TextSelector)
    assert (
        api_selector.config.type
        == config_flow_stubs.config_flow.TextSelectorType.PASSWORD
    )


def test_reauth_confirm_schema_masks_api_key_and_uses_blank_default(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reauth form should mask API key input and avoid prefilling secrets."""

    captured_default: dict[str, object] = {}
    orig_required = config_flow_stubs.config_flow.vol.Required

    def _capture_required(key, **kwargs):
        if key == config_flow_stubs.CONF_API_KEY:
            captured_default["api_key"] = kwargs.get("default")
        return orig_required(key, **kwargs)

    monkeypatch.setattr(
        config_flow_stubs.config_flow.vol, "Required", _capture_required
    )

    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={
            config_flow_stubs.CONF_API_KEY: "old-key",
            config_flow_stubs.CONF_LATITUDE: 1.0,
            config_flow_stubs.CONF_LONGITUDE: 2.0,
        },
        entry_id="entry-id",
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(config_entries=SimpleNamespace())
    flow.context = {"entry_id": "entry-id"}
    flow._get_reauth_entry = lambda: entry  # type: ignore[method-assign]

    captured: dict[str, object] = {}

    def _capture_show_form(*, step_id=None, data_schema=None, **kwargs):
        captured["step_id"] = step_id
        captured["schema"] = data_schema
        return {"step_id": step_id}

    flow.async_show_form = _capture_show_form  # type: ignore[method-assign]

    result = asyncio.run(flow.async_step_reauth_confirm())

    assert result == {"step_id": "reauth_confirm"}
    assert captured_default["api_key"] == ""
    schema = captured["schema"]
    assert hasattr(schema, "schema")
    api_selector = schema.schema[config_flow_stubs.CONF_API_KEY]
    assert isinstance(api_selector, config_flow_stubs.config_flow.TextSelector)
    assert (
        api_selector.config.type
        == config_flow_stubs.config_flow.TextSelectorType.PASSWORD
    )


def test_reconfigure_schema_masks_api_key_and_uses_blank_default(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconfigure form should mask API key input and avoid prefilling secrets."""

    captured_default: dict[str, object] = {}
    orig_required = config_flow_stubs.config_flow.vol.Required

    def _capture_required(key, **kwargs):
        if key == config_flow_stubs.CONF_API_KEY:
            captured_default["api_key"] = kwargs.get("default")
        return orig_required(key, **kwargs)

    monkeypatch.setattr(
        config_flow_stubs.config_flow.vol, "Required", _capture_required
    )

    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={
            config_flow_stubs.CONF_API_KEY: "old-key",
            config_flow_stubs.CONF_LATITUDE: 1.0,
            config_flow_stubs.CONF_LONGITUDE: 2.0,
        },
        entry_id="entry-id",
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(config_entries=SimpleNamespace())
    flow.context = {"entry_id": "entry-id"}
    flow._get_reconfigure_entry = lambda: entry  # type: ignore[method-assign]

    captured: dict[str, object] = {}

    def _capture_show_form(*, step_id=None, data_schema=None, **kwargs):
        captured["step_id"] = step_id
        captured["schema"] = data_schema
        return {"step_id": step_id}

    flow.async_show_form = _capture_show_form  # type: ignore[method-assign]

    result = asyncio.run(flow.async_step_reconfigure())

    assert result == {"step_id": "reconfigure"}
    assert captured_default["api_key"] == ""
    schema = captured["schema"]
    assert hasattr(schema, "schema")
    api_selector = schema.schema[config_flow_stubs.CONF_API_KEY]
    assert isinstance(api_selector, config_flow_stubs.config_flow.TextSelector)
    assert (
        api_selector.config.type
        == config_flow_stubs.config_flow.TextSelectorType.PASSWORD
    )


def test_validate_input_update_interval_below_min_sets_error(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sub-1 update intervals should surface a field error and skip I/O."""

    calls = _patch_client_fetch(config_flow_stubs, monkeypatch)

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    user_input = {
        **_base_user_input(config_flow_stubs),
        config_flow_stubs.CONF_UPDATE_INTERVAL: 0,
    }

    errors, normalized = asyncio.run(
        flow._async_validate_input(user_input, check_unique_id=False)
    )

    assert errors == {config_flow_stubs.CONF_UPDATE_INTERVAL: "invalid_update_interval"}
    assert normalized is None
    assert not calls


def test_validate_input_update_interval_float_string(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Float-like strings should coerce to int and allow validation to proceed."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        result=_valid_daily_info_payload(),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    user_input = {
        **_base_user_input(config_flow_stubs),
        config_flow_stubs.CONF_UPDATE_INTERVAL: "1.0",
    }

    errors, normalized = asyncio.run(
        flow._async_validate_input(user_input, check_unique_id=False)
    )

    assert errors == {}
    assert normalized is not None
    assert normalized[config_flow_stubs.CONF_UPDATE_INTERVAL] == 1
    assert calls


def test_validate_input_update_interval_non_numeric_sets_error(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-numeric update intervals should surface a field error and skip I/O."""

    calls = _patch_client_fetch(config_flow_stubs, monkeypatch)

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    user_input = {
        **_base_user_input(config_flow_stubs),
        config_flow_stubs.CONF_UPDATE_INTERVAL: "abc",
    }

    errors, normalized = asyncio.run(
        flow._async_validate_input(user_input, check_unique_id=False)
    )

    assert errors == {config_flow_stubs.CONF_UPDATE_INTERVAL: "invalid_update_interval"}
    assert normalized is None
    assert not calls


@pytest.mark.parametrize(
    ("exception_name", "message", "expected"),
    [
        (
            "ConfigEntryAuthFailed",
            "HTTP 401",
            {"base": "invalid_auth"},
        ),
        ("UpdateFailed", "HTTP 403", {"base": "cannot_connect"}),
    ],
)
def test_validate_input_http_auth_errors_map_correctly(
    monkeypatch: pytest.MonkeyPatch,
    config_flow_stubs: ConfigFlowStubs,
    exception_name: str,
    message: str,
    expected: dict,
) -> None:
    """HTTP auth failures during validation should map correctly."""

    error = getattr(config_flow_stubs, exception_name)(message)
    calls = _patch_client_fetch(config_flow_stubs, monkeypatch, error=error)

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs), check_unique_id=False
        )
    )

    assert calls
    assert errors == expected
    assert normalized is None


def test_validate_input_http_429_code_only_uses_quota_fallback(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Code-only quota messages should be replaced by a friendly fallback."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.config_flow.PollenQuotaExceededError("HTTP 429"),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "quota_exceeded"}
    assert normalized is None
    assert placeholders.get("error_message") == "Quota exceeded."


def test_validate_input_http_429_sets_quota_exceeded(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 429 during validation should map to quota_exceeded."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.config_flow.PollenQuotaExceededError(
            "HTTP 429 Too Many Requests"
        ),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs), check_unique_id=False
        )
    )

    assert calls
    assert errors == {"base": "quota_exceeded"}
    assert normalized is None


def test_validate_input_http_500_sets_cannot_connect(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected HTTP failures should map to cannot_connect."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.UpdateFailed("HTTP 500 Internal Server Error"),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs), check_unique_id=False
        )
    )

    assert calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None


def test_validate_input_http_code_only_uses_connect_fallback(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Code-only UpdateFailed messages should use a friendly connect fallback."""

    calls = _patch_client_fetch(
        config_flow_stubs, monkeypatch, error=config_flow_stubs.UpdateFailed("HTTP 500")
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None
    assert (
        placeholders.get("error_message") == "Failed to connect to the pollen service."
    )


def test_validate_input_http_500_sets_error_message_placeholder(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 500 should populate the cannot_connect error_message placeholder."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.UpdateFailed("HTTP 500 Internal Server Error"),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None
    assert placeholders.get("error_message")


def test_validate_input_update_failed_redacts_api_key_and_coordinates(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UpdateFailed placeholders should redact API keys and precise coordinates."""

    user_input = _base_user_input(config_flow_stubs)
    latitude = "48.8566123"
    longitude = "2.3522456"
    user_input[config_flow_stubs.CONF_LOCATION] = {
        config_flow_stubs.CONF_LATITUDE: latitude,
        config_flow_stubs.CONF_LONGITUDE: longitude,
    }
    api_key = user_input[config_flow_stubs.CONF_API_KEY]
    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.UpdateFailed(
            f"API key {api_key} failed for "
            f"location.latitude={latitude} location.longitude={longitude}"
        ),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            user_input,
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    error_message = placeholders.get("error_message", "")
    assert calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None
    assert api_key not in error_message
    assert latitude not in error_message
    assert longitude not in error_message
    assert "***" in error_message


def test_validate_input_clears_error_message_placeholder_on_validation_error(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Field-level validation errors should clear stale error_message placeholders."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.UpdateFailed("HTTP 500 Internal Server Error"),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None
    assert placeholders.get("error_message")

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                **_base_user_input(config_flow_stubs),
                config_flow_stubs.CONF_LANGUAGE_CODE: "bad code",
            },
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert errors == {config_flow_stubs.CONF_LANGUAGE_CODE: "invalid_language_format"}
    assert normalized is None
    assert "error_message" not in placeholders


def test_validate_input_connection_error_sets_error_message_placeholder(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connection errors should keep a safe error_message placeholder."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.UpdateFailed("HTTP 500 Internal Server Error"),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None
    assert placeholders.get("error_message")

    assert "error_message" in placeholders


def test_validate_input_ignores_removed_forecast_options_and_uses_fixed_days(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removed forecast options are not saved and validation calls days=5."""

    calls = _patch_client_fetch(
        config_flow_stubs, monkeypatch, result=_valid_daily_info_payload()
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                **_base_user_input(config_flow_stubs),
                config_flow_stubs.CONF_FORECAST_DAYS: "bad",
                config_flow_stubs.CONF_CREATE_FORECAST_SENSORS: "D+1+2",
            },
            check_unique_id=False,
        )
    )

    assert calls
    assert errors == {}
    assert normalized is not None
    assert calls[0]["days"] == config_flow_stubs.FORECAST_DAYS
    assert config_flow_stubs.CONF_FORECAST_DAYS not in normalized
    assert config_flow_stubs.CONF_CREATE_FORECAST_SENSORS not in normalized


def test_validate_input_auth_error_sets_error_message_placeholder(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auth failures should populate the invalid_auth error_message placeholder."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.ConfigEntryAuthFailed(
            "HTTP 401: Forbidden for this project"
        ),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "invalid_auth"}
    assert normalized is None
    assert "Forbidden" in placeholders.get("error_message", "")


def test_validate_input_auth_error_empty_message_uses_fallback_placeholder(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auth failures with empty text should use the default placeholder message."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.ConfigEntryAuthFailed(""),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "invalid_auth"}
    assert normalized is None
    assert placeholders.get("error_message") == "Authentication failed."


def test_validate_input_quota_error_maps_to_quota_exceeded(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dedicated quota errors should map to quota_exceeded."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.config_flow.PollenQuotaExceededError(
            "HTTP 429: API key not valid. Please pass a valid API key."
        ),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "quota_exceeded"}
    assert normalized is None
    assert "api key not valid" in placeholders.get("error_message", "").lower()


def test_validate_input_update_failed_empty_message_uses_connect_fallback(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UpdateFailed with empty text should use cannot_connect fallback message."""

    calls = _patch_client_fetch(
        config_flow_stubs, monkeypatch, error=config_flow_stubs.UpdateFailed("")
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None
    assert (
        placeholders.get("error_message") == "Failed to connect to the pollen service."
    )


def test_validate_input_http_429_whitespace_redacted_uses_quota_fallback(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whitespace-only redacted quota messages should still use fallback text."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.config_flow.PollenQuotaExceededError("HTTP 429"),
    )
    monkeypatch.setattr(
        config_flow_stubs.config_flow,
        "_redact_validation_error",
        lambda *_args, **_kwargs: "   ",
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "quota_exceeded"}
    assert normalized is None
    assert placeholders.get("error_message") == "Quota exceeded."


def test_validate_input_update_failed_whitespace_redacted_uses_connect_fallback(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whitespace-only redacted UpdateFailed messages should use connect fallback."""

    calls = _patch_client_fetch(
        config_flow_stubs, monkeypatch, error=config_flow_stubs.UpdateFailed("HTTP 500")
    )
    monkeypatch.setattr(
        config_flow_stubs.config_flow,
        "_redact_validation_error",
        lambda *_args, **_kwargs: "   ",
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None
    assert (
        placeholders.get("error_message") == "Failed to connect to the pollen service."
    )


def test_validate_input_http_429_empty_redacted_uses_quota_fallback(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quota-exceeded errors should use fallback text when redaction is empty."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.config_flow.PollenQuotaExceededError("HTTP 429"),
    )
    monkeypatch.setattr(
        config_flow_stubs.config_flow,
        "_redact_validation_error",
        lambda *_args, **_kwargs: "",
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "quota_exceeded"}
    assert normalized is None
    assert placeholders.get("error_message") == "Quota exceeded."


def test_validate_input_timeout_sets_fallback_error_message(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TimeoutError without a message should still provide a user-friendly fallback."""

    calls = _patch_client_fetch(config_flow_stubs, monkeypatch, error=TimeoutError())

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None
    assert placeholders.get("error_message") == "Validation request timed out."


def test_validate_input_client_error_sets_fallback_error_message(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ClientError without details should still provide a network fallback message."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.config_flow.aiohttp.ClientError(),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None
    assert placeholders.get("error_message") == (
        "Network error while connecting to the pollen service."
    )


def test_validate_input_redacts_api_key_in_error_message(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Error placeholders should redact API keys returned by the service."""

    calls = _patch_client_fetch(
        config_flow_stubs,
        monkeypatch,
        error=config_flow_stubs.ConfigEntryAuthFailed(
            "HTTP 401: API key test-key not valid"
        ),
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    user_input = _base_user_input(config_flow_stubs)
    user_input[config_flow_stubs.CONF_API_KEY] = "test-key"

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            user_input,
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert calls
    assert errors == {"base": "invalid_auth"}
    assert normalized is None
    error_message = placeholders.get("error_message", "")
    assert "test-key" not in error_message
    assert "***" in error_message


def test_validate_input_http_200_non_list_dailyinfo_sets_cannot_connect(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-list dailyInfo in HTTP 200 should be treated as invalid."""

    calls = _patch_client_fetch(
        config_flow_stubs, monkeypatch, result={"dailyInfo": "invalid"}
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs), check_unique_id=False
        )
    )

    assert calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None


def test_validate_input_http_200_dailyinfo_with_non_dict_sets_cannot_connect(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dailyInfo list with non-dict items should be treated as invalid."""

    calls = _patch_client_fetch(
        config_flow_stubs, monkeypatch, result={"dailyInfo": ["invalid-item"]}
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(config_flow_stubs), check_unique_id=False
        )
    )

    assert calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None


def test_validate_input_unexpected_exception_sets_unknown(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unexpected exceptions should map to unknown without logging raw details."""

    def _raise_session(hass):
        raise RuntimeError(
            "boom test-key at location.latitude=48.8566123 "
            "location.longitude=2.3522456"
        )

    monkeypatch.setattr(
        config_flow_stubs.config_flow, "async_get_clientsession", _raise_session
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    user_input = _base_user_input(config_flow_stubs)
    user_input[config_flow_stubs.CONF_LOCATION] = {
        config_flow_stubs.CONF_LATITUDE: "48.8566123",
        config_flow_stubs.CONF_LONGITUDE: "2.3522456",
    }

    with caplog.at_level("ERROR", logger=config_flow_stubs.config_flow.__name__):
        errors, normalized = asyncio.run(
            flow._async_validate_input(user_input, check_unique_id=False)
        )

    assert errors == {"base": "unknown"}
    assert normalized is None
    assert "Traceback" not in caplog.text
    assert "test-key" not in caplog.text
    assert "48.8566123" not in caplog.text
    assert "2.3522456" not in caplog.text
    assert "***" in caplog.text


def test_validate_input_happy_path_sets_unique_id_and_normalizes(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful validation should normalize data and set unique ID."""

    calls = _patch_client_fetch(
        config_flow_stubs, monkeypatch, result=_valid_daily_info_payload()
    )

    class _TrackingFlow(config_flow_stubs.PollenLevelsConfigFlow):
        def __init__(self) -> None:
            super().__init__()
            self.unique_ids: list[str] = []
            self.abort_calls = 0

        async def async_set_unique_id(self, uid: str, raise_on_progress: bool = False):
            self.unique_ids.append(uid)
            return None

        def _abort_if_unique_id_configured(self):
            self.abort_calls += 1
            return None

    flow = _TrackingFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(),
    )

    user_input = {
        **_base_user_input(config_flow_stubs),
        config_flow_stubs.CONF_LANGUAGE_CODE: " es ",
    }

    errors, normalized = asyncio.run(
        flow._async_validate_input(user_input, check_unique_id=True)
    )

    assert calls
    assert errors == {}
    assert normalized is not None
    assert normalized[config_flow_stubs.CONF_LATITUDE] == pytest.approx(1.0)
    assert normalized[config_flow_stubs.CONF_LONGITUDE] == pytest.approx(2.0)
    assert normalized[config_flow_stubs.CONF_LANGUAGE_CODE] == "es"
    assert flow.unique_ids == ["1.0000_2.0000"]
    assert flow.abort_calls == 1


def test_validate_input_unique_id_collapses_nearby_locations_legacy_compat(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unique-id format should match legacy 4-decimal duplicate detection."""

    calls = _patch_client_fetch(
        config_flow_stubs, monkeypatch, result=_valid_daily_info_payload()
    )

    class _TrackingFlow(config_flow_stubs.PollenLevelsConfigFlow):
        def __init__(self) -> None:
            super().__init__()
            self.unique_ids: list[str] = []

        async def async_set_unique_id(self, uid: str, raise_on_progress: bool = False):
            self.unique_ids.append(uid)
            return None

        def _abort_if_unique_id_configured(self):
            return None

    flow = _TrackingFlow()
    flow.hass = SimpleNamespace(config=SimpleNamespace())

    first = {
        **_base_user_input(config_flow_stubs),
        config_flow_stubs.CONF_LOCATION: {
            config_flow_stubs.CONF_LATITUDE: "1.0000044",
            config_flow_stubs.CONF_LONGITUDE: "2.0000044",
        },
    }
    second = {
        **_base_user_input(config_flow_stubs),
        config_flow_stubs.CONF_LOCATION: {
            config_flow_stubs.CONF_LATITUDE: "1.0000046",
            config_flow_stubs.CONF_LONGITUDE: "2.0000046",
        },
    }

    first_errors, first_normalized = asyncio.run(
        flow._async_validate_input(first, check_unique_id=True)
    )
    second_errors, second_normalized = asyncio.run(
        flow._async_validate_input(second, check_unique_id=True)
    )

    assert calls
    assert first_errors == {}
    assert second_errors == {}
    assert first_normalized is not None
    assert second_normalized is not None
    assert len(flow.unique_ids) == 2
    assert flow.unique_ids[0] == flow.unique_ids[1] == "1.0000_2.0000"


@pytest.mark.parametrize(
    ("step_method_name", "entry_getter"),
    [
        ("async_step_reauth_confirm", "_get_reauth_entry"),
        ("async_step_reconfigure", "_get_reconfigure_entry"),
    ],
)
def test_api_key_confirm_description_placeholders_round_coordinates(
    config_flow_stubs: ConfigFlowStubs, step_method_name: str, entry_getter: str
) -> None:
    """Reauth/reconfigure placeholders should round visible coordinates."""

    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={
            config_flow_stubs.CONF_API_KEY: "old-key",
            config_flow_stubs.CONF_LATITUDE: 39.123456,
            config_flow_stubs.CONF_LONGITUDE: -0.123456,
            config_flow_stubs.CONF_LANGUAGE_CODE: "en",
        },
        entry_id="entry-id",
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_update_entry=lambda *args, **kwargs: None,
            async_reload=lambda *args, **kwargs: None,
        )
    )
    flow.context = {"entry_id": "entry-id"}
    setattr(flow, entry_getter, lambda: entry)

    captured: dict[str, object] = {}
    normalized = {**entry.data, config_flow_stubs.CONF_API_KEY: "new-key"}

    async def fake_validate(
        user_input, *, check_unique_id, description_placeholders=None
    ):
        captured["description_placeholders"] = description_placeholders
        captured["user_input"] = dict(user_input)
        return {}, normalized

    flow._async_validate_input = fake_validate  # type: ignore[assignment]

    step_method = getattr(flow, step_method_name)
    asyncio.run(step_method({config_flow_stubs.CONF_API_KEY: "new-key"}))

    placeholders = captured["description_placeholders"]
    assert placeholders is not None
    assert placeholders["latitude"] == "39.12"
    assert placeholders["longitude"] == "-0.12"

    combined_input = captured["user_input"]
    assert combined_input[config_flow_stubs.CONF_LATITUDE] == 39.123456
    assert combined_input[config_flow_stubs.CONF_LONGITUDE] == -0.123456


def test_reconfigure_api_key_validation_accepts_later_working_location(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """Parent API-key validation should try another location after a location failure."""

    first = config_flow_stubs.config_flow.config_entries.ConfigSubentry(
        data={
            config_flow_stubs.CONF_LATITUDE: 1.0,
            config_flow_stubs.CONF_LONGITUDE: 2.0,
        },
        subentry_id="subentry-1",
        title="First",
        unique_id="1.0000_2.0000",
    )
    second = config_flow_stubs.config_flow.config_entries.ConfigSubentry(
        data={
            config_flow_stubs.CONF_LATITUDE: 3.0,
            config_flow_stubs.CONF_LONGITUDE: 4.0,
        },
        subentry_id="subentry-2",
        title="Second",
        unique_id="3.0000_4.0000",
    )
    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={config_flow_stubs.CONF_API_KEY: "old-key"},
        options={config_flow_stubs.CONF_LANGUAGE_CODE: "en"},
        entry_id="entry-id",
        subentries={
            first.subentry_id: first,
            second.subentry_id: second,
        },
    )

    class _Recorder:
        def __init__(self) -> None:
            self.updated = None
            self.reloaded = None

        def async_get_entry(self, entry_id: str):
            return entry if entry_id == entry.entry_id else None

        def async_update_entry(self, entry_to_update, *, data):
            self.updated = (entry_to_update, data)

        def async_reload(self, entry_id: str):
            self.reloaded = entry_id

    recorder = _Recorder()
    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(config_entries=recorder)
    flow.context = {"entry_id": "entry-id"}
    attempts: list[tuple[float, float]] = []

    async def fake_validate(
        user_input, *, check_unique_id, description_placeholders=None
    ):
        attempts.append(
            (
                user_input[config_flow_stubs.CONF_LATITUDE],
                user_input[config_flow_stubs.CONF_LONGITUDE],
            )
        )
        if user_input[config_flow_stubs.CONF_LATITUDE] == 1.0:
            return {"base": "cannot_connect"}, None
        return {}, {**user_input, config_flow_stubs.CONF_API_KEY: "new-key"}

    flow._async_validate_input = fake_validate  # type: ignore[assignment]

    result = asyncio.run(
        flow.async_step_reconfigure({config_flow_stubs.CONF_API_KEY: "new-key"})
    )

    assert result == {"type": "abort", "reason": "reconfigure_successful"}
    assert attempts == [(1.0, 2.0), (3.0, 4.0)]
    assert recorder.updated == (
        entry,
        {config_flow_stubs.CONF_API_KEY: "new-key"},
    )
    assert recorder.reloaded == "entry-id"


def test_reconfigure_api_key_validation_stops_on_invalid_auth(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """Credential failures should not be retried against every location."""

    first = config_flow_stubs.config_flow.config_entries.ConfigSubentry(
        data={
            config_flow_stubs.CONF_LATITUDE: 1.0,
            config_flow_stubs.CONF_LONGITUDE: 2.0,
        },
        subentry_id="subentry-1",
        title="First",
        unique_id="1.0000_2.0000",
    )
    second = config_flow_stubs.config_flow.config_entries.ConfigSubentry(
        data={
            config_flow_stubs.CONF_LATITUDE: 3.0,
            config_flow_stubs.CONF_LONGITUDE: 4.0,
        },
        subentry_id="subentry-2",
        title="Second",
        unique_id="3.0000_4.0000",
    )
    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={config_flow_stubs.CONF_API_KEY: "old-key"},
        entry_id="entry-id",
        subentries={
            first.subentry_id: first,
            second.subentry_id: second,
        },
    )

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_get_entry=lambda entry_id: (
                entry if entry_id == entry.entry_id else None
            ),
            async_update_entry=lambda *args, **kwargs: None,
            async_reload=lambda *args, **kwargs: None,
        )
    )
    flow.context = {"entry_id": "entry-id"}
    flow.async_show_form = (  # type: ignore[method-assign]
        lambda *args, **kwargs: {
            "step_id": kwargs.get("step_id") or (args[0] if args else None),
            "errors": kwargs.get("errors") or {},
        }
    )
    attempts = 0

    async def fake_validate(
        user_input, *, check_unique_id, description_placeholders=None
    ):
        nonlocal attempts
        attempts += 1
        return {"base": "invalid_auth"}, None

    flow._async_validate_input = fake_validate  # type: ignore[assignment]

    result = asyncio.run(
        flow.async_step_reconfigure({config_flow_stubs.CONF_API_KEY: "bad-key"})
    )

    assert result == {"step_id": "reconfigure", "errors": {"base": "invalid_auth"}}
    assert attempts == 1


def test_reauth_confirm_does_not_reintroduce_option_fields_in_data(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """Reauth should only update API key in data, preserving option boundaries."""

    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={
            config_flow_stubs.CONF_API_KEY: "old-key",
            config_flow_stubs.CONF_LATITUDE: 1.0,
            config_flow_stubs.CONF_LONGITUDE: 2.0,
            config_flow_stubs.CONF_LANGUAGE_CODE: "en",
            config_flow_stubs.CONF_UPDATE_INTERVAL: 6,
            # Intentionally no CONF_FORECAST_DAYS in data.
        },
        options={
            config_flow_stubs.CONF_FORECAST_DAYS: 5,
            config_flow_stubs.CONF_CREATE_FORECAST_SENSORS: "D+1",
        },
        entry_id="entry-id",
    )

    class _Recorder:
        def __init__(self) -> None:
            self.updated = None

        def async_get_entry(self, entry_id: str):
            return entry if entry_id == entry.entry_id else None

        def async_update_entry(self, entry_to_update, *, data):
            self.updated = (entry_to_update, data)

        def async_reload(self, entry_id: str):
            return None

    recorder = _Recorder()

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(config_entries=recorder)
    flow.context = {"entry_id": "entry-id"}

    # Validation may normalize and include option-backed fields.
    normalized = {
        **entry.data,
        config_flow_stubs.CONF_API_KEY: "new-key",
        config_flow_stubs.CONF_FORECAST_DAYS: 2,
        config_flow_stubs.CONF_CREATE_FORECAST_SENSORS: "none",
    }

    async def fake_validate(
        user_input, *, check_unique_id, description_placeholders=None
    ):
        return {}, normalized

    flow._async_validate_input = fake_validate  # type: ignore[assignment]

    async def run_flow():
        await flow.async_step_reauth(entry.data)
        return await flow.async_step_reauth_confirm(
            {config_flow_stubs.CONF_API_KEY: "new-key"}
        )

    result = asyncio.run(run_flow())

    assert result == {"type": "abort", "reason": "reauth_successful"}
    assert recorder.updated is not None
    updated_entry, updated_data = recorder.updated
    assert updated_entry is entry
    assert updated_data[config_flow_stubs.CONF_API_KEY] == "new-key"
    assert config_flow_stubs.CONF_FORECAST_DAYS not in updated_data
    assert config_flow_stubs.CONF_CREATE_FORECAST_SENSORS not in updated_data


def test_reconfigure_does_not_reintroduce_option_fields_in_data(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """Reconfigure should only update API key in data, preserving option boundaries."""

    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={
            config_flow_stubs.CONF_API_KEY: "old-key",
            config_flow_stubs.CONF_LATITUDE: 1.0,
            config_flow_stubs.CONF_LONGITUDE: 2.0,
            config_flow_stubs.CONF_LANGUAGE_CODE: "en",
            config_flow_stubs.CONF_UPDATE_INTERVAL: 6,
            # Intentionally no CONF_CREATE_FORECAST_SENSORS in data.
        },
        options={config_flow_stubs.CONF_CREATE_FORECAST_SENSORS: "D+1"},
        entry_id="entry-id",
    )

    class _Recorder:
        def __init__(self) -> None:
            self.updated = None

        def async_get_entry(self, entry_id: str):
            return entry if entry_id == entry.entry_id else None

        def async_update_entry(self, entry_to_update, *, data):
            self.updated = (entry_to_update, data)

        def async_reload(self, entry_id: str):
            return None

    recorder = _Recorder()

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(config_entries=recorder)
    flow.context = {"entry_id": "entry-id"}
    created: dict[str, bool] = {"called": False}

    def _capture_create_entry(*args, **kwargs):
        created["called"] = True
        return {"type": "create_entry"}

    flow.async_create_entry = _capture_create_entry  # type: ignore[method-assign]

    # Validation may normalize and include option-backed fields.
    normalized = {
        **entry.data,
        config_flow_stubs.CONF_API_KEY: "new-key",
        config_flow_stubs.CONF_CREATE_FORECAST_SENSORS: "none",
    }

    async def fake_validate(
        user_input, *, check_unique_id, description_placeholders=None
    ):
        return {}, normalized

    flow._async_validate_input = fake_validate  # type: ignore[assignment]

    async def run_flow():
        first = await flow.async_step_reconfigure()
        assert first == {"step_id": "reconfigure"}
        return await flow.async_step_reconfigure(
            {config_flow_stubs.CONF_API_KEY: "new-key"}
        )

    result = asyncio.run(run_flow())

    assert result == {"type": "abort", "reason": "reconfigure_successful"}
    assert recorder.updated is not None
    updated_entry, updated_data = recorder.updated
    assert updated_entry is entry
    assert updated_data[config_flow_stubs.CONF_API_KEY] == "new-key"
    assert config_flow_stubs.CONF_CREATE_FORECAST_SENSORS not in updated_data
    assert created["called"] is False


def test_async_step_user_defaults_entry_name(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """Blank entry names should fall back to the default integration title."""

    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(latitude=1.0, longitude=2.0, language="en")
    )

    normalized = {
        config_flow_stubs.CONF_API_KEY: "test-key",
        config_flow_stubs.CONF_LATITUDE: 1.0,
        config_flow_stubs.CONF_LONGITUDE: 2.0,
        config_flow_stubs.CONF_LANGUAGE_CODE: "en",
    }

    async def fake_validate(
        user_input, *, check_unique_id, description_placeholders=None
    ):
        assert user_input[config_flow_stubs.CONF_NAME] == "   "
        return {}, normalized

    flow._async_validate_input = fake_validate  # type: ignore[assignment]

    user_input = {
        config_flow_stubs.CONF_API_KEY: "test-key",
        config_flow_stubs.CONF_NAME: "   ",
        config_flow_stubs.CONF_LOCATION: {
            config_flow_stubs.CONF_LATITUDE: 1.0,
            config_flow_stubs.CONF_LONGITUDE: 2.0,
        },
        config_flow_stubs.CONF_UPDATE_INTERVAL: 6,
        config_flow_stubs.CONF_LANGUAGE_CODE: "en",
    }

    result = asyncio.run(flow.async_step_user(user_input))

    assert result["title"] == config_flow_stubs.DEFAULT_ENTRY_TITLE
    assert result["data"] == {config_flow_stubs.CONF_API_KEY: "test-key"}
    assert result["subentries"][0]["title"] == config_flow_stubs.DEFAULT_ENTRY_TITLE
    assert result["subentries"][0]["data"] == {
        config_flow_stubs.CONF_LATITUDE: 1.0,
        config_flow_stubs.CONF_LONGITUDE: 2.0,
    }


def test_async_step_user_checks_api_key_unique_id_with_async_entries_fallback(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """New setup should detect duplicate API-key parents via async_entries fallback."""

    class _TrackingFlow(config_flow_stubs.PollenLevelsConfigFlow):
        def __init__(self) -> None:
            super().__init__()
            self.unique_ids: list[str] = []

        async def async_set_unique_id(self, uid: str, raise_on_progress: bool = False):
            self.unique_ids.append(uid)
            return None

    duplicate_unique_id = config_flow_stubs.config_flow._api_key_unique_id("shared-key")
    flow = _TrackingFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(latitude=1.0, longitude=2.0, language="en"),
        config_entries=SimpleNamespace(
            async_entries=lambda _domain: [
                SimpleNamespace(unique_id=duplicate_unique_id)
            ]
        ),
    )

    normalized = {
        config_flow_stubs.CONF_API_KEY: "shared-key",
        config_flow_stubs.CONF_LATITUDE: 1.0,
        config_flow_stubs.CONF_LONGITUDE: 2.0,
        config_flow_stubs.CONF_LANGUAGE_CODE: "en",
    }

    async def fake_validate(
        user_input, *, check_unique_id, description_placeholders=None
    ):
        assert check_unique_id is False
        return {}, normalized

    flow._async_validate_input = fake_validate  # type: ignore[assignment]

    result = asyncio.run(
        flow.async_step_user(
            {
                config_flow_stubs.CONF_API_KEY: "shared-key",
            }
        )
    )

    assert result == {"type": "abort", "reason": "api_key_already_configured"}
    assert flow.unique_ids == [duplicate_unique_id]


class _SubentryRecorder:
    def __init__(self, entry) -> None:
        self.entry = entry
        self.reload_calls: list[str] = []
        self.created_tasks = []

    def async_get_entry(self, entry_id: str):
        return self.entry if entry_id == self.entry.entry_id else None

    def async_schedule_reload(self, entry_id: str) -> None:
        self.reload_calls.append(entry_id)


class _ReloadOnlySubentryRecorder:
    def __init__(self) -> None:
        self.reload_calls: list[str] = []

    async def async_reload(self, entry_id: str) -> None:
        self.reload_calls.append(entry_id)


def _build_location_subentry_flow(config_flow_stubs: ConfigFlowStubs, entry):
    recorder = _SubentryRecorder(entry)

    def _async_create_task(coro, *, name=None):
        task = asyncio.create_task(coro, name=name)
        recorder.created_tasks.append(task)
        return task

    flow = config_flow_stubs.config_flow.PollenLevelsLocationSubentryFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(
            latitude=1.0,
            longitude=2.0,
            location_name="Home",
        ),
        config_entries=recorder,
        async_create_task=_async_create_task,
    )
    flow.handler = (
        entry.entry_id,
        config_flow_stubs.config_flow.SUBENTRY_TYPE_LOCATION,
    )
    flow.context = {}
    return flow, recorder


def test_location_subentry_user_step_shows_form(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """The add-location subentry flow should render its form initially."""

    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={config_flow_stubs.CONF_API_KEY: "key"},
        entry_id="entry-id",
    )
    flow, _recorder = _build_location_subentry_flow(config_flow_stubs, entry)

    result = asyncio.run(flow.async_step_user())

    assert result == {"type": "form", "step_id": "user", "errors": {}}


def test_location_subentry_create_reload_helper_falls_back_to_async_reload(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """Subentry reload helper should use async_reload when schedule_reload is absent."""

    recorder = _ReloadOnlySubentryRecorder()
    hass = SimpleNamespace(config_entries=recorder)

    asyncio.run(
        config_flow_stubs.config_flow._async_reload_parent_after_subentry_create(
            hass, "entry-id"
        )
    )

    assert recorder.reload_calls == ["entry-id"]


def test_location_subentry_user_step_rejects_invalid_api_payload(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding a location should reject invalid dailyInfo before persistence."""

    calls = _patch_client_fetch(
        config_flow_stubs, monkeypatch, result={"dailyInfo": []}
    )
    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={config_flow_stubs.CONF_API_KEY: "key"},
        entry_id="entry-id",
    )
    flow, recorder = _build_location_subentry_flow(config_flow_stubs, entry)

    result = asyncio.run(
        flow.async_step_user(
            {
                config_flow_stubs.CONF_NAME: "Garden",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: 12.34567,
                    config_flow_stubs.CONF_LONGITUDE: -98.76543,
                },
            }
        )
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}
    assert result["description_placeholders"]["error_message"] == (
        "API response missing expected pollen forecast information."
    )
    assert calls
    assert recorder.created_tasks == []
    assert recorder.reload_calls == []


def test_location_subentry_user_step_rejects_timeout_before_create(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding a location should map validation timeouts to cannot_connect."""

    calls = _patch_client_fetch(
        config_flow_stubs, monkeypatch, error=TimeoutError("timed out")
    )
    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={config_flow_stubs.CONF_API_KEY: "key"},
        entry_id="entry-id",
    )
    flow, recorder = _build_location_subentry_flow(config_flow_stubs, entry)

    result = asyncio.run(
        flow.async_step_user(
            {
                config_flow_stubs.CONF_NAME: "Garden",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: 12.34567,
                    config_flow_stubs.CONF_LONGITUDE: -98.76543,
                },
            }
        )
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}
    assert result["description_placeholders"]["error_message"] == "timed out"
    assert calls
    assert recorder.created_tasks == []
    assert recorder.reload_calls == []


def test_location_subentry_user_step_rejects_invalid_coordinates(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """Invalid location input should stay on the form without reloading."""

    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={config_flow_stubs.CONF_API_KEY: "key"},
        entry_id="entry-id",
    )
    flow, recorder = _build_location_subentry_flow(config_flow_stubs, entry)

    result = asyncio.run(
        flow.async_step_user(
            {
                config_flow_stubs.CONF_NAME: "Garden",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: "north",
                    config_flow_stubs.CONF_LONGITUDE: -98.76543,
                },
            }
        )
    )

    assert result == {
        "type": "form",
        "step_id": "user",
        "errors": {config_flow_stubs.CONF_LOCATION: "invalid_coordinates"},
    }
    assert recorder.created_tasks == []
    assert recorder.reload_calls == []


def test_location_subentry_reconfigure_preserves_legacy_entry_id(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconfiguring a migrated location should preserve legacy identity data."""

    _patch_client_fetch(config_flow_stubs, monkeypatch)
    subentry = config_flow_stubs.config_flow.config_entries.ConfigSubentry(
        data={
            config_flow_stubs.CONF_LATITUDE: 1.0,
            config_flow_stubs.CONF_LONGITUDE: 2.0,
            config_flow_stubs.config_flow.CONF_LEGACY_ENTRY_ID: "legacy-entry",
        },
        subentry_id="subentry-1",
        title="Home",
        unique_id="1.0000_2.0000",
    )
    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={config_flow_stubs.CONF_API_KEY: "key"},
        entry_id="entry-id",
        subentries={subentry.subentry_id: subentry},
    )
    flow, _recorder = _build_location_subentry_flow(config_flow_stubs, entry)
    flow.context = {"subentry_id": subentry.subentry_id}

    asyncio.run(
        flow.async_step_reconfigure(
            {
                config_flow_stubs.CONF_NAME: "Home",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: 5.0,
                    config_flow_stubs.CONF_LONGITUDE: 6.0,
                },
            }
        )
    )

    assert subentry.data[config_flow_stubs.config_flow.CONF_LEGACY_ENTRY_ID] == (
        "legacy-entry"
    )


def test_location_subentry_reconfigure_rejects_invalid_api_payload_without_update(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconfigure should not update the subentry when validation fails."""

    calls = _patch_client_fetch(
        config_flow_stubs, monkeypatch, result={"dailyInfo": [{"day": "D0"}, "bad"]}
    )
    subentry = config_flow_stubs.config_flow.config_entries.ConfigSubentry(
        data={
            config_flow_stubs.CONF_LATITUDE: 1.0,
            config_flow_stubs.CONF_LONGITUDE: 2.0,
        },
        subentry_id="subentry-1",
        title="Home",
        unique_id="1.0000_2.0000",
    )
    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={config_flow_stubs.CONF_API_KEY: "key"},
        entry_id="entry-id",
        subentries={subentry.subentry_id: subentry},
    )
    flow, recorder = _build_location_subentry_flow(config_flow_stubs, entry)
    flow.context = {"subentry_id": subentry.subentry_id}

    result = asyncio.run(
        flow.async_step_reconfigure(
            {
                config_flow_stubs.CONF_NAME: "Garden",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: 3.0,
                    config_flow_stubs.CONF_LONGITUDE: 4.0,
                },
            }
        )
    )

    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "cannot_connect"}
    assert subentry.title == "Home"
    assert subentry.data == {
        config_flow_stubs.CONF_LATITUDE: 1.0,
        config_flow_stubs.CONF_LONGITUDE: 2.0,
    }
    assert subentry.unique_id == "1.0000_2.0000"
    assert recorder.reload_calls == []
    assert calls


def test_location_subentry_reconfigure_rejects_other_duplicate(
    config_flow_stubs: ConfigFlowStubs,
) -> None:
    """Reconfigure duplicate detection should ignore current subentry only."""

    current = config_flow_stubs.config_flow.config_entries.ConfigSubentry(
        data={
            config_flow_stubs.CONF_LATITUDE: 1.0,
            config_flow_stubs.CONF_LONGITUDE: 2.0,
        },
        subentry_id="subentry-1",
        title="Home",
        unique_id="1.0000_2.0000",
    )
    other = config_flow_stubs.config_flow.config_entries.ConfigSubentry(
        data={
            config_flow_stubs.CONF_LATITUDE: 3.0,
            config_flow_stubs.CONF_LONGITUDE: 4.0,
        },
        subentry_id="subentry-2",
        title="Office",
        unique_id="3.0000_4.0000",
    )
    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={config_flow_stubs.CONF_API_KEY: "key"},
        entry_id="entry-id",
        subentries={
            current.subentry_id: current,
            other.subentry_id: other,
        },
    )
    flow, recorder = _build_location_subentry_flow(config_flow_stubs, entry)
    flow.context = {"subentry_id": current.subentry_id}

    result = asyncio.run(
        flow.async_step_reconfigure(
            {
                config_flow_stubs.CONF_NAME: "Duplicate",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: 3.0,
                    config_flow_stubs.CONF_LONGITUDE: 4.0,
                },
            }
        )
    )

    assert result == {
        "type": "form",
        "step_id": "reconfigure",
        "errors": {"base": "already_configured"},
    }
    assert recorder.reload_calls == []


def test_location_subentry_reconfigure_allows_current_location(
    config_flow_stubs: ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keeping the same coordinates should not count as a duplicate."""

    _patch_client_fetch(config_flow_stubs, monkeypatch)
    current = config_flow_stubs.config_flow.config_entries.ConfigSubentry(
        data={
            config_flow_stubs.CONF_LATITUDE: 1.0,
            config_flow_stubs.CONF_LONGITUDE: 2.0,
        },
        subentry_id="subentry-1",
        title="Home",
        unique_id="1.0000_2.0000",
    )
    entry = config_flow_stubs.config_flow.config_entries.ConfigEntry(
        data={config_flow_stubs.CONF_API_KEY: "key"},
        entry_id="entry-id",
        subentries={current.subentry_id: current},
    )
    flow, recorder = _build_location_subentry_flow(config_flow_stubs, entry)
    flow.context = {"subentry_id": current.subentry_id}

    result = asyncio.run(
        flow.async_step_reconfigure(
            {
                config_flow_stubs.CONF_NAME: "Home Updated",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: 1.0,
                    config_flow_stubs.CONF_LONGITUDE: 2.0,
                },
            }
        )
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert current.title == "Home Updated"
    assert recorder.reload_calls == ["entry-id"]


@pytest.mark.parametrize("raw", ["inf", "-inf", "nan"])
def test_parse_int_option_non_finite_returns_error(
    config_flow_stubs: ConfigFlowStubs, raw: str
) -> None:
    """Non-finite numeric values should be rejected safely."""

    parsed, err = config_flow_stubs.config_flow._parse_int_option(
        raw,
        default=config_flow_stubs.config_flow.DEFAULT_UPDATE_INTERVAL,
        min_value=config_flow_stubs.config_flow.MIN_UPDATE_INTERVAL_HOURS,
        max_value=config_flow_stubs.config_flow.MAX_UPDATE_INTERVAL_HOURS,
        error_key="invalid_update_interval",
    )

    assert parsed == config_flow_stubs.config_flow.DEFAULT_UPDATE_INTERVAL
    assert err == "invalid_update_interval"


@pytest.mark.parametrize("raw", ["2.9", 2.1])
def test_parse_int_option_decimal_returns_error(
    config_flow_stubs: ConfigFlowStubs, raw: object
) -> None:
    """Decimal values should be rejected for integer-only options."""

    parsed, err = config_flow_stubs.config_flow._parse_int_option(
        raw,
        default=config_flow_stubs.config_flow.DEFAULT_UPDATE_INTERVAL,
        min_value=config_flow_stubs.config_flow.MIN_UPDATE_INTERVAL_HOURS,
        max_value=config_flow_stubs.config_flow.MAX_UPDATE_INTERVAL_HOURS,
        error_key="invalid_update_interval",
    )

    assert parsed == config_flow_stubs.config_flow.DEFAULT_UPDATE_INTERVAL
    assert err == "invalid_update_interval"
