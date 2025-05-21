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
    await coordinator.async_config_entry_first_refresh()

    sensors = [
        PollenSensor(coordinator, code)
        for code in coordinator.data_keys
    ]
    _LOGGER.debug(
        "Creating %d sensors: %s", len(sensors), coordinator.data_keys
    )
    async_add_entities(sensors, True)


class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch pollen data periodically."""

    def __init__(self, hass, api_key, lat, lon, hours, entry_id):
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry_id}",
            update_interval=timedelta(hours=hours),
        )
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.entry_id = entry_id
        self.data = {}
        self.data_keys = []

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

        new_data = {}
        new_keys = []
        daily = payload.get("dailyInfo")
        if isinstance(daily, list) and daily:
            info = daily[0]
            for section in ("pollenTypeInfo", "plantInfo"):
                for item in info.get(section, []) or []:
                    code = item.get("code")
                    index = item.get("indexInfo")
                    if not code:
                        continue
                    if isinstance(index, dict):
                        new_data[code] = {
                            "value": index.get("value"),
                            "category": index.get("category"),
                        }
                    else:
                        new_data[code] = {"value": None, "category": None}
                    new_keys.append(code)

        self.data = new_data
        self.data_keys = new_keys
        _LOGGER.debug("Updated pollen varieties: %s", self.data)
        return self.data


class PollenSensor(Entity):
    """Sensor for an individual pollen code."""

    def __init__(self, coordinator: PollenDataUpdateCoordinator, code: str):
        self.coordinator = coordinator
        self.code = code

    @property
    def unique_id(self) -> str:
        """Unique ID based on entry and code."""
        return f"{self.coordinator.entry_id}_{self.code}"

    @property
    def name(self) -> str:
        """Name shown in the UI."""
        return f"Pollen {self.code.capitalize()}"

    @property
    def state(self):
        """Return the current pollen index value (or None)."""
        return self.coordinator.data.get(self.code, {}).get("value")

    @property
    def icon(self) -> str:
        """Use the pollen icon for all sensors."""
        return "mdi:flower-pollen"

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes: category and attribution."""
        info = self.coordinator.data.get(self.code, {})
        attrs = {"category": info.get("category")}
        attrs[ATTR_ATTRIBUTION] = "Data provided by Google Maps Pollen API"
        return attrs

    @property
    def device_info(self) -> dict:
        """Group all sensors under a single location device."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.entry_id)},
            "name": f"Pollen Levels ({self.coordinator.lat:.6f},{self.coordinator.lon:.6f})",
            "manufacturer": "Google",
            "model": "Pollen API",
        }
