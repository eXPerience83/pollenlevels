"""Home Assistant contract tests for external pollen card consumers."""

from __future__ import annotations

from typing import Any

from aiointercept import aiointercept
from homeassistant.const import ATTR_ICON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.pollenlevels.const import DOMAIN
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import async_setup_config_entry, mock_pollen_api


async def test_ha_classifier_metadata_contract_for_external_cards(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """Keep public type icons and plant classifier metadata stable."""
    clear_integration_modules()
    entry = ha_config_entry
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

    registry = er.async_get(hass)
    identity_id = f"{entry.entry_id}_location-madrid"
    entries_by_unique_id = {
        entity.unique_id: entity
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        if entity.domain == "sensor" and entity.platform == DOMAIN
    }

    expected_type_icons = {
        f"{identity_id}_type_grass": "mdi:grass",
        f"{identity_id}_type_tree": "mdi:tree",
        f"{identity_id}_type_weed": "mdi:flower-tulip",
    }
    for unique_id, expected_icon in expected_type_icons.items():
        registry_entry = entries_by_unique_id[unique_id]
        assert registry_entry.config_subentry_id == "location-madrid"
        state = hass.states.get(registry_entry.entity_id)
        assert state is not None
        assert state.attributes[ATTR_ICON] == expected_icon
        assert "code" not in state.attributes

    plant_entry = entries_by_unique_id[f"{identity_id}_plants_birch"]
    assert plant_entry.config_subentry_id == "location-madrid"
    plant_state = hass.states.get(plant_entry.entity_id)
    assert plant_state is not None
    assert plant_state.attributes[ATTR_ICON] == "mdi:tree"
    assert plant_state.attributes["code"] == "BIRCH"
    assert plant_state.attributes["type"] == "TREE"
