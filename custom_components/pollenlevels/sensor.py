"""Sensor platform for Pollen Levels integration."""
import logging
from datetime import timedelta
import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.entity import Entity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_ALLERGENS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensors for each selected allergen."""
    api_key = entry.data[CONF_API_KEY]
    lat = entry.data[CONF_LATITUDE]
    lon = entry.data[CONF_LONGITUDE]
    allergens = entry.data.get(CONF_ALLERGENS, [])
    interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    coordinator = PollenDataUpdateCoordinator(hass, api_key, lat, lon, allergens, interval)
    await coordinator.async_config_entry_first_refresh()

    sensors = [PollenSensor(coordinator, allergen) for allergen in allergens]
    async_add_entities(sensors)

class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch pollen data periodically."""
    def __init__(self, hass, api_key, lat, lon, allergens, hours):
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(hours=hours)
        )
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.allergens = allergens
        self.data = {}

    async def _async_update_data(self):
        """Fetch current pollen levels from Google Maps Pollen API."""
        url = (
            f"https://pollenws.googleapis.com/v1/pollen?"
            f"latitude={self.lat:.6f}&longitude={self.lon:.6f}&key={self.api_key}"
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 403:
                        raise UpdateFailed("API key invalid or restricted")
                    if response.status == 429:
                        raise UpdateFailed("API rate limit exceeded")
                    if response.status != 200:
                        raise UpdateFailed(f"Error fetching data: {response.status}")
                    payload = await response.json()

            if not isinstance(payload.get("data"), list):
                _LOGGER.warning("API response 'data' is not a list")
                return {}

            filtered = {
                item["type"]: item
                for item in payload.get("data", [])
                if item.get("type") in self.allergens
            }
            self.data = filtered
            return self.data
        except Exception as err:
            raise UpdateFailed(err)

class PollenSensor(Entity):
    """Sensor for an individual allergen."""
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
        if not entry:
            return {}
        # Parse timestamp to ISO
        ts = entry.get("timestamp")
        try:
            parsed = dt_util.parse_datetime(ts)
            iso_ts = parsed.isoformat() if parsed else ts
        except Exception:
            iso_ts = ts or "N/A"
        return {
            "category": entry.get("category", "Unknown"),
            "unit": entry.get("unit", "grains/m³"),
            "timestamp": iso_ts,
            "location": f"{self.coordinator.lat:.6f},{self.coordinator.lon:.6f}"
        }
