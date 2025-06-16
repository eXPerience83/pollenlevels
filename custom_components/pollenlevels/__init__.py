"""Initialize Pollen Levels integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ---- Service -------------------------------------------------------------

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register services and perform initial setup."""
    _LOGGER.debug("PollenLevels async_setup called")

    async def handle_force_update_service(call):
        """Trigger a manual pollen update for all configured entries."""
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if coordinator:
                _LOGGER.info("Manual pollen update triggered via service for entry %s", entry.entry_id)
                await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "force_update",
        handle_force_update_service,
        schema=None,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    _LOGGER.debug(
        "PollenLevels async_setup_entry called for entry_id=%s title=%s",
        entry.entry_id,
        entry.title,
    )

    try:
        # Forward to sensor platform
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    except Exception as err:  # noqa: BLE001  # runtime safety; noqa comment retained intentionally
        _LOGGER.error("Error forwarding entry setups: %s", err)
        raise ConfigEntryNotReady from err

    _LOGGER.info("PollenLevels integration loaded successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and remove stored coordinator."""
    _LOGGER.debug("PollenLevels async_unload_entry called for entry_id=%s", entry.entry_id)
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unloaded and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
