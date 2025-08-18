"""Provide Pollen Levels sensors with multi-day forecast for pollen TYPES.

Phase 1.1 (v1.6.x):
- Unified per-day sensor option into a single selector 'create_forecast_sensors':
  values: "none" | "D+1" | "D+1+2".
- Internally maps to create_d1/create_d2 flags for existing logic.
- Everything else stays as in Phase 1:
  * forecast attribute on type sensors (list of {offset, date, has_index, value, category, description, color_*})
  * convenience fields: tomorrow_* and d2_*
  * trend (vs tomorrow) and expected_peak
  * optional per-day sensors for (D+1) and (D+2), created only if requested and data available.

Robustness:
- Days without indexInfo are represented with has_index=false and null values.
- Entity names for per-day sensors use neutral suffixes "(D+1)" / "(D+2)".

v1.6.3:
- Add proactive cleanup of per-day entities (D+1/D+2) in the Entity Registry when options
  no longer request them or forecast_days is insufficient. This prevents "Unavailable"
  leftovers after reloading the entry.
- Normalize plant 'type' to uppercase for icon mapping.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.helpers import entity_registry as er  # <-- entity-registry cleanup
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# ---- Icons ---------------------------------------------------------------

TYPE_ICONS = {
    "GRASS": "mdi:grass",
    "TREE": "mdi:tree",
    "WEED": "mdi:flower-tulip",
}
PLANT_TYPE_ICONS = TYPE_ICONS
DEFAULT_ICON = "mdi:flower-pollen"


def _normalize_channel(v: Any) -> int | None:
    """Normalize a single channel to 0..255 (accept 0..1 or 0..255 inputs)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if 0.0 <= f <= 1.0:
        f *= 255.0
    return max(0, min(255, int(round(f))))


def _rgb_from_api(color: dict[str, Any] | None) -> tuple[int, int, int] | None:
    """Build an (R, G, B) tuple from API color dict, tolerating missing channels."""
    if not isinstance(color, dict):
        return None
    r = _normalize_channel(color.get("red", 0))
    g = _normalize_channel(color.get("green", 0))
    b = _normalize_channel(color.get("blue", 0))
    if r is None and g is None and b is None:
        return None
    return (r or 0, g or 0, b or 0)


def _rgb_to_hex_triplet(rgb: tuple[int, int, int] | None) -> str | None:
    """Convert (R,G,B) 0..255 to #RRGGBB."""
    if rgb is None:
        return None
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


async def _cleanup_per_day_entities(
    hass, entry_id: str, allow_d1: bool, allow_d2: bool
) -> int:
    """Remove stale per-day entities (D+1/D+2) for this entry from the Entity Registry.

    This is needed because Home Assistant keeps entity registry entries across reloads.
    If options disable per-day sensors (or forecast_days is insufficient), we proactively
    remove the registry entries so the UI doesn't show "Unavailable" ghosts.

    Returns the number of removed entities.
    """
    registry = er.async_get(hass)
    # Get all entities belonging to this config entry
    entries = er.async_entries_for_config_entry(registry, entry_id)
    removed = 0

    # Helper: determine whether a unique_id corresponds to a D+1 or D+2 sensor
    def _matches(uid: str, suffix: str) -> bool:
        # Our unique_id format is: f"{entry_id}_{code}"
        if not uid.startswith(f"{entry_id}_"):
            return False
        return uid.endswith(suffix)

    # We remove any *_d1 if !allow_d1 and any *_d2 if !allow_d2
    for ent in entries:
        if ent.domain != "sensor" or ent.platform != DOMAIN:
            continue
        if not allow_d1 and _matches(ent.unique_id, "_d1"):
            _LOGGER.debug(
                "Removing stale D+1 entity from registry: %s (%s)",
                ent.entity_id,
                ent.unique_id,
            )
            registry.async_remove(ent.entity_id)
            removed += 1
            continue
        if not allow_d2 and _matches(ent.unique_id, "_d2"):
            _LOGGER.debug(
                "Removing stale D+2 entity from registry: %s (%s)",
                ent.entity_id,
                ent.unique_id,
            )
            registry.async_remove(ent.entity_id)
            removed += 1

    if removed:
        _LOGGER.info(
            "Entity Registry cleanup: removed %d per-day sensors for entry %s",
            removed,
            entry_id,
        )
    return removed


async def async_setup_entry(hass, entry, async_add_entities):
    """Create coordinator and build sensors for pollen data."""
    api_key = entry.data[CONF_API_KEY]
    lat = entry.data[CONF_LATITUDE]
    lon = entry.data[CONF_LONGITUDE]

    opts = entry.options or {}
    interval = opts.get(
        CONF_UPDATE_INTERVAL,
        entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
    )
    lang = opts.get(CONF_LANGUAGE_CODE, entry.data.get(CONF_LANGUAGE_CODE))
    forecast_days = int(opts.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS))

    # Map unified selector to internal flags
    mode = opts.get(CONF_CREATE_FORECAST_SENSORS, "none")
    create_d1 = mode == "D+1" or mode == "D+1+2"
    create_d2 = mode == "D+1+2"

    # Decide if per-day entities are allowed *given current options*
    allow_d1 = create_d1 and forecast_days >= 2
    allow_d2 = create_d2 and forecast_days >= 3

    # --- NEW: proactively remove stale D+ entities from the Entity Registry ----
    await _cleanup_per_day_entities(
        hass, entry.entry_id, allow_d1=allow_d1, allow_d2=allow_d2
    )

    coordinator = PollenDataUpdateCoordinator(
        hass=hass,
        api_key=api_key,
        lat=lat,
        lon=lon,
        hours=interval,
        language=lang,
        entry_id=entry.entry_id,
        forecast_days=forecast_days,
        create_d1=allow_d1,  # pass the effective flags
        create_d2=allow_d2,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    if not coordinator.data:
        _LOGGER.warning("No pollen data found during initial setup")
        return

    sensors: list[CoordinatorEntity] = []
    for code in coordinator.data:
        if code in ("region", "date"):
            continue
        sensors.append(PollenSensor(coordinator, code))

    sensors.extend(
        [
            RegionSensor(coordinator),
            DateSensor(coordinator),
            LastUpdatedSensor(coordinator),
        ]
    )

    _LOGGER.debug(
        "Creating %d sensors: %s", len(sensors), [s.unique_id for s in sensors]
    )
    async_add_entities(sensors, True)


class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinate pollen data fetch with forecast support for types."""

    def __init__(
        self,
        hass,
        api_key: str,
        lat: float,
        lon: float,
        hours: int,
        language: str | None,
        entry_id: str,
        forecast_days: int,
        create_d1: bool,
        create_d2: bool,
    ):
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
        self.forecast_days = max(1, min(5, int(forecast_days)))
        self.create_d1 = create_d1
        self.create_d2 = create_d2

        self.data: dict[str, dict] = {}
        self.last_updated = None
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self):
        """Fetch pollen data and extract sensors for current day and forecast."""
        url = "https://pollen.googleapis.com/v1/forecast:lookup"
        params = {
            "key": self.api_key,
            "location.latitude": f"{self.lat:.6f}",
            "location.longitude": f"{self.lon:.6f}",
            "days": self.forecast_days,
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

        # region
        if region := payload.get("regionCode"):
            new_data["region"] = {"source": "meta", "value": region}

        daily: list[dict] = payload.get("dailyInfo") or []
        if not daily:
            self.data = new_data
            self.last_updated = dt_util.utcnow()
            return self.data

        # date (today)
        first_day = daily[0]
        date_obj = first_day.get("date", {}) or {}
        if all(k in date_obj for k in ("year", "month", "day")):
            new_data["date"] = {
                "source": "meta",
                "value": f"{date_obj['year']:04d}-{date_obj['month']:02d}-{date_obj['day']:02d}",
            }

        # collect type codes found in any day
        type_codes: set[str] = set()
        for day in daily:
            for item in day.get("pollenTypeInfo", []) or []:
                code = (item.get("code") or "").upper()
                if code:
                    type_codes.add(code)

        def _find_type(day: dict, code: str) -> dict | None:
            for item in day.get("pollenTypeInfo", []) or []:
                if (item.get("code") or "").upper() == code:
                    return item
            return None

        # Current-day TYPES
        for tcode in type_codes:
            titem = _find_type(first_day, tcode) or {}
            idx = (titem.get("indexInfo") or {}) if isinstance(titem, dict) else {}
            rgb = _rgb_from_api(idx.get("color"))
            key = f"type_{tcode.lower()}"
            new_data[key] = {
                "source": "type",
                "value": idx.get("value"),
                "category": idx.get("category"),
                "displayName": titem.get("displayName", tcode),
                "inSeason": titem.get("inSeason"),
                "description": idx.get("indexDescription"),
                "advice": titem.get("healthRecommendations"),
                "color_hex": _rgb_to_hex_triplet(rgb),
                "color_rgb": list(rgb) if rgb is not None else None,
                "color_raw": (
                    idx.get("color") if isinstance(idx.get("color"), dict) else None
                ),
            }

        # Current-day PLANTS (unchanged in Phase 1.1)
        for pitem in first_day.get("plantInfo", []) or []:
            code = pitem.get("code")
            idx = pitem.get("indexInfo", {}) or {}
            desc = pitem.get("plantDescription", {}) or {}
            rgb = _rgb_from_api(idx.get("color"))
            key = f"plants_{(code or '').lower()}"
            new_data[key] = {
                "source": "plant",
                "value": idx.get("value"),
                "category": idx.get("category"),
                "displayName": pitem.get("displayName", code),
                "code": code,
                "inSeason": pitem.get("inSeason"),
                "type": desc.get("type"),
                "family": desc.get("family"),
                "season": desc.get("season"),
                "cross_reaction": desc.get("crossReaction"),
                "description": idx.get("indexDescription"),
                "advice": pitem.get("healthRecommendations"),
                "color_hex": _rgb_to_hex_triplet(rgb),
                "color_rgb": list(rgb) if rgb is not None else None,
                "color_raw": (
                    idx.get("color") if isinstance(idx.get("color"), dict) else None
                ),
                "picture": desc.get("picture"),
                "picture_closeup": desc.get("pictureCloseup"),
            }

        # Forecast for TYPES
        def _extract_day_info(day: dict) -> tuple[str | None, str | None]:
            d = day.get("date") or {}
            if not all(k in d for k in ("year", "month", "day")):
                return None, None
            return f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}", d

        for tcode in type_codes:
            type_key = f"type_{tcode.lower()}"
            base = new_data.get(type_key, {})
            forecast_list: list[dict[str, Any]] = []
            for offset, day in enumerate(daily[1:], start=1):
                if offset >= self.forecast_days:
                    break
                date_str, _ = _extract_day_info(day)
                item = _find_type(day, tcode) or {}
                idx = item.get("indexInfo") if isinstance(item, dict) else None
                has_index = isinstance(idx, dict)
                rgb = _rgb_from_api(idx.get("color")) if has_index else None
                forecast_list.append(
                    {
                        "offset": offset,
                        "date": date_str,
                        "has_index": has_index,
                        "value": idx.get("value") if has_index else None,
                        "category": idx.get("category") if has_index else None,
                        "description": (
                            idx.get("indexDescription") if has_index else None
                        ),
                        "color_hex": _rgb_to_hex_triplet(rgb) if has_index else None,
                        "color_rgb": (
                            list(rgb) if (has_index and rgb is not None) else None
                        ),
                        "color_raw": (
                            idx.get("color")
                            if has_index and isinstance(idx.get("color"), dict)
                            else None
                        ),
                    }
                )
            base["forecast"] = forecast_list

            # Convenience for tomorrow (1) and d2 (2)
            # Bind loop variables into defaults to avoid late-binding issues (ruff B023).
            def _set_convenience(
                prefix: str,
                off: int,
                *,
                _forecast_list=forecast_list,
                _base=base,
            ) -> None:
                """Set convenience attributes for a given offset using bound snapshot values."""
                f = next((d for d in _forecast_list if d["offset"] == off), None)
                _base[f"{prefix}_has_index"] = f.get("has_index") if f else False
                _base[f"{prefix}_value"] = (
                    f.get("value") if f and f.get("has_index") else None
                )
                _base[f"{prefix}_category"] = (
                    f.get("category") if f and f.get("has_index") else None
                )
                _base[f"{prefix}_description"] = (
                    f.get("description") if f and f.get("has_index") else None
                )
                _base[f"{prefix}_color_hex"] = (
                    f.get("color_hex") if f and f.get("has_index") else None
                )

            _set_convenience("tomorrow", 1)
            _set_convenience("d2", 2)

            # Trend (use PEP 604 union in isinstance as suggested by ruff UP038)
            now_val = base.get("value")
            tomorrow_val = base.get("tomorrow_value")
            if isinstance(now_val, int | float) and isinstance(
                tomorrow_val, int | float
            ):
                if tomorrow_val > now_val:
                    base["trend"] = "up"
                elif tomorrow_val < now_val:
                    base["trend"] = "down"
                else:
                    base["trend"] = "flat"
            else:
                base["trend"] = None

            # Expected peak (excluding today)
            peak = None
            for f in forecast_list:
                if f.get("has_index") and isinstance(f.get("value"), int | float):
                    if peak is None or f["value"] > peak["value"]:
                        peak = f
            base["expected_peak"] = (
                {
                    "offset": peak["offset"],
                    "date": peak["date"],
                    "value": peak["value"],
                    "category": peak["category"],
                }
                if peak
                else None
            )

            new_data[type_key] = base

            # Optional per-day sensors (only if requested and day exists)
            # Bind loop variables into defaults to avoid B023.
            def _add_day_sensor(
                off: int,
                *,
                _forecast_list=forecast_list,
                _base=base,
                _tcode=tcode,
                _type_key=type_key,
            ) -> None:
                """Create per-day type sensor for a given offset using bound snapshot values."""
                f = next((d for d in _forecast_list if d["offset"] == off), None)
                if not f:
                    return
                dname = f"{_base.get('displayName', _tcode)} (D+{off})"
                new_data[f"{_type_key}_d{off}"] = {
                    "source": "type",
                    "displayName": dname,
                    "value": f.get("value") if f.get("has_index") else None,
                    "category": f.get("category") if f.get("has_index") else None,
                    "description": f.get("description") if f.get("has_index") else None,
                    "inSeason": _base.get("inSeason"),
                    "advice": _base.get("advice"),
                    "color_hex": f.get("color_hex"),
                    "color_rgb": f.get("color_rgb"),
                    "color_raw": f.get("color_raw"),
                    "date": f.get("date"),
                    "has_index": f.get("has_index"),
                }

            if self.create_d1:
                _add_day_sensor(1)
            if self.create_d2:
                _add_day_sensor(2)

        self.data = new_data
        self.last_updated = dt_util.utcnow()
        _LOGGER.debug("Updated data: %s", self.data)
        return self.data


class PollenSensor(CoordinatorEntity):
    """Represent a pollen sensor for a type, plant, or per-day type."""

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
            base_key = self.code.split("_", 1)[1].split("_d", 1)[0].upper()
            return TYPE_ICONS.get(base_key, DEFAULT_ICON)
        # NEW: normalize plant 'type' to uppercase to map icons reliably
        ptype = (info.get("type") or "").upper()
        return PLANT_TYPE_ICONS.get(ptype, DEFAULT_ICON)

    @property
    def extra_state_attributes(self):
        """Return extra attributes for sensor."""
        info = self.coordinator.data[self.code]
        attrs = {
            "category": info.get("category"),
            ATTR_ATTRIBUTION: "Data provided by Google Maps Pollen API",
        }

        for k in (
            "description",
            "inSeason",
            "advice",
            "color_hex",
            "color_rgb",
            "color_raw",
            "date",
            "has_index",
        ):
            if info.get(k) is not None:
                attrs[k] = info.get(k)

        # Forecast-related attributes only on main type sensors (not per-day)
        if info.get("source") == "type" and not self.code.endswith(("_d1", "_d2")):
            for k in (
                "forecast",
                "tomorrow_has_index",
                "tomorrow_value",
                "tomorrow_category",
                "tomorrow_description",
                "tomorrow_color_hex",
                "d2_has_index",
                "d2_value",
                "d2_category",
                "d2_description",
                "d2_color_hex",
                "trend",
                "expected_peak",
            ):
                if info.get(k) is not None:
                    attrs[k] = info.get(k)

        # Plant-specific attributes (unchanged Phase 1.1)
        if info.get("source") == "plant":
            plant_attrs = {
                "code": info.get("code"),
                "type": info.get("type"),
                "family": info.get("family"),
                "season": info.get("season"),
                "cross_reaction": info.get("cross_reaction"),
                "picture": info.get("picture"),
                "picture_closeup": info.get("picture_closeup"),
            }
            for k, v in plant_attrs.items():
                if v is not None:
                    attrs[k] = v

        return attrs

    @property
    def device_info(self):
        """Return device info with translation support for the group."""
        group = self.coordinator.data[self.code].get("source")
        device_id = f"{self.coordinator.entry_id}_{group}"
        translation_keys = {"type": "types", "plant": "plants", "meta": "info"}
        translation_key = translation_keys.get(group, "info")
        return {
            "identifiers": {(DOMAIN, device_id)},
            "manufacturer": "Google",
            "model": "Pollen API",
            "translation_key": translation_key,
            "translation_placeholders": {
                "latitude": f"{self.coordinator.lat:.6f}",
                "longitude": f"{self.coordinator.lon:.6f}",
            },
        }


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
            },
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
