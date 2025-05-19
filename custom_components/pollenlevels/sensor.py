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

    coordinator = PollenDataUpdateCoordinator(
        hass, api_key, lat, lon, allergens, interval
    )
    await coordinator.async_config_entry_first_refresh()
    async_add_entities([PollenSensor(coordinator, allergen) for allergen in allergens])

class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch pollen forecast periodically."""
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
        """Fetch pollen forecast via forecast:lookup."""
        url = (
            f"https://pollen.googleapis.com/v1/forecast:lookup?"
            f"key={self.api_key}"
            f"&location.latitude={self.lat:.6f}"
            f"&location.longitude={self.lon:.6f}"
            f"&days=1"
        )
        _LOGGER.debug("Fetching pollen data from: %s", url)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 403:
                    raise UpdateFailed("API key invalid or restricted")
                if response.status == 429:
                    raise UpdateFailed("API rate limit exceeded")
                if response.status != 200:
                    raise UpdateFailed(f"Error fetching data: {response.status}")
                payload = await response.json()

        daily = payload.get("dailyInfo", [])
        if not daily:
            _LOGGER.warning("No 'dailyInfo' returned")
            return {}

        # Construir timestamp ISO desde date
        date = daily[0].get("date", {})
        ts = f"{date.get('year',0):04d}-{date.get('month',0):02d}-" \
             f"{date.get('day',0):02d}T00:00:00"

        pollen_items = daily[0].get("pollenTypeInfo", [])
        if not isinstance(pollen_items, list):
            _LOGGER.warning("Invalid 'pollenTypeInfo'")
            return {}

        filtered = {}
        for item in pollen_items:
            code = item.get("code")
            index = item.get("indexInfo")
            if code in self.allergens and index:
                # fusionar indexInfo con timestamp
                filtered[code] = {**index, "forecastDate": ts}

        self.data = filtered
        return self.data

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
        return entry.get("value") if entry else None

    @property
    def icon(self):
        return "mdi:flower-pollen"

    @property
    def extra_state_attributes(self):
        entry = self.coordinator.data.get(self.allergen)
        if not entry:
            return {}
        return {
            "category": entry.get("category", "Unknown"),
            "indexDescription": entry.get("indexDescription", ""),
            "forecastDate": entry.get("forecastDate", ""),
        }
