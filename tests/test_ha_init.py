"""Home Assistant harness tests for config entry setup."""

from __future__ import annotations

import asyncio
import json
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
    async_migrate_config_entry,
    async_setup_config_entry,
    device_ownership,
    legacy_config_entry,
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
                    "ownership": device_ownership(device),
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


@pytest.mark.parametrize("valid_coordinates", [False, True], ids=["invalid", "valid"])
async def test_ha_subentry_removed_during_setup_keeps_lifecycle_guards(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    valid_coordinates: bool,
) -> None:
    """Removal during a fetch must preserve Repair and platform stale guards."""
    clear_integration_modules()
    from custom_components.pollenlevels import _location_issue_subentry_id
    from custom_components.pollenlevels.client import GooglePollenApiClient
    from custom_components.pollenlevels.diagnostics import (
        async_get_config_entry_diagnostics,
    )
    from custom_components.pollenlevels.issue_helpers import (
        invalid_stored_location_issue_id,
    )
    from custom_components.pollenlevels.util import device_subentry_ids

    removed_id = "location-removed"
    removed_data = location_subentry_data(
        subentry_id=removed_id, title="Removed", latitude=3.0, longitude=4.0
    )
    if not valid_coordinates:
        removed_data["data"][CONF_LATITUDE] = None
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="setup-removal-parent",
        title="Pollen Levels",
        data={CONF_API_KEY: "synthetic-setup-removal-key"},
        subentries_data=[
            location_subentry_data(
                subentry_id="location-kept", title="Kept", latitude=1.0, longitude=2.0
            ),
            removed_data,
        ],
        version=6,
    )
    entry.add_to_hass(hass)
    fetch_started = asyncio.Event()
    release_fetch = asyncio.Event()
    original_fetch = GooglePollenApiClient.async_fetch_pollen_data

    async def _delayed_fetch(client, **kwargs):
        fetch_started.set()
        await release_fetch.wait()
        return await original_fetch(client, **kwargs)

    monkeypatch.setattr(
        GooglePollenApiClient, "async_fetch_pollen_data", _delayed_fetch
    )
    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        setup_task = asyncio.create_task(
            hass.config_entries.async_setup(entry.entry_id)
        )
        try:
            await asyncio.wait_for(fetch_started.wait(), timeout=5)
            assert hass.config_entries.async_remove_subentry(entry, removed_id)
        finally:
            release_fetch.set()
            setup_result = await setup_task
        assert setup_result
        await hass.async_block_till_done()

        assert removed_id not in entry.subentries
        assert _location_issue_subentry_id(entry, removed_id) is None
        if valid_coordinates:
            assert removed_id in entry.runtime_data.locations
        else:
            assert removed_id in entry.runtime_data.failed_locations
            issue_id = invalid_stored_location_issue_id(entry.entry_id)
            assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

        entity_registry = er.async_get(hass)
        entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        assert entities
        assert {entity.domain for entity in entities} == {"sensor", "button"}
        assert all(entity.config_subentry_id == "location-kept" for entity in entities)
        entity_identity = {
            entity.entity_id: (entity.unique_id, entity.config_subentry_id)
            for entity in entities
        }
        assert any(
            entity.unique_id == "setup-removal-parent_location-kept_update_now"
            for entity in entities
        )
        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        assert devices
        assert all(
            device_subentry_ids(device, entry.entry_id) == {"location-kept"}
            for device in devices
        )
        device_identity = {device.id: device.identifiers for device in devices}

        diagnostics = await async_get_config_entry_diagnostics(hass, entry)
        assert set(diagnostics["locations"]) == {"location-kept"}
        assert removed_id not in diagnostics["failed_locations"]
        assert diagnostics["runtime_summary"]["stale_location_ids"] == (
            [removed_id] if valid_coordinates else []
        )

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert set(entry.subentries) == {"location-kept"}
        assert set(entry.runtime_data.locations) == {"location-kept"}
        assert {
            entity.entity_id: (entity.unique_id, entity.config_subentry_id)
            for entity in er.async_entries_for_config_entry(
                entity_registry, entry.entry_id
            )
        } == entity_identity
        assert {
            device.id: device.identifiers
            for device in dr.async_entries_for_config_entry(
                device_registry, entry.entry_id
            )
        } == device_identity


@pytest.mark.parametrize(
    "scenario",
    ["new_single", "new_multiple", "migrated_single", "migrated_multiple", "mixed"],
)
async def test_ha_location_identity_survives_migration_reload_and_restart(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    google_pollen_5_day_payload: dict[str, Any],
    scenario: str,
) -> None:
    """Persisted entity/device records must stay exact across location lifecycle."""
    clear_integration_modules()
    from custom_components.pollenlevels.const import CONF_LEGACY_ENTRY_ID

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    historical_entities: dict[str, tuple[str, str, str]] = {}
    historical_devices: dict[str, set[tuple[str, str]]] = {}
    expected_identities: set[str] = set()
    synthetic_key = "synthetic-identity-lifecycle-key"

    def _add_legacy_location(entry_id: str, latitude: float, longitude: float):
        entry = legacy_config_entry(
            entry_id=entry_id,
            title="Home" if entry_id == "legacy-home" else "Office",
            api_key=synthetic_key,
            latitude=latitude,
            longitude=longitude,
        )
        entry.add_to_hass(hass)
        expected_identities.add(entry_id)
        for domain, suffix, group in (
            ("sensor", "type_grass", "type"),
            ("button", "update_now", "meta"),
        ):
            device = device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"{entry_id}_{group}")},
            )
            entity = entity_registry.async_get_or_create(
                domain,
                DOMAIN,
                f"{entry_id}_{suffix}",
                config_entry=entry,
                device_id=device.id,
                suggested_object_id=f"{entry_id}_preserved_{suffix}",
            )
            historical_entities[entity.entity_id] = (
                entity.id,
                entity.unique_id,
                device.id,
            )
            historical_devices[device.id] = set(device.identifiers)
        return entry

    if scenario in {"new_single", "new_multiple", "mixed"}:
        locations = [("location-home", "Home", 1.0, 2.0)]
        expected_identities.add("audit-parent_location-home")
        if scenario == "new_multiple":
            locations.append(("location-office", "Office", 3.0, 4.0))
            expected_identities.add("audit-parent_location-office")
        parent = _parent_entry(
            entry_id="audit-parent", api_key=synthetic_key, locations=locations
        )
        parent.add_to_hass(hass)
        if scenario == "mixed":
            legacy = _add_legacy_location("legacy-office", 3.0, 4.0)
            assert await async_migrate_config_entry(hass, legacy)
    else:
        parent = _add_legacy_location("legacy-home", 1.0, 2.0)
        if scenario == "migrated_multiple":
            _add_legacy_location("legacy-office", 3.0, 4.0)
        assert await async_migrate_config_entry(hass, parent)

    # Exact suffixes of all entities created from this supported API fixture.
    expected_groups = {
        "type": {
            "type_grass",
            "type_tree",
            "type_weed",
            "overall_pollen_risk_today",
            "top_pollen_types_today",
        },
        "plant": {
            "plants_alder",
            "plants_ash",
            "plants_birch",
            "plants_cottonwood",
            "plants_graminales",
            "plants_hazel",
            "plants_mugwort",
            "plants_oak",
            "plants_olive",
            "plants_pine",
            "plants_ragweed",
            "plants_in_season_today",
        },
        "meta": {"region", "date", "last_updated", "update_now"},
    }

    def _assert_identity_and_snapshot(entry):
        entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        devices_by_id = {device.id: device for device in devices}
        actual_entities = {entity.unique_id: entity for entity in entities}
        expected_entities: dict[str, tuple[str, str, str]] = {}
        identities: set[str] = set()
        for subentry in entry.subentries.values():
            legacy_identity = subentry.data.get(CONF_LEGACY_ENTRY_ID)
            identity = (
                legacy_identity
                if legacy_identity is not None
                else f"{entry.entry_id}_{subentry.subentry_id}"
            )
            identities.add(identity)
            coordinator = entry.runtime_data.locations[subentry.subentry_id].coordinator
            assert coordinator.config_entry is entry
            assert coordinator.subentry_id == subentry.subentry_id
            assert coordinator.entity_identity_id == identity
            assert coordinator.device_identity_id == identity
            for group, suffixes in expected_groups.items():
                group_device_ids: set[str] = set()
                for suffix in suffixes:
                    unique_id = f"{identity}_{suffix}"
                    expected_entities[unique_id] = (
                        "button" if suffix == "update_now" else "sensor",
                        subentry.subentry_id,
                        f"{identity}_{group}",
                    )
                    entity = actual_entities[unique_id]
                    assert entity.config_entry_id == entry.entry_id
                    assert entity.config_subentry_id == subentry.subentry_id
                    device = devices_by_id[entity.device_id]
                    assert device.identifiers == {(DOMAIN, f"{identity}_{group}")}
                    assert device_ownership(device) == (
                        {entry.entry_id},
                        {entry.entry_id: {subentry.subentry_id}},
                    )
                    group_device_ids.add(device.id)
                assert len(group_device_ids) == 1
        assert identities == expected_identities
        assert {
            unique_id: (
                entity.domain,
                entity.config_subentry_id,
                next(iter(devices_by_id[entity.device_id].identifiers))[1],
            )
            for unique_id, entity in actual_entities.items()
        } == expected_entities
        assert {
            identifier for device in devices for identifier in device.identifiers
        } == {
            (DOMAIN, f"{identity}_{group}")
            for identity in expected_identities
            for group in expected_groups
        }
        for entity_id, (
            registry_id,
            unique_id,
            device_id,
        ) in historical_entities.items():
            entity = entity_registry.async_get(entity_id)
            assert entity is not None
            assert (entity.id, entity.unique_id, entity.device_id) == (
                registry_id,
                unique_id,
                device_id,
            )
        for device_id, identifiers in historical_devices.items():
            assert device_registry.async_get(device_id).identifiers == identifiers
        return (
            {
                entity.entity_id: (
                    entity.id,
                    entity.entity_id,
                    entity.unique_id,
                    entity.platform,
                    entity.config_entry_id,
                    entity.config_subentry_id,
                    entity.device_id,
                )
                for entity in entities
            },
            {
                device.id: (
                    device.id,
                    frozenset(device.identifiers),
                    device_ownership(device),
                )
                for device in devices
            },
        )

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, parent)
        initial_snapshot = _assert_identity_and_snapshot(parent)

        assert await hass.config_entries.async_unload(parent.entry_id)
        await hass.async_block_till_done()
        assert not hasattr(parent, "runtime_data")
        await async_setup_config_entry(hass, parent)
        assert _assert_identity_and_snapshot(parent) == initial_snapshot

        assert await hass.config_entries.async_reload(parent.entry_id)
        await hass.async_block_till_done()
        assert _assert_identity_and_snapshot(parent) == initial_snapshot

        assert await hass.config_entries.async_unload(parent.entry_id)
        await hass.async_block_till_done()
        # Rehydrate a fresh entry from persisted values while retaining its registries.
        persisted = json.loads(
            json.dumps(
                {
                    "domain": parent.domain,
                    "entry_id": parent.entry_id,
                    "title": parent.title,
                    "data": dict(parent.data),
                    "options": dict(parent.options),
                    "unique_id": parent.unique_id,
                    "version": parent.version,
                    "minor_version": parent.minor_version,
                    "subentries_data": [
                        subentry.as_dict() for subentry in parent.subentries.values()
                    ],
                }
            )
        )
        restored = MockConfigEntry(**persisted)
        assert not hasattr(restored, "runtime_data")
        del hass.config_entries._entries[parent.entry_id]
        restored.add_to_hass(hass)
        await async_setup_config_entry(hass, restored)
        assert _assert_identity_and_snapshot(restored) == initial_snapshot
