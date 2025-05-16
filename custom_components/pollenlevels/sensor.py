""" Sensor platform for Pollen Levels integration """
import logging
from datetime import timedelta
import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.entity import Entity
from .const import (
    DOMAIN, CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE,
    CONF_ALLERGENS, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    api_key = entry.data[CONF_API_KEY]
    lat = entry.data[CONF_LATITUDE]
    lon = entry.data[CONF_LONGITUDE]
    allergens = entry.data[CONF_ALLERGENS]
    interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    coordinator = PollenDataUpdateCoordinator(
        hass, api_key, lat, lon, allergens, interval
    )
    await coordinator.async_config_entry_first_refresh()

    sensors = [PollenSensor(coordinator, a) for a in allergens]
    async_add_entities(sensors)

class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """
    Coordinator fetching pollen data periodically
    """
    def __init__(self, hass, api_key, lat, lon, allergens, hours):
        super().__init__(hass, _LOGGER, name=DOMAIN,
                         update_interval=timedelta(hours=hours))
        self.api_key, self.lat, self.lon = api_key, lat, lon
        self.allergens = allergens
        self.data = {}

    async def _async_update_data(self):
        """
        Fetch current pollen levels from Google Maps Pollen API
        """
        url = (f"https://pollenws.googleapis.com/v1/pollen?"
               f"latitude={self.lat}&longitude={self.lon}&key={self.api_key}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise UpdateFailed(f"HTTP {resp.status}")
                    payload = await resp.json()

            filtered = {e["type"]: e for e in payload.get("data", [])
                        if e.get("type") in self.allergens}
            self.data = filtered
            return self.data
        except Exception as e:
            raise UpdateFailed(e)

class PollenSensor(Entity):
    """
    Sensor for individual allergen levels
    """
    def __init__(self, coordinator, allergen):
        self.coordinator = coordinator
        self.allergen = allergen

    @property
    def name(self):
        return f"Pollen {self.allergen.capitalize()}"

    @property
    def state(self):
        entry = self.coordinator.data.get(self.allergen)
        return entry.get("level") if entry else None

    @property
    def icon(self):
        return "mdi:flower-pollen"

    @property
    def extra_state_attributes(self):
        entry = self.coordinator.data.get(self.allergen)
        if not entry: return {}
        return {
            "category": entry.get("category"),
            "unit": entry.get("unit", "grains/m3"),
            "timestamp": entry.get("timestamp"),
            "location": f"{self.coordinator.lat},{self.coordinator.lon}"}

    async def async_update(self):
        await self.coordinator.async_request_refresh()
