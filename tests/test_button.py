"""Unit tests for the Pollen Levels button platform."""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def stub_ha_modules(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Stub required Home Assistant modules before importing button platform."""

    custom_components_pkg = types.ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(ROOT / "custom_components")]
    monkeypatch.setitem(sys.modules, "custom_components", custom_components_pkg)

    pollenlevels_pkg = types.ModuleType("custom_components.pollenlevels")
    pollenlevels_pkg.__path__ = [str(ROOT / "custom_components" / "pollenlevels")]
    monkeypatch.setitem(sys.modules, "custom_components.pollenlevels", pollenlevels_pkg)

    button_mod = types.ModuleType("homeassistant.components.button")

    class StubButtonEntity:
        pass

    button_mod.ButtonEntity = StubButtonEntity
    monkeypatch.setitem(sys.modules, "homeassistant.components.button", button_mod)

    entity_mod = types.ModuleType("homeassistant.helpers.entity")

    class StubEntityCategory:
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    entity_mod.EntityCategory = StubEntityCategory
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.entity", entity_mod)

    update_mod = types.ModuleType("homeassistant.helpers.update_coordinator")

    class StubCoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

    update_mod.CoordinatorEntity = StubCoordinatorEntity
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.update_coordinator", update_mod
    )

    core_mod = types.ModuleType("homeassistant.core")

    class StubHomeAssistant:
        pass

    core_mod.HomeAssistant = StubHomeAssistant
    monkeypatch.setitem(sys.modules, "homeassistant.core", core_mod)

    exceptions_mod = types.ModuleType("homeassistant.exceptions")

    class StubHomeAssistantError(Exception):
        def __init__(
            self,
            *args,
            translation_domain=None,
            translation_key=None,
            translation_placeholders=None,
        ):
            super().__init__(*args)
            self.translation_domain = translation_domain
            self.translation_key = translation_key
            self.translation_placeholders = translation_placeholders

    class StubConfigEntryNotReady(Exception):
        pass

    exceptions_mod.HomeAssistantError = StubHomeAssistantError
    exceptions_mod.ConfigEntryNotReady = StubConfigEntryNotReady
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", exceptions_mod)

    config_entries_mod = types.ModuleType("homeassistant.config_entries")

    class StubConfigEntry:
        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    config_entries_mod.ConfigEntry = StubConfigEntry
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries_mod)

    return {
        "exceptions_mod": exceptions_mod,
        "StubHomeAssistant": StubHomeAssistant,
    }


BUTTON_MODULE = None
EXCEPTIONS_MOD = None
STUB_HOME_ASSISTANT = None


@pytest.fixture(autouse=True)
def button_module(stub_ha_modules: dict[str, object]):
    """Import the button module after stubbing Home Assistant dependencies."""

    global BUTTON_MODULE, EXCEPTIONS_MOD, STUB_HOME_ASSISTANT

    sys.modules.pop("custom_components.pollenlevels.button", None)
    BUTTON_MODULE = importlib.import_module("custom_components.pollenlevels.button")
    EXCEPTIONS_MOD = stub_ha_modules["exceptions_mod"]
    STUB_HOME_ASSISTANT = stub_ha_modules["StubHomeAssistant"]


class _FakeCoordinator:
    def __init__(self) -> None:
        self.entry_id = "entry-123"
        self.entry_title = "Test Location"
        self.lat = 40.7128
        self.lon = -74.0060
        self.async_request_refresh = AsyncMock()
        self.last_update_success = True
        self.last_exception = None


def test_button_attributes() -> None:
    coordinator = _FakeCoordinator()
    entity = BUTTON_MODULE.PollenLevelsUpdateButton(coordinator)

    assert entity._attr_unique_id == "entry-123_update_now"
    assert entity._attr_translation_key == "update_now"
    assert entity._attr_entity_category == "config"
    assert entity._attr_device_info["identifiers"] == {
        ("pollenlevels", "entry-123_meta")
    }
    assert entity._attr_device_info["translation_key"] == "info"


def test_button_available_when_last_update_failed() -> None:
    coordinator = _FakeCoordinator()
    coordinator.last_update_success = False

    entity = BUTTON_MODULE.PollenLevelsUpdateButton(coordinator)

    assert entity.available is True


def test_button_press_awaits_async_request_refresh() -> None:
    coordinator = _FakeCoordinator()
    entity = BUTTON_MODULE.PollenLevelsUpdateButton(coordinator)

    asyncio.run(entity.async_press())

    coordinator.async_request_refresh.assert_awaited_once()


def test_button_press_raises_homeassistant_error_on_refresh_failure() -> None:
    coordinator = _FakeCoordinator()
    coordinator.async_request_refresh.side_effect = RuntimeError("boom")
    entity = BUTTON_MODULE.PollenLevelsUpdateButton(coordinator)

    with pytest.raises(EXCEPTIONS_MOD.HomeAssistantError) as err:
        asyncio.run(entity.async_press())

    assert err.value.translation_domain == "pollenlevels"
    assert err.value.translation_key == "refresh_failed"


def test_button_press_raises_when_refresh_reports_failure() -> None:
    coordinator = _FakeCoordinator()

    async def _refresh_without_raise() -> None:
        coordinator.last_update_success = False
        coordinator.last_exception = RuntimeError("boom")

    coordinator.async_request_refresh.side_effect = _refresh_without_raise
    entity = BUTTON_MODULE.PollenLevelsUpdateButton(coordinator)

    with pytest.raises(EXCEPTIONS_MOD.HomeAssistantError) as err:
        asyncio.run(entity.async_press())

    assert err.value.translation_domain == "pollenlevels"
    assert err.value.translation_key == "refresh_failed"


def test_setup_entry_raises_if_runtime_data_missing() -> None:
    entry = types.SimpleNamespace(runtime_data=None)

    with pytest.raises(EXCEPTIONS_MOD.ConfigEntryNotReady):
        asyncio.run(
            BUTTON_MODULE.async_setup_entry(
                STUB_HOME_ASSISTANT(), entry, lambda entities: None
            )
        )


def test_setup_entry_adds_one_button_entity() -> None:
    coordinator = _FakeCoordinator()
    runtime = types.SimpleNamespace(coordinator=coordinator)
    entry = types.SimpleNamespace(runtime_data=runtime)
    added = []

    def _add_entities(entities):
        added.extend(entities)

    asyncio.run(
        BUTTON_MODULE.async_setup_entry(STUB_HOME_ASSISTANT(), entry, _add_entities)
    )
    assert len(added) == 1
    assert isinstance(added[0], BUTTON_MODULE.PollenLevelsUpdateButton)
