"""Reconcile committed migration locations with an active parent's runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .runtime import PollenLevelsConfigEntry

_DATA_KEY = f"{DOMAIN}_migration_reconciliation"


@dataclass
class _Reconciliation:
    """One short-lived reconciliation shared by migrations of the same parent."""

    hass: HomeAssistant
    entry: PollenLevelsConfigEntry
    targets: set[str] = field(default_factory=set)
    generation: int = 0
    task: asyncio.Task[None] | None = None
    unsubscribe: Callable[[], None] | None = None

    def close(self) -> None:
        """Release listeners and bookkeeping, including on external unload."""
        if self.unsubscribe is not None:
            # HA iterates state listeners directly. Removing ourselves inside
            # that callback would skip the next subscriber in the same dispatch.
            self.hass.loop.call_soon(self.unsubscribe)
            self.unsubscribe = None
        pending = self.hass.data[_DATA_KEY]
        if pending.get(self.entry.entry_id) is self:
            del pending[self.entry.entry_id]
        if self.task is not None and self.task is not asyncio.current_task():
            self.task.cancel()

    def state_changed(self) -> None:
        """Wait for setup, but never restart an externally stopped parent."""
        if self.unsubscribe is None:
            return
        # async_reload changes state synchronously in its calling task. Its own
        # unload must not cancel it; an external unload must cancel queued work.
        if self.task is not None and self.task is asyncio.current_task():
            return
        if self.entry.disabled_by is not None or self.entry.state not in (
            ConfigEntryState.LOADED,
            ConfigEntryState.SETUP_IN_PROGRESS,
        ):
            self.close()
        elif self.entry.state is ConfigEntryState.LOADED and self.task is None:
            # Do not use an entry-owned task: it would cancel itself on reload.
            # Defer execution to coalesce requests and leave HA's setup stack.
            self.task = self.hass.async_create_task(
                self.run(), "pollenlevels migration reconciliation", eager_start=False
            )

    async def run(self) -> None:
        """Reload at most once per committed generation, without holding locks."""
        try:
            while (
                self.entry.state is ConfigEntryState.LOADED
                and self.entry.disabled_by is None
            ):
                if self.hass.config_entries.flow.async_progress_by_handler(
                    DOMAIN,
                    match_context={
                        "entry_id": self.entry.entry_id,
                        "source": SOURCE_REAUTH,
                    },
                ):
                    return
                runtime = self.entry.runtime_data
                accounted = set(runtime.locations) | set(runtime.failed_locations)
                if not (self.targets & self.entry.subentries.keys()) - accounted:
                    return
                generation = self.generation
                await self.hass.config_entries.async_reload(self.entry.entry_id)
                # A legitimate setup failure is not a missing-location signal.
                # Only a new committed migration can justify another reload.
                if generation == self.generation:
                    return
        finally:
            self.close()


def async_reconcile_migrated_locations(
    hass: HomeAssistant, entry: PollenLevelsConfigEntry, subentry_ids: set[str]
) -> None:
    """Request reconciliation only after registry reassociation has succeeded."""
    if entry.disabled_by is not None or entry.state not in (
        ConfigEntryState.LOADED,
        ConfigEntryState.SETUP_IN_PROGRESS,
    ):
        return
    pending = hass.data.setdefault(_DATA_KEY, {})
    if (reconciliation := pending.get(entry.entry_id)) is None:
        reconciliation = pending[entry.entry_id] = _Reconciliation(hass, entry)
        reconciliation.unsubscribe = entry.async_on_state_change(
            reconciliation.state_changed
        )
    reconciliation.targets.update(subentry_ids)
    reconciliation.generation += 1
    reconciliation.state_changed()
