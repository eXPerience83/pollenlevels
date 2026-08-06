"""Home Assistant harness tests for platform entity setup."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from aiointercept import aiointercept
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from custom_components.pollenlevels.const import (
    DOMAIN,
)
from custom_components.pollenlevels.issue_helpers import (
    PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID,
)
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import (
    async_setup_config_entry,
    mock_pollen_api,
)


async def test_ha_platforms_create_entities_for_each_location_subentry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_two_location_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """Sensor and button platforms should attach entities to each subentry."""
    clear_integration_modules()
    entry = ha_two_location_config_entry
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

    registry = er.async_get(hass)
    entries = [
        entity
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        if entity.platform == DOMAIN
    ]

    expected_subentries = {"location-madrid", "location-barcelona"}
    assert expected_subentries <= {
        entity.config_subentry_id for entity in entries if entity.config_subentry_id
    }
    for subentry_id in expected_subentries:
        assert any(
            entity.domain == "sensor" and entity.config_subentry_id == subentry_id
            for entity in entries
        )
        assert any(
            entity.domain == "button" and entity.config_subentry_id == subentry_id
            for entity in entries
        )


async def test_ha_button_press_refreshes_location_coordinator(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """button.press should refresh the coordinator for its location subentry."""
    clear_integration_modules()
    ha_config_entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, ha_config_entry)

        registry = er.async_get(hass)
        button_entry = next(
            entity
            for entity in er.async_entries_for_config_entry(
                registry, ha_config_entry.entry_id
            )
            if entity.domain == "button"
            and entity.config_subentry_id == "location-madrid"
        )
        refresh = AsyncMock()
        monkeypatch.setattr(
            ha_config_entry.runtime_data.locations["location-madrid"].coordinator,
            "async_request_refresh",
            refresh,
        )

        await hass.services.async_call(
            "button",
            "press",
            {ATTR_ENTITY_ID: button_entry.entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()

    refresh.assert_awaited_once()


async def test_ha_platforms_clean_legacy_per_day_entities_and_create_repair(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """Sensor setup should remove legacy D+1/D+2 entities in the real registry."""
    clear_integration_modules()
    ha_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    identity_id = f"{ha_config_entry.entry_id}_location-madrid"
    legacy_unique_ids = [
        f"{identity_id}_type_grass_d1",
        f"{identity_id}_type_grass_d2",
    ]

    for unique_id in legacy_unique_ids:
        registry.async_get_or_create(
            "sensor",
            DOMAIN,
            unique_id,
            suggested_object_id=unique_id,
            config_entry=ha_config_entry,
            config_subentry_id="location-madrid",
        )

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, ha_config_entry)

    for unique_id in legacy_unique_ids:
        assert registry.async_get_entity_id("sensor", DOMAIN, unique_id) is None

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID
    )
    assert issue is not None
