from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .client import GooglePollenApiClient
    from .sensor import PollenDataUpdateCoordinator


@dataclass(slots=True)
class PollenLevelsRuntimeData:
    """Runtime container for a Pollen Levels config entry."""

    coordinator: PollenDataUpdateCoordinator
    client: GooglePollenApiClient


if TYPE_CHECKING:
    PollenLevelsConfigEntry = ConfigEntry[PollenLevelsRuntimeData]
else:
    PollenLevelsConfigEntry = ConfigEntry
