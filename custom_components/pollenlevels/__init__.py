"""Initialize Pollen Levels integration.

Notes:
- Adds a top-level INFO log when the force_update service is invoked to aid debugging.
- Registers an options update listener to reload the entry so interval/language changes
  take effect immediately without reinstalling.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from typing import Any, cast

import homeassistant.helpers.config_validation as cv
import voluptuous as vol  # Service schema validation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import GooglePollenApiClient
from .const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .runtime import PollenLevelsConfigEntry, PollenLevelsRuntimeData
from .sensor import ForecastSensorMode, PollenDataUpdateCoordinator

# Ensure YAML config is entry-only for this domain (no YAML schema).
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)

# ---- Service -------------------------------------------------------------


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register force_update service."""
    _LOGGER.debug("PollenLevels async_setup called")

    async def handle_force_update_service(call: ServiceCall) -> None:
        """Refresh pollen data for all entries."""
        # Added: top-level log to confirm manual trigger for easier debugging.
        _LOGGER.info("Executing force_update service for all Pollen Levels entries")
        entries = list(hass.config_entries.async_entries(DOMAIN))
        tasks: list[Awaitable[None]] = []
        task_entries: list[ConfigEntry] = []
        for entry in entries:
            runtime = getattr(entry, "runtime_data", None)
            coordinator = getattr(runtime, "coordinator", None)
            if coordinator:
                _LOGGER.info("Trigger manual refresh for entry %s", entry.entry_id)
                tasks.append(coordinator.async_refresh())
                task_entries.append(entry)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for entry, result in zip(task_entries, results, strict=False):
                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "Manual refresh failed for entry %s: %r",
                        entry.entry_id,
                        result,
                    )

    # Enforce empty payload for the service; reject unknown fields for clearer errors.
    hass.services.async_register(
        DOMAIN, "force_update", handle_force_update_service, schema=vol.Schema({})
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: PollenLevelsConfigEntry
) -> bool:
    """Forward config entry to sensor platform and register options listener."""
    _LOGGER.debug(
        "PollenLevels async_setup_entry for entry_id=%s title=%s",
        entry.entry_id,
        entry.title,
    )

    options = entry.options or {}
    hours = int(
        options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
    )
    forecast_days = int(
        options.get(
            CONF_FORECAST_DAYS,
            entry.data.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS),
        )
    )
    language = options.get(CONF_LANGUAGE_CODE, entry.data.get(CONF_LANGUAGE_CODE))
    mode = options.get(CONF_CREATE_FORECAST_SENSORS, ForecastSensorMode.NONE)
    create_d1 = mode in (ForecastSensorMode.D1, ForecastSensorMode.D1_D2)
    create_d2 = mode == ForecastSensorMode.D1_D2

    api_key = entry.data.get(CONF_API_KEY)
    if not api_key:
        raise ConfigEntryAuthFailed("Missing API key")

    raw_title = entry.title or ""
    clean_title = raw_title.strip() or DEFAULT_ENTRY_TITLE

    session = async_get_clientsession(hass)
    client = GooglePollenApiClient(session, api_key)

    coordinator = PollenDataUpdateCoordinator(
        hass=hass,
        api_key=api_key,
        lat=cast(float, entry.data[CONF_LATITUDE]),
        lon=cast(float, entry.data[CONF_LONGITUDE]),
        hours=hours,
        language=language,
        entry_id=entry.entry_id,
        entry_title=clean_title,
        forecast_days=forecast_days,
        create_d1=create_d1,
        create_d2=create_d2,
        client=client,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except ConfigEntryNotReady:
        raise
    except Exception as err:
        _LOGGER.exception("Error forwarding entry setups: %s", err)
        raise ConfigEntryNotReady from err

    entry.runtime_data = PollenLevelsRuntimeData(coordinator=coordinator, client=client)

    try:
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    except ConfigEntryAuthFailed:
        raise
    except ConfigEntryNotReady:
        raise
    except Exception as err:
        _LOGGER.exception("Error forwarding entry setups: %s", err)
        raise ConfigEntryNotReady from err

    # Ensure options updates (interval/language/forecast settings) trigger reload.
    entry.async_on_unload(entry.add_update_listener(_update_listener))

    _LOGGER.info("PollenLevels integration loaded successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry and remove coordinator reference."""
    _LOGGER.debug(
        "PollenLevels async_unload_entry called for entry_id=%s", entry.entry_id
    )
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    return unloaded


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update by reloading the entry.

    Home Assistant calls this listener after the user saves Options.
    Reloading recreates the coordinator with the new settings.
    """
    _LOGGER.debug("Reloading entry %s after options update", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
