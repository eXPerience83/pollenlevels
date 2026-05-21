"""Unit tests for the Pollen Levels button platform."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

custom_components_pkg = types.ModuleType("custom_components")
custom_components_pkg.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components_pkg)

pollenlevels_pkg = types.ModuleType("custom_components.pollenlevels")
pollenlevels_pkg.__path__ = [str(ROOT / "custom_components" / "pollenlevels")]
sys.modules.setdefault("custom_components.pollenlevels", pollenlevels_pkg)


class _FakeCoordinator:
    def __init__(self) -> None:
        self.entry_id = "entry-123"
        self.entry_title = "Test Location"
        self.lat = 40.7128
        self.lon = -74.0060
        self.async_request_refresh = AsyncMock()
        self.last_update_success = True
        self.last_exception = None


@pytest.fixture
def stub_ha_modules(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """Provide Home Assistant stubs required by button.py."""

    button_mod = types.ModuleType("homeassistant.components.button")

    class _StubButtonEntity:
        pass

    button_mod.ButtonEntity = _StubButtonEntity
    monkeypatch.setitem(sys.modules, "homeassistant.components.button", button_mod)

    entity_mod = types.ModuleType("homeassistant.helpers.entity")

    class _StubEntityCategory:
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    entity_mod.EntityCategory = _StubEntityCategory
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.entity", entity_mod)

    update_mod = types.ModuleType("homeassistant.helpers.update_coordinator")

    class _StubCoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

    update_mod.CoordinatorEntity = _StubCoordinatorEntity
    monkeypatch.setitem(
        sys.modules,
        "homeassistant.helpers.update_coordinator",
        update_mod,
    )

    core_mod = types.ModuleType("homeassistant.core")

    class _StubHomeAssistant:
        pass

    core_mod.HomeAssistant = _StubHomeAssistant
    monkeypatch.setitem(sys.modules, "homeassistant.core", core_mod)

    exceptions_mod = types.ModuleType("homeassistant.exceptions")

    class _StubHomeAssistantError(Exception):
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

    class _StubConfigEntryNotReady(Exception):
        pass

    exceptions_mod.HomeAssistantError = _StubHomeAssistantError
    exceptions_mod.ConfigEntryNotReady = _StubConfigEntryNotReady
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", exceptions_mod)

    config_entries_mod = types.ModuleType("homeassistant.config_entries")

    class _StubConfigEntry:
        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    config_entries_mod.ConfigEntry = _StubConfigEntry
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries_mod)

    return types.SimpleNamespace(
        exceptions=exceptions_mod,
        hass_class=_StubHomeAssistant,
    )


@pytest.fixture
def button_platform(
    stub_ha_modules: types.SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> types.SimpleNamespace:
    """Import button platform after stubbing Home Assistant modules."""

    monkeypatch.delitem(
        sys.modules,
        "custom_components.pollenlevels.button",
        raising=False,
    )
    module = importlib.import_module("custom_components.pollenlevels.button")
    return types.SimpleNamespace(
        module=module,
        exceptions=stub_ha_modules.exceptions,
        hass_class=stub_ha_modules.hass_class,
    )


def test_button_attributes(button_platform: types.SimpleNamespace) -> None:
    coordinator = _FakeCoordinator()
    entity = button_platform.module.PollenLevelsUpdateButton(coordinator)

    assert entity._attr_unique_id == "entry-123_update_now"
    assert entity._attr_translation_key == "update_now"
    assert entity._attr_entity_category == "config"
    assert entity._attr_device_info["identifiers"] == {
        ("pollenlevels", "entry-123_meta")
    }
    assert entity._attr_device_info["translation_key"] == "info"


def test_button_available_when_last_update_failed(
    button_platform: types.SimpleNamespace,
) -> None:
    coordinator = _FakeCoordinator()
    coordinator.last_update_success = False

    entity = button_platform.module.PollenLevelsUpdateButton(coordinator)

    assert entity.available is True


@pytest.mark.asyncio
async def test_button_press_awaits_async_request_refresh(
    button_platform: types.SimpleNamespace,
    stub_ha_modules: types.SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _FakeCoordinator()
    entity = button_platform.module.PollenLevelsUpdateButton(coordinator)

    await entity.async_press()

    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_button_press_raises_homeassistant_error_on_refresh_failure(
    button_platform: types.SimpleNamespace,
    stub_ha_modules: types.SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _FakeCoordinator()
    coordinator.async_request_refresh.side_effect = RuntimeError("boom")
    entity = button_platform.module.PollenLevelsUpdateButton(coordinator)

    with pytest.raises(button_platform.exceptions.HomeAssistantError) as err:
        await entity.async_press()

    assert err.value.translation_domain == "pollenlevels"
    assert err.value.translation_key == "refresh_failed"


@pytest.mark.asyncio
async def test_button_press_raises_when_refresh_reports_failure(
    button_platform: types.SimpleNamespace,
    stub_ha_modules: types.SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _FakeCoordinator()

    async def _refresh_without_raise() -> None:
        coordinator.last_update_success = False
        coordinator.last_exception = RuntimeError("boom")

    coordinator.async_request_refresh.side_effect = _refresh_without_raise
    entity = button_platform.module.PollenLevelsUpdateButton(coordinator)

    with pytest.raises(button_platform.exceptions.HomeAssistantError) as err:
        await entity.async_press()

    assert err.value.translation_domain == "pollenlevels"
    assert err.value.translation_key == "refresh_failed"


@pytest.mark.asyncio
async def test_setup_entry_raises_if_runtime_data_missing(
    button_platform: types.SimpleNamespace,
    stub_ha_modules: types.SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = types.SimpleNamespace(runtime_data=None)

    with pytest.raises(button_platform.exceptions.ConfigEntryNotReady):
        await button_platform.module.async_setup_entry(
            button_platform.hass_class(),
            entry,
            lambda entities: None,
        )


@pytest.mark.asyncio
async def test_setup_entry_adds_one_button_entity(
    button_platform: types.SimpleNamespace,
    stub_ha_modules: types.SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _FakeCoordinator()
    runtime = types.SimpleNamespace(coordinator=coordinator)
    entry = types.SimpleNamespace(runtime_data=runtime)
    added = []

    def _add_entities(entities):
        added.extend(entities)

    await button_platform.module.async_setup_entry(
        button_platform.hass_class(),
        entry,
        _add_entities,
    )
    assert len(added) == 1
    assert isinstance(added[0], button_platform.module.PollenLevelsUpdateButton)
