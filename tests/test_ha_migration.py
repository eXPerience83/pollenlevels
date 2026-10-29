"""Home Assistant harness tests for legacy entry migration."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from aiointercept import CallbackResult, aiointercept
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)

from custom_components.pollenlevels.const import (
    CONF_API_KEY,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LEGACY_ENTRY_ID,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    SUBENTRY_TYPE_LOCATION,
)
from custom_components.pollenlevels.issue_helpers import (
    invalid_stored_location_issue_id,
)
from custom_components.pollenlevels.util import api_key_unique_id
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import (
    POLLEN_API_URL_RE,
    async_migrate_config_entry,
    device_ownership,
    legacy_config_entry,
    location_subentry_data,
)


def _subentries_by_legacy_entry(entry) -> dict[str, Any]:
    """Return migrated location subentries keyed by legacy entry id."""
    return {
        legacy_entry_id: subentry
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_LOCATION
        if isinstance(
            legacy_entry_id := subentry.data.get(CONF_LEGACY_ENTRY_ID),
            str,
        )
    }


def _assert_location_subentry(
    subentry: Any,
    *,
    title: str,
    latitude: float,
    longitude: float,
    legacy_entry_id: str,
) -> None:
    """Assert a migrated location subentry has the expected stored payload."""
    assert subentry.subentry_type == SUBENTRY_TYPE_LOCATION
    assert subentry.title == title
    assert subentry.unique_id == f"{latitude:.4f}_{longitude:.4f}"
    assert dict(subentry.data) == {
        CONF_LATITUDE: latitude,
        CONF_LONGITUDE: longitude,
        CONF_LEGACY_ENTRY_ID: legacy_entry_id,
    }


async def test_ha_migration_single_legacy_entry_creates_location_subentry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """A legacy entry should become one parent entry with one location subentry."""
    clear_integration_modules()
    from custom_components.pollenlevels import TARGET_ENTRY_VERSION

    entry = legacy_config_entry(
        entry_id="legacy-home",
        title="Legacy Home",
        api_key="single-key",
        latitude=12.34567,
        longitude=-98.76543,
        data={CONF_UPDATE_INTERVAL: 12, CONF_LANGUAGE_CODE: "en"},
        unique_id="12.3457_-98.7654",
    )
    entry.add_to_hass(hass)

    assert await async_migrate_config_entry(hass, entry)

    assert entry.version == TARGET_ENTRY_VERSION
    assert entry.data == {CONF_API_KEY: "single-key"}
    assert entry.options == {
        CONF_UPDATE_INTERVAL: 12,
        CONF_LANGUAGE_CODE: "en",
    }
    assert entry.unique_id == api_key_unique_id("single-key")
    assert len(entry.subentries) == 1
    _assert_location_subentry(
        next(iter(entry.subentries.values())),
        title="Legacy Home",
        latitude=12.34567,
        longitude=-98.76543,
        legacy_entry_id="legacy-home",
    )


async def test_ha_migration_same_api_key_entries_group_under_one_parent(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Legacy entries sharing one API key should become one parent with locations."""
    clear_integration_modules()
    from custom_components.pollenlevels import TARGET_ENTRY_VERSION

    parent = legacy_config_entry(
        entry_id="legacy-home",
        title="Home",
        api_key="shared-key",
        latitude=1.0,
        longitude=2.0,
        data={CONF_UPDATE_INTERVAL: 12},
        unique_id="1.0000_2.0000",
    )
    duplicate = legacy_config_entry(
        entry_id="legacy-office",
        title="Office",
        api_key="shared-key",
        latitude=3.0,
        longitude=4.0,
        data={CONF_LANGUAGE_CODE: "en"},
        unique_id="3.0000_4.0000",
    )
    parent.add_to_hass(hass)
    duplicate.add_to_hass(hass)

    assert await async_migrate_config_entry(hass, parent)

    assert parent.version == TARGET_ENTRY_VERSION
    assert parent.data == {CONF_API_KEY: "shared-key"}
    assert parent.options == {
        CONF_UPDATE_INTERVAL: 12,
        CONF_LANGUAGE_CODE: "en",
    }
    assert parent.unique_id == api_key_unique_id("shared-key")
    assert hass.config_entries.async_get_entry("legacy-office") is None

    subentries = _subentries_by_legacy_entry(parent)
    assert set(subentries) == {"legacy-home", "legacy-office"}
    _assert_location_subentry(
        subentries["legacy-home"],
        title="Home",
        latitude=1.0,
        longitude=2.0,
        legacy_entry_id="legacy-home",
    )
    _assert_location_subentry(
        subentries["legacy-office"],
        title="Office",
        latitude=3.0,
        longitude=4.0,
        legacy_entry_id="legacy-office",
    )


async def test_ha_migration_legacy_entry_merges_into_existing_clean_v3_parent(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """A residual legacy entry should merge into an existing clean parent."""
    clear_integration_modules()
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.pollenlevels import TARGET_ENTRY_VERSION

    clean_parent = MockConfigEntry(
        domain=DOMAIN,
        entry_id="clean-parent",
        title="Pollen Levels",
        data={CONF_API_KEY: "shared-key"},
        options={CONF_LANGUAGE_CODE: "en"},
        version=TARGET_ENTRY_VERSION,
        unique_id=api_key_unique_id("shared-key"),
        subentries_data=[
            location_subentry_data(
                subentry_id="existing-location",
                title="Existing",
                latitude=10.0,
                longitude=20.0,
            )
        ],
    )
    legacy = legacy_config_entry(
        entry_id="legacy-office",
        title="Office",
        api_key="shared-key",
        latitude=3.0,
        longitude=4.0,
        options={CONF_UPDATE_INTERVAL: 8},
        unique_id="3.0000_4.0000",
    )
    legacy.add_to_hass(hass)
    clean_parent.add_to_hass(hass)

    assert await async_migrate_config_entry(hass, legacy)

    assert clean_parent.version == TARGET_ENTRY_VERSION
    assert clean_parent.data == {CONF_API_KEY: "shared-key"}
    assert clean_parent.unique_id == api_key_unique_id("shared-key")
    assert clean_parent.options == {
        CONF_LANGUAGE_CODE: "en",
        CONF_UPDATE_INTERVAL: 8,
    }
    assert "existing-location" in clean_parent.subentries
    assert clean_parent.subentries["existing-location"].unique_id == "10.0000_20.0000"
    subentries = _subentries_by_legacy_entry(clean_parent)
    _assert_location_subentry(
        subentries["legacy-office"],
        title="Office",
        latitude=3.0,
        longitude=4.0,
        legacy_entry_id="legacy-office",
    )
    assert hass.config_entries.async_get_entry("legacy-office") is None


async def test_ha_migration_different_api_keys_stay_separate(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Legacy entries with different API keys should migrate independently."""
    clear_integration_modules()

    first = legacy_config_entry(
        entry_id="legacy-home",
        title="Home",
        api_key="key-one",
        latitude=1.0,
        longitude=2.0,
    )
    second = legacy_config_entry(
        entry_id="legacy-office",
        title="Office",
        api_key="key-two",
        latitude=3.0,
        longitude=4.0,
    )
    first.add_to_hass(hass)
    second.add_to_hass(hass)

    assert await async_migrate_config_entry(hass, first)
    assert await async_migrate_config_entry(hass, second)

    assert hass.config_entries.async_get_entry("legacy-home") is first
    assert hass.config_entries.async_get_entry("legacy-office") is second
    assert first.data == {CONF_API_KEY: "key-one"}
    assert second.data == {CONF_API_KEY: "key-two"}
    assert first.unique_id == api_key_unique_id("key-one")
    assert second.unique_id == api_key_unique_id("key-two")
    assert set(_subentries_by_legacy_entry(first)) == {"legacy-home"}
    assert set(_subentries_by_legacy_entry(second)) == {"legacy-office"}


async def test_ha_migration_preserves_version_newer_than_target(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Migration should clean legacy storage without downgrading newer entries."""
    clear_integration_modules()
    from custom_components.pollenlevels import TARGET_ENTRY_VERSION

    entry = legacy_config_entry(
        entry_id="newer-entry",
        title="Newer Entry",
        api_key="newer-key",
        latitude=1.0,
        longitude=2.0,
        data={"http_referer": "https://legacy.example.com"},
        options={"http_referer": "https://legacy.example.com"},
        version=TARGET_ENTRY_VERSION + 1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_config_entry(hass, entry)

    assert "http_referer" not in entry.data
    assert "http_referer" not in entry.options
    assert entry.version == TARGET_ENTRY_VERSION + 1
    assert entry.data == {CONF_API_KEY: "newer-key"}
    assert set(_subentries_by_legacy_entry(entry)) == {"newer-entry"}


async def test_ha_migration_attaches_entity_and_device_registries_to_subentry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Legacy registry links should move to the migrated location subentry."""
    clear_integration_modules()
    entry = legacy_config_entry(
        entry_id="legacy-home",
        title="Home",
        api_key="registry-key",
        latitude=1.0,
        longitude=2.0,
    )
    entry.add_to_hass(hass)
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "legacy-home-grass",
        suggested_object_id="legacy_home_grass",
        config_entry=entry,
    )
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "legacy-home-device")},
    )

    assert await async_migrate_config_entry(hass, entry)

    subentry = next(iter(entry.subentries.values()))
    migrated_entity = entity_registry.async_get(entity.entity_id)
    assert migrated_entity is not None
    assert migrated_entity.config_entry_id == entry.entry_id
    assert migrated_entity.config_subentry_id == subentry.subentry_id

    migrated_device = device_registry.async_get(device.id)
    assert migrated_device is not None
    assert device_ownership(migrated_device) == (
        {entry.entry_id},
        {entry.entry_id: {subentry.subentry_id}},
    )


async def test_ha_migration_grouped_entry_attaches_registries_to_parent_subentry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Merged legacy registry links should move to the parent location subentry."""
    clear_integration_modules()
    parent = legacy_config_entry(
        entry_id="legacy-home",
        title="Home",
        api_key="shared-registry-key",
        latitude=1.0,
        longitude=2.0,
    )
    duplicate = legacy_config_entry(
        entry_id="legacy-office",
        title="Office",
        api_key="shared-registry-key",
        latitude=3.0,
        longitude=4.0,
    )
    parent.add_to_hass(hass)
    duplicate.add_to_hass(hass)
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "legacy-office-grass",
        suggested_object_id="legacy_office_grass",
        config_entry=duplicate,
    )
    device = device_registry.async_get_or_create(
        config_entry_id=duplicate.entry_id,
        identifiers={(DOMAIN, "legacy-office-device")},
    )

    assert await async_migrate_config_entry(hass, parent)

    office_subentry = _subentries_by_legacy_entry(parent)["legacy-office"]
    migrated_entity = entity_registry.async_get(entity.entity_id)
    assert migrated_entity is not None
    assert migrated_entity.config_entry_id == parent.entry_id
    assert migrated_entity.config_subentry_id == office_subentry.subentry_id

    migrated_device = device_registry.async_get(device.id)
    assert migrated_device is not None
    assert device_ownership(migrated_device) == (
        {parent.entry_id},
        {parent.entry_id: {office_subentry.subentry_id}},
    )


async def test_ha_migration_invalid_legacy_coordinates_abort_and_create_repair(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Invalid legacy coordinates should abort migration and create a Repair."""
    clear_integration_modules()
    entry = legacy_config_entry(
        entry_id="legacy-corrupt",
        title="Corrupt Legacy",
        api_key="secret-key",
        latitude="not-a-number",
        longitude=2.0,
        unique_id="legacy-corrupt",
    )
    original_data = dict(entry.data)
    entry.add_to_hass(hass)

    assert await async_migrate_config_entry(hass, entry) is False

    assert entry.data == original_data
    assert entry.subentries == {}
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN,
        invalid_stored_location_issue_id(entry.entry_id, subentry_id=None),
    )
    assert issue is not None
    assert issue.translation_key == "invalid_stored_location"


async def test_ha_migration_retry_after_entity_registry_failure_is_idempotent(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry should reuse the created subentry and finish registry migration."""
    clear_integration_modules()
    entry = legacy_config_entry(
        entry_id="legacy-home",
        title="Home",
        api_key="retry-key",
        latitude=1.0,
        longitude=2.0,
    )
    entry.add_to_hass(hass)
    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "retry-home-grass",
        suggested_object_id="retry_home_grass",
        config_entry=entry,
    )
    original_update_entity = entity_registry.async_update_entity
    attempts = 0

    def _fail_once(entity_id: str, **kwargs: Any):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("registry boom")
        return original_update_entity(entity_id, **kwargs)

    monkeypatch.setattr(entity_registry, "async_update_entity", _fail_once)

    assert await async_migrate_config_entry(hass, entry) is False
    assert len(entry.subentries) == 1
    first_subentry_id = next(iter(entry.subentries))
    assert entity_registry.async_get(entity.entity_id).config_subentry_id is None

    assert await async_migrate_config_entry(hass, entry)

    assert len(entry.subentries) == 1
    assert next(iter(entry.subentries)) == first_subentry_id
    migrated_entity = entity_registry.async_get(entity.entity_id)
    assert migrated_entity is not None
    assert migrated_entity.config_subentry_id == first_subentry_id


class _UnaccountedMigrationLocation(AssertionError):
    """Only the known missing-runtime invariant may be expected to fail."""


# Remove this marker when #226 implements automatic runtime reconciliation.
@pytest.mark.xfail(
    strict=True,
    reason="Known migration race: #226",
    raises=_UnaccountedMigrationLocation,
)
async def test_ha_migration_during_parent_refresh_accounts_for_every_location(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """A legacy merge during setup must converge without a manual reload."""
    clear_integration_modules()
    parent = ha_config_entry
    parent.add_to_hass(hass)
    original_subentry = next(iter(parent.subentries.values()))
    original_unique_id = original_subentry.unique_id
    request_started = asyncio.Event()
    release_response = asyncio.Event()

    async def controlled_response(_url, **_kwargs):
        request_started.set()
        await release_response.wait()
        return CallbackResult(status=200, payload=google_pollen_5_day_payload)

    async with aiointercept(mock_external_urls=True) as mocked:
        mocked.get(POLLEN_API_URL_RE, callback=controlled_response, repeat=True)
        setup_task = asyncio.create_task(
            hass.config_entries.async_setup(parent.entry_id)
        )
        request_task = asyncio.create_task(request_started.wait())
        try:
            # Fail promptly if setup exits before reaching the HTTP boundary.
            await asyncio.wait(
                {setup_task, request_task}, return_when=asyncio.FIRST_COMPLETED
            )
            assert request_started.is_set()
            assert not setup_task.done()
            assert parent.state is ConfigEntryState.SETUP_IN_PROGRESS
            legacy = legacy_config_entry(
                entry_id="concurrent-legacy",
                title="Synthetic legacy",
                api_key=parent.data[CONF_API_KEY],
                latitude=1.0,
                longitude=2.0,
            )
            legacy.add_to_hass(hass)
            device_registry = dr.async_get(hass)
            entity_registry = er.async_get(hass)
            device = device_registry.async_get_or_create(
                config_entry_id=legacy.entry_id,
                identifiers={(DOMAIN, "concurrent-legacy-device")},
            )
            entity = entity_registry.async_get_or_create(
                "sensor",
                DOMAIN,
                "concurrent-legacy-grass",
                config_entry=legacy,
                device_id=device.id,
            )
            # Fail clearly if migration waits on the blocked parent setup.
            async with asyncio.timeout(15):
                assert await hass.config_entries.async_setup(legacy.entry_id)
        finally:
            release_response.set()
            request_task.cancel()
            await asyncio.gather(request_task, return_exceptions=True)
            setup_result = await setup_task
        assert setup_result
        await hass.async_block_till_done()

        assert parent.state is ConfigEntryState.LOADED
        assert parent.disabled_by is None
        assert hass.config_entries.async_get_entry(legacy.entry_id) is None
        assert len(parent.subentries) == 2
        assert (
            parent.subentries[original_subentry.subentry_id].unique_id
            == original_unique_id
        )
        target = _subentries_by_legacy_entry(parent)[legacy.entry_id]
        migrated_entity = entity_registry.async_get(entity.entity_id)
        assert migrated_entity is not None
        assert migrated_entity.unique_id == entity.unique_id
        assert migrated_entity.device_id == device.id
        assert migrated_entity.config_entry_id == parent.entry_id
        assert migrated_entity.config_subentry_id == target.subentry_id
        migrated_device = device_registry.async_get(device.id)
        assert migrated_device is not None
        assert migrated_device.identifiers == device.identifiers
        assert device_ownership(migrated_device) == (
            {parent.entry_id},
            {parent.entry_id: {target.subentry_id}},
        )

        runtime = parent.runtime_data
        active = {
            subentry.subentry_id
            for subentry in parent.subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_LOCATION
        }
        assert not runtime.failed_locations  # Every mocked response is healthy.
        assert not set(runtime.locations) & set(runtime.failed_locations)
        assert len(
            {id(location.coordinator) for location in runtime.locations.values()}
        ) == len(runtime.locations)
        for subentry_id, location in runtime.locations.items():
            assert location.subentry_id == subentry_id
            assert location.coordinator.entry_id == parent.entry_id
            assert location.coordinator.subentry_id == subentry_id
        if active != set(runtime.locations) | set(runtime.failed_locations):
            raise _UnaccountedMigrationLocation(
                f"Loaded parent has {len(active)} configured locations, "
                f"{len(runtime.locations)} coordinators and "
                f"{len(runtime.failed_locations)} recorded failures"
            )
        assert (
            runtime.locations[target.subentry_id].coordinator.entity_identity_id
            == legacy.entry_id
        )
