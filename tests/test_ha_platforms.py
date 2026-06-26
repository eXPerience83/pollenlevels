"""Home Assistant harness tests for platform entity setup."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from aiointercept import aiointercept
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from custom_components.pollenlevels.const import (
    CONF_API_KEY,
    CONF_LANGUAGE_CODE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.pollenlevels.issue_helpers import (
    PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID,
)
from custom_components.pollenlevels.util import api_key_unique_id
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import (
    async_setup_config_entry,
    location_subentry_data,
    mock_pollen_api,
)


async def test_ha_platforms_create_entities_for_each_location_subentry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    sample_location_subentry_data: dict[str, Any],
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """Sensor and button platforms should attach entities to each subentry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    clear_integration_modules()
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="pollenlevels-entry",
        title="Pollen Levels",
        data={CONF_API_KEY: fake_api_key},
        options={
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_LANGUAGE_CODE: "es",
        },
        unique_id=api_key_unique_id(fake_api_key),
        subentries_data=[
            sample_location_subentry_data,
            location_subentry_data(
                subentry_id="location-barcelona",
                title="Barcelona",
                latitude=41.3874,
                longitude=2.1686,
            ),
        ],
        version=6,
    )
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
