"""Home Assistant Pollen Levels integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration (no YAML support)."""
    _LOGGER.debug("PollenLevels async_setup called")
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    _LOGGER.debug("PollenLevels async_setup_entry called for entry_id=%s title=%s", entry.entry_id, entry.title)

    try:
        # Forward to sensor platform
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    except Exception as err:
        _LOGGER.error("Error forwarding entry setups: %s", err)
        raise ConfigEntryNotReady from err

    _LOGGER.info("PollenLevels integration loaded successfully")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("PollenLevels async_unload_entry called for entry_id=%s", entry.entry_id)
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
