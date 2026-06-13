"""Options flow validation tests for Pollen Levels."""

from __future__ import annotations

import asyncio
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

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


@dataclass(frozen=True)
class OptionsFlowEnv:
    """Imported options-flow module and constants backed by local HA stubs."""

    config_flow: ModuleType
    PollenLevelsOptionsFlow: type[Any]
    StubConfigEntry: type[Any]
    CONF_API_KEY: str
    CONF_CREATE_FORECAST_SENSORS: str
    CONF_FORECAST_DAYS: str
    CONF_LANGUAGE_CODE: str
    CONF_LATITUDE: str
    CONF_LONGITUDE: str
    CONF_UPDATE_INTERVAL: str
    DEFAULT_UPDATE_INTERVAL: int
    MAX_UPDATE_INTERVAL_HOURS: int
    MIN_UPDATE_INTERVAL_HOURS: int


@pytest.fixture
def options_flow_env(monkeypatch: pytest.MonkeyPatch) -> OptionsFlowEnv:
    """Install local Home Assistant stubs before importing config_flow."""

    clear_integration_modules(monkeypatch=monkeypatch)
    stub_custom_components_packages(root=ROOT, monkeypatch=monkeypatch)

    ha_mod = stub_homeassistant_package(monkeypatch=monkeypatch)

    config_entries_mod = ModuleType("homeassistant.config_entries")

    class StubConfigFlow:
        def __init_subclass__(cls, **_kwargs):
            return super().__init_subclass__()

    class StubOptionsFlow:
        pass

    class StubOptionsFlowWithReload(StubOptionsFlow):
        pass

    class StubConfigEntry:
        def __init__(
            self, data=None, options=None, entry_id="stub-entry", subentries=None
        ):
            self.data = data or {}
            self.options = options or {}
            self.entry_id = entry_id
            self.subentries = subentries or {}
            raw = self.data.get("name", "Pollen Levels") or ""
            self.title = raw.strip() or "Pollen Levels"

    class StubConfigSubentryFlow:
        pass

    config_entries_mod.ConfigFlow = StubConfigFlow
    config_entries_mod.OptionsFlow = StubOptionsFlow
    config_entries_mod.OptionsFlowWithReload = StubOptionsFlowWithReload
    config_entries_mod.ConfigEntry = StubConfigEntry
    config_entries_mod.ConfigSubentryFlow = StubConfigSubentryFlow
    config_entries_mod.ConfigSubentryData = dict
    config_entries_mod.ConfigFlowResult = dict
    config_entries_mod.SubentryFlowResult = dict
    monkeypatch.setitem(
        sys_modules := sys.modules,
        "homeassistant.config_entries",
        config_entries_mod,
    )

    class StubConfigEntryAuthFailed(Exception):
        pass

    stub_exceptions(
        monkeypatch=monkeypatch,
        ConfigEntryAuthFailed=StubConfigEntryAuthFailed,
    )

    const_mod = ModuleType("homeassistant.const")
    const_mod.CONF_LATITUDE = "latitude"
    const_mod.CONF_LOCATION = "location"
    const_mod.CONF_LONGITUDE = "longitude"
    const_mod.CONF_NAME = "name"
    monkeypatch.setitem(sys_modules, "homeassistant.const", const_mod)

    helpers_mod = ModuleType("homeassistant.helpers")
    monkeypatch.setitem(sys_modules, "homeassistant.helpers", helpers_mod)

    aiohttp_client_mod = ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client_mod.async_get_clientsession = lambda hass: None
    monkeypatch.setitem(
        sys_modules,
        "homeassistant.helpers.aiohttp_client",
        aiohttp_client_mod,
    )

    class StubUpdateFailed(Exception):
        pass

    class StubDataUpdateCoordinator:
        pass

    class StubCoordinatorEntity:
        pass

    stub_update_coordinator_module(
        update_failed=StubUpdateFailed,
        data_update_coordinator=StubDataUpdateCoordinator,
        coordinator_entity=StubCoordinatorEntity,
        monkeypatch=monkeypatch,
    )

    stub_util_dt_module(monkeypatch=monkeypatch)

    stub_selector_module(monkeypatch=monkeypatch)

    ha_mod.helpers = helpers_mod
    ha_mod.config_entries = config_entries_mod

    stub_aiohttp_module(monkeypatch=monkeypatch)

    vol_mod = ModuleType("voluptuous")

    class StubInvalid(Exception):
        def __init__(self, error_message=""):
            super().__init__(error_message)
            self.error_message = error_message

    class StubSchema:
        def __init__(self, schema):
            self.schema = schema

    vol_mod.Invalid = StubInvalid
    vol_mod.Schema = lambda schema, **kwargs: StubSchema(schema)
    vol_mod.Optional = lambda key, **kwargs: key
    vol_mod.Required = lambda key, **kwargs: key
    vol_mod.All = lambda *args, **kwargs: None
    vol_mod.Coerce = lambda *args, **kwargs: None
    vol_mod.Range = lambda *args, **kwargs: None
    vol_mod.In = lambda *args, **kwargs: None
    monkeypatch.setitem(sys_modules, "voluptuous", vol_mod)

    cf = importlib.import_module("custom_components.pollenlevels.config_flow")
    const = importlib.import_module("custom_components.pollenlevels.const")

    return OptionsFlowEnv(
        config_flow=cf,
        PollenLevelsOptionsFlow=cf.PollenLevelsOptionsFlow,
        StubConfigEntry=StubConfigEntry,
        CONF_API_KEY=cf.CONF_API_KEY,
        CONF_CREATE_FORECAST_SENSORS=const.CONF_CREATE_FORECAST_SENSORS,
        CONF_FORECAST_DAYS=const.CONF_FORECAST_DAYS,
        CONF_LANGUAGE_CODE=cf.CONF_LANGUAGE_CODE,
        CONF_LATITUDE=cf.CONF_LATITUDE,
        CONF_LONGITUDE=cf.CONF_LONGITUDE,
        CONF_UPDATE_INTERVAL=cf.CONF_UPDATE_INTERVAL,
        DEFAULT_UPDATE_INTERVAL=cf.DEFAULT_UPDATE_INTERVAL,
        MAX_UPDATE_INTERVAL_HOURS=cf.MAX_UPDATE_INTERVAL_HOURS,
        MIN_UPDATE_INTERVAL_HOURS=cf.MIN_UPDATE_INTERVAL_HOURS,
    )


def _flow(
    env: OptionsFlowEnv,
    entry_data: dict | None = None,
    options: dict | None = None,
):
    entry = env.StubConfigEntry(
        data=entry_data
        or {
            env.CONF_API_KEY: "key",
            env.CONF_LATITUDE: 1.0,
            env.CONF_LONGITUDE: 2.0,
            env.CONF_LANGUAGE_CODE: "en",
            env.CONF_UPDATE_INTERVAL: 6,
        },
        options=options,
    )
    flow = env.PollenLevelsOptionsFlow()
    flow.config_entry = entry
    flow.hass = SimpleNamespace(config=SimpleNamespace(language="en"))
    flow.async_show_form = lambda **kwargs: kwargs
    flow.async_create_entry = lambda *, title, data: {"title": title, "data": data}
    return flow


def test_options_flow_uses_modern_reload_base_class(
    options_flow_env: OptionsFlowEnv,
) -> None:
    """Options flow should inherit OptionsFlowWithReload."""

    assert issubclass(
        options_flow_env.PollenLevelsOptionsFlow,
        options_flow_env.config_flow.config_entries.OptionsFlowWithReload,
    )


def test_options_flow_invalid_language_sets_error(
    options_flow_env: OptionsFlowEnv,
) -> None:
    """Invalid language in options should map to invalid_language_format."""

    flow = _flow(options_flow_env)

    result = asyncio.run(
        flow.async_step_init(
            {
                options_flow_env.CONF_LANGUAGE_CODE: "bad code",
                options_flow_env.CONF_UPDATE_INTERVAL: 6,
            }
        )
    )

    assert result["errors"] == {
        options_flow_env.CONF_LANGUAGE_CODE: "invalid_language_format"
    }


def test_options_flow_invalid_language_code_not_logged_raw(
    options_flow_env: OptionsFlowEnv, caplog
) -> None:
    """Invalid language in options should not log the raw user-provided value."""
    flow = _flow(options_flow_env)

    with caplog.at_level("WARNING", logger=options_flow_env.config_flow.__name__):
        result = asyncio.run(
            flow.async_step_init(
                {
                    options_flow_env.CONF_LANGUAGE_CODE: "bad code",
                    options_flow_env.CONF_UPDATE_INTERVAL: 6,
                }
            )
        )

    assert "bad code" not in caplog.text
    assert result["errors"] == {
        options_flow_env.CONF_LANGUAGE_CODE: "invalid_language_format"
    }


def test_options_flow_update_interval_below_min_sets_error(
    options_flow_env: OptionsFlowEnv,
) -> None:
    """Sub-1 update intervals should raise a field error."""

    flow = _flow(options_flow_env)

    result = asyncio.run(
        flow.async_step_init(
            {
                options_flow_env.CONF_LANGUAGE_CODE: "en",
                options_flow_env.CONF_UPDATE_INTERVAL: 0,
            }
        )
    )

    assert result["errors"] == {
        options_flow_env.CONF_UPDATE_INTERVAL: "invalid_update_interval"
    }


def test_options_flow_invalid_update_interval_short_circuits(
    options_flow_env: OptionsFlowEnv,
) -> None:
    """Invalid update interval should short-circuit without extra errors."""

    flow = _flow(options_flow_env)

    result = asyncio.run(
        flow.async_step_init(
            {
                options_flow_env.CONF_LANGUAGE_CODE: "en",
                options_flow_env.CONF_UPDATE_INTERVAL: "not-a-number",
            }
        )
    )

    assert result["errors"] == {
        options_flow_env.CONF_UPDATE_INTERVAL: "invalid_update_interval"
    }


def test_options_flow_update_interval_above_max_sets_error(
    options_flow_env: OptionsFlowEnv,
) -> None:
    """Over-max update intervals should raise a field error."""

    flow = _flow(options_flow_env)

    result = asyncio.run(
        flow.async_step_init(
            {
                options_flow_env.CONF_LANGUAGE_CODE: "en",
                options_flow_env.CONF_UPDATE_INTERVAL: 999,
            }
        )
    )

    assert result["errors"] == {
        options_flow_env.CONF_UPDATE_INTERVAL: "invalid_update_interval"
    }


@pytest.mark.parametrize(
    ("raw_value", "expected_name"),
    [
        ("not-a-number", "DEFAULT_UPDATE_INTERVAL"),
        (0, "MIN_UPDATE_INTERVAL_HOURS"),
        (999, "MAX_UPDATE_INTERVAL_HOURS"),
    ],
)
def test_options_schema_update_interval_default_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    options_flow_env: OptionsFlowEnv,
    raw_value: object,
    expected_name: str,
) -> None:
    """Options form should clamp invalid update interval defaults."""

    expected = {
        "DEFAULT_UPDATE_INTERVAL": options_flow_env.DEFAULT_UPDATE_INTERVAL,
        "MIN_UPDATE_INTERVAL_HOURS": options_flow_env.MIN_UPDATE_INTERVAL_HOURS,
        "MAX_UPDATE_INTERVAL_HOURS": options_flow_env.MAX_UPDATE_INTERVAL_HOURS,
    }[expected_name]
    captured_defaults: list[int | None] = []

    def _capture_optional(key, **kwargs):
        if key == options_flow_env.CONF_UPDATE_INTERVAL:
            captured_defaults.append(kwargs.get("default"))
        return key

    monkeypatch.setattr(options_flow_env.config_flow.vol, "Optional", _capture_optional)

    flow = _flow(
        options_flow_env,
        options={options_flow_env.CONF_UPDATE_INTERVAL: raw_value},
    )
    asyncio.run(flow.async_step_init(user_input=None))

    assert captured_defaults == [expected]


def test_options_schema_omits_removed_forecast_options(
    monkeypatch: pytest.MonkeyPatch,
    options_flow_env: OptionsFlowEnv,
) -> None:
    """Removed forecast options should not be exposed in the options schema."""

    captured_keys: list[str] = []

    def _capture_optional(key, **kwargs):
        captured_keys.append(key)
        return key

    monkeypatch.setattr(options_flow_env.config_flow.vol, "Optional", _capture_optional)

    flow = _flow(
        options_flow_env,
        options={
            options_flow_env.CONF_FORECAST_DAYS: 0,
            options_flow_env.CONF_CREATE_FORECAST_SENSORS: "bad",
        },
    )
    asyncio.run(flow.async_step_init(user_input=None))

    assert options_flow_env.CONF_FORECAST_DAYS not in captured_keys
    assert options_flow_env.CONF_CREATE_FORECAST_SENSORS not in captured_keys
