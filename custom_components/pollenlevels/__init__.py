"""Initialize Pollen Levels integration."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    CONF_LANGUAGE_CODE,
)
from .sensor import PollenDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


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
                await coordinator.async_refresh()

    hass.services.async_register(DOMAIN, "force_update", handle_force_update_service)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration from config entry."""
    _LOGGER.debug(
        "PollenLevels async_setup_entry entry_id=%s title=%s",
        entry.entry_id,
        entry.title,
    )

    # Create coordinator and do initial fetch
    data = entry.data
    coordinator = PollenDataUpdateCoordinator(
        hass,
        data[CONF_API_KEY],
        data[CONF_LATITUDE],
        data[CONF_LONGITUDE],
        data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        data.get(CONF_LANGUAGE_CODE),
        entry.entry_id,
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Forward to sensor and button platforms
    try:
        await hass.config_entries.async_forward_entry_setups(
            entry, ["sensor", "button"]
        )
    except Exception as err:
        _LOGGER.error("Error forwarding entry setups: %s", err)
        raise ConfigEntryNotReady from err

    _LOGGER.info("PollenLevels integration loaded successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug(
        "PollenLevels async_unload_entry entry_id=%s", entry.entry_id
    )
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, ["sensor", "button"]
    )
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded
