"""Sensor platform for Pollen Levels integration."""
import logging
from datetime import timedelta
import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.entity import Entity
from .const import (
    CONF_API_KEY, 
    CONF_LATITUDE, 
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL, 
    DEFAULT_UPDATE_INTERVAL,
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
        hass, api_key, lat, lon, interval
    )
    await coordinator.async_config_entry_first_refresh()
    
    # Create sensors only for allergens present in plantInfo
    plant_codes = [
        item["code"] for item in coordinator.data.values()
    ]
    sensors = [PollenSensor(coordinator, code) for code in plant_codes]
    
    _LOGGER.debug("Creating %d sensors: %s", len(sensors), plant_codes)
    async_add_entities(sensors, True)

class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch pollen data periodically."""
    def __init__(self, hass, api_key, lat, lon, hours):
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(hours=hours)
        )
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
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
        
        result = {
            item["code"]: {
                "value": item.get("indexInfo", {}).get("value"),
                "category": item.get("indexInfo", {}).get("category"),
                "timestamp": daily[0].get("date", {}),
                "display_name": item.get("displayName")
            }
            for item in plant_list
            if item.get("indexInfo")
        }
        
        self.data = result
        _LOGGER.debug("Updated pollen varieties: %s", self.data)
        return self.data

class PollenSensor(Entity):
    """Sensor for an individual plant variety."""
    def __init__(self, coordinator, code):
        self.coordinator = coordinator
        self.code = code
        self._name = self.coordinator.data[code]["display_name"]

    @property
    def name(self):
        return f"Pollen {self._name}"

    @property
    def state(self):
        info = self.coordinator.data.get(self.code)
        return info.get("value") if info else None

    @property
    def icon(self):
        return "mdi:flower-pollen"

    @property
    def extra_state_attributes(self):
        info = self.coordinator.data.get(self.code)
        if not info:
            return {}
        
        date_info = info["timestamp"]
        try:
            iso_date = f"{date_info['year']}-{date_info['month']}-{date_info['day']}"
        except:
            iso_date = "N/A"
        
        return {
            "category": info.get("category"),
            "timestamp": iso_date,
            "location": f"{self.coordinator.lat:.6f},{self.coordinator.lon:.6f}"
        }
