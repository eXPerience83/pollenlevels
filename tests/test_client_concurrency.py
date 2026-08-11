"""Concurrency tests for the Google Pollen API client."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.pollenlevels.client import GooglePollenApiClient


async def _fetch(client: GooglePollenApiClient) -> dict[str, Any]:
    """Run one representative client fetch."""
    return await client.async_fetch_pollen_data(
        latitude=1.0,
        longitude=2.0,
        days=5,
        language_code=None,
    )


@pytest.mark.asyncio
async def test_shared_client_serializes_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent calls through one client should never overlap."""
    client = GooglePollenApiClient(object(), "test")  # type: ignore[arg-type]
    first_entered = asyncio.Event()
    second_entered = asyncio.Event()
    release_first = asyncio.Event()
    calls = 0
    active = 0
    max_active = 0

    async def _fake_fetch(**_kwargs: Any) -> dict[str, Any]:
        nonlocal active, calls, max_active
        calls += 1
        call_number = calls
        active += 1
        max_active = max(max_active, active)
        try:
            if call_number == 1:
                first_entered.set()
                await release_first.wait()
            else:
                second_entered.set()
            return {"call": call_number}
        finally:
            active -= 1

    monkeypatch.setattr(client, "_async_fetch_pollen_data", _fake_fetch)

    first_task = asyncio.create_task(_fetch(client))
    await first_entered.wait()

    second_task = asyncio.create_task(_fetch(client))
    await asyncio.sleep(0)

    assert calls == 1
    assert second_entered.is_set() is False
    assert max_active == 1

    release_first.set()
    results = await asyncio.gather(first_task, second_task)

    assert results == [{"call": 1}, {"call": 2}]
    assert second_entered.is_set() is True
    assert max_active == 1


@pytest.mark.asyncio
async def test_separate_clients_do_not_block_each_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Independent client instances should retain independent concurrency."""
    client_a = GooglePollenApiClient(object(), "key-a")  # type: ignore[arg-type]
    client_b = GooglePollenApiClient(object(), "key-b")  # type: ignore[arg-type]
    entered_a = asyncio.Event()
    entered_b = asyncio.Event()
    release = asyncio.Event()

    async def _fetch_a(**_kwargs: Any) -> dict[str, Any]:
        entered_a.set()
        await release.wait()
        return {"client": "a"}

    async def _fetch_b(**_kwargs: Any) -> dict[str, Any]:
        entered_b.set()
        await release.wait()
        return {"client": "b"}

    monkeypatch.setattr(client_a, "_async_fetch_pollen_data", _fetch_a)
    monkeypatch.setattr(client_b, "_async_fetch_pollen_data", _fetch_b)

    task_a = asyncio.create_task(_fetch(client_a))
    task_b = asyncio.create_task(_fetch(client_b))

    await asyncio.wait_for(
        asyncio.gather(entered_a.wait(), entered_b.wait()),
        timeout=1.0,
    )

    release.set()
    assert await asyncio.gather(task_a, task_b) == [
        {"client": "a"},
        {"client": "b"},
    ]


@pytest.mark.asyncio
async def test_cancelled_lock_wait_does_not_leak_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation while waiting for the client lock should propagate safely."""
    client = GooglePollenApiClient(object(), "test")  # type: ignore[arg-type]
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    calls = 0

    async def _fake_fetch(**_kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        call_number = calls
        if call_number == 1:
            first_entered.set()
            await release_first.wait()
        return {"call": call_number}

    monkeypatch.setattr(client, "_async_fetch_pollen_data", _fake_fetch)

    first_task = asyncio.create_task(_fetch(client))
    await first_entered.wait()

    waiting_task = asyncio.create_task(_fetch(client))
    await asyncio.sleep(0)
    waiting_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await waiting_task

    assert calls == 1

    release_first.set()
    assert await first_task == {"call": 1}
    assert await _fetch(client) == {"call": 2}
    assert calls == 2
