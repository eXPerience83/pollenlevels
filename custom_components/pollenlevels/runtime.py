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


@dataclass(slots=True)
class PollenLocationSetupFailure:
    """Runtime metadata for one location that could not finish setup."""

    subentry_id: str
    title: str
    reason: str
    error_type: str


@dataclass(slots=True, init=False)
class PollenLevelsRuntimeData:
    """Runtime container for a Pollen Levels parent config entry."""

    client: GooglePollenApiClient
    locations: dict[str, PollenLocationRuntime]
    failed_locations: dict[str, PollenLocationSetupFailure]

    def __init__(
        self,
        *,
        client: GooglePollenApiClient,
        locations: dict[str, PollenLocationRuntime] | None = None,
        failed_locations: dict[str, PollenLocationSetupFailure] | None = None,
    ) -> None:
        """Initialize runtime data for configured pollen locations."""
        self.client = client
        self.failed_locations = failed_locations or {}
        self.locations = locations if locations is not None else {}


if TYPE_CHECKING:
    PollenLevelsConfigEntry = ConfigEntry[PollenLevelsRuntimeData]
else:
    PollenLevelsConfigEntry = ConfigEntry
