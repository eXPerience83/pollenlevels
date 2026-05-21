"""Unit tests for the Pollen Levels button platform."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

custom_components_pkg = types.ModuleType("custom_components")
custom_components_pkg.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components_pkg)

pollenlevels_pkg = types.ModuleType("custom_components.pollenlevels")
pollenlevels_pkg.__path__ = [str(ROOT / "custom_components" / "pollenlevels")]
sys.modules.setdefault("custom_components.pollenlevels", pollenlevels_pkg)

button_mod = types.ModuleType("homeassistant.components.button")


class _StubButtonEntity:
    pass


button_mod.ButtonEntity = _StubButtonEntity
sys.modules.setdefault("homeassistant.components.button", button_mod)

entity_mod = sys.modules.get("homeassistant.helpers.entity") or types.ModuleType(
    "homeassistant.helpers.entity"
)


class _StubEntityCategory:
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"


entity_mod.EntityCategory = _StubEntityCategory
sys.modules["homeassistant.helpers.entity"] = entity_mod

update_mod = types.ModuleType("homeassistant.helpers.update_coordinator")


class _StubCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator


update_mod.CoordinatorEntity = _StubCoordinatorEntity
sys.modules.setdefault("homeassistant.helpers.update_coordinator", update_mod)

exceptions_mod = sys.modules.get("homeassistant.exceptions") or types.ModuleType(
    "homeassistant.exceptions"
)


class _StubHomeAssistantError(Exception):
    pass


exceptions_mod.HomeAssistantError = _StubHomeAssistantError
sys.modules["homeassistant.exceptions"] = exceptions_mod

config_entries_mod = sys.modules.get(
    "homeassistant.config_entries"
) or types.ModuleType("homeassistant.config_entries")


class _StubConfigEntry:
    @classmethod
    def __class_getitem__(cls, _item):
        return cls


config_entries_mod.ConfigEntry = _StubConfigEntry
sys.modules["homeassistant.config_entries"] = config_entries_mod

button = importlib.import_module("custom_components.pollenlevels.button")


class _FakeCoordinator:
    def __init__(self) -> None:
        self.entry_id = "entry-123"
        self.entry_title = "Test Location"
        self.lat = 40.7128
        self.lon = -74.0060
        self.refresh_calls = 0

    async def async_request_refresh(self) -> None:
        self.refresh_calls += 1


def test_button_attributes() -> None:
    coordinator = _FakeCoordinator()
    entity = button.PollenLevelsUpdateButton(coordinator)

    assert entity._attr_unique_id == "entry-123_update_now"
    assert entity._attr_translation_key == "update_now"
    assert entity._attr_entity_category == "config"
    assert entity._attr_device_info["identifiers"] == {
        ("pollenlevels", "entry-123_meta")
    }
    assert entity._attr_device_info["translation_key"] == "info"


@pytest.mark.asyncio
async def test_button_press_triggers_refresh() -> None:
    coordinator = _FakeCoordinator()
    entity = button.PollenLevelsUpdateButton(coordinator)

    await entity.async_press()

    assert coordinator.refresh_calls == 1


@pytest.mark.asyncio
async def test_button_press_raises_homeassistant_error_on_refresh_failure() -> None:
    coordinator = _FakeCoordinator()

    async def _raise_error() -> None:
        raise RuntimeError("boom")

    coordinator.async_request_refresh = _raise_error  # type: ignore[method-assign]
    entity = button.PollenLevelsUpdateButton(coordinator)

    with pytest.raises(exceptions_mod.HomeAssistantError):
        await entity.async_press()


@pytest.mark.asyncio
async def test_setup_entry_adds_one_button_entity() -> None:
    coordinator = _FakeCoordinator()
    runtime = types.SimpleNamespace(coordinator=coordinator)
    entry = types.SimpleNamespace(runtime_data=runtime)
    added = []

    def _add_entities(entities):
        added.extend(entities)

    await button.async_setup_entry(None, entry, _add_entities)
    assert len(added) == 1
    assert isinstance(added[0], button.PollenLevelsUpdateButton)
