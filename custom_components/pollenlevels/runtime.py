from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .client import GooglePollenApiClient
    from .coordinator import PollenDataUpdateCoordinator


@dataclass(slots=True)
class PollenLocationRuntime:
    """Runtime container for one configured pollen location."""

    subentry_id: str
    coordinator: PollenDataUpdateCoordinator
    legacy_entry_id: str | None = None


@dataclass(slots=True, init=False)
class PollenLevelsRuntimeData:
    """Runtime container for a Pollen Levels parent config entry."""

    client: GooglePollenApiClient
    locations: dict[str, PollenLocationRuntime]

    def __init__(
        self,
        *,
        client: GooglePollenApiClient,
        locations: dict[str, PollenLocationRuntime] | None = None,
        coordinator: PollenDataUpdateCoordinator | None = None,
    ) -> None:
        """Initialize runtime data with v3 locations or a legacy coordinator."""
        self.client = client
        if locations is not None:
            self.locations = locations
            return
        self.locations = {}
        if coordinator is not None:
            subentry_id = getattr(coordinator, "subentry_id", None) or getattr(
                coordinator, "entry_id", "legacy"
            )
            self.locations[subentry_id] = PollenLocationRuntime(
                subentry_id=subentry_id,
                coordinator=coordinator,
                legacy_entry_id=getattr(coordinator, "legacy_entry_id", None),
            )

    @property
    def coordinator(self) -> PollenDataUpdateCoordinator | None:
        """Return the first location coordinator for legacy callers/tests."""
        if not self.locations:
            return None
        return next(iter(self.locations.values())).coordinator


if TYPE_CHECKING:
    PollenLevelsConfigEntry = ConfigEntry[PollenLevelsRuntimeData]
else:
    PollenLevelsConfigEntry = ConfigEntry
