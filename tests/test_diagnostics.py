"""Diagnostics tests for privacy and payload sizing."""

from __future__ import annotations

import datetime as dt
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


def _force_module(name: str, module: ModuleType) -> None:
    sys.modules[name] = module


components_mod = ModuleType("homeassistant.components")
diagnostics_mod = ModuleType("homeassistant.components.diagnostics")


def _async_redact_data(data: dict[str, Any], _redact: set[str]) -> dict[str, Any]:
    return data


diagnostics_mod.async_redact_data = _async_redact_data
_force_module("homeassistant.components", components_mod)
_force_module("homeassistant.components.diagnostics", diagnostics_mod)

config_entries_mod = ModuleType("homeassistant.config_entries")


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


config_entries_mod.ConfigEntry = _ConfigEntry
_force_module("homeassistant.config_entries", config_entries_mod)

core_mod = ModuleType("homeassistant.core")


class _HomeAssistant:
    pass


core_mod.HomeAssistant = _HomeAssistant
_force_module("homeassistant.core", core_mod)

from custom_components.pollenlevels import diagnostics as diag  # noqa: E402
from custom_components.pollenlevels.const import (  # noqa: E402
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
)
from custom_components.pollenlevels.runtime import PollenLevelsRuntimeData  # noqa: E402


@pytest.mark.asyncio
async def test_diagnostics_rounds_coordinates_and_truncates_keys() -> None:
    """Diagnostics should use rounded coordinates and limit data_keys length."""

    data = {
        CONF_LATITUDE: 12.3456,
        CONF_LONGITUDE: 78.9876,
        CONF_LANGUAGE_CODE: "en",
    }
    options = {CONF_FORECAST_DAYS: 3}

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
    entry.runtime_data = PollenLevelsRuntimeData(
        coordinator=coordinator, client=object()
    )

    diagnostics = await diag.async_get_config_entry_diagnostics(None, entry)

    assert CONF_LATITUDE not in diagnostics["entry"]["data"]
    assert CONF_LONGITUDE not in diagnostics["entry"]["data"]
    assert diagnostics["request_params_example"]["location.latitude"] == 12.3
    assert diagnostics["request_params_example"]["location.longitude"] == 79.0
    assert diagnostics["coordinator"]["data_keys_total"] == 60
    assert len(diagnostics["coordinator"]["data_keys"]) == 50
