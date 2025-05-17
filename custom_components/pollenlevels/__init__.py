"""Home Assistant Pollen Levels integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the integration (no YAML support)."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the integration from a config entry."""
    try:
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    except Exception as err:
        raise ConfigEntryNotReady from err
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    return True
