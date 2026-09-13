from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .coordinator import PollenDataUpdateCoordinator


@dataclass(slots=True)
class PollenLocationRuntime:
    """Runtime container for one configured pollen location."""

    subentry_id: str
    coordinator: PollenDataUpdateCoordinator


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

    locations: dict[str, PollenLocationRuntime] = field(default_factory=dict)
    failed_locations: dict[str, PollenLocationSetupFailure] = field(default_factory=dict)


if TYPE_CHECKING:
    PollenLevelsConfigEntry = ConfigEntry[PollenLevelsRuntimeData]
else:
    PollenLevelsConfigEntry = ConfigEntry
