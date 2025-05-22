"""Sensor platform for Pollen Levels with language support."""
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
    CONF_LANGUAGE_CODE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Icons mapping
TYPE_ICONS = {"GRASS": "mdi:grass", "TREE": "mdi:tree", "WEED": "mdi:flower-tulip"}
PLANT_TYPE_ICONS = TYPE_ICONS
DEFAULT_ICON = "mdi:flower-pollen"


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensors grouped by type and plant."""
    api_key = entry.data[CONF_API_KEY]
    lat = entry.data[CONF_LATITUDE]
    lon = entry.data[CONF_LONGITUDE]
    interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    lang = entry.data.get(CONF_LANGUAGE_CODE)

    coordinator = PollenDataUpdateCoordinator(
        hass, api_key, lat, lon, interval, lang, entry.entry_id
    )
    await coordinator.async_config_entry_first_refresh()

    if not coordinator.data:
        _LOGGER.warning("No pollen data found during initial setup")
        return

    sensors = [PollenSensor(coordinator, code) for code in coordinator.data.keys()]
    _LOGGER.debug(
        "Creating %d sensors: %s", len(sensors), list(coordinator.data.keys())
    )
    async_add_entities(sensors, True)


class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch pollen data with selected language."""

    def __init__(self, hass, api_key, lat, lon, hours, language, entry_id):
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry_id}",
            update_interval=timedelta(hours=hours),
        )
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.language = language
        self.entry_id = entry_id
        self.data = {}

    async def _async_update_data(self):
        """Fetch pollen data with optional languageCode."""
        url = "https://pollen.googleapis.com/v1/forecast:lookup"
        params = {
            "key": self.api_key,
            "location.latitude": f"{self.lat:.6f}",
            "location.longitude": f"{self.lon:.6f}",
            "days": 1,
        }
        if self.language:
            params["languageCode"] = self.language

        _LOGGER.debug("Fetching with params: %s", params)

        try:
            async with aiohttp.ClientSession() as session:
                resp = await session.get(url, params=params)
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
                idx = item.get("indexInfo", {}) or {}
                new_data[f"type_{code.lower()}"] = {
                    "source": "type",
                    "value": idx.get("value"),
                    "category": idx.get("category"),
                    "displayName": item.get("displayName", code),
                }
            # plantInfo
            for item in info.get("plantInfo", []) or []:
                code = item.get("code")
                if not code:
                    continue
                idx = item.get("indexInfo", {}) or {}
                desc = item.get("plantDescription", {}) or {}
                new_data[f"plants_{code.lower()}"] = {
                    "source": "plant",
                    "value": idx.get("value"),
                    "category": idx.get("category"),
                    "displayName": item.get("displayName", code),
                    "inSeason": item.get("inSeason"),
                    "type": desc.get("type"),
                    "family": desc.get("family"),
                    "season": desc.get("season"),
                }

        self.data = new_data
        _LOGGER.debug("Updated data: %s", self.data)
        return self.data


class PollenSensor(Entity):
    """Sensor for an individual pollen code."""

    def __init__(self, coordinator: PollenDataUpdateCoordinator, code: str):
        self.coordinator = coordinator
        self.code = code
        # No polling: uses coordinator
        self._attr_should_poll = False

    @property
    def unique_id(self) -> str:
        """
        Unique ID used by Home Assistant registry.
        It drives entity_id → sensor.pollenlevels_<unique_id>
        """
        return f"{self.coordinator.entry_id}_{self.code}"

    @property
    def name(self) -> str:
        """Friendly name from API's displayName."""
        return self.coordinator.data[self.code].get("displayName", self.code)

    @property
    def state(self):
        """Current pollen index value."""
        return self.coordinator.data[self.code].get("value")

    @property
    def icon(self) -> str:
        """Icon depending on type or plant."""
        info = self.coordinator.data[self.code]
        if info.get("source") == "type":
            # extract e.g. "GRASS" from "type_grass"
            key = self.code.split("_", 1)[1].upper()
            return TYPE_ICONS.get(key, DEFAULT_ICON)
        plant_type = info.get("type")
        return PLANT_TYPE_ICONS.get(plant_type, DEFAULT_ICON)

    @property
    def extra_state_attributes(self) -> dict:
        """Category, attribution and plant-specific details."""
        info = self.coordinator.data[self.code]
        attrs = {
            "category": info.get("category"),
            ATTR_ATTRIBUTION: "Data provided by Google Maps Pollen API",
        }
        if info.get("source") == "plant":
            attrs.update(
                {
                    "inSeason": info.get("inSeason"),
                    "type": info.get("type"),
                    "family": info.get("family"),
                    "season": info.get("season"),
                }
            )
        return attrs

    @property
    def device_info(self) -> dict:
        """Group sensors by source under a single device per location."""
        info = self.coordinator.data[self.code]
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
