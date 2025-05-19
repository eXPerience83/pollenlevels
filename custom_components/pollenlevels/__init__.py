"""Home Assistant Pollen Levels integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

DOMAIN = "pollenlevels"

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration (no YAML support)."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    try:
        # Creamos la plataforma sensor para cada variedad obtenida dinámicamente
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    except Exception as err:
        raise ConfigEntryNotReady from err
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
