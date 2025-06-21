"""Provide button to manually refresh pollen data."""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up refresh button for Pollen Levels."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RefreshButton(coordinator, hass)], True)


class RefreshButton(CoordinatorEntity, ButtonEntity):
    """Represent manual refresh button."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, hass):
        """Initialize refresh button."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.hass = hass

    @property
    def unique_id(self) -> str:
        """Return unique ID for refresh button."""
        return f"{self.coordinator.entry_id}_refresh"

    @property
    def name(self) -> str:
        """Return name for refresh button."""
        return "Refresh Now"

    @property
    def icon(self) -> str:
        """Return icon for refresh button."""
        return "mdi:refresh"

    @property
    def device_info(self) -> dict:
        """Associate button with Pollen Info device."""
        device_id = f"{self.coordinator.entry_id}_meta"
        device_name = f"Pollen Info ({self.coordinator.lat:.6f},{self.coordinator.lon:.6f})"
        return {
            "identifiers": {(DOMAIN, device_id)},
            "name": device_name,
            "manufacturer": "Google",
            "model": "Pollen API",
        }

    async def async_press(self) -> None:
        """Trigger manual pollen refresh."""
        _LOGGER.debug("Refresh button pressed for %s", self.coordinator.entry_id)
        await self.hass.services.async_call(DOMAIN, "force_update", {})
