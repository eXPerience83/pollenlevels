```python
"""Sensor platform for Pollen Levels integration."""
import logging
from datetime import timedelta, date
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
    """Set up sensors for region, date, pollenTypeInfo and plantInfo."""
    api_key = entry.data[CONF_API_KEY]
    lat = entry.data[CONF_LATITUDE]
    lon = entry.data[CONF_LONGITUDE]
    interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    coordinator = PollenDataCoordinator(hass, api_key, lat, lon, interval, entry.entry_id)
    await coordinator.async_config_entry_first_refresh()

    sensors = []
    # Region code sensor
    sensors.append(RegionSensor(coordinator))
    # Date sensor
    sensors.append(DateSensor(coordinator))
    # pollenTypeInfo sensors (grass, tree, weed)
    for info in coordinator.pollen_types:
        sensors.append(PollenTypeSensor(coordinator, info))
    # plantInfo sensors
    for info in coordinator.plant_info:
        sensors.append(PlantSensor(coordinator, info))

    _LOGGER.debug("Creating %d sensors", len(sensors))
    async_add_entities(sensors, True)

class PollenDataCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch all pollen data periodically."""
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
        self.region = None
        self.current_date = None
        self.pollen_types = []  # list of dicts from pollenTypeInfo
        self.plant_info = []    # list of dicts from plantInfo

    async def _async_update_data(self):
        """Fetch pollen forecast and parse data."""
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

        self.region = payload.get("regionCode")
        daily = payload.get("dailyInfo", []) or []
        if not daily:
            _LOGGER.warning("No 'dailyInfo' returned")
            return
        entry = daily[0]
        d = entry.get("date", {})
        try:
            self.current_date = date(d.get("year"), d.get("month"), d.get("day"))
        except Exception:
            self.current_date = None

        # Parse pollenTypeInfo
        self.pollen_types = []
        for item in entry.get("pollenTypeInfo", []):
            self.pollen_types.append({
                "code": item.get("code"),
                "display_name": item.get("displayName"),
                "in_season": item.get("inSeason"),
                "index": item.get("indexInfo", {}).get("value"),
                "category": item.get("indexInfo", {}).get("category"),
            })

        # Parse plantInfo
        self.plant_info = []
        for item in entry.get("plantInfo", []):
            info = {"code": item.get("code"), "display_name": item.get("displayName")}
            idx = item.get("indexInfo")
            if idx:
                info.update({
                    "value": idx.get("value"),
                    "category": idx.get("category"),
                    "in_season": item.get("inSeason"),
                })
            # include plantDescription if present
            pd = item.get("plantDescription")
            if pd:
                info["type"] = pd.get("type")
                info["family"] = pd.get("family")
                info["season"] = pd.get("season")
            self.plant_info.append(info)

class RegionSensor(Entity):
    """Sensor for region code."""
    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def name(self):
        return "Pollen Region"

    @property
    def state(self):
        return self.coordinator.region or "unknown"

class DateSensor(Entity):
    """Sensor for forecast date."""
    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def name(self):
        return "Pollen Date"

    @property
    def state(self):
        return self.coordinator.current_date.isoformat() if self.coordinator.current_date else None

class PollenTypeSensor(Entity):
    """Sensor for a pollen category (grass, tree, weed)."""
    def __init__(self, coordinator, info):
        self.coordinator = coordinator
        self.info = info
        self._attr_attribution = "Data provided by Google Maps Pollen API"

    @property
    def unique_id(self):
        return f"{self.coordinator.entry_id}_type_{self.info['code']}"

    @property
    def name(self):
        return f"Pollen {self.info['display_name']}"

    @property
    def state(self):
        return self.info.get("index") if self.info.get("index") is not None else "unavailable"

    @property
    def extra_state_attributes(self):
        attrs = {"category": self.info.get("category"), "in_season": self.info.get("in_season")}
        attrs[ATTR_ATTRIBUTION] = self._attr_attribution
        return attrs

class PlantSensor(Entity):
    """Sensor for an individual plant variety."""
    def __init__(self, coordinator, info):
        self.coordinator = coordinator
        self.info = info
        self._attr_attribution = "Data provided by Google Maps Pollen API"

    @property
    def unique_id(self):
        return f"{self.coordinator.entry_id}_plant_{self.info['code']}"

    @property
    def name(self):
        return f"Pollen {self.info['display_name']}"

    @property
    def state(self):
        return self.info.get("value") if self.info.get("value") is not None else "unavailable"

    @property
    def extra_state_attributes(self):
        attrs = {key: val for key, val in self.info.items() if key not in ("code", "display_name")}
        attrs[ATTR_ATTRIBUTION] = self._attr_attribution
        return attrs

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.entry_id)},
            "name": f"Pollen Levels ({self.coordinator.lat:.6f},{self.coordinator.lon:.6f})",
            "model": "Google Pollen API",
            "manufacturer": "Google",
        }
```
