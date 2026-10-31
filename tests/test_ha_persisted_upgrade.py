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
from typing import Any

import pytest
from homeassistant import config_entries
from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.db_schema import States, StatesMeta
from homeassistant.components.recorder.util import session_scope
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_test_home_assistant,
    flush_store,
)

from custom_components.pollenlevels.const import DOMAIN
from custom_components.pollenlevels.util import api_key_unique_id
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import async_migrate_config_entry

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
