"""Sensor platform for Pollen Levels integration with grouped devices and type/plant-specific icons."""
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

# Icons mapping
TYPE_ICONS = {
    "GRASS": "mdi:grass",
    "TREE": "mdi:tree",
    "WEED": "mdi:flower-tulip",
}
PLANT_TYPE_ICONS = TYPE_ICONS  # same mapping for "type" in plantInfo
DEFAULT_ICON = "mdi:flower-pollen"


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensors for each pollen code returned by the API, grouped by source."""
    api_key = entry.data[CONF_API_KEY]
    lat = entry.data[CONF_LATITUDE]
    lon = entry.data[CONF_LONGITUDE]
    interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    coordinator = PollenDataUpdateCoordinator(
        hass, api_key, lat, lon, interval, entry.entry_id
    )
    await coordinator.async_config_entry_first_refresh()

    sensors = [PollenSensor(coordinator, code) for code in coordinator.data.keys()]
    _LOGGER.debug("Creating %d sensors: %s", len(sensors), list(coordinator.data.keys()))
    async_add_entities(sensors, True)


class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch pollen data periodically and separate type vs plant sensors."""

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

    async def _async_update_data(self):
        """Fetch pollen data via forecast:lookup?days=1 and merge type and plant info."""
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
        daily = payload.get("dailyInfo")
        if isinstance(daily, list) and daily:
            info = daily[0]
            # pollenTypeInfo
            for item in info.get("pollenTypeInfo", []) or []:
                code = item.get("code")
                if not code:
                    continue
                index = item.get("indexInfo", {})
                new_data[code] = {
                    "source": "type",
                    "value": index.get("value"),
                    "category": index.get("category"),
                    "displayName": item.get("displayName", code),
                }
            # plantInfo
            for item in info.get("plantInfo", []) or []:
                code = item.get("code")
                if not code:
                    continue
                index = item.get("indexInfo", {})
                desc = item.get("plantDescription", {}) or {}
                new_data[code] = {
                    "source": "plant",
                    "value": index.get("value"),
                    "category": index.get("category"),
                    "displayName": item.get("displayName", code),
                    "inSeason": item.get("inSeason"),
                    "type": desc.get("type"),
                    "family": desc.get("family"),
                    "season": desc.get("season"),
                }

        self.data = new_data
        _LOGGER.debug("Updated pollen data: %s", self.data)
        return self.data


class PollenSensor(Entity):
    """Sensor for an individual pollen code, supports grouping and attributes."""

    def __init__(self, coordinator: PollenDataUpdateCoordinator, code: str):
        self.coordinator = coordinator
        self.code = code

    @property
    def unique_id(self) -> str:
        return f"{self.coordinator.entry_id}_{self.code}"

    @property
    def name(self) -> str:
        return f"Pollen {self.coordinator.data.get(self.code, {}).get('displayName', self.code)}"

    @property
    def state(self):
        return self.coordinator.data.get(self.code, {}).get("value")

    @property
    def icon(self) -> str:
        info = self.coordinator.data.get(self.code, {})
        source = info.get("source")

        if source == "type":
            return TYPE_ICONS.get(self.code, DEFAULT_ICON)
        elif source == "plant":
            plant_type = info.get("type")
            return PLANT_TYPE_ICONS.get(plant_type, DEFAULT_ICON)
        return DEFAULT_ICON

    @property
    def extra_state_attributes(self) -> dict:
        info = self.coordinator.data.get(self.code, {})
        attrs = {
            "category": info.get("category"),
            ATTR_ATTRIBUTION: "Data provided by Google Maps Pollen API"
        }
        if info.get("source") == "plant":
            attrs.update({
                "inSeason": info.get("inSeason"),
                "type": info.get("type"),
                "family": info.get("family"),
                "season": info.get("season"),
            })
        return attrs

    @property
    def device_info(self) -> dict:
        info = self.coordinator.data.get(self.code, {})
        group = info.get("source")
        device_id = f"{self.coordinator.entry_id}_{group}"
        device_name = (
            f"Pollen Types ({self.coordinator.lat:.6f},{self.coordinator.lon:.6f})"
            if group == "type"
            else f"Plants ({self.coordinator.lat:.6f},{self.coordinator.lon:.6f})"
        )
        return {
            "identifiers": {(DOMAIN, device_id)},
            "name": device_name,
            "manufacturer": "Google",
            "model": "Pollen API",
        }
