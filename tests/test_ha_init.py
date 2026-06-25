"""Home Assistant harness tests for config entry setup."""

from __future__ import annotations

from typing import Any

from aiointercept import aiointercept
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import (
    assert_fixed_forecast_days,
    async_setup_config_entry,
    mock_pollen_api,
)


async def test_ha_setup_unload_reload_smoke(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    ha_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """Set up, unload and reload a parent entry with one location subentry."""
    captured_params: list[dict[str, Any]] = []
    clear_integration_modules()
    ha_config_entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload, captured_params)

        await async_setup_config_entry(hass, ha_config_entry)

        assert ha_config_entry.state is ConfigEntryState.LOADED
        assert set(ha_config_entry.runtime_data.locations) == {"location-madrid"}
        assert_fixed_forecast_days(captured_params)

        registry = er.async_get(hass)
        entries = er.async_entries_for_config_entry(
            registry,
            ha_config_entry.entry_id,
        )
        assert any(entity.domain == "sensor" for entity in entries)
        assert any(entity.domain == "button" for entity in entries)

        assert await hass.config_entries.async_unload(ha_config_entry.entry_id)
        await hass.async_block_till_done()
        assert ha_config_entry.state is ConfigEntryState.NOT_LOADED
        assert getattr(ha_config_entry, "runtime_data", None) is None

        assert await hass.config_entries.async_setup(ha_config_entry.entry_id)
        await hass.async_block_till_done()
        assert ha_config_entry.state is ConfigEntryState.LOADED
