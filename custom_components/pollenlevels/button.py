"""Button platform for per-entry manual updates."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .runtime import PollenLevelsConfigEntry, PollenLevelsRuntimeData

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _hass,
    config_entry: PollenLevelsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Pollen Levels update button for one config entry."""
    runtime = cast(
        PollenLevelsRuntimeData | None, getattr(config_entry, "runtime_data", None)
    )
    if runtime is None:
        return

    async_add_entities([PollenLevelsUpdateButton(runtime.coordinator)])


class PollenLevelsUpdateButton(CoordinatorEntity, ButtonEntity):
    """Button entity to manually refresh a single location."""

    _attr_has_entity_name = True
    _attr_translation_key = "update_now"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        """Initialize update button entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_update_now"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{coordinator.entry_id}_meta")},
            "manufacturer": "Google",
            "model": "Pollen API",
            "translation_key": "info",
            "translation_placeholders": {
                "title": coordinator.entry_title,
                "latitude": f"{coordinator.lat:.2f}",
                "longitude": f"{coordinator.lon:.2f}",
            },
        }

    async def async_press(self) -> None:
        """Refresh this config entry's coordinator."""
        try:
            await self.coordinator.async_request_refresh()
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Manual update button refresh failed for entry %s (%s)",
                self.coordinator.entry_id,
                type(err).__name__,
            )
            raise HomeAssistantError("Failed to refresh pollen data") from err
