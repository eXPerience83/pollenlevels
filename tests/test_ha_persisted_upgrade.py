"""Isolated historical config storage and Recorder continuity regressions.

Historical *integration* data shapes are grounded in tagged 2.3.0 / 4.0.3 code.
The enclosing Home Assistant Store structure is the supported 2026.10.4 format.
This harness is not yet a complete independent-process upgrade/Marketplace test.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing
from pathlib import Path
from shutil import copytree
from typing import Any

import pytest
from aiointercept import aiointercept
from homeassistant import config_entries, loader
from homeassistant.components.recorder import Recorder
from homeassistant.config_entries import ConfigEntryState
from homeassistant.components.recorder.db_schema import States, StatesMeta
from homeassistant.components.recorder.util import session_scope
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er, frame
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_test_home_assistant,
    flush_store,
)
from pytest_homeassistant.components.recorder.common import async_wait_recording_done

from custom_components.pollenlevels.const import DOMAIN
from custom_components.pollenlevels.util import api_key_unique_id
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import (
    async_migrate_config_entry,
    async_setup_config_entry,
    mock_pollen_api,
)

HISTORICAL_KEY = "synthetic-history-key"
HISTORY_ENTITY = "sensor.synthetic_pollen_history"
STORAGE_DATE = "2026-01-01T00:00:00+00:00"


def _historical_entries(release: str) -> list[MockConfigEntry]:
    """Create supported HA storage records with genuine tagged integration layouts."""
    if release == "2.3.0":
        # v2.3.0 ConfigFlow.VERSION=3, one entry per location, coordinates in data.
        return [
            MockConfigEntry(
                domain=DOMAIN,
                entry_id=f"historical-{suffix}",
                title=title,
                version=3,
                unique_id=f"{lat:.4f}_{lon:.4f}",
                data={"api_key": HISTORICAL_KEY, "latitude": lat, "longitude": lon},
                options={"update_interval": 12, "forecast_days": 3},
            )
            for suffix, title, lat, lon in [
                ("home", "Home", 1.0, 2.0),
                ("office", "Office", 3.0, 4.0),
            ]
        ]

    if release == "4.0.3":
        # v4.0.3 ConfigFlow.VERSION=6, one API-key parent with location subentries.
        return [
            MockConfigEntry(
                domain=DOMAIN,
                entry_id="historical-parent",
                title="Pollen Levels",
                version=6,
                unique_id=api_key_unique_id(HISTORICAL_KEY),
                data={"api_key": HISTORICAL_KEY},
                options={"update_interval": 12, "language_code": "en"},
                subentries_data=[
                    {
                        "subentry_id": f"historical-location-{suffix}",
                        "subentry_type": "location",
                        "title": title,
                        "unique_id": f"{lat:.4f}_{lon:.4f}",
                        "data": {"latitude": lat, "longitude": lon},
                    }
                    for suffix, title, lat, lon in [
                        ("home", "Home", 1.0, 2.0),
                        ("office", "Office", 3.0, 4.0),
                    ]
                ],
            )
        ]

    raise AssertionError(f"Unsupported historical release: {release}")


@pytest.fixture
def mock_recorder_before_hass(async_test_recorder: Any) -> None:
    """Prepare Recorder fixtures before Home Assistant is constructed."""


@pytest.fixture
def recorder_config(tmp_path: Path) -> dict[str, str]:
    """Use an actual on-disk SQLite database, not Recorder's :memory: default."""
    return {"db_url": f"sqlite:///{tmp_path / 'history.sqlite'}"}


def _recorded_values(hass: HomeAssistant, entity_id: str) -> list[str]:
    """Read recorded states from the actual SQL database, by stable entity ID."""
    with session_scope(hass=hass, read_only=True) as session:
        rows = (
            session.query(States.state)
            .join(StatesMeta, States.metadata_id == StatesMeta.metadata_id)
            .filter(StatesMeta.entity_id == entity_id)
            .order_by(States.state_id)
            .all()
        )
        return [row[0] for row in rows]


@pytest.mark.parametrize("historical_release", ["2.3.0", "4.0.3"])
async def test_historical_config_store_upgrade_keeps_registry_and_recorder_history(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    recorder_mock: Recorder,
    enable_custom_integrations: None,
    historical_release: str,
    tmp_path: Path,
) -> None:
    """Load serialized historical config through HA and retain linked SQL history."""
    clear_integration_modules()
    from custom_components.pollenlevels import TARGET_ENTRY_VERSION

    entries = _historical_entries(historical_release)
    stored = json.loads(json.dumps([entry.as_dict() for entry in entries]))
    hass_storage[config_entries.STORAGE_KEY] = {
        "version": config_entries.STORAGE_VERSION,
        "minor_version": config_entries.STORAGE_VERSION_MINOR,
        "key": config_entries.STORAGE_KEY,
        "data": {"entries": stored},
    }

    # The pytest hass factory initializes an empty manager by default.
    # Explicitly invoke the *real* HA config-entry Store deserializer here.
    await hass.config_entries.async_initialize()
    loaded = hass.config_entries.async_entries(DOMAIN)
    assert len(loaded) == len(stored)
    assert all(type(entry) is config_entries.ConfigEntry for entry in loaded)
    assert {entry.entry_id for entry in loaded} == {
        entry["entry_id"] for entry in stored
    }

    first = next(entry for entry in loaded if entry.entry_id == entries[0].entry_id)
    original_subentry_id = (
        next(iter(first.subentries)) if historical_release == "4.0.3" else None
    )
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=first.entry_id,
        config_subentry_id=original_subentry_id,
        identifiers={(DOMAIN, f"{first.entry_id}_type")},
    )
    device = device_registry.async_update_device(
        device.id, name_by_user="Customized device"
    )
    entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{first.entry_id}_type_grass",
        config_entry=first,
        config_subentry_id=original_subentry_id,
        device_id=device.id,
        suggested_object_id="synthetic_pollen_history",
    )
    assert entity.entity_id == HISTORY_ENTITY
    before_entity = (entity.id, entity.entity_id, entity.unique_id, entity.device_id)
    before_device = (device.id, device.identifiers, device.name_by_user)

    # Record historical data in the real SQLite-backed HA Recorder, then migrate.
    hass.states.async_set(entity.entity_id, "2")
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    # HA can schedule Recorder writes asynchronously; wait for its commit
    # barrier before reading historical rows from the SQLite connection.
    await recorder_mock.async_block_till_done()
    before_states = await recorder_mock.async_add_executor_job(
        _recorded_values, hass, entity.entity_id
    )
    assert "2" in before_states

    assert await async_migrate_config_entry(hass, first)
    await hass.async_block_till_done()
    parent = hass.config_entries.async_get_entry(first.entry_id)
    assert parent is not None
    assert parent.version == TARGET_ENTRY_VERSION
    assert len(parent.subentries) == 2

    moved = entity_registry.async_get(entity.entity_id)
    reassigned_device = device_registry.async_get(device.id)
    assert moved is not None and reassigned_device is not None
    assert (
        moved.id,
        moved.entity_id,
        moved.unique_id,
        moved.device_id,
    ) == before_entity
    assert (
        reassigned_device.id,
        reassigned_device.identifiers,
        reassigned_device.name_by_user,
    ) == before_device
    assert moved.config_entry_id == parent.entry_id
    assert moved.config_subentry_id in parent.subentries
    assert reassigned_device.config_entry_id == parent.entry_id
    assert reassigned_device.config_subentry_id == moved.config_subentry_id
    if historical_release == "2.3.0":
        assert hass.config_entries.async_get_entry("historical-office") is None
        assert parent.subentries[moved.config_subentry_id].data["legacy_entry_id"] == (
            first.entry_id
        )
    else:
        assert moved.config_subentry_id == original_subentry_id

    # Recorder keeps existing history under the unchanged entity_id.
    hass.states.async_set(entity.entity_id, "3")
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    # The new state may still be queued after HA's event loop becomes idle.
    await recorder_mock.async_block_till_done()
    after_states = await recorder_mock.async_add_executor_job(
        _recorded_values, hass, entity.entity_id
    )
    assert len(after_states) >= len(before_states) + 1
    assert after_states[: len(before_states)] == before_states
    assert after_states[-1] == "3"

    # Verify the resulting config is serialized to HA's actual Store interface.
    await flush_store(hass.config_entries._store)
    output = hass_storage[config_entries.STORAGE_KEY]["data"]["entries"]
    persisted_parent = next(
        item for item in output if item["entry_id"] == parent.entry_id
    )
    assert persisted_parent["version"] == TARGET_ENTRY_VERSION
    assert len(persisted_parent["subentries"]) == 2
    assert all(
        item["subentry_id"] in parent.subentries
        for item in persisted_parent["subentries"]
    )
    assert (tmp_path / "history.sqlite").is_file()

    # Running migration twice must not duplicate entries or mutate history.
    assert await async_migrate_config_entry(hass, parent)
    assert {s.subentry_id for s in parent.subentries.values()} == {
        item["subentry_id"] for item in persisted_parent["subentries"]
    }
    again = await recorder_mock.async_add_executor_job(
        _recorded_values, hass, entity.entity_id
    )
    assert again == after_states


@asynccontextmanager
async def _persisted_ha(config_dir: Path) -> AsyncIterator[HomeAssistant]:
    """Start an isolated HA object and always close its lifecycle properly."""
    async with async_test_home_assistant(
        config_dir=str(config_dir), load_registries=False
    ) as home:
        try:
            yield home
        finally:
            await home.async_stop(force=True)


@pytest.mark.parametrize("historical_release", ["2.3.0", "4.0.3"])
async def test_real_storage_survives_new_ha_instances_and_recorder_reopen(
    hass_tmp_config_dir: str,
    async_test_recorder: Any,
    recorder_config: dict[str, str],
    historical_release: str,
) -> None:
    """Restore genuine on-disk HA stores in separate HA instances and reopen SQLite."""
    clear_integration_modules()
    from custom_components.pollenlevels import TARGET_ENTRY_VERSION

    config_dir = Path(hass_tmp_config_dir)
    config_file = config_dir / ".storage" / config_entries.STORAGE_KEY
    entity_file = config_dir / ".storage" / er.STORAGE_KEY
    device_file = config_dir / ".storage" / dr.STORAGE_KEY
    db_path = Path(recorder_config["db_url"].removeprefix("sqlite:///"))

    async def load_registries(home: HomeAssistant) -> None:
        dr.async_setup(home)
        await dr.async_load(home)
        await er.async_load(home)

    # HA instance A: create records using the historical integration layout,
    # persist them through the real Store implementation and write to SQLite.
    async with _persisted_ha(config_dir) as home_a:
        await home_a.config_entries.async_initialize()
        await load_registries(home_a)
        old = _historical_entries(historical_release)[0]
        old.add_to_hass(home_a)
        subentry_id = next(iter(old.subentries), None)
        devices_a = dr.async_get(home_a)
        entities_a = er.async_get(home_a)
        device = devices_a.async_get_or_create(
            config_entry_id=old.entry_id,
            config_subentry_id=subentry_id,
            identifiers={(DOMAIN, f"{old.entry_id}_type")},
        )
        device = devices_a.async_update_device(
            device.id, name_by_user="Customized device"
        )
        entity = entities_a.async_get_or_create(
            "sensor",
            DOMAIN,
            f"{old.entry_id}_type_grass",
            config_entry=old,
            config_subentry_id=subentry_id,
            device_id=device.id,
            suggested_object_id="synthetic_pollen_history",
        )
        original_entity = (
            entity.id,
            entity.entity_id,
            entity.unique_id,
            entity.device_id,
        )
        original_device = (device.id, device.identifiers, device.name_by_user)
        await home_a.config_entries._store.async_save({"entries": [old.as_dict()]})
        await flush_store(devices_a._store)
        await flush_store(entities_a._store)
        async with async_test_recorder(home_a, recorder_config) as recorder_a:
            home_a.states.async_set(entity.entity_id, "2")
            await home_a.async_block_till_done()
            await recorder_a.async_block_till_done()
            assert "2" in await recorder_a.async_add_executor_job(
                _recorded_values, home_a, entity.entity_id
            )

    for store_file in (config_file, entity_file, device_file, db_path):
        assert store_file.is_file(), f"Missing persisted artifact: {store_file.name}"
    before = json.loads(config_file.read_text(encoding="utf-8"))
    assert before["data"]["entries"][0]["version"] == (
        3 if historical_release == "2.3.0" else 6
    )

    # HA instance B: reconstruct config entries, device and entity registry
    # from those files, then reopen the *same* SQLite Recorder database.
    async with _persisted_ha(config_dir) as home_b:
        await home_b.config_entries.async_initialize()
        await load_registries(home_b)
        restored = home_b.config_entries.async_get_entry(old.entry_id)
        assert restored is not None
        assert type(restored) is config_entries.ConfigEntry
        restored_entity = er.async_get(home_b).async_get(entity.entity_id)
        restored_device = dr.async_get(home_b).async_get(device.id)
        assert restored_entity is not None and restored_device is not None
        assert (
            restored_entity.id,
            restored_entity.entity_id,
            restored_entity.unique_id,
            restored_entity.device_id,
        ) == original_entity
        assert (
            restored_device.id,
            restored_device.identifiers,
            restored_device.name_by_user,
        ) == original_device

        async with async_test_recorder(home_b, recorder_config) as recorder_b:
            historical_states = await recorder_b.async_add_executor_job(
                _recorded_values, home_b, entity.entity_id
            )
            assert "2" in historical_states
            assert await async_migrate_config_entry(home_b, restored)
            await home_b.async_block_till_done()
            updated_entity = er.async_get(home_b).async_get(entity.entity_id)
            updated_device = dr.async_get(home_b).async_get(device.id)
            assert updated_entity is not None and updated_device is not None
            assert (
                updated_entity.id,
                updated_entity.entity_id,
                updated_entity.unique_id,
                updated_entity.device_id,
            ) == original_entity
            assert (
                updated_device.id,
                updated_device.identifiers,
                updated_device.name_by_user,
            ) == original_device
            assert updated_entity.config_subentry_id in restored.subentries
            assert (
                updated_device.config_subentry_id == updated_entity.config_subentry_id
            )
            if historical_release == "4.0.3":
                assert updated_entity.config_subentry_id == subentry_id
            else:
                assert (
                    restored.subentries[updated_entity.config_subentry_id].data[
                        "legacy_entry_id"
                    ]
                    == old.entry_id
                )
            assert restored.version == TARGET_ENTRY_VERSION
            home_b.states.async_set(entity.entity_id, "3")
            await home_b.async_block_till_done()
            await recorder_b.async_block_till_done()
            after = await recorder_b.async_add_executor_job(
                _recorded_values, home_b, entity.entity_id
            )
            assert after[: len(historical_states)] == historical_states
            assert after[-1] == "3"
        await flush_store(home_b.config_entries._store)
        await flush_store(dr.async_get(home_b)._store)
        await flush_store(er.async_get(home_b)._store)

    # HA instance C: read the migrated persisted registry entries again.
    async with _persisted_ha(config_dir) as home_c:
        await home_c.config_entries.async_initialize()
        await load_registries(home_c)
        migrated = home_c.config_entries.async_get_entry(old.entry_id)
        assert migrated is not None and migrated.version == TARGET_ENTRY_VERSION
        assert len(migrated.subentries) == (1 if historical_release == "2.3.0" else 2)
        final_entity = er.async_get(home_c).async_get(entity.entity_id)
        final_device = dr.async_get(home_c).async_get(device.id)
        assert final_entity is not None and final_device is not None
        assert (
            final_entity.id,
            final_entity.entity_id,
            final_entity.unique_id,
            final_entity.device_id,
        ) == original_entity
        assert (
            final_device.id,
            final_device.identifiers,
            final_device.name_by_user,
        ) == original_device
        assert final_entity.config_subentry_id in migrated.subentries
        assert final_device.config_subentry_id == final_entity.config_subentry_id
        if historical_release == "4.0.3":
            assert final_entity.config_subentry_id == subentry_id
        else:
            assert (
                migrated.subentries[final_entity.config_subentry_id].data[
                    "legacy_entry_id"
                ]
                == old.entry_id
            )

    # Verify the SQL data remains readable after all three HA instances shut down.
    with closing(sqlite3.connect(db_path)) as connection:
        values = connection.execute(
            "SELECT states.state FROM states "
            "JOIN states_meta ON states.metadata_id = states_meta.metadata_id "
            "WHERE states_meta.entity_id = ? ORDER BY states.state_id",
            (entity.entity_id,),
        ).fetchall()
    assert [value[0] for value in values][-2:] == ["2", "3"]


def _multi_key_historical_entries(release: str) -> list[MockConfigEntry]:
    """Represent three old locations under two distinct API-key owners."""
    first = _historical_entries(release)
    if release == "2.3.0":
        return [
            *first,
            MockConfigEntry(
                domain=DOMAIN,
                entry_id="historical-other",
                title="Other",
                version=3,
                unique_id="5.0000_6.0000",
                data={
                    "api_key": "synthetic-second-key",
                    "latitude": 5.0,
                    "longitude": 6.0,
                },
                options={"update_interval": 8},
            ),
        ]

    return [
        *first,
        MockConfigEntry(
            domain=DOMAIN,
            entry_id="historical-parent-other",
            title="Other pollen service",
            version=6,
            unique_id=api_key_unique_id("synthetic-second-key"),
            data={"api_key": "synthetic-second-key"},
            options={"update_interval": 8},
            subentries_data=[
                {
                    "subentry_id": "historical-location-other",
                    "subentry_type": "location",
                    "title": "Other",
                    "unique_id": "5.0000_6.0000",
                    "data": {"latitude": 5.0, "longitude": 6.0},
                }
            ],
        ),
    ]


@pytest.mark.parametrize("historical_release", ["2.3.0", "4.0.3"])
async def test_persisted_multikey_upgrade_preserves_custom_ids_and_each_history(
    hass_tmp_config_dir: str,
    async_test_recorder: Any,
    recorder_config: dict[str, str],
    historical_release: str,
    socket_enabled: None,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """Replay old integration shapes on disk, then reopen registries and Recorder.

    The payloads match tagged integration structures; this does not replay old
    Home Assistant Core storage envelopes or actual Marketplace ownership.
    """
    clear_integration_modules()
    from custom_components.pollenlevels import TARGET_ENTRY_VERSION

    entries = _multi_key_historical_entries(historical_release)
    primary_id = entries[0].entry_id
    secondary_id = entries[-1].entry_id
    config_dir = Path(hass_tmp_config_dir)
    db_path = Path(recorder_config["db_url"].removeprefix("sqlite:///"))
    # Isolated Home Assistant must discover the actual custom component from
    # its config directory. Do not enable in-memory hass_storage interception.
    copytree(
        Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN,
        config_dir / "custom_components" / DOMAIN,
    )

    if historical_release == "2.3.0":
        locations = [
            (entries[0], None, "home"),
            (entries[1], None, "office"),
            (entries[2], None, "other"),
        ]
    else:
        locations = [
            (entries[0], "historical-location-home", "home"),
            (entries[0], "historical-location-office", "office"),
            (entries[1], "historical-location-other", "other"),
        ]

    async def load_registries(home: HomeAssistant) -> None:
        dr.async_setup(home)
        await dr.async_load(home)
        await er.async_load(home)

    # Each snapshot includes the original parent, location, user-facing name
    # and stable identity. All keys and positions are synthetic.
    snapshots: dict[str, dict[str, Any]] = {}

    async with _persisted_ha(config_dir) as old_hass:
        await old_hass.config_entries.async_initialize()
        await load_registries(old_hass)
        for entry in entries:
            entry.add_to_hass(old_hass)

        device_registry = dr.async_get(old_hass)
        entity_registry = er.async_get(old_hass)
        for entry, subentry_id, suffix in locations:
            # Match the IDs that tagged 2.3.0 / 4.0.3 sensors actually used,
            # so real post-migration setup must adopt these Registry objects.
            identity_id = (
                entry.entry_id
                if historical_release == "2.3.0"
                else f"{entry.entry_id}_{subentry_id}"
            )
            device = device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                config_subentry_id=subentry_id,
                identifiers={(DOMAIN, f"{identity_id}_type")},
            )
            device = device_registry.async_update_device(
                device.id, name_by_user=f"Renamed device {suffix}"
            )
            entity = entity_registry.async_get_or_create(
                "sensor",
                DOMAIN,
                f"{identity_id}_type_grass",
                config_entry=entry,
                config_subentry_id=subentry_id,
                device_id=device.id,
                suggested_object_id=f"legacy_{suffix}_grass",
            )
            entity = entity_registry.async_update_entity(
                entity.entity_id,
                new_entity_id=f"sensor.user_renamed_{suffix}_pollen",
            )
            snapshots[suffix] = {
                "entry_id": entry.entry_id,
                "subentry_id": subentry_id,
                "entity": (
                    entity.id,
                    entity.entity_id,
                    entity.unique_id,
                    entity.device_id,
                ),
                "device": (
                    device.id,
                    device.identifiers,
                    device.name_by_user,
                ),
            }

        await old_hass.config_entries._store.async_save(
            {"entries": [entry.as_dict() for entry in entries]}
        )
        await flush_store(device_registry._store)
        await flush_store(entity_registry._store)

        async with async_test_recorder(old_hass, recorder_config) as recorder:
            for snapshot in snapshots.values():
                old_hass.states.async_set(snapshot["entity"][1], "2")
            await old_hass.async_block_till_done()
            await async_wait_recording_done(old_hass)
            await recorder.async_block_till_done()
            for snapshot in snapshots.values():
                assert "2" in await recorder.async_add_executor_job(
                    _recorded_values, old_hass, snapshot["entity"][1]
                )

    for key in (config_entries.STORAGE_KEY, er.STORAGE_KEY, dr.STORAGE_KEY):
        assert (config_dir / ".storage" / key).is_file()
    assert db_path.is_file()

    # Upgrade from disk after a real HA object shutdown. The shared-key
    # legacy entries must converge into one parent, while the other key stays
    # independent. Preserve every renamed entity's Registry and SQL identity.
    async with _persisted_ha(config_dir) as upgraded_hass:
        await upgraded_hass.config_entries.async_initialize()
        await load_registries(upgraded_hass)
        assert len(upgraded_hass.config_entries.async_entries(DOMAIN)) == len(entries)
        async with async_test_recorder(upgraded_hass, recorder_config) as recorder:
            for snapshot in snapshots.values():
                assert "2" in await recorder.async_add_executor_job(
                    _recorded_values, upgraded_hass, snapshot["entity"][1]
                )

            for entry_id in (primary_id, secondary_id):
                restored = upgraded_hass.config_entries.async_get_entry(entry_id)
                assert restored is not None
                assert await async_migrate_config_entry(upgraded_hass, restored)

            parents = upgraded_hass.config_entries.async_entries(DOMAIN)
            assert {entry.entry_id for entry in parents} == {primary_id, secondary_id}
            for parent in parents:
                assert parent.version == TARGET_ENTRY_VERSION
                assert len(parent.subentries) == (
                    2 if parent.entry_id == primary_id else 1
                )
                assert parent.data["api_key"] == (
                    HISTORICAL_KEY
                    if parent.entry_id == primary_id
                    else "synthetic-second-key"
                )

            for suffix, snapshot in snapshots.items():
                expected_parent_id = secondary_id if suffix == "other" else primary_id
                moved = er.async_get(upgraded_hass).async_get(snapshot["entity"][1])
                device = dr.async_get(upgraded_hass).async_get(snapshot["device"][0])
                assert moved is not None and device is not None
                assert (
                    moved.id,
                    moved.entity_id,
                    moved.unique_id,
                    moved.device_id,
                ) == snapshot["entity"]
                assert (
                    device.id,
                    device.identifiers,
                    device.name_by_user,
                ) == snapshot["device"]
                assert moved.config_entry_id == expected_parent_id
                assert device.config_entry_id == expected_parent_id
                assert moved.config_subentry_id == device.config_subentry_id
                parent = upgraded_hass.config_entries.async_get_entry(
                    expected_parent_id
                )
                assert parent is not None
                assert moved.config_subentry_id in parent.subentries
                if historical_release == "4.0.3":
                    assert moved.config_subentry_id == snapshot["subentry_id"]
                else:
                    assert (
                        parent.subentries[moved.config_subentry_id].data[
                            "legacy_entry_id"
                        ]
                        == snapshot["entry_id"]
                    )

            # Exercise the real integration's API-backed sensor setup, not
            # manually injected post-upgrade states. GRASS=3 in this fixture.
            # async_test_home_assistant disables custom component discovery
            # by default. Enable it for this isolated instance only.
            upgraded_hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)
            frame.async_setup(upgraded_hass)
            async with aiointercept(mock_external_urls=True) as mocked:
                mock_pollen_api(mocked, google_pollen_5_day_payload)
                for parent in parents:
                    # Setting up the integration can load sibling entries too.
                    if parent.state is ConfigEntryState.NOT_LOADED:
                        await async_setup_config_entry(upgraded_hass, parent)
            assert all(parent.state is ConfigEntryState.LOADED for parent in parents)

            for snapshot in snapshots.values():
                live = upgraded_hass.states.get(snapshot["entity"][1])
                assert live is not None and live.state == "3"
                assert (
                    er.async_get(upgraded_hass).async_get(snapshot["entity"][1]).id
                    == snapshot["entity"][0]
                )
            await async_wait_recording_done(upgraded_hass)
            await recorder.async_block_till_done()
            for snapshot in snapshots.values():
                values = await recorder.async_add_executor_job(
                    _recorded_values, upgraded_hass, snapshot["entity"][1]
                )
                assert values[-2:] == ["2", "3"]

            # A repeated migration must be a no-op, not an entity duplicate.
            for parent in parents:
                assert await async_migrate_config_entry(upgraded_hass, parent)
            assert len(upgraded_hass.config_entries.async_entries(DOMAIN)) == 2

        # Unload coordinators explicitly: the lightweight HA context manager
        # does not provide the normal pytest hass fixture's entry cleanup.
        for parent in parents:
            if parent.state is ConfigEntryState.LOADED:
                assert await upgraded_hass.config_entries.async_unload(parent.entry_id)
        await upgraded_hass.async_block_till_done()
        await flush_store(upgraded_hass.config_entries._store)
        await flush_store(dr.async_get(upgraded_hass)._store)
        await flush_store(er.async_get(upgraded_hass)._store)

    # Third HA object reload and direct offline SQL reads prove that both the
    # Registry names and older Recorder rows survived on the same filesystem.
    async with _persisted_ha(config_dir) as reopened_hass:
        await reopened_hass.config_entries.async_initialize()
        await load_registries(reopened_hass)
        reloaded_parents = {
            entry.entry_id: entry
            for entry in reopened_hass.config_entries.async_entries(DOMAIN)
        }
        assert set(reloaded_parents) == {primary_id, secondary_id}
        for parent_id, parent in reloaded_parents.items():
            assert parent.version == TARGET_ENTRY_VERSION
            assert parent.data["api_key"] == (
                HISTORICAL_KEY if parent_id == primary_id else "synthetic-second-key"
            )
            assert parent.unique_id == api_key_unique_id(parent.data["api_key"])
            assert len(parent.subentries) == (2 if parent_id == primary_id else 1)
        for suffix, snapshot in snapshots.items():
            entity = er.async_get(reopened_hass).async_get(snapshot["entity"][1])
            device = dr.async_get(reopened_hass).async_get(snapshot["device"][0])
            assert entity is not None and device is not None
            assert (
                entity.id,
                entity.entity_id,
                entity.unique_id,
                entity.device_id,
            ) == snapshot["entity"]
            assert (device.id, device.identifiers, device.name_by_user) == (
                snapshot["device"]
            )
            assert entity.config_subentry_id == device.config_subentry_id
            expected_parent_id = secondary_id if suffix == "other" else primary_id
            assert entity.config_entry_id == expected_parent_id
            assert device.config_entry_id == expected_parent_id
            parent = reloaded_parents[expected_parent_id]
            assert entity.config_subentry_id in parent.subentries
            if historical_release == "4.0.3":
                assert entity.config_subentry_id == snapshot["subentry_id"]
            else:
                assert (
                    parent.subentries[entity.config_subentry_id].data["legacy_entry_id"]
                    == snapshot["entry_id"]
                )

    with closing(sqlite3.connect(db_path)) as connection:
        for snapshot in snapshots.values():
            recorded = connection.execute(
                "SELECT states.state FROM states "
                "JOIN states_meta ON states.metadata_id = states_meta.metadata_id "
                "WHERE states_meta.entity_id = ? ORDER BY states.state_id",
                (snapshot["entity"][1],),
            ).fetchall()
            assert [row[0] for row in recorded][-2:] == ["2", "3"]
