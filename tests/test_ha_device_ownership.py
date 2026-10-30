"""Single-owner reads and historical Device Registry migration contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.pollenlevels.const import DOMAIN
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import async_migrate_config_entry, legacy_config_entry


@pytest.fixture(autouse=True)
def forbid_deprecated_device_reads(monkeypatch):
    """Migration must use only the public single-owner fields."""

    def forbidden_read(_device):
        raise AssertionError("Deprecated device ownership read")

    for name in ("config_entries", "config_entries_subentries", "primary_config_entry"):
        monkeypatch.setattr(dr.DeviceEntry, name, property(forbidden_read))


def _legacy_entry(entry_id="legacy-home"):
    return legacy_config_entry(
        entry_id=entry_id,
        title="Home",
        api_key="synthetic-ownership-key",
        latitude=1.0,
        longitude=2.0,
    )


@pytest.mark.parametrize("load_registries", [False])
@pytest.mark.parametrize("association", [[None], [None, "historical-location"]])
@pytest.mark.parametrize("composite", [False, True])
async def test_historical_device_storage_retains_identity(
    hass,
    hass_storage,
    enable_custom_integrations,
    association,
    composite,
):
    """HA normalizes old None/subentry links without replacing ordinary IDs."""
    clear_integration_modules()
    from custom_components.pollenlevels.util import device_subentry_ids

    entry = _legacy_entry()
    entry.add_to_hass(hass)
    device = {
        "id": "historical-device",
        "config_entries": [entry.entry_id],
        "config_entries_subentries": {entry.entry_id: association},
        "primary_config_entry": entry.entry_id,
        "identifiers": [[DOMAIN, "legacy-home_type_grass"]],
        "connections": [],
        "labels": [],
        "name": "Grass",
        "name_by_user": "User device name",
        "area_id": "user-area",
        "disabled_by": "user",
        "created_at": "2026-01-01T00:00:00+00:00",
        "modified_at": "2026-01-01T00:00:00+00:00",
        **dict.fromkeys(
            (
                "configuration_url",
                "entry_type",
                "hw_version",
                "manufacturer",
                "model",
                "model_id",
                "serial_number",
                "sw_version",
                "via_device_id",
            )
        ),
    }
    if composite:
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        other = MockConfigEntry(domain="test", entry_id="other-owner")
        other.add_to_hass(hass)
        device["config_entries"].append(other.entry_id)
        device["config_entries_subentries"][other.entry_id] = [None]
    hass_storage[dr.STORAGE_KEY] = {
        "version": 1,
        "minor_version": 12,
        "key": dr.STORAGE_KEY,
        "data": {"devices": [device], "deleted_devices": []},
    }
    dr.async_setup(hass)
    await dr.async_load(hass)
    registry = dr.async_get(hass)
    if composite:
        historical = registry.async_get("historical-device")
        assert historical.is_composite_device
        assert device_subentry_ids(historical, entry.entry_id) is None
        real_devices = dr.async_entries_for_config_entry(registry, entry.entry_id)
        assert len(real_devices) == 1
        assert real_devices[0].id != historical.id
        loaded = real_devices[0]
        other_device = dr.async_entries_for_config_entry(registry, "other-owner")[0]
    else:
        loaded = registry.async_get("historical-device")
    assert loaded is not None and not loaded.is_composite_device
    assert loaded.identifiers == {(DOMAIN, "legacy-home_type_grass")}
    assert loaded.name_by_user == "User device name"
    assert loaded.area_id == "user-area"
    assert loaded.disabled_by is dr.DeviceEntryDisabler.USER
    assert device_subentry_ids(loaded, entry.entry_id) == {association[-1]}
    assert device_subentry_ids(loaded, "different-owner") == set()

    if association == [None]:
        await er.async_load(hass)
        assert await async_migrate_config_entry(hass, entry)
        migrated = registry.async_get(loaded.id)
        assert migrated is not None
        assert migrated.id == loaded.id
        assert migrated.identifiers == loaded.identifiers
        assert migrated.name_by_user == loaded.name_by_user
        assert migrated.area_id == loaded.area_id
        assert migrated.disabled_by == loaded.disabled_by
        assert device_subentry_ids(migrated, entry.entry_id) == set(entry.subentries)
        if composite:
            assert registry.async_get("historical-device").is_composite_device
            assert registry.async_get(other_device.id) == other_device


@pytest.mark.parametrize("ownership", ["other", "unknown", "composite"])
async def test_migration_rejects_unverified_device_ownership_and_retries(
    hass,
    enable_custom_integrations,
    monkeypatch,
    ownership,
):
    """A failed ownership read must never be converted into a legacy None link."""
    clear_integration_modules()
    entry = _legacy_entry()
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "legacy-home")},
    )
    enumerate_devices = dr.async_entries_for_config_entry
    candidate = {
        "other": SimpleNamespace(
            id=device.id, config_entry_id="other", config_subentry_id=None
        ),
        "unknown": SimpleNamespace(id=device.id),
        "composite": SimpleNamespace(id=device.id, is_composite_device=True),
    }[ownership]
    with monkeypatch.context() as patch:
        patch.setattr(dr, "async_entries_for_config_entry", lambda *_: [candidate])
        update = Mock(wraps=registry.async_update_device)
        patch.setattr(registry, "async_update_device", update)
        assert not await async_migrate_config_entry(hass, entry)
        update.assert_not_called()
    assert hass.config_entries.async_get_entry(entry.entry_id) is entry
    assert registry.async_get(device.id).config_subentry_id is None
    persisted_ids = set(entry.subentries)
    assert await async_migrate_config_entry(hass, entry)
    assert set(entry.subentries) == persisted_ids
    assert registry.async_get(device.id).config_subentry_id in persisted_ids
    assert enumerate_devices(registry, entry.entry_id)[0].id == device.id


async def test_migration_device_failure_retries_without_changing_identity(
    hass,
    enable_custom_integrations,
    monkeypatch,
):
    """Device move failure preserves the source and reuses its subentry on retry."""
    clear_integration_modules()
    entry = _legacy_entry()
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "legacy-home")},
    )
    entities = er.async_get(hass)
    entity = entities.async_get_or_create(
        "sensor",
        DOMAIN,
        "legacy-home_type_grass",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id="retained_grass",
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            registry,
            "async_update_device",
            Mock(side_effect=RuntimeError("Synthetic move failure")),
        )
        assert not await async_migrate_config_entry(hass, entry)
    subentries = set(entry.subentries)
    assert await async_migrate_config_entry(hass, entry)
    assert set(entry.subentries) == subentries
    retained = entities.async_get(entity.entity_id)
    assert retained.unique_id == entity.unique_id
    assert retained.device_id == device.id
    assert retained.config_subentry_id in subentries
    assert registry.async_get(device.id).config_subentry_id in subentries


@pytest.mark.parametrize("same_owner", [False, True])
async def test_atomic_move_and_noop_counters(
    hass,
    ha_config_entry,
    same_owner,
    monkeypatch,
):
    """Moves retain identity; a repeated destination produces no update or count."""
    clear_integration_modules()
    from custom_components.pollenlevels.migration import (
        _migrate_device_registry_for_merged_entry,
        _MigrationLocation,
    )

    parent = ha_config_entry
    parent.add_to_hass(hass)
    source = parent if same_owner else _legacy_entry()
    if not same_owner:
        source.add_to_hass(hass)
    target = next(iter(parent.subentries.values()))
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=source.entry_id,
        identifiers={(DOMAIN, "atomic-device")},
        connections={("test", "synthetic-connection")},
    )
    device = registry.async_update_device(
        device.id,
        name_by_user="User name",
        area_id="user-area",
        disabled_by=dr.DeviceEntryDisabler.USER,
    )
    location = _MigrationLocation(source, "Home", {}, source.entry_id, None)
    update = Mock(wraps=registry.async_update_device)
    monkeypatch.setattr(registry, "async_update_device", update)
    result = _migrate_device_registry_for_merged_entry(
        hass, source, parent, [(location, target)]
    )
    assert result == (True, 1, int(same_owner))
    expected = {"new_config_subentry_id": target.subentry_id}
    if not same_owner:
        expected["new_config_entry_id"] = parent.entry_id
    update.assert_called_once_with(device.id, **expected)
    actual = registry.async_get(device.id)
    assert actual.config_entry_id == parent.entry_id
    assert actual.config_subentry_id == target.subentry_id
    for field in (
        "id",
        "identifiers",
        "connections",
        "name_by_user",
        "area_id",
        "disabled_by",
    ):
        assert getattr(actual, field) == getattr(device, field)
    update.reset_mock()
    location = _MigrationLocation(
        parent, "Home", {}, source.entry_id, None, target.subentry_id
    )
    assert _migrate_device_registry_for_merged_entry(
        hass, parent, parent, [(location, target)]
    ) == (True, 0, 0)
    update.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        "identifier",
        "connection",
        "children",
        "missing_entry",
        "missing_subentry",
        "ignored",
        "none",
    ],
)
async def test_atomic_move_rejection_keeps_registry_state(
    hass,
    ha_config_entry,
    monkeypatch,
    failure,
):
    """Real HA validation and ignored updates must never count as successful moves."""
    clear_integration_modules()
    from custom_components.pollenlevels.migration import (
        _migrate_device_registry_for_merged_entry,
        _MigrationLocation,
    )

    parent = ha_config_entry
    if failure != "missing_entry":
        parent.add_to_hass(hass)
    source = _legacy_entry()
    source.add_to_hass(hass)
    target = next(iter(parent.subentries.values()))
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=source.entry_id,
        identifiers={(DOMAIN, "collision")},
        connections={("test", "synthetic-connection")},
    )
    if failure in {"identifier", "connection"}:
        registry.async_get_or_create(
            config_entry_id=parent.entry_id,
            identifiers=device.identifiers
            if failure == "identifier"
            else {(DOMAIN, "other-device")},
            connections=device.connections if failure == "connection" else set(),
        )
    elif failure == "children":
        registry.async_get_or_create_child(
            config_entry_id=source.entry_id,
            parent_device_id=device.id,
            identifiers={(DOMAIN, "child")},
        )
    elif failure == "missing_subentry":
        target = SimpleNamespace(subentry_id="missing-location")
    elif failure in {"ignored", "none"}:
        monkeypatch.setattr(
            registry,
            "async_update_device",
            Mock(return_value=device if failure == "ignored" else None),
        )
    location = _MigrationLocation(source, "Home", {}, source.entry_id, None)
    assert _migrate_device_registry_for_merged_entry(
        hass, source, parent, [(location, target)]
    ) == (False, 0, 0)
    assert registry.async_get(device.id) == device
    assert hass.config_entries.async_get_entry(source.entry_id) is source


@pytest.mark.parametrize("failure", ["exception", "ignored", "collision"])
async def test_grouped_atomic_failure_retains_source_after_entity_success(
    hass,
    ha_config_entry,
    enable_custom_integrations,
    monkeypatch,
    failure,
):
    """Partial entity success is retryable without removing the legacy source."""
    clear_integration_modules()
    from custom_components.pollenlevels.const import CONF_API_KEY

    parent = ha_config_entry
    parent.add_to_hass(hass)
    source = legacy_config_entry(
        entry_id="atomic-source",
        title="Legacy",
        api_key=parent.data[CONF_API_KEY],
        latitude=1.0,
        longitude=2.0,
    )
    source.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=source.entry_id, identifiers={(DOMAIN, "retained-device")}
    )
    entities = er.async_get(hass)
    entity = entities.async_get_or_create(
        "sensor", DOMAIN, "retained-unique", config_entry=source, device_id=device.id
    )
    blocker = None
    with monkeypatch.context() as patch:
        if failure == "collision":
            blocker = registry.async_get_or_create(
                config_entry_id=parent.entry_id, identifiers=device.identifiers
            )
        else:
            patch.setattr(
                registry,
                "async_update_device",
                Mock(side_effect=RuntimeError("Synthetic failure"))
                if failure == "exception"
                else Mock(return_value=device),
            )
        assert not await async_migrate_config_entry(hass, parent)
    assert entities.async_get(entity.entity_id).config_entry_id == parent.entry_id
    assert registry.async_get(device.id).config_entry_id == source.entry_id
    assert hass.config_entries.async_get_entry(source.entry_id) is source
    persisted = set(parent.subentries)
    if blocker:
        # Resolve the injected conflict; production never deletes the competing device.
        registry.async_update_device(
            blocker.id, new_identifiers={(DOMAIN, "resolved-conflict")}
        )
    assert await async_migrate_config_entry(hass, parent)
    assert hass.config_entries.async_get_entry(source.entry_id) is None
    assert set(parent.subentries) == persisted
    retained = entities.async_get(entity.entity_id)
    assert retained.unique_id == entity.unique_id
    assert retained.device_id == device.id
    assert registry.async_get(device.id).config_entry_id == parent.entry_id
    assert (
        registry.async_get(device.id).config_subentry_id == retained.config_subentry_id
    )
    assert await async_migrate_config_entry(hass, parent)
    assert set(parent.subentries) == persisted


@pytest.mark.parametrize(
    "source_disabled,target_disabled,expected",
    [(True, False, None), (False, True, dr.DeviceEntryDisabler.CONFIG_ENTRY)],
)
async def test_atomic_move_respects_config_entry_disabled_state(
    hass,
    ha_config_entry,
    source_disabled,
    target_disabled,
    expected,
):
    """HA reconciles CONFIG_ENTRY disabling with the destination owner."""
    from homeassistant.config_entries import ConfigEntryDisabler

    clear_integration_modules()
    from custom_components.pollenlevels.migration import (
        _migrate_device_registry_for_merged_entry,
        _MigrationLocation,
    )

    parent = ha_config_entry
    parent.add_to_hass(hass)
    source = _legacy_entry()
    source.add_to_hass(hass)
    if source_disabled:
        await hass.config_entries.async_set_disabled_by(
            source.entry_id, ConfigEntryDisabler.USER
        )
    if target_disabled:
        await hass.config_entries.async_set_disabled_by(
            parent.entry_id, ConfigEntryDisabler.USER
        )
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=source.entry_id, identifiers={(DOMAIN, "disabled-device")}
    )
    target = next(iter(parent.subentries.values()))
    location = _MigrationLocation(source, "Home", {}, source.entry_id, None)
    assert _migrate_device_registry_for_merged_entry(
        hass, source, parent, [(location, target)]
    ) == (True, 1, 0)
    assert registry.async_get(device.id).disabled_by == expected
