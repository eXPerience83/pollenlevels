"""Initialize Pollen Levels integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ---- Service -------------------------------------------------------------

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register force_update service."""
    _LOGGER.debug("PollenLevels async_setup called")

    async def handle_force_update_service(call):
        """Refresh pollen data for all entries."""
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if coordinator:
                _LOGGER.info(
                    "Trigger manual refresh for entry %s", entry.entry_id
                )
                # Wait until the update completes
                await coordinator.async_refresh()

    hass.services.async_register(
        DOMAIN, "force_update", handle_force_update_service, schema=None
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Forward config entry to sensor platform."""
    _LOGGER.debug(
        "PollenLevels async_setup_entry for entry_id=%s title=%s",
        entry.entry_id,
        entry.title,
    )

    try:
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    except Exception as err:
        _LOGGER.error("Error forwarding entry setups: %s", err)
        raise ConfigEntryNotReady from err

    _LOGGER.info("PollenLevels integration loaded successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry and remove coordinator reference."""
    _LOGGER.debug(
        "PollenLevels async_unload_entry called for entry_id=%s", entry.entry_id
    )
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unloaded and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
