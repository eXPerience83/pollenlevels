"""Sensor platform for Pollen Levels with language support and Region/Date sensors."""
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

# Icons mapping for pollenTypeInfo codes (GRASS, TREE, WEED)
TYPE_ICONS = {
    "GRASS": "mdi:grass",
    "TREE": "mdi:tree",
    "WEED": "mdi:flower-tulip",
}
# Same mapping for plant types based on 'type' attribute
PLANT_TYPE_ICONS = TYPE_ICONS
# Fallback icon
DEFAULT_ICON = "mdi:flower-pollen"


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up all sensors: pollen types, plants, plus region & date meta-sensors."""
    api_key = entry.data[CONF_API_KEY]
    lat = entry.data[CONF_LATITUDE]
    lon = entry.data[CONF_LONGITUDE]
    interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    lang = entry.data.get(CONF_LANGUAGE_CODE)

    # Create the coordinator with language support
    coordinator = PollenDataUpdateCoordinator(
        hass, api_key, lat, lon, interval, lang, entry.entry_id
    )
    await coordinator.async_config_entry_first_refresh()

    if not coordinator.data:
        _LOGGER.warning("No pollen data found during initial setup")
        return

    # Build sensors for each pollen code
    sensors = [
        PollenSensor(coordinator, code)
        for code in coordinator.data.keys()
        if code not in ("region", "date")
    ]

    # Add the two extra metadata sensors: region and date
    sensors.extend([
        RegionSensor(coordinator),
        DateSensor(coordinator),
    ])

    _LOGGER.debug(
        "Creating %d sensors: %s",
        len(sensors),
        [s.unique_id for s in sensors],
    )
    async_add_entities(sensors, True)


class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch pollen data with optional languageCode."""

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
        self.data = {}  # will hold all pollen entries plus meta

    async def _async_update_data(self):
        """Fetch pollen data and extract types, plants, region, and date."""
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
        # --- Extract region code ---
        region = payload.get("regionCode")
        if region:
            new_data["region"] = {
                "source": "meta",
                "value": region,
            }

        # --- Extract date info ---
        daily = payload.get("dailyInfo")
        if isinstance(daily, list) and daily:
            date_obj = daily[0].get("date", {})
            year = date_obj.get("year")
            month = date_obj.get("month")
            day = date_obj.get("day")
            if year and month and day:
                new_data["date"] = {
                    "source": "meta",
                    "value": f"{year:04d}-{month:02d}-{day:02d}",
                }

            info = daily[0]

            # --- pollenTypeInfo → type sensors ---
            for item in info.get("pollenTypeInfo", []) or []:
                code = item.get("code")
                idx = item.get("indexInfo", {}) or {}
                key = f"type_{code.lower()}"
                new_data[key] = {
                    "source": "type",
                    "value": idx.get("value"),
                    "category": idx.get("category"),
                    "displayName": item.get("displayName", code),
                }

            # --- plantInfo → plant sensors ---
            for item in info.get("plantInfo", []) or []:
                code = item.get("code")
                idx = item.get("indexInfo", {}) or {}
                desc = item.get("plantDescription", {}) or {}
                key = f"plants_{code.lower()}"
                new_data[key] = {
                    "source": "plant",
                    "value": idx.get("value"),
                    "category": idx.get("category"),
                    "displayName": item.get("displayName", code),
                    "inSeason": item.get("inSeason"),
                    "type": desc.get("type"),
                    "family": desc.get("family"),
                    "season": desc.get("season"),
                    # Add cross_reaction attribute if available
                    "cross_reaction": desc.get("crossReaction"),
                }

        self.data = new_data
        _LOGGER.debug("Updated data: %s", self.data)
        return self.data


class PollenSensor(Entity):
    """Generic sensor for pollen types or plant types."""

    def __init__(self, coordinator: PollenDataUpdateCoordinator, code: str):
        self.coordinator = coordinator
        self.code = code
        self._attr_should_poll = False

    @property
    def unique_id(self) -> str:
        return f"{self.coordinator.entry_id}_{self.code}"

    @property
    def name(self) -> str:
        return self.coordinator.data[self.code].get("displayName", self.code)

    @property
    def state(self):
        return self.coordinator.data[self.code].get("value")

    @property
    def icon(self) -> str:
        info = self.coordinator.data[self.code]
        if info.get("source") == "type":
            key = self.code.split("_", 1)[1].upper()
            return TYPE_ICONS.get(key, DEFAULT_ICON)
        plant_type = info.get("type")
        return PLANT_TYPE_ICONS.get(plant_type, DEFAULT_ICON)

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {
            "category": self.coordinator.data[self.code].get("category"),
            ATTR_ATTRIBUTION: "Data provided by Google Maps Pollen API",
        }
        if self.coordinator.data[self.code].get("source") == "plant":
            attrs.update({
                "inSeason": self.coordinator.data[self.code].get("inSeason"),
                "type": self.coordinator.data[self.code].get("type"),
                "family": self.coordinator.data[self.code].get("family"),
                "season": self.coordinator.data[self.code].get("season"),
                # Add cross_reaction attribute if available
                "cross_reaction": self.coordinator.data[self.code].get("cross_reaction"),
            })
        return attrs

    @property
    def device_info(self) -> dict:
        group = self.coordinator.data[self.code].get("source")
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


class RegionSensor(Entity):
    def __init__(self, coordinator: PollenDataUpdateCoordinator):
        self.coordinator = coordinator
        self._attr_should_poll = False

    @property
    def unique_id(self) -> str:
        return f"{self.coordinator.entry_id}_region"

    @property
    def name(self) -> str:
        return "Region"

    @property
    def state(self):
        return self.coordinator.data.get("region", {}).get("value")

    @property
    def icon(self) -> str:
        return "mdi:earth"

    @property
    def device_info(self) -> dict:
        device_id = f"{self.coordinator.entry_id}_meta"
        device_name = f"Pollen Info ({self.coordinator.lat:.6f},{self.coordinator.lon:.6f})"
        return {
            "identifiers": {(DOMAIN, device_id)},
            "name": device_name,
            "manufacturer": "Google",
            "model": "Pollen API",
        }


class DateSensor(Entity):
    def __init__(self, coordinator: PollenDataUpdateCoordinator):
        self.coordinator = coordinator
        self._attr_should_poll = False

    @property
    def unique_id(self) -> str:
        return f"{self.coordinator.entry_id}_date"

    @property
    def name(self) -> str:
        return "Date"

    @property
    def state(self):
        return self.coordinator.data.get("date", {}).get("value")

    @property
    def icon(self) -> str:
        return "mdi:calendar"

    @property
    def device_info(self) -> dict:
        device_id = f"{self.coordinator.entry_id}_meta"
        device_name = f"Pollen Info ({self.coordinator.lat:.6f},{self.coordinator.lon:.6f})"
        return {
            "identifiers": {(DOMAIN, device_id)},
            "name": device_name,
            "manufacturer": "Google",
            "model": "Pollen API",
        }
