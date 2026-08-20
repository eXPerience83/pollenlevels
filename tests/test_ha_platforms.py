"""Home Assistant harness tests for platform entity setup."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

from aiointercept import aiointercept
from homeassistant.components.recorder import statistics
from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    entity_platform,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
    do_adhoc_statistics,
)

from custom_components.pollenlevels import (
    button as button_platform,
    sensor as sensor_platform,
)
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


def test_platform_parallel_update_limits() -> None:
    """Entity platforms should declare their intended concurrency limits."""
    assert sensor_platform.PARALLEL_UPDATES == 0
    assert button_platform.PARALLEL_UPDATES == 1


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


async def test_ha_current_day_pollen_sensors_restore_measurement_state_class(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """Current-day pollen values should preserve HACS statistics compatibility."""
    clear_integration_modules()
    entry = ha_config_entry
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

    registry = er.async_get(hass)
    entity_ids_by_unique_id = {
        entity.unique_id: entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        if entity.domain == "sensor" and entity.config_subentry_id == "location-madrid"
    }
    identity_id = f"{entry.entry_id}_location-madrid"

    for unique_id in (
        f"{identity_id}_type_grass",
        f"{identity_id}_plants_birch",
        f"{identity_id}_overall_pollen_risk_today",
    ):
        state = hass.states.get(entity_ids_by_unique_id[unique_id])
        assert state is not None
        assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT

    for unique_id in (
        f"{identity_id}_plants_in_season_today",
        f"{identity_id}_top_pollen_types_today",
        f"{identity_id}_region",
    ):
        state = hass.states.get(entity_ids_by_unique_id[unique_id])
        assert state is not None
        assert "state_class" not in state.attributes


async def test_ha_restored_state_class_reconciles_existing_statistics(
    recorder_mock,
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """Restored measurement metadata should reuse existing statistics identity."""
    clear_integration_modules()
    entry = ha_config_entry
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

    registry = er.async_get(hass)
    identity_id = f"{entry.entry_id}_location-madrid"
    unique_id = f"{identity_id}_type_grass"
    registry_entry = next(
        entity
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        if entity.unique_id == unique_id
    )
    entity_id = registry_entry.entity_id
    restored_state = hass.states.get(entity_id)
    assert restored_state is not None
    assert restored_state.attributes["state_class"] == SensorStateClass.MEASUREMENT

    await async_wait_recording_done(hass)
    now = dt_util.utcnow()
    statistics_start = now.replace(
        minute=now.minute - now.minute % 5,
        second=0,
        microsecond=0,
    )
    do_adhoc_statistics(hass, start=statistics_start)
    await async_wait_recording_done(hass)

    metadata_before = statistics.get_metadata(hass, statistic_ids={entity_id})
    assert entity_id in metadata_before
    metadata_id, metadata = metadata_before[entity_id]
    assert metadata["statistic_id"] == entity_id
    assert metadata["has_mean"] is True
    assert metadata["has_sum"] is False
    assert metadata["unit_of_measurement"] is None

    state_31_attributes = dict(restored_state.attributes)
    state_31_attributes.pop("state_class")
    hass.states.async_set(entity_id, restored_state.state, state_31_attributes)
    await hass.async_add_executor_job(statistics.update_statistics_issues, hass)
    await hass.async_block_till_done()

    issue_id = f"state_class_removed_{entity_id}"
    issue_registry = ir.async_get(hass)
    assert issue_registry.async_get_issue("sensor", issue_id) is not None

    hass.states.async_set(entity_id, restored_state.state, restored_state.attributes)
    await hass.async_add_executor_job(statistics.update_statistics_issues, hass)
    await hass.async_block_till_done()

    assert issue_registry.async_get_issue("sensor", issue_id) is None
    metadata_after = statistics.get_metadata(hass, statistic_ids={entity_id})
    assert metadata_after == metadata_before
    assert metadata_after[entity_id][0] == metadata_id

    current_state = hass.states.get(entity_id)
    assert current_state is not None
    assert current_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
    assert current_state.attributes["state_class"] == SensorStateClass.MEASUREMENT


async def test_ha_expired_snapshot_notifies_entities_and_releases_summary_cache(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_two_location_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """Snapshot expiry should make one location unavailable and release summaries."""
    clear_integration_modules()
    entry = ha_two_location_config_entry
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

    madrid = entry.runtime_data.locations["location-madrid"].coordinator
    barcelona = entry.runtime_data.locations["location-barcelona"].coordinator
    old_madrid_data = madrid.data
    old_barcelona_data = barcelona.data
    summary = next(
        entity
        for platform in entity_platform.async_get_platforms(hass, DOMAIN)
        for entity in platform.entities.values()
        if type(entity).__name__ == "PlantsInSeasonTodaySensor"
        and entity.coordinator is madrid
    )
    assert summary.native_value is not None
    assert summary._summary_data_ref is old_madrid_data

    expires_at = madrid.last_updated + madrid._stale_data_ttl()
    monkeypatch.setattr(madrid, "_utcnow", lambda: expires_at)
    madrid._cache_expiry_handle.cancel()
    madrid._cache_expiry_handle = None
    madrid._handle_cache_expiry(madrid.last_updated)
    await hass.async_block_till_done()

    assert madrid.data == {}
    assert madrid.last_updated is None
    assert madrid.using_stale_data is False
    assert madrid.last_payload_valid is True
    assert madrid.last_update_success is False
    assert hass.states.get(summary.entity_id).state == STATE_UNAVAILABLE
    assert summary._summary_data_ref is madrid.data
    assert summary._summary_data_ref is not old_madrid_data
    assert barcelona.data is old_barcelona_data
    assert barcelona.last_update_success is True

    recovery_time = expires_at + timedelta(minutes=1)
    monkeypatch.setattr(madrid, "_utcnow", lambda: recovery_time)

    async def _valid_response(**_kwargs: Any) -> dict[str, Any]:
        return google_pollen_5_day_payload

    monkeypatch.setattr(madrid._client, "async_fetch_pollen_data", _valid_response)
    await madrid.async_refresh()
    await hass.async_block_till_done()

    assert madrid.data
    assert madrid.last_updated == recovery_time
    assert madrid.using_stale_data is False
    assert madrid.last_update_success is True
    assert hass.states.get(summary.entity_id).state != STATE_UNAVAILABLE

    existing_failure = UpdateFailed("existing transport failure")
    barcelona.async_set_update_error(existing_failure)
    assert barcelona.last_update_success is False
    assert barcelona.last_exception is existing_failure

    barcelona_expires_at = barcelona.last_updated + barcelona._stale_data_ttl()
    monkeypatch.setattr(barcelona, "_utcnow", lambda: barcelona_expires_at)
    barcelona._cache_expiry_handle.cancel()
    barcelona._cache_expiry_handle = None
    barcelona._handle_cache_expiry(barcelona.last_updated)
    await hass.async_block_till_done()

    assert barcelona.data == {}
    assert barcelona.last_updated is None
    assert barcelona.last_payload_valid is True
    assert barcelona.last_exception is existing_failure

    madrid_handle = madrid._cache_expiry_handle
    assert madrid_handle is not None
    assert barcelona._cache_expiry_handle is None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert madrid_handle.cancelled()


async def test_ha_button_press_refreshes_only_location_coordinator(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_two_location_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """button.press should refresh only the selected location coordinator."""
    clear_integration_modules()
    entry = ha_two_location_config_entry
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

        registry = er.async_get(hass)
        button_entry = next(
            entity
            for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
            if entity.domain == "button"
            and entity.config_subentry_id == "location-madrid"
        )
        madrid_refresh = AsyncMock()
        barcelona_refresh = AsyncMock()
        monkeypatch.setattr(
            entry.runtime_data.locations["location-madrid"].coordinator,
            "async_request_refresh",
            madrid_refresh,
        )
        monkeypatch.setattr(
            entry.runtime_data.locations["location-barcelona"].coordinator,
            "async_request_refresh",
            barcelona_refresh,
        )

        await hass.services.async_call(
            "button",
            "press",
            {ATTR_ENTITY_ID: button_entry.entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()

    madrid_refresh.assert_awaited_once()
    barcelona_refresh.assert_not_awaited()


async def test_ha_same_parent_button_presses_are_serialized(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_two_location_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """Update buttons under one parent should not refresh concurrently."""
    clear_integration_modules()
    entry = ha_two_location_config_entry
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

        registry = er.async_get(hass)
        button_entries = {
            entity.config_subentry_id: entity
            for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
            if entity.domain == "button" and entity.config_subentry_id is not None
        }

        active = 0
        max_active = 0
        calls = {"location-madrid": 0, "location-barcelona": 0}

        def _tracked_refresh(subentry_id: str):
            async def _refresh() -> None:
                nonlocal active, max_active
                calls[subentry_id] += 1
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0)
                active -= 1

            return _refresh

        for subentry_id in calls:
            monkeypatch.setattr(
                entry.runtime_data.locations[subentry_id].coordinator,
                "async_request_refresh",
                _tracked_refresh(subentry_id),
            )

        await asyncio.gather(
            *(
                hass.services.async_call(
                    "button",
                    "press",
                    {ATTR_ENTITY_ID: button_entries[subentry_id].entity_id},
                    blocking=True,
                )
                for subentry_id in calls
            )
        )
        await hass.async_block_till_done()

    assert calls == {"location-madrid": 1, "location-barcelona": 1}
    assert max_active == 1


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
