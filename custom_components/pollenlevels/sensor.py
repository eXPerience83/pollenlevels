"""Sensor platform for Pollen Levels integration."""
import logging
from datetime import timedelta
import aiohttp

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.const import ATTR_ATTRIBUTION

from .const import (
    CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL,
    DOMAIN
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensors for each plant variety in plantInfo."""
    api_key = entry.data[CONF_API_KEY]
    lat = entry.data[CONF_LATITUDE]
    lon = entry.data[CONF_LONGITUDE]
    interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    coordinator = PollenDataUpdateCoordinator(
        hass, api_key, lat, lon, interval, entry.entry_id
    )
    # Fuerza la primera actualización
    await coordinator.async_config_entry_first_refresh()

    # Creamos un sensor por cada código en los datos recibidos
    sensors = [
        PollenSensor(coordinator, code)
        for code in coordinator.data.keys()
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
            update_method=self._async_update_data,
            update_interval=timedelta(hours=hours),
        )
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.entry_id = entry_id
        self.data = {}

    async def _async_update_data(self):
        """Fetch pollen data using forecast:lookup?days=1."""
        url = (
            f"https://pollen.googleapis.com/v1/forecast:lookup?"
            f"key={self.api_key}"
            f"&location.latitude={self.lat:.6f}"
            f"&location.longitude={self.lon:.6f}"
            f"&days=1"
        )
        _LOGGER.debug("Fetching pollen data from: %s", url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 403:
                        raise UpdateFailed("Invalid API key")
                    if resp.status == 429:
                        raise UpdateFailed("Quota exceeded")
                    if resp.status != 200:
                        raise UpdateFailed(f"HTTP {resp.status}")
                    payload = await resp.json()
        except Exception as err:
            raise UpdateFailed(err)

        daily = payload.get("dailyInfo", [])
        if not daily:
            _LOGGER.warning("No 'dailyInfo' returned")
            return {}

        plant_list = daily[0].get("plantInfo", [])
        if not isinstance(plant_list, list):
            _LOGGER.warning("'plantInfo' not a list")
            return {}

        result = {}
        for item in plant_list:
            code = item.get("code")
            index = item.get("indexInfo")
            if code and index:
                result[code] = {
                    "value": index.get("value"),
                    "category": index.get("category"),
                }

        self.data = result
        _LOGGER.debug("Updated pollen varieties: %s", self.data)
        return self.data

class PollenSensor(Entity):
    """Sensor for an individual plant variety."""
    def __init__(self, coordinator: PollenDataUpdateCoordinator, code: str):
        self.coordinator = coordinator
        self.code = code
        self._attr_attribution = "Data provided by Google Maps Pollen API"

    @property
    def unique_id(self) -> str:
        """Unique ID based on entry_id and plant code."""
        return f"{self.coordinator.entry_id}_{self.code}"

    @property
    def name(self) -> str:
        """Name of the sensor."""
        return f"Pollen {self.code.capitalize()}"

    @property
    def state(self):
        """Return the current pollen index value."""
        info = self.coordinator.data.get(self.code)
        return info.get("value") if info else None

    @property
    def icon(self) -> str:
        """Icon to use in the frontend."""
        return "mdi:flower-pollen"

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        info = self.coordinator.data.get(self.code)
        if not info:
            return {}
        return {
            "category": info.get("category"),
            ATTR_ATTRIBUTION: self._attr_attribution,
        }

    @property
    def device_info(self) -> dict:
        """Register all sensors under a single device (the location)."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.entry_id)},
            "name": f"Pollen Levels ({self.coordinator.lat:.6f},{self.coordinator.lon:.6f})",
            "model": "Google Pollen API",
            "manufacturer": "Google",
        }
