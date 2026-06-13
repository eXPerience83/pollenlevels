"""Home Assistant harness tests for legacy entry migration."""

from __future__ import annotations

from typing import Any

import pytest
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
from tests.ha_helpers import async_migrate_config_entry, legacy_config_entry


def _subentries_by_legacy_entry(entry) -> dict[str, Any]:
    """Return migrated location subentries keyed by legacy entry id."""
    return {
        subentry.data[CONF_LEGACY_ENTRY_ID]: subentry
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_LOCATION
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
    assert migrated_device.config_entries == {entry.entry_id}
    assert migrated_device.config_entries_subentries == {
        entry.entry_id: {subentry.subentry_id}
    }


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
    assert migrated_device.config_entries == {parent.entry_id}
    assert migrated_device.config_entries_subentries == {
        parent.entry_id: {office_subentry.subentry_id}
    }


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
