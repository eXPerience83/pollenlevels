"""Lifecycle coverage for committed migration runtime reconciliation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiointercept import CallbackResult, aiointercept
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.setup import async_setup_component

from custom_components.pollenlevels.const import CONF_API_KEY, DOMAIN
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import POLLEN_API_URL_RE, legacy_config_entry


@pytest.fixture
async def migration_parent(
    hass,
    enable_custom_integrations,
    socket_enabled,
    ha_config_entry,
    google_pollen_5_day_payload,
):
    """Use real HA lifecycle with a controllable synthetic Google boundary."""
    clear_integration_modules()
    assert await async_setup_component(hass, DOMAIN, {})
    parent = ha_config_entry
    parent.add_to_hass(hass)
    controls = {"callback": None, "requests": 0}

    async def response(url, **kwargs):
        controls["requests"] += 1
        if controls["callback"] is not None:
            result = await controls["callback"](url, **kwargs)
            if result is not None:
                return result
        return CallbackResult(status=200, payload=google_pollen_5_day_payload)

    async with aiointercept(mock_external_urls=True) as mocked:
        mocked.get(POLLEN_API_URL_RE, callback=response, repeat=True)
        yield parent, controls
        await hass.async_block_till_done()


async def _merge(hass, parent, number):
    """Run the migration hook against real HA entries and registry managers."""
    from custom_components.pollenlevels import async_migrate_entry

    legacy = legacy_config_entry(
        entry_id=f"synthetic-legacy-{number}",
        title=f"Synthetic {number}",
        api_key=parent.data[CONF_API_KEY],
        latitude=float(number),
        longitude=2.0,
    )
    legacy.add_to_hass(hass)
    assert await async_migrate_entry(hass, legacy)
    return next(
        subentry.subentry_id
        for subentry in parent.subentries.values()
        if subentry.data.get("legacy_entry_id") == legacy.entry_id
    )


def _assert_accounted(parent):
    """Every persisted eligible location has one runtime outcome."""
    assert parent.state is ConfigEntryState.LOADED
    runtime = parent.runtime_data
    assert set(parent.subentries) == set(runtime.locations) | set(
        runtime.failed_locations
    )
    assert not set(runtime.locations) & set(runtime.failed_locations)
    assert len({id(loc.coordinator) for loc in runtime.locations.values()}) == len(
        runtime.locations
    )
    for subentry_id, location in runtime.locations.items():
        assert location.subentry_id == location.coordinator.subentry_id == subentry_id
        assert location.coordinator.entry_id == parent.entry_id


def _assert_finished(hass):
    assert not hass.data.get(f"{DOMAIN}_migration_reconciliation")


async def test_loaded_parent_coalesces_committed_migrations(
    hass, migration_parent, monkeypatch
):
    """Two commits before the worker runs require just one reload."""
    parent, controls = migration_parent
    assert await hass.config_entries.async_setup(parent.entry_id)
    reload = AsyncMock(wraps=hass.config_entries.async_reload)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    await _merge(hass, parent, 1)
    await _merge(hass, parent, 3)
    await hass.async_block_till_done()
    _assert_accounted(parent)
    assert len(parent.runtime_data.locations) == 3
    assert reload.await_count == 1
    assert controls["requests"] == 4
    _assert_finished(hass)


async def test_migration_during_reconciliation_is_not_lost(
    hass, migration_parent, monkeypatch
):
    """A commit after the reload snapshot requires one further generation."""
    parent, controls = migration_parent
    assert await hass.config_entries.async_setup(parent.entry_id)
    started, release = asyncio.Event(), asyncio.Event()

    async def blocked(_url, **_kwargs):
        started.set()
        await release.wait()

    controls["callback"] = blocked
    reload = AsyncMock(wraps=hass.config_entries.async_reload)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    await _merge(hass, parent, 1)
    try:
        async with asyncio.timeout(15):
            await started.wait()
        assert parent.state is ConfigEntryState.SETUP_IN_PROGRESS
        await _merge(hass, parent, 3)
        await _merge(hass, parent, 5)
    finally:
        release.set()
    await hass.async_block_till_done()
    _assert_accounted(parent)
    assert len(parent.runtime_data.locations) == 4
    assert reload.await_count == 2
    _assert_finished(hass)


@pytest.mark.parametrize("action", ["unload", "remove", "remove_subentry"])
async def test_pending_reconciliation_respects_removal(
    hass, migration_parent, monkeypatch, action
):
    """Queued migration work must not reverse an explicit lifecycle change."""
    parent, _ = migration_parent
    assert await hass.config_entries.async_setup(parent.entry_id)
    reload = AsyncMock(wraps=hass.config_entries.async_reload)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    target = await _merge(hass, parent, 1)
    observed_states = []
    unsubscribe = parent.async_on_state_change(
        lambda: observed_states.append(parent.state)
    )
    if action == "remove_subentry":
        hass.config_entries.async_remove_subentry(parent, target)
    elif action == "unload":
        assert await hass.config_entries.async_unload(parent.entry_id)
    else:
        await hass.config_entries.async_remove(parent.entry_id)
    await hass.async_block_till_done()
    unsubscribe()
    assert reload.await_count == 0
    if action == "remove_subentry":
        _assert_accounted(parent)
    else:
        assert parent.state is ConfigEntryState.NOT_LOADED
        assert ConfigEntryState.UNLOAD_IN_PROGRESS in observed_states
    _assert_finished(hass)


@pytest.mark.parametrize("disabled", [False, True])
async def test_migration_does_not_start_inactive_parent(
    hass, migration_parent, disabled
):
    """Persisted locations await the next explicit setup of inactive parents."""
    parent, controls = migration_parent
    if disabled:
        await hass.config_entries.async_set_disabled_by(
            parent.entry_id, ConfigEntryDisabler.USER
        )
    await _merge(hass, parent, 1)
    await hass.async_block_till_done()
    assert len(parent.subentries) == 2
    assert parent.state is ConfigEntryState.NOT_LOADED
    assert controls["requests"] == 0
    _assert_finished(hass)


@pytest.mark.parametrize("failure", ["local", "retry", "auth"])
async def test_reconciliation_failures_do_not_loop(
    hass, migration_parent, monkeypatch, failure
):
    """Failed locations count; retry and auth remain owned by HA."""
    parent, controls = migration_parent
    assert await hass.config_entries.async_setup(parent.entry_id)

    async def fail(url, **_kwargs):
        if failure == "local" and float(url.query["location.latitude"]) != 1.0:
            return None
        return CallbackResult(
            status=400,
            payload={
                "error": {
                    "message": (
                        "API key expired. Please renew the API key."
                        if failure == "auth"
                        else "Synthetic location unavailable"
                    )
                }
            },
        )

    controls["callback"] = fail
    reload = AsyncMock(wraps=hass.config_entries.async_reload)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    target = await _merge(hass, parent, 1)
    await hass.async_block_till_done()
    if failure == "local":
        _assert_accounted(parent)
        assert target in parent.runtime_data.failed_locations
        # Existing local retry policy may retry once, independently of migration.
        assert 1 <= reload.await_count <= 2
    else:
        expected = (
            ConfigEntryState.SETUP_ERROR
            if failure == "auth"
            else ConfigEntryState.SETUP_RETRY
        )
        assert parent.state is expected
        assert reload.await_count == 1
        flows_before = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        await _merge(hass, parent, 3)
        await hass.async_block_till_done()
        assert parent.state is expected
        assert reload.await_count == 1
        assert (
            hass.config_entries.flow.async_progress_by_handler(DOMAIN) == flows_before
        )
        assert bool(flows_before) is (failure == "auth")
    _assert_finished(hass)


@pytest.mark.parametrize("failure", ["retry", "auth", "cancel"])
async def test_migration_during_failed_setup_leaves_recovery_to_ha(
    hass,
    migration_parent,
    monkeypatch,
    failure,
):
    """A pending commit must not revive failed or cancelled initial setup."""
    parent, controls = migration_parent
    started, release = asyncio.Event(), asyncio.Event()

    async def fail(_url, **_kwargs):
        started.set()
        await release.wait()
        return CallbackResult(
            status=400,
            payload={
                "error": {
                    "message": (
                        "API key expired. Please renew the API key."
                        if failure == "auth"
                        else "Synthetic location unavailable"
                    )
                }
            },
        )

    controls["callback"] = fail
    reload = AsyncMock(wraps=hass.config_entries.async_reload)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    setup = asyncio.create_task(hass.config_entries.async_setup(parent.entry_id))
    try:
        async with asyncio.timeout(15):
            await started.wait()
        await _merge(hass, parent, 1)
        if failure == "cancel":
            setup.cancel()
    finally:
        release.set()
    await asyncio.gather(setup, return_exceptions=True)
    await hass.async_block_till_done()
    assert parent.state in (ConfigEntryState.SETUP_ERROR, ConfigEntryState.SETUP_RETRY)
    assert reload.await_count == 0
    assert len(parent.subentries) == 2
    _assert_finished(hass)


async def test_loaded_parent_reauth_is_not_aborted(hass, migration_parent, monkeypatch):
    """A coordinator may start reauth while its parent still remains loaded."""
    parent, _ = migration_parent
    assert await hass.config_entries.async_setup(parent.entry_id)
    parent.async_start_reauth(hass)
    await hass.async_block_till_done()
    before = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(before) == 1
    reload = AsyncMock(wraps=hass.config_entries.async_reload)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    await _merge(hass, parent, 1)
    await hass.async_block_till_done()
    assert reload.await_count == 0
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == before
    _assert_finished(hass)


async def test_reconciliation_cancellation_cleans_bookkeeping(hass, migration_parent):
    """Cancellation of an in-flight reconciliation leaves no worker/listener."""
    parent, controls = migration_parent
    assert await hass.config_entries.async_setup(parent.entry_id)
    started, release = asyncio.Event(), asyncio.Event()

    async def blocked(_url, **_kwargs):
        started.set()
        await release.wait()

    controls["callback"] = blocked
    await _merge(hass, parent, 1)
    try:
        async with asyncio.timeout(15):
            await started.wait()
        worker = hass.data[f"{DOMAIN}_migration_reconciliation"][parent.entry_id].task
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
    finally:
        release.set()
    await hass.async_block_till_done()
    _assert_finished(hass)
    # Explicit recovery remains possible and accounts for the committed location.
    assert await hass.config_entries.async_reload(parent.entry_id)
    await hass.async_block_till_done()
    _assert_accounted(parent)


async def test_simultaneous_legacy_setups_converge(hass, migration_parent):
    """Independent legacy setup tasks converge on the same loaded parent."""
    parent, _ = migration_parent
    assert await hass.config_entries.async_setup(parent.entry_id)

    async def setup_legacy(number):
        legacy = legacy_config_entry(
            entry_id=f"simultaneous-{number}",
            title=f"Synthetic {number}",
            api_key=parent.data[CONF_API_KEY],
            latitude=float(number),
            longitude=2.0,
        )
        legacy.add_to_hass(hass)
        await hass.config_entries.async_setup(legacy.entry_id)

    async with asyncio.timeout(15):
        await asyncio.gather(setup_legacy(1), setup_legacy(3), setup_legacy(5))
        await hass.async_block_till_done()
    _assert_accounted(parent)
    assert len(parent.subentries) == 4
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    _assert_finished(hass)


@pytest.mark.parametrize("action", ["disable", "remove"])
async def test_external_stop_during_reconciliation_wins(hass, migration_parent, action):
    """An external stop waiting on HA's setup lock is never undone."""
    parent, controls = migration_parent
    assert await hass.config_entries.async_setup(parent.entry_id)
    started, release = asyncio.Event(), asyncio.Event()

    async def blocked(_url, **_kwargs):
        started.set()
        await release.wait()

    controls["callback"] = blocked
    await _merge(hass, parent, 1)
    try:
        async with asyncio.timeout(15):
            await started.wait()
        await _merge(hass, parent, 3)
        stop = hass.async_create_task(
            hass.config_entries.async_set_disabled_by(
                parent.entry_id, ConfigEntryDisabler.USER
            )
            if action == "disable"
            else hass.config_entries.async_remove(parent.entry_id)
        )
    finally:
        release.set()
    async with asyncio.timeout(15):
        await stop
        await hass.async_block_till_done()
    assert parent.state is ConfigEntryState.NOT_LOADED
    _assert_finished(hass)
