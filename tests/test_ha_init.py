"""Home Assistant harness tests for config entry setup."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from aiointercept import CallbackResult, aiointercept
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.pollenlevels.const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    DOMAIN,
)
from custom_components.pollenlevels.util import api_key_unique_id
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import (
    POLLEN_API_URL_RE,
    assert_fixed_forecast_days,
    async_setup_config_entry,
    location_subentry_data,
    mock_pollen_api,
)


def _parent_entry(
    *,
    entry_id: str,
    api_key: str,
    locations: list[tuple[str, str, float, float]],
) -> MockConfigEntry:
    """Build a parent entry with synthetic location subentries."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        title=f"Pollen Levels {entry_id}",
        unique_id=api_key_unique_id(api_key),
        data={CONF_API_KEY: api_key},
        subentries_data=[
            location_subentry_data(
                subentry_id=subentry_id,
                title=title,
                latitude=latitude,
                longitude=longitude,
            )
            for subentry_id, title, latitude, longitude in locations
        ],
        version=6,
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


async def test_ha_invalid_location_repair_stores_redacted_placeholders(
    hass: HomeAssistant,
) -> None:
    """The real issue registry should store only redacted dynamic placeholders."""
    clear_integration_modules()
    from custom_components.pollenlevels.issue_helpers import (
        create_entry_invalid_stored_location_issue,
        invalid_stored_location_issue_id,
    )

    synthetic_key = "SYNTHETIC-HA-REPAIR-KEY"
    latitude = 12.345678
    longitude = -45.678912
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry-private-repair",
        title=f"Safe Home {synthetic_key} {latitude} {longitude}",
        data={
            CONF_API_KEY: synthetic_key,
            CONF_LATITUDE: latitude,
            CONF_LONGITUDE: longitude,
        },
        version=6,
    )

    create_entry_invalid_stored_location_issue(hass, entry)

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, invalid_stored_location_issue_id(entry.entry_id)
    )
    assert issue is not None
    assert issue.translation_placeholders == {
        "entry_title": "Safe Home *** *** ***",
        "location_title": "Safe Home *** *** ***",
    }
    assert issue.translation_key == "invalid_stored_location"
    assert issue.severity is ir.IssueSeverity.ERROR
    assert issue.is_persistent is False
    assert issue.is_fixable is False


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
        assert (
            ha_config_entry.runtime_data.locations[
                "location-madrid"
            ].coordinator.config_entry
            is ha_config_entry
        )
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
        assert (
            ha_config_entry.runtime_data.locations[
                "location-madrid"
            ].coordinator.config_entry
            is ha_config_entry
        )


async def test_ha_external_setup_cancellation_sets_setup_error_and_shuts_down_coordinators(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real external cancellation should fail setup and clean coordinators."""
    clear_integration_modules()
    assert await async_setup_component(hass, DOMAIN, {})

    from custom_components.pollenlevels.coordinator import (
        PollenDataUpdateCoordinator,
    )

    entry = _parent_entry(
        entry_id="cancelled-parent",
        api_key="synthetic-cancelled-key",
        locations=[
            ("first-location", "First", 1.0, 2.0),
            ("second-location", "Second", 3.0, 4.0),
            ("third-location", "Third", 5.0, 6.0),
        ],
    )
    entry.add_to_hass(hass)
    second_entered = asyncio.Event()
    coordinators: list[PollenDataUpdateCoordinator] = []
    shutdown_coordinators: list[PollenDataUpdateCoordinator] = []
    update_order: list[str] = []
    original_init = PollenDataUpdateCoordinator.__init__
    original_shutdown = PollenDataUpdateCoordinator.async_shutdown

    def _capture_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        coordinators.append(self)

    async def _controlled_update(self):
        update_order.append(self.subentry_id)
        if self.subentry_id == "second-location":
            second_entered.set()
            await asyncio.Event().wait()
        return {"date": {"source": "meta", "value": "2026-08-15"}}

    async def _capture_shutdown(self):
        shutdown_coordinators.append(self)
        await original_shutdown(self)

    monkeypatch.setattr(PollenDataUpdateCoordinator, "__init__", _capture_init)
    monkeypatch.setattr(
        PollenDataUpdateCoordinator, "_async_update_data", _controlled_update
    )
    monkeypatch.setattr(
        PollenDataUpdateCoordinator, "async_shutdown", _capture_shutdown
    )

    setup_task = asyncio.create_task(hass.config_entries.async_setup(entry.entry_id))
    await second_entered.wait()
    setup_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await setup_task
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert getattr(entry, "runtime_data", None) is None
    assert update_order == ["first-location", "second-location"]
    assert len(coordinators) == 2
    assert set(shutdown_coordinators) == set(coordinators)
    assert not er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)


async def test_ha_slow_parent_setup_does_not_block_independent_parent(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blocked parent should not prevent an independent parent from loading."""
    clear_integration_modules()
    assert await async_setup_component(hass, DOMAIN, {})

    from custom_components.pollenlevels.coordinator import (
        PollenDataUpdateCoordinator,
    )

    blocked_entry = _parent_entry(
        entry_id="blocked-parent",
        api_key="synthetic-blocked-key",
        locations=[("blocked-location", "Blocked", 1.0, 2.0)],
    )
    healthy_entry = _parent_entry(
        entry_id="healthy-parent",
        api_key="synthetic-healthy-key",
        locations=[("healthy-location", "Healthy", 3.0, 4.0)],
    )
    blocked_entry.add_to_hass(hass)
    healthy_entry.add_to_hass(hass)
    blocked_entered = asyncio.Event()

    async def _controlled_update(self):
        if self.config_entry is blocked_entry:
            blocked_entered.set()
            await asyncio.Event().wait()
        return {"date": {"source": "meta", "value": "2026-08-15"}}

    monkeypatch.setattr(
        PollenDataUpdateCoordinator, "_async_update_data", _controlled_update
    )

    blocked_task = asyncio.create_task(
        hass.config_entries.async_setup(blocked_entry.entry_id)
    )
    await blocked_entered.wait()

    assert await hass.config_entries.async_setup(healthy_entry.entry_id)
    await hass.async_block_till_done()
    assert healthy_entry.state is ConfigEntryState.LOADED
    assert set(healthy_entry.runtime_data.locations) == {"healthy-location"}

    blocked_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await blocked_task
    await hass.async_block_till_done()

    assert blocked_entry.state is ConfigEntryState.SETUP_ERROR
    assert getattr(blocked_entry, "runtime_data", None) is None
    assert healthy_entry.state is ConfigEntryState.LOADED
    assert set(healthy_entry.runtime_data.locations) == {"healthy-location"}


async def test_ha_transport_threshold_enters_setup_retry_and_recovers(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exhausted transport failures should defer setup to HA-managed retry."""
    clear_integration_modules()
    assert await async_setup_component(hass, DOMAIN, {})

    from custom_components.pollenlevels.client import PollenTransportError
    from custom_components.pollenlevels.coordinator import (
        PollenDataUpdateCoordinator,
    )

    entry = _parent_entry(
        entry_id="retry-parent",
        api_key="synthetic-retry-key",
        locations=[
            ("first-location", "First", 1.0, 2.0),
            ("second-location", "Second", 3.0, 4.0),
        ],
    )
    entry.add_to_hass(hass)
    recovered = False
    update_order: list[str] = []

    async def _controlled_update(self):
        update_order.append(self.subentry_id)
        if not recovered:
            raise PollenTransportError("transport unavailable")
        return {"date": {"source": "meta", "value": "2026-08-15"}}

    monkeypatch.setattr(
        PollenDataUpdateCoordinator, "_async_update_data", _controlled_update
    )

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert getattr(entry, "runtime_data", None) is None
    assert update_order == ["first-location", "second-location"]
    assert not er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)

    recovered = True
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done(wait_background_tasks=True)

    assert entry.state is ConfigEntryState.LOADED
    assert set(entry.runtime_data.locations) == {
        "first-location",
        "second-location",
    }
    assert update_order == [
        "first-location",
        "second-location",
        "first-location",
        "second-location",
    ]


async def test_ha_expired_api_key_reload_preserves_registry_identity(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """A loaded entry should preserve registry identity through expired-key reauth."""
    clear_integration_modules()
    ha_config_entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, ha_config_entry)

    assert ha_config_entry.state is ConfigEntryState.LOADED
    assert set(ha_config_entry.runtime_data.locations) == {"location-madrid"}

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    def _registry_identity_snapshot() -> dict[str, Any]:
        entity_entries = [
            entity
            for entity in er.async_entries_for_config_entry(
                entity_registry, ha_config_entry.entry_id
            )
            if entity.platform == DOMAIN
        ]
        device_entries = dr.async_entries_for_config_entry(
            device_registry, ha_config_entry.entry_id
        )
        return {
            "entities": {
                (
                    entity.entity_id,
                    entity.unique_id,
                    entity.device_id,
                    getattr(entity, "config_subentry_id", None),
                )
                for entity in entity_entries
            },
            "devices": {
                device.id: {
                    "identifiers": frozenset(device.identifiers),
                    "config_entries_subentries": {
                        config_entry_id: frozenset(subentry_ids)
                        for config_entry_id, subentry_ids in getattr(
                            device, "config_entries_subentries", {}
                        ).items()
                    },
                }
                for device in device_entries
            },
        }

    identities_before = _registry_identity_snapshot()
    assert identities_before["entities"]
    assert identities_before["devices"]

    async with aiointercept(mock_external_urls=True) as mocked:
        mocked.get(
            POLLEN_API_URL_RE,
            callback=lambda *_args, **_kwargs: CallbackResult(
                status=400,
                payload={
                    "error": {"message": "API key expired. Please renew the API key."}
                },
            ),
            repeat=True,
        )
        assert not await hass.config_entries.async_reload(ha_config_entry.entry_id)
        await hass.async_block_till_done()

    assert ha_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    flow = flows[0]
    assert flow["context"]["source"] == SOURCE_REAUTH
    assert flow["context"]["entry_id"] == ha_config_entry.entry_id
    assert flow["step_id"] == "reauth_confirm"

    recovery_params: list[dict[str, Any]] = []
    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload, recovery_params)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            {CONF_API_KEY: "replacement-key"},
        )
        await hass.async_block_till_done()

    assert {params["key"] for params in recovery_params} == {"replacement-key"}
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert ha_config_entry.data[CONF_API_KEY] == "replacement-key"
    assert ha_config_entry.state is ConfigEntryState.LOADED
    assert set(ha_config_entry.runtime_data.locations) == {"location-madrid"}
    assert _registry_identity_snapshot() == identities_before


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
