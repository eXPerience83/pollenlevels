"""Sensor platform for Pollen Levels integration."""
import logging
from datetime import timedelta

import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.entity import Entity
from homeassistant.const import ATTR_ATTRIBUTION

from .const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensors for each pollen code returned by the API."""
    api_key = entry.data[CONF_API_KEY]
    lat = entry.data[CONF_LATITUDE]
    lon = entry.data[CONF_LONGITUDE]
    interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    coordinator = PollenDataUpdateCoordinator(
        hass, api_key, lat, lon, interval, entry.entry_id
    )
    # Primera actualización forzada
    await coordinator.async_config_entry_first_refresh()

    # Genera un sensor por cada código presente en los datos
    sensors = [
        PollenSensor(coordinator, code, info)
        for code, info in coordinator.data.items()
    ]
    _LOGGER.debug("Creating %d sensors: %s", len(sensors), list(coordinator.data.keys()))
    async_add_entities(sensors, True)


class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch pollen data periodically."""

    def __init__(self, hass, api_key, lat, lon, hours, entry_id):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=hours),
        )
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.entry_id = entry_id
        self.data = {}

    async def _async_update_data(self):
        """Fetch pollen data via forecast:lookup?days=1."""
        url = (
            f"https://pollen.googleapis.com/v1/forecast:lookup"
            f"?key={self.api_key}"
            f"&location.latitude={self.lat:.6f}"
            f"&location.longitude={self.lon:.6f}"
            f"&days=1"
        )
        _LOGGER.debug("Fetching pollen data from: %s", url)

        try:
            async with aiohttp.ClientSession() as session:
                resp = await session.get(url)
                if resp.status == 403:
                    raise UpdateFailed("Invalid API key")
                if resp.status == 429:
                    raise UpdateFailed("Quota exceeded")
                if resp.status != 200:
                    raise UpdateFailed(f"HTTP {resp.status}")
                payload = await resp.json()
        except Exception as err:
            raise UpdateFailed(err)

        items = {}
        daily = payload.get("dailyInfo")
        if isinstance(daily, list) and daily:
            info = daily[0]
            for section in ("pollenTypeInfo", "plantInfo"):
                for item in info.get(section, []) or []:
                    code = item.get("code")
                    index = item.get("indexInfo")
                    if not code or not isinstance(index, dict):
                        continue
                    items[code] = {
                        "value": index.get("value"),
                        "category": index.get("category"),
                        "display_name": item.get("displayName"),
                        "in_season": item.get("inSeason", None),
                    }

        self.data = items
        _LOGGER.debug("Updated pollen varieties: %s", self.data)
        return self.data


class PollenSensor(Entity):
    """Sensor for an individual pollen code."""

    def __init__(self, coordinator: PollenDataUpdateCoordinator, code: str, info: dict):
        self.coordinator = coordinator
        self.code = code
        self.info = info

    @property
    def unique_id(self) -> str:
        """Unique ID based on entry and code."""
        return f"{self.coordinator.entry_id}_{self.code}"

    @property
    def name(self) -> str:
        """Name shown in the UI."""
        dn = self.info.get("display_name") or self.code.capitalize()
        return f"Pollen {dn}"

    @property
    def state(self):
        """Return the current pollen index value."""
        return self.info.get("value")

    @property
    def icon(self) -> str:
        """Use the pollen icon for all sensors."""
        return "mdi:flower-pollen"

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        attrs = {"category": self.info.get("category")}
        if self.info.get("in_season") is not None:
            attrs["in_season"] = self.info.get("in_season")
        attrs[ATTR_ATTRIBUTION] = "Data provided by Google Maps Pollen API"
        return attrs

    @property
    def device_info(self) -> dict:
        """Register all sensors under one device (the location)."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.entry_id)},
            "name": f"Pollen Levels ({self.coordinator.lat:.6f},{self.coordinator.lon:.6f})",
            "manufacturer": "Google",
            "model": "Pollen API",
        }
