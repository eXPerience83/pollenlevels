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
    CONF_HTTP_REFERER,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    normalize_http_referer,
)
from .coordinator import PollenDataUpdateCoordinator
from .runtime import PollenLevelsConfigEntry, PollenLevelsRuntimeData
from .sensor import ForecastSensorMode
from .util import normalize_sensor_mode

# Ensure YAML config is entry-only for this domain (no YAML schema).
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)

# ---- Service -------------------------------------------------------------


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry data to options when needed."""
    try:
        target_version = 2
        current_version_raw = getattr(entry, "version", 1)
        current_version = (
            current_version_raw if isinstance(current_version_raw, int) else 1
        )
        if current_version >= target_version:
            return True

        new_options = dict(entry.options)
        if CONF_CREATE_FORECAST_SENSORS in new_options:
            mode = new_options.get(CONF_CREATE_FORECAST_SENSORS)
            if mode is None:
                new_options.pop(CONF_CREATE_FORECAST_SENSORS, None)
                mode = entry.data.get(CONF_CREATE_FORECAST_SENSORS)
                if mode is not None:
                    normalized_mode = normalize_sensor_mode(mode, _LOGGER)
                    new_options[CONF_CREATE_FORECAST_SENSORS] = normalized_mode
            else:
                normalized_mode = normalize_sensor_mode(mode, _LOGGER)
                if normalized_mode != mode:
                    new_options[CONF_CREATE_FORECAST_SENSORS] = normalized_mode
        else:
            mode = entry.data.get(CONF_CREATE_FORECAST_SENSORS)
            if mode is not None:
                normalized_mode = normalize_sensor_mode(mode, _LOGGER)
                new_options[CONF_CREATE_FORECAST_SENSORS] = normalized_mode

        if new_options != entry.options:
            hass.config_entries.async_update_entry(
                entry, options=new_options, version=target_version
            )
        else:
            hass.config_entries.async_update_entry(entry, version=target_version)
        return True
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        _LOGGER.exception(
            "Failed to migrate per-day sensor mode to entry options for entry %s "
            "(version=%s)",
            entry.entry_id,
            getattr(entry, "version", None),
        )
        return False


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
                refresh_coro = coordinator.async_request_refresh()
                tasks.append(refresh_coro)
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
    raw_mode = options.get(
        CONF_CREATE_FORECAST_SENSORS,
        entry.data.get(CONF_CREATE_FORECAST_SENSORS, ForecastSensorMode.NONE),
    )
    try:
        mode = ForecastSensorMode(raw_mode)
    except (ValueError, TypeError):
        mode = ForecastSensorMode.NONE
    create_d1 = mode in (ForecastSensorMode.D1, ForecastSensorMode.D1_D2)
    create_d2 = mode == ForecastSensorMode.D1_D2

    api_key = entry.data.get(CONF_API_KEY)
    if not api_key:
        raise ConfigEntryAuthFailed("Missing API key")

    http_referer: str | None = None
    try:
        http_referer = normalize_http_referer(entry.data.get(CONF_HTTP_REFERER))
    except ValueError:
        _LOGGER.warning(
            "Ignoring http_referer for entry %s because it contains newline characters",
            entry.entry_id,
        )

    raw_title = entry.title or ""
    clean_title = raw_title.strip() or DEFAULT_ENTRY_TITLE

    session = async_get_clientsession(hass)
    client = GooglePollenApiClient(session, api_key, http_referer)

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
        _LOGGER.exception("Error during initial data refresh: %s", err)
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
    if unloaded:
        entry.runtime_data = None
    return unloaded


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update by reloading the entry.

    Home Assistant calls this listener after the user saves Options.
    Reloading recreates the coordinator with the new settings.
    """
    _LOGGER.debug("Reloading entry %s after options update", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
