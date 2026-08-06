"""Home Assistant harness test for config subentry removal."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

from aiointercept import aiointercept
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
)

from custom_components.pollenlevels.const import (
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import (
    async_setup_config_entry,
    mock_pollen_api,
)


def _entities_for_subentry(
    registry: er.EntityRegistry, entry_id: str, subentry_id: str
) -> list[er.RegistryEntry]:
    """Return integration entities associated with one config subentry."""
    return [
        entity
        for entity in er.async_entries_for_config_entry(registry, entry_id)
        if entity.platform == DOMAIN and entity.config_subentry_id == subentry_id
    ]


def _devices_for_subentry(
    registry: dr.DeviceRegistry, entry_id: str, subentry_id: str
) -> list[dr.DeviceEntry]:
    """Return devices associated with one config subentry."""
    return [
        device
        for device in dr.async_entries_for_config_entry(registry, entry_id)
        if device.config_subentry_id == subentry_id
    ]


async def test_ha_real_subentry_removal_lifecycle(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_two_location_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """A real subentry removal should clean registries and stale runtime."""
    clear_integration_modules()
    entry = ha_two_location_config_entry
    entry.add_to_hass(hass)
    captured_params: list[dict[str, Any]] = []

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(
            mocked,
            google_pollen_5_day_payload,
            captured_params=captured_params,
        )
        await async_setup_config_entry(hass, entry)

        assert entry.state is ConfigEntryState.LOADED
        assert set(entry.subentries) == {
            "location-madrid",
            "location-barcelona",
        }
        assert set(entry.runtime_data.locations) == {
            "location-madrid",
            "location-barcelona",
        }
        assert {
            (
                float(params["location.latitude"]),
                float(params["location.longitude"]),
            )
            for params in captured_params
        } == {(40.4168, -3.7038), (41.3874, 2.1686)}

        madrid_coordinator = entry.runtime_data.locations["location-madrid"].coordinator
        barcelona_coordinator = entry.runtime_data.locations[
            "location-barcelona"
        ].coordinator

        entity_registry = er.async_get(hass)
        device_registry = dr.async_get(hass)
        madrid_entities = _entities_for_subentry(
            entity_registry, entry.entry_id, "location-madrid"
        )
        barcelona_entities = _entities_for_subentry(
            entity_registry, entry.entry_id, "location-barcelona"
        )
        madrid_devices = _devices_for_subentry(
            device_registry, entry.entry_id, "location-madrid"
        )
        barcelona_devices = _devices_for_subentry(
            device_registry, entry.entry_id, "location-barcelona"
        )

        for entities in (madrid_entities, barcelona_entities):
            assert entities
            assert any(entity.domain == "sensor" for entity in entities)
            assert any(entity.domain == "button" for entity in entities)
            assert all(
                hass.states.get(entity.entity_id) is not None for entity in entities
            )
        assert madrid_devices
        assert barcelona_devices

        madrid_entity_ids = {entity.entity_id for entity in madrid_entities}
        barcelona_entity_ids = {entity.entity_id for entity in barcelona_entities}
        madrid_device_ids = {device.id for device in madrid_devices}
        barcelona_device_ids = {device.id for device in barcelona_devices}

        madrid_scheduled_update = AsyncMock(return_value=madrid_coordinator.data)
        barcelona_scheduled_update = AsyncMock(return_value=barcelona_coordinator.data)
        monkeypatch.setattr(
            madrid_coordinator, "_async_update_data", madrid_scheduled_update
        )
        monkeypatch.setattr(
            barcelona_coordinator,
            "_async_update_data",
            barcelona_scheduled_update,
        )

        assert hass.config_entries.async_remove_subentry(entry, "location-barcelona")
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert set(entry.subentries) == {"location-madrid"}
        assert set(entry.runtime_data.locations) == {
            "location-madrid",
            "location-barcelona",
        }

        assert all(
            entity_registry.async_get(entity_id) is None
            and hass.states.get(entity_id) is None
            for entity_id in barcelona_entity_ids
        )
        assert all(
            device_registry.async_get(device_id) is None
            for device_id in barcelona_device_ids
        )
        assert not _entities_for_subentry(
            entity_registry, entry.entry_id, "location-barcelona"
        )
        assert not _devices_for_subentry(
            device_registry, entry.entry_id, "location-barcelona"
        )
        assert all(
            entity_registry.async_get(entity_id) is not None
            and hass.states.get(entity_id) is not None
            for entity_id in madrid_entity_ids
        )
        assert all(
            device_registry.async_get(device_id) is not None
            for device_id in madrid_device_ids
        )

        async_fire_time_changed(
            hass,
            datetime.now(UTC) + timedelta(hours=DEFAULT_UPDATE_INTERVAL, seconds=1),
        )
        await hass.async_block_till_done()

        madrid_scheduled_update.assert_awaited_once()
        barcelona_scheduled_update.assert_not_awaited()

        with (
            patch.object(
                madrid_coordinator,
                "async_request_refresh",
                new_callable=AsyncMock,
            ) as madrid_force_update,
            patch.object(
                barcelona_coordinator,
                "async_request_refresh",
                new_callable=AsyncMock,
            ) as barcelona_force_update,
        ):
            await hass.services.async_call(DOMAIN, "force_update", {}, blocking=True)
            await hass.async_block_till_done()

        madrid_force_update.assert_awaited_once()
        barcelona_force_update.assert_not_awaited()
        assert not _entities_for_subentry(
            entity_registry, entry.entry_id, "location-barcelona"
        )
        assert not _devices_for_subentry(
            device_registry, entry.entry_id, "location-barcelona"
        )

        diagnostics_module = importlib.import_module(
            "custom_components.pollenlevels.diagnostics"
        )
        diagnostics = await diagnostics_module.async_get_config_entry_diagnostics(
            hass, entry
        )
        assert diagnostics["runtime_summary"] == {
            "stale_location_count": 1,
            "stale_location_ids": ["location-barcelona"],
            "failed_location_count": 0,
            "failed_location_ids": [],
        }
        assert set(diagnostics["locations"]) == {"location-madrid"}
        assert set(diagnostics["registry_summary"]["entities"]["by_subentry_id"]) == {
            "location-madrid"
        }
        assert diagnostics["registry_summary"]["entities"]["without_subentry"] == 0
        assert set(diagnostics["registry_summary"]["devices"]["by_subentry_id"]) == {
            "location-madrid"
        }
        assert diagnostics["registry_summary"]["devices"]["without_subentry"] == 0

        madrid_scheduled_update.reset_mock()
        barcelona_scheduled_update.reset_mock()
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert set(entry.subentries) == {"location-madrid"}
        assert set(entry.runtime_data.locations) == {"location-madrid"}
        assert (
            entry.runtime_data.locations["location-madrid"].coordinator
            is not madrid_coordinator
        )
        assert not _entities_for_subentry(
            entity_registry, entry.entry_id, "location-barcelona"
        )
        assert not _devices_for_subentry(
            device_registry, entry.entry_id, "location-barcelona"
        )
        remaining_entities = _entities_for_subentry(
            entity_registry, entry.entry_id, "location-madrid"
        )
        assert any(entity.domain == "sensor" for entity in remaining_entities)
        assert any(entity.domain == "button" for entity in remaining_entities)

        diagnostics = await diagnostics_module.async_get_config_entry_diagnostics(
            hass, entry
        )
        assert diagnostics["runtime_summary"] == {
            "stale_location_count": 0,
            "stale_location_ids": [],
            "failed_location_count": 0,
            "failed_location_ids": [],
        }

        captured_params.clear()
        async_fire_time_changed(
            hass,
            datetime.now(UTC) + timedelta(hours=DEFAULT_UPDATE_INTERVAL, seconds=1),
        )
        await hass.async_block_till_done()

        madrid_scheduled_update.assert_not_awaited()
        barcelona_scheduled_update.assert_not_awaited()
        assert len(captured_params) == 1
        assert float(captured_params[0]["location.latitude"]) == 40.4168
        assert float(captured_params[0]["location.longitude"]) == -3.7038

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
