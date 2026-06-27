"""Home Assistant harness tests for config entry setup."""

from __future__ import annotations

from typing import Any

from aiointercept import aiointercept
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import (
    assert_fixed_forecast_days,
    async_setup_config_entry,
    mock_pollen_api,
)


def _create_test_repair(
    hass: HomeAssistant,
    domain: str,
    issue_id: str,
    *,
    is_persistent: bool = True,
) -> None:
    """Create a minimal Repair issue for registry cleanup tests."""
    ir.async_create_issue(
        hass,
        domain,
        issue_id,
        is_fixable=False,
        is_persistent=is_persistent,
        severity=ir.IssueSeverity.WARNING,
        translation_key="location_setup_failed",
    )


async def test_ha_setup_unload_reload_smoke(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
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


async def test_ha_stale_location_repairs_are_discovered_from_registry(
    hass: HomeAssistant,
) -> None:
    """Stale Repairs should be deleted without runtime issue bookkeeping."""
    clear_integration_modules()
    from custom_components.pollenlevels.const import DOMAIN
    from custom_components.pollenlevels.issue_helpers import (
        delete_stale_location_subentry_issues,
        invalid_stored_location_issue_id,
        location_setup_failed_issue_id,
    )

    entry_id = "entry-target"
    active_issue_id = location_setup_failed_issue_id(entry_id, "active-location")
    stale_issue_id = location_setup_failed_issue_id(entry_id, "stale-location")
    stale_invalid_issue_id = invalid_stored_location_issue_id(
        entry_id, "stale-location"
    )
    legacy_issue_id = invalid_stored_location_issue_id(entry_id)
    other_entry_issue_id = location_setup_failed_issue_id(
        "entry-other", "stale-location"
    )

    _create_test_repair(hass, DOMAIN, active_issue_id)
    _create_test_repair(hass, DOMAIN, stale_issue_id)
    _create_test_repair(
        hass,
        DOMAIN,
        stale_invalid_issue_id,
        is_persistent=False,
    )
    _create_test_repair(hass, DOMAIN, legacy_issue_id, is_persistent=False)
    _create_test_repair(hass, DOMAIN, other_entry_issue_id)
    _create_test_repair(hass, "other_domain", stale_issue_id)

    assert "location_repair_issue_ids" not in hass.data.get(DOMAIN, {})

    delete_stale_location_subentry_issues(
        hass,
        entry_id=entry_id,
        active_subentry_ids={"active-location"},
    )

    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, stale_issue_id) is None
    assert registry.async_get_issue(DOMAIN, stale_invalid_issue_id) is None
    assert registry.async_get_issue(DOMAIN, legacy_issue_id) is not None
    assert registry.async_get_issue(DOMAIN, active_issue_id) is not None
    assert registry.async_get_issue(DOMAIN, other_entry_issue_id) is not None
    assert registry.async_get_issue("other_domain", stale_issue_id) is not None


async def test_ha_remove_entry_clears_only_owned_location_repairs(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    ha_config_entry,
) -> None:
    """Removing a config entry should delete only its location Repairs."""
    clear_integration_modules()
    from custom_components.pollenlevels.const import DOMAIN
    from custom_components.pollenlevels.issue_helpers import (
        PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID,
        invalid_stored_location_issue_id,
        location_setup_failed_issue_id,
    )

    ha_config_entry.add_to_hass(hass)
    entry_id = ha_config_entry.entry_id
    setup_issue_id = location_setup_failed_issue_id(entry_id, "location-madrid")
    invalid_issue_id = invalid_stored_location_issue_id(entry_id, "location-madrid")
    legacy_issue_id = invalid_stored_location_issue_id(entry_id)
    other_entry_issue_id = location_setup_failed_issue_id(
        "entry-other", "location-madrid"
    )

    _create_test_repair(hass, DOMAIN, setup_issue_id)
    _create_test_repair(hass, DOMAIN, invalid_issue_id, is_persistent=False)
    _create_test_repair(hass, DOMAIN, legacy_issue_id, is_persistent=False)
    _create_test_repair(hass, DOMAIN, other_entry_issue_id)
    _create_test_repair(
        hass,
        DOMAIN,
        PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID,
    )
    hass.data.setdefault(DOMAIN, {})["setup_retry_failures"] = {
        entry_id: {"location-madrid"},
        "entry-other": {"other-location"},
    }

    await hass.config_entries.async_remove(entry_id)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, setup_issue_id) is None
    assert registry.async_get_issue(DOMAIN, invalid_issue_id) is None
    assert registry.async_get_issue(DOMAIN, legacy_issue_id) is None
    assert registry.async_get_issue(DOMAIN, other_entry_issue_id) is not None
    assert (
        registry.async_get_issue(
            DOMAIN,
            PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID,
        )
        is not None
    )
    assert hass.data[DOMAIN]["setup_retry_failures"] == {
        "entry-other": {"other-location"}
    }
