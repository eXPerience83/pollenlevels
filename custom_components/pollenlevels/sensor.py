"""Provide Pollen Levels sensors with language support and metadata."""
import logging
from datetime import timedelta

from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
    CoordinatorEntity,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import EntityCategory
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

# ---- Icons ---------------------------------------------------------------

TYPE_ICONS = {
    "GRASS": "mdi:grass",
    "TREE": "mdi:tree",
    "WEED": "mdi:flower-tulip",
}
PLANT_TYPE_ICONS = TYPE_ICONS  # Reuse mapping for plant "type" attribute
DEFAULT_ICON = "mdi:flower-pollen"

# ---- Service -------------------------------------------------------------
# (Service registration is handled in __init__.py)


async def async_setup_entry(hass, entry, async_add_entities):
    """Create coordinator and build sensors for pollen data."""
    # ------------------------------------------------------------------
    # Coordinator
    # ------------------------------------------------------------------

    api_key = entry.data[CONF_API_KEY]
    lat = entry.data[CONF_LATITUDE]
    lon = entry.data[CONF_LONGITUDE]
    interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    lang = entry.data.get(CONF_LANGUAGE_CODE)

    coordinator = PollenDataUpdateCoordinator(
        hass, api_key, lat, lon, interval, lang, entry.entry_id
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    if not coordinator.data:
        _LOGGER.warning("No pollen data found during initial setup")
        return

    # ------------------------------------------------------------------
    # Build sensors for each pollen & plant code + metadata sensors
    # ------------------------------------------------------------------

    sensors = [
        PollenSensor(coordinator, code)
        for code in coordinator.data
        if code not in ("region", "date")
    ]

    sensors.extend(
        [
            RegionSensor(coordinator),
            DateSensor(coordinator),
            LastUpdatedSensor(coordinator),
        ]
    )

    _LOGGER.debug(
        "Creating %d sensors: %s",
        len(sensors),
        [s.unique_id for s in sensors],
    )
    async_add_entities(sensors, True)


# ---------------------------------------------------------------------------
# DataUpdateCoordinator
# ---------------------------------------------------------------------------

class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinate pollen data fetch with optional language code."""

    def __init__(self, hass, api_key, lat, lon, hours, language, entry_id):
        """Initialize coordinator with configuration and interval."""
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
        self.data: dict[str, dict] = {}
        self.last_updated = None  # Track last successful update timestamp
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self):
        """Fetch pollen data and extract sensors."""
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
            async with self._session.get(url, params=params, timeout=10) as resp:
                if resp.status == 403:
                    raise UpdateFailed("Invalid API key")
                if resp.status == 429:
                    raise UpdateFailed("Quota exceeded")
                if resp.status != 200:
                    raise UpdateFailed(f"HTTP {resp.status}")
                payload = await resp.json()
        except Exception as err:
            raise UpdateFailed(err) from err

        new_data: dict[str, dict] = {}

        # Extract region code
        if (region := payload.get("regionCode")):
            new_data["region"] = {"source": "meta", "value": region}

        # Extract date and pollen information
        if (daily := payload.get("dailyInfo")) and isinstance(daily, list):
            first_day = daily[0]
            date_obj = first_day.get("date", {})
            if all(k in date_obj for k in ("year", "month", "day")):
                new_data["date"] = {
                    "source": "meta",
                    "value": f"{date_obj['year']:04d}-{date_obj['month']:02d}-{date_obj['day']:02d}",
                }

            # pollenTypeInfo → type sensors
            for item in first_day.get("pollenTypeInfo", []) or []:
                code = item.get("code")
                idx = item.get("indexInfo", {}) or {}
                key = f"type_{code.lower()}"
                new_data[key] = {
                    "source": "type",
                    "value": idx.get("value"),
                    "category": idx.get("category"),
                    "displayName": item.get("displayName", code),
                }

            # plantInfo → plant sensors
            for item in first_day.get("plantInfo", []) or []:
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
                    "cross_reaction": desc.get("crossReaction"),
                }

        self.data = new_data
        self.last_updated = dt_util.utcnow()
        _LOGGER.debug("Updated data: %s", self.data)
        return self.data


# ---------------------------------------------------------------------------
# Generic Pollen Sensor (type & plant)
# ---------------------------------------------------------------------------

class PollenSensor(CoordinatorEntity):
    """Represent a pollen sensor for a type or plant."""

    def __init__(self, coordinator: PollenDataUpdateCoordinator, code: str):
        """Initialize pollen sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.code = code

    @property
    def unique_id(self) -> str:
        """Return unique ID for sensor."""
        return f"{self.coordinator.entry_id}_{self.code}"

    @property
    def name(self) -> str:
        """Return display name of sensor."""
        return self.coordinator.data[self.code].get("displayName", self.code)

    @property
    def state(self):
        """Return current pollen index value."""
        return self.coordinator.data[self.code].get("value")

    @property
    def icon(self) -> str:
        """Return icon for sensor."""
        info = self.coordinator.data[self.code]
        if info.get("source") == "type":
            key = self.code.split("_", 1)[1].upper()
            return TYPE_ICONS.get(key, DEFAULT_ICON)
        return PLANT_TYPE_ICONS.get(info.get("type"), DEFAULT_ICON)

    @property
    def extra_state_attributes(self):
        """Return extra attributes for sensor."""
        attrs = {
            "category": self.coordinator.data[self.code].get("category"),
            ATTR_ATTRIBUTION: "Data provided by Google Maps Pollen API",
        }
        if self.coordinator.data[self.code].get("source") == "plant":
            attrs.update(
                {
                    "inSeason": self.coordinator.data[self.code].get("inSeason"),
                    "type": self.coordinator.data[self.code].get("type"),
                    "family": self.coordinator.data[self.code].get("family"),
                    "season": self.coordinator.data[self.code].get("season"),
                    "cross_reaction": self.coordinator.data[self.code].get("cross_reaction"),
                }
            )
        return attrs

    @property
    def device_info(self):
        """Return device info with translation support for the group."""
        group = self.coordinator.data[self.code].get("source")
        device_id = f"{self.coordinator.entry_id}_{group}"
        translation_keys = {
            "type": "types",
            "plant": "plants",
            "meta": "info",
        }
        translation_key = translation_keys.get(group, "info")
        return {
            "identifiers": {(DOMAIN, device_id)},
            "manufacturer": "Google",
            "model": "Pollen API",
            "translation_key": translation_key,
            "translation_placeholders": {
                "latitude": f"{self.coordinator.lat:.6f}",
                "longitude": f"{self.coordinator.lon:.6f}",
            }
        }


# ---------------------------------------------------------------------------
# Metadata Sensors (Region / Date / Last Updated)
# ---------------------------------------------------------------------------

class _BaseMetaSensor(CoordinatorEntity):
    """Provide base for metadata sensors."""

    def __init__(self, coordinator: PollenDataUpdateCoordinator):
        """Initialize metadata sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator

    @property
    def device_info(self):
        """Return device info with translation for metadata sensors."""
        device_id = f"{self.coordinator.entry_id}_meta"
        return {
            "identifiers": {(DOMAIN, device_id)},
            "manufacturer": "Google",
            "model": "Pollen API",
            "translation_key": "info",
            "translation_placeholders": {
                "latitude": f"{self.coordinator.lat:.6f}",
                "longitude": f"{self.coordinator.lon:.6f}",
            }
        }


class RegionSensor(_BaseMetaSensor):
    """Represent region code sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "region"

    @property
    def unique_id(self) -> str:
        """Return unique ID for region sensor."""
        return f"{self.coordinator.entry_id}_region"

    @property
    def state(self):
        """Return region code."""
        return self.coordinator.data.get("region", {}).get("value")

    @property
    def icon(self):
        """Return icon for region sensor."""
        return "mdi:earth"


class DateSensor(_BaseMetaSensor):
    """Represent forecast date sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "date"

    @property
    def unique_id(self) -> str:
        """Return unique ID for date sensor."""
        return f"{self.coordinator.entry_id}_date"

    @property
    def state(self):
        """Return forecast date."""
        return self.coordinator.data.get("date", {}).get("value")

    @property
    def icon(self):
        """Return icon for date sensor."""
        return "mdi:calendar"


class LastUpdatedSensor(_BaseMetaSensor):
    """Represent timestamp of last successful update."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "last_updated"

    @property
    def unique_id(self) -> str:
        """Return unique ID for last updated sensor."""
        return f"{self.coordinator.entry_id}_last_updated"

    @property
    def state(self):
        """Return local timestamp of last update in 'YYYY-MM-DD HH:MM:SS'."""
        if not self.coordinator.last_updated:
            return None
        local_ts = dt_util.as_local(self.coordinator.last_updated)
        return local_ts.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def icon(self):
        """Return icon for last updated sensor."""
        return "mdi:clock-check"
