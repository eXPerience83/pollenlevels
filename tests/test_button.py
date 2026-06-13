"""Unit tests for the Pollen Levels button platform."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


@pytest.fixture
def stub_ha_modules(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    clear_integration_modules(monkeypatch=monkeypatch)
    stub_custom_components_packages(root=ROOT, monkeypatch=monkeypatch)
    stub_homeassistant_package(monkeypatch=monkeypatch)

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

    class _StubCoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

    stub_update_coordinator_module(
        update_failed=RuntimeError,
        data_update_coordinator=object,
        coordinator_entity=_StubCoordinatorEntity,
        monkeypatch=monkeypatch,
    )

    core_mod = types.ModuleType("homeassistant.core")

    class _StubHomeAssistant:
        pass

    core_mod.HomeAssistant = _StubHomeAssistant
    monkeypatch.setitem(sys.modules, "homeassistant.core", core_mod)

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

    exceptions_mod = stub_exceptions(
        monkeypatch=monkeypatch,
        HomeAssistantError=_StubHomeAssistantError,
        ConfigEntryNotReady=_StubConfigEntryNotReady,
    )

    class _StubConfigEntry:
        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    stub_config_entry_class(_StubConfigEntry, monkeypatch=monkeypatch)

    return SimpleNamespace(
        exceptions=exceptions_mod,
        hass_class=_StubHomeAssistant,
    )


@pytest.fixture
def button_platform(
    monkeypatch: pytest.MonkeyPatch, stub_ha_modules: SimpleNamespace
) -> SimpleNamespace:
    module = importlib.import_module("custom_components.pollenlevels.button")
    return SimpleNamespace(
        module=module,
        exceptions=stub_ha_modules.exceptions,
        hass_class=stub_ha_modules.hass_class,
    )


class _FakeCoordinator:
    def __init__(self) -> None:
        self.entry_id = "entry-123"
        self.entry_title = "Test Location"
        self.lat = 40.7128
        self.lon = -74.0060
        self.async_request_refresh = AsyncMock()
        self.last_update_success = True
        self.last_exception = None


def test_button_attributes(button_platform: SimpleNamespace) -> None:
    coordinator = _FakeCoordinator()
    entity = button_platform.module.PollenLevelsUpdateButton(coordinator)

    assert entity._attr_unique_id == "entry-123_update_now"
    assert entity._attr_translation_key == "update_now"
    assert entity._attr_entity_category == "config"
    assert entity._attr_device_info["identifiers"] == {
        ("pollenlevels", "entry-123_meta")
    }
    assert entity._attr_device_info["translation_key"] == "info"


def test_button_attributes_use_legacy_identity(
    button_platform: SimpleNamespace,
) -> None:
    coordinator = _FakeCoordinator()
    coordinator.entity_identity_id = "legacy-entry"
    coordinator.device_identity_id = "legacy-entry"
    entity = button_platform.module.PollenLevelsUpdateButton(coordinator)

    assert entity._attr_unique_id == "legacy-entry_update_now"
    assert entity._attr_device_info["identifiers"] == {
        ("pollenlevels", "legacy-entry_meta")
    }


def test_button_attributes_use_new_subentry_identity(
    button_platform: SimpleNamespace,
) -> None:
    first = _FakeCoordinator()
    first.entity_identity_id = "parent-entry_location-1"
    first.device_identity_id = "parent-entry_location-1"
    changed = _FakeCoordinator()
    changed.entity_identity_id = "parent-entry_location-1"
    changed.device_identity_id = "parent-entry_location-1"
    changed.entry_title = "Renamed"
    changed.lat = 3.0
    changed.lon = 4.0

    first_entity = button_platform.module.PollenLevelsUpdateButton(first)
    changed_entity = button_platform.module.PollenLevelsUpdateButton(changed)

    assert first_entity._attr_unique_id == changed_entity._attr_unique_id
    assert first_entity._attr_unique_id == "parent-entry_location-1_update_now"
    assert (
        first_entity._attr_device_info["identifiers"]
        == changed_entity._attr_device_info["identifiers"]
    )


def test_button_available_when_last_update_failed(
    button_platform: SimpleNamespace,
) -> None:
    coordinator = _FakeCoordinator()
    coordinator.last_update_success = False

    entity = button_platform.module.PollenLevelsUpdateButton(coordinator)

    assert entity.available is True


@pytest.mark.asyncio
async def test_button_press_awaits_async_request_refresh(
    button_platform: SimpleNamespace,
) -> None:
    coordinator = _FakeCoordinator()
    entity = button_platform.module.PollenLevelsUpdateButton(coordinator)

    await entity.async_press()

    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_button_press_raises_homeassistant_error_on_refresh_failure(
    button_platform: SimpleNamespace,
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
    button_platform: SimpleNamespace,
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
    button_platform: SimpleNamespace,
) -> None:
    entry = types.SimpleNamespace(runtime_data=None)

    with pytest.raises(button_platform.exceptions.ConfigEntryNotReady):
        await button_platform.module.async_setup_entry(
            button_platform.hass_class(), entry, lambda entities: None
        )


@pytest.mark.asyncio
async def test_setup_entry_raises_if_runtime_data_attribute_missing(
    button_platform: SimpleNamespace,
) -> None:
    entry = types.SimpleNamespace()

    with pytest.raises(button_platform.exceptions.ConfigEntryNotReady):
        await button_platform.module.async_setup_entry(
            button_platform.hass_class(), entry, lambda entities: None
        )


@pytest.mark.asyncio
async def test_setup_entry_adds_one_button_entity(
    button_platform: SimpleNamespace,
) -> None:
    coordinator = _FakeCoordinator()
    runtime = types.SimpleNamespace(coordinator=coordinator)
    entry = types.SimpleNamespace(runtime_data=runtime)
    added = []

    def _add_entities(entities):
        added.extend(entities)

    await button_platform.module.async_setup_entry(
        button_platform.hass_class(), entry, _add_entities
    )
    assert len(added) == 1
    assert isinstance(added[0], button_platform.module.PollenLevelsUpdateButton)


@pytest.mark.asyncio
async def test_setup_entry_without_locations_adds_no_button(
    button_platform: SimpleNamespace,
) -> None:
    entry = types.SimpleNamespace(runtime_data=types.SimpleNamespace(locations={}))
    added = []

    def _add_entities(entities):
        added.extend(entities)

    await button_platform.module.async_setup_entry(
        button_platform.hass_class(), entry, _add_entities
    )

    assert added == []


@pytest.mark.asyncio
async def test_setup_entry_skips_stale_runtime_locations(
    button_platform: SimpleNamespace,
) -> None:
    """Button setup should not recreate buttons for deleted location subentries."""

    coordinator = _FakeCoordinator()
    entry = types.SimpleNamespace(
        data={},
        subentries={},
        runtime_data=types.SimpleNamespace(
            locations={
                "deleted-location": types.SimpleNamespace(
                    subentry_id="deleted-location",
                    coordinator=coordinator,
                )
            }
        ),
    )
    added = []

    def _add_entities(entities, **_kwargs):
        added.extend(entities)

    await button_platform.module.async_setup_entry(
        button_platform.hass_class(), entry, _add_entities
    )

    assert added == []


@pytest.mark.asyncio
async def test_setup_entry_ignores_failed_locations(
    button_platform: SimpleNamespace,
) -> None:
    """Button setup should create buttons only for loaded runtime locations."""

    coordinator = _FakeCoordinator()
    entry = types.SimpleNamespace(
        data={},
        subentries={
            "loaded-location": types.SimpleNamespace(
                subentry_id="loaded-location",
                subentry_type="location",
            ),
            "failed-location": types.SimpleNamespace(
                subentry_id="failed-location",
                subentry_type="location",
            ),
        },
        runtime_data=types.SimpleNamespace(
            locations={
                "loaded-location": types.SimpleNamespace(
                    subentry_id="loaded-location",
                    coordinator=coordinator,
                )
            },
            failed_locations={
                "failed-location": types.SimpleNamespace(
                    subentry_id="failed-location",
                    title="Failed",
                    error_type="UpdateFailed",
                    reason="No data",
                )
            },
        ),
    )
    added = []
    subentry_ids = []

    def _add_entities(entities, **kwargs):
        added.extend(entities)
        subentry_ids.append(kwargs.get("config_subentry_id"))

    await button_platform.module.async_setup_entry(
        button_platform.hass_class(), entry, _add_entities
    )

    assert len(added) == 1
    assert subentry_ids == ["loaded-location"]
