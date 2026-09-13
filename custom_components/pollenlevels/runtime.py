from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .coordinator import PollenDataUpdateCoordinator


@dataclass(slots=True)
class PollenLocationRuntime:
    """Runtime container for one configured pollen location."""

    subentry_id: str
    coordinator: PollenDataUpdateCoordinator
    # Constructor-only compatibility input for older internal/test call sites.
    # The legacy identity is owned by the coordinator and is not stored here.
    legacy_entry_id: InitVar[str | None] = None


@dataclass(slots=True)
class PollenLocationSetupFailure:
    """Runtime metadata for one location that could not finish setup."""

    subentry_id: str
    title: str
    reason: str
    error_type: str


@dataclass(slots=True)
class PollenLevelsRuntimeData:
    """Runtime container for a Pollen Levels parent config entry."""

    # Constructor-only compatibility input for older internal/test call sites.
    # Coordinators own the client reference; the runtime container does not.
    client: InitVar[object | None] = None
    locations: dict[str, PollenLocationRuntime] = field(default_factory=dict)
    failed_locations: dict[str, PollenLocationSetupFailure] = field(
        default_factory=dict
    )


if TYPE_CHECKING:
    PollenLevelsConfigEntry = ConfigEntry[PollenLevelsRuntimeData]
else:
    PollenLevelsConfigEntry = ConfigEntry
