"""Provide Pollen Levels sensors with multi-day forecast for TYPES and PLANTS.

Phase 2:
- Add `forecast` and convenience/derived attributes to PLANT sensors.
- Keep per-day optional sensors only for TYPES, controlled by `create_forecast_sensors`.
- Clean up outdated per-day sensors on options reload.

Hotfixes for 1.6.4a:
- Color robustness: default missing RGB channels to 0 so `color_hex` is always produced
  when a color dict is present (regression vs 1.5.4/1.6.3).
- Device grouping with translations: restore three translated groups (Types / Plants / Info)
  via `translation_key` + placeholders, as in 1.6.3.
- Backward compatibility for option values: accept legacy "D+1" / "D+1+2" by normalizing to "d1" / "d12".
- Dynamic plant icon: compute icon on every update (in case `type` changes).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta, date
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    CONF_LANGUAGE_CODE,
    CONF_FORECAST_DAYS,
    DEFAULT_FORECAST_DAYS,
    CONF_CREATE_FORECAST_SENSORS,
    DEFAULT_CREATE_FORECAST_SENSORS,
    CFS_NONE,
    CFS_D1,
    CFS_D12,
    POLLEN_TYPES,
)

_LOGGER = logging.getLogger(__name__)

TYPE_ICONS = {"GRASS": "mdi:grass", "TREE": "mdi:tree", "WEED": "mdi:flower-tulip"}
PLANT_TYPE_ICONS = TYPE_ICONS
DEFAULT_ICON = "mdi:flower-pollen"

API_URL = "https://pollen.googleapis.com/v1/forecast:lookup"


# ---------------------- Helpers: colors, dates, options --------------------


def _normalize_channel(v: Any) -> Optional[int]:
    """Normalize a single channel to 0..255.

    Accepts 0..1 floats or 0..255 numbers.
    IMPORTANT: When a color dict is present but a channel is missing/None,
    we default that channel to 0 to keep color_hex available.
    """
    try:
        if v is None:
            return 0
        if isinstance(v, (int, float)):
            f = float(v)
            if 0.0 <= f <= 1.0:
                return int(round(f * 255.0))
            v_int = int(round(f))
            return max(0, min(255, v_int))
    except Exception:  # pragma: no cover - defensive
        return 0
    return 0


def _color_dict_to_rgb(color: Dict[str, Any] | None) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Convert API color dict to (R,G,B) 0..255 tuple.

    Returns (None, None, None) when no color dict is provided at all.
    Otherwise, missing channels default to 0 as per robustness policy.
    """
    if not isinstance(color, dict):
        return None, None, None
    r = _normalize_channel(color.get("red"))
    g = _normalize_channel(color.get("green"))
    b = _normalize_channel(color.get("blue"))
    return r, g, b


def _rgb_to_hex(r: Optional[int], g: Optional[int], b: Optional[int]) -> Optional[str]:
    """Turn (R,G,B) to '#RRGGBB' if all components are present."""
    if r is None or g is None or b is None:
        return None
    return f"#{r:02X}{g:02X}{b:02X}"


def _to_iso(year: int, month: int, day: int) -> str:
    """Format an API date triple to ISO 'YYYY-MM-DD'."""
    try:
        return date(year, month, day).isoformat()
    except Exception:
        return f"{year:04d}-{month:02d}-{day:02d}"


def _normalize_cfs(value: Any) -> str:
    """Normalize 'create_forecast_sensors' option across legacy and new values."""
    if not isinstance(value, str):
        return DEFAULT_CREATE_FORECAST_SENSORS
    v = value.strip().lower()
    if v in {"d1", "d+1"}:
        return "d1"
    if v in {"d12", "d+1+2", "d1+2"}:
        return "d12"
    if v in {"none", ""}:
        return "none"
    if value in {"D+1"}:
        return "d1"
    if value in {"D+1+2"}:
        return "d12"
    return DEFAULT_CREATE_FORECAST_SENSORS


# ---------------------- Data model -----------------------------------------


@dataclass
class PollenIndex:
    value: Optional[float]
    category: Optional[str]
    description: Optional[str]
    color_raw: Optional[dict]
    color_rgb: Optional[List[int]]
    color_hex: Optional[str]

    @classmethod
    def from_index_info(cls, info: dict | None) -> "PollenIndex":
        """Create a PollenIndex from API indexInfo (can be None)."""
        if not isinstance(info, dict):
            return cls(None, None, None, None, None, None)
        value = info.get("value")
        category = info.get("category")
        # Google UPI sometimes exposes indexDescription or description
        description = info.get("indexDescription") or info.get("description")
        color = info.get("color")
        r, g, b = _color_dict_to_rgb(color)
        hexv = _rgb_to_hex(r, g, b)
        rgb_list = None if None in (r, g, b) else [r, g, b]
        return cls(value, category, description, color, rgb_list, hexv)


class PollenCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and normalize pollen data for multiple days."""

    def __init__(self, hass: HomeAssistant, entry):
        self.hass = hass
        self.entry = entry
        self.api_key: str = entry.data[CONF_API_KEY]
        self.lat: float = float(entry.data[CONF_LATITUDE])
        self.lon: float = float(entry.data[CONF_LONGITUDE])
        # Options (prefer options, fallback to data/defaults)
        self.interval_h: int = entry.options.get(
            CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )
        self.lang: str = entry.options.get(
            CONF_LANGUAGE_CODE, entry.data.get(CONF_LANGUAGE_CODE, hass.config.language or "en")
        )
        self.days: int = int(entry.options.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS))
        # Normalize legacy values for per-day sensors (D+1/D+1+2)
        raw_cfs = entry.options.get(CONF_CREATE_FORECAST_SENSORS, DEFAULT_CREATE_FORECAST_SENSORS)
        self.cfs: str = _normalize_cfs(raw_cfs)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(hours=max(1, self.interval_h)),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Call the API and normalize data for sensors."""
        params = {
            "key": self.api_key,
            "location.latitude": f"{self.lat:.6f}",
            "location.longitude": f"{self.lon:.6f}",
            "days": max(1, min(5, self.days)),
            "languageCode": self.lang,
        }
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(API_URL, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise UpdateFailed(f"HTTP {resp.status}: {text}")
                payload = await resp.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise UpdateFailed("Timeout calling Pollen API") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Client error: {err}") from err
        except Exception as err:  # pragma: no cover
            raise UpdateFailed(f"Unexpected error: {err}") from err

        return self._normalize_payload(payload)

    def _normalize_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        """Produce a normalized dict with aggregates for TYPES and PLANTS."""
        region = data.get("regionCode")
        daily = data.get("dailyInfo") or []

        days_norm: list[dict[str, Any]] = []
        for i, day in enumerate(daily):
            d = day.get("date") or {}
            iso = _to_iso(d.get("year", 1970), d.get("month", 1), d.get("day", 1))
            # Types
            ptypes = {}
            for t in day.get("pollenTypeInfo") or []:
                code = t.get("code")
                if not code:
                    continue
                idx = PollenIndex.from_index_info(t.get("indexInfo"))
                ptypes[code] = {
                    "code": code,
                    "displayName": t.get("displayName") or code,
                    "index": idx.__dict__,
                }
            # Plants
            plants = {}
            for p in day.get("plantInfo") or []:
                code = p.get("code")
                if not code:
                    continue
                idx = PollenIndex.from_index_info(p.get("indexInfo"))
                plants[code] = {
                    "code": code,
                    "displayName": p.get("displayName") or code,
                    "index": idx.__dict__,
                    "inSeason": p.get("inSeason"),
                    "type": p.get("type"),
                    "family": p.get("family"),
                    "season": p.get("season"),
                    "advice": p.get("advice"),
                    "cross_reaction": p.get("cross_reaction"),
                }
            days_norm.append({"offset": i, "date": iso, "types": ptypes, "plants": plants})

        # Aggregate per TYPE across days
        types_agg: dict[str, dict[str, Any]] = {}
        for day in days_norm:
            for code, obj in day["types"].items():
                entry = types_agg.setdefault(
                    code,
                    {
                        "code": code,
                        "displayName": obj["displayName"],
                        "forecast": [],
                    },
                )
                idx = obj.get("index") or {}
                has_index = idx.get("value") is not None
                entry["forecast"].append(
                    {
                        "offset": day["offset"],
                        "date": day["date"],
                        "has_index": has_index,
                        "value": idx.get("value"),
                        "category": idx.get("category"),
                        "description": idx.get("description"),
                        "color_hex": idx.get("color_hex"),
                        "color_rgb": idx.get("color_rgb"),
                        "color_raw": idx.get("color_raw"),
                    }
                )

        # Aggregate per PLANT across days
        plants_agg: dict[str, dict[str, Any]] = {}
        for day in days_norm:
            for code, obj in day["plants"].items():
                entry = plants_agg.setdefault(
                    code,
                    {
                        "code": code,
                        "displayName": obj["displayName"],
                        "inSeason": obj.get("inSeason"),
                        "type": obj.get("type"),
                        "family": obj.get("family"),
                        "season": obj.get("season"),
                        "advice": obj.get("advice"),
                        "cross_reaction": obj.get("cross_reaction"),
                        "forecast": [],
                    },
                )
                idx = obj.get("index") or {}
                has_index = idx.get("value") is not None
                entry["forecast"].append(
                    {
                        "offset": day["offset"],
                        "date": day["date"],
                        "has_index": has_index,
                        "value": idx.get("value"),
                        "category": idx.get("category"),
                        "description": idx.get("description"),
                        "color_hex": idx.get("color_hex"),
                        "color_rgb": idx.get("color_rgb"),
                        "color_raw": idx.get("color_raw"),
                    }
                )

        # Compute conveniences/derived
        def _inject_convenience(base: dict[str, Any]) -> None:
            """Add tomorrow_*, d2_*, trend and expected_peak to a base dict with 'forecast'."""
            flist = base.get("forecast") or []
            # tomorrow / d2
            for label, off in (("tomorrow", 1), ("d2", 2)):
                found = next((d for d in flist if d["offset"] == off), None)
                base[f"{label}_has_index"] = found.get("has_index") if found else False
                base[f"{label}_value"] = found.get("value") if found and found.get("has_index") else None
                base[f"{label}_category"] = found.get("category") if found and found.get("has_index") else None
                base[f"{label}_description"] = (
                    found.get("description") if found and found.get("has_index") else None
                )
                base[f"{label}_color_hex"] = found.get("color_hex") if found and found.get("has_index") else None

            # trend (0 vs 1)
            now = next((d for d in flist if d["offset"] == 0), None)
            nxt = next((d for d in flist if d["offset"] == 1), None)
            base["trend"] = None
            if now and nxt and isinstance(now.get("value"), (int, float)) and isinstance(
                nxt.get("value"), (int, float)
            ):
                if nxt["value"] > now["value"]:
                    base["trend"] = "up"
                elif nxt["value"] < now["value"]:
                    base["trend"] = "down"
                else:
                    base["trend"] = "flat"

            # expected_peak (max value in future horizon)
            peak = None
            for f in flist:
                if f.get("has_index") and isinstance(f.get("value"), (int, float)):
                    if peak is None or f["value"] > peak["value"]:
                        peak = f
            base["expected_peak"] = peak

        for v in types_agg.values():
            _inject_convenience(v)
        for v in plants_agg.values():
            _inject_convenience(v)

        return {
            "regionCode": region,
            "days": days_norm,
            "types": types_agg,
            "plants": plants_agg,
            "last_updated": dt_util.utcnow().isoformat(),
        }


# ---------------------- Entities -------------------------------------------


class BasePollenEntity(CoordinatorEntity[PollenCoordinator]):
    """Common behavior for entities, with translated device grouping."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PollenCoordinator) -> None:
        super().__init__(coordinator)
        self._entry_id = coordinator.entry.entry_id

    # Group key used for device translation: 'types' | 'plants' | 'info'
    @property
    def group_key(self) -> str:
        return "info"

    @property
    def device_info(self):
        """Group entities per logical translated device (Types / Plants / Info)."""
        lat = self.coordinator.lat
        lon = self.coordinator.lon
        device_id = f"{self._entry_id}_{self.group_key}"
        return {
            "identifiers": {(DOMAIN, device_id)},
            "manufacturer": "Google Maps Pollen API",
            "model": "forecast:lookup",
            "translation_key": self.group_key,
            "translation_placeholders": {
                "latitude": f"{lat:.4f}",
                "longitude": f"{lon:.4f}",
            },
        }

    @property
    def attribution(self) -> str:
        return "Data provided by Google Maps Pollen API"

    @property
    def extra_state_attributes(self):
        return {ATTR_ATTRIBUTION: self.attribution}


class RegionSensor(BasePollenEntity):
    """Region code sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "region"

    @property
    def group_key(self) -> str:  # ensure device under Info
        return "info"

    def __init__(self, coordinator: PollenCoordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._entry_id}_region"

    @property
    def native_value(self) -> Optional[str]:
        return self.coordinator.data.get("regionCode")


class DateSensor(BasePollenEntity):
    """Date (ISO) of the first day in payload."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "date"

    @property
    def group_key(self) -> str:
        return "info"

    def __init__(self, coordinator: PollenCoordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._entry_id}_date"

    @property
    def native_value(self) -> Optional[str]:
        days = self.coordinator.data.get("days") or []
        return (days[0].get("date") if days else None) or None


class LastUpdatedSensor(BasePollenEntity):
    """Last successful update timestamp (UTC ISO-8601)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "last_updated"

    @property
    def group_key(self) -> str:
        return "info"

    def __init__(self, coordinator: PollenCoordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._entry_id}_last_updated"
        self._attr_icon = "mdi:update"

    @property
    def native_value(self) -> Optional[str]:
        return self.coordinator.data.get("last_updated")


class PollenTypeSensor(BasePollenEntity):
    """A sensor for a pollen TYPE (GRASS/TREE/WEED)."""

    @property
    def group_key(self) -> str:
        return "types"

    def __init__(self, coordinator: PollenCoordinator, code: str):
        super().__init__(coordinator)
        self.code = code
        self._attr_unique_id = f"{self._entry_id}_type_{self.code.lower()}"
        self._attr_icon = TYPE_ICONS.get(code, DEFAULT_ICON)
        self._attr_name = self.display_name

    @property
    def display_name(self) -> str:
        item = (self.coordinator.data.get("types") or {}).get(self.code, {})
        return item.get("displayName") or self.code

    @property
    def native_value(self) -> Optional[float]:
        item = (self.coordinator.data.get("types") or {}).get(self.code, {})
        f0 = next((d for d in item.get("forecast", []) if d["offset"] == 0), None)
        return f0.get("value") if f0 and f0.get("has_index") else None

    @property
    def extra_state_attributes(self) -> dict:
        base = (self.coordinator.data.get("types") or {}).get(self.code, {})
        f0 = next((d for d in base.get("forecast", []) if d["offset"] == 0), None) or {}
        attrs = {
            **super().extra_state_attributes,
            "category": f0.get("category"),
            "description": f0.get("description"),
            "color_hex": f0.get("color_hex"),
            "color_rgb": f0.get("color_rgb"),
            "color_raw": f0.get("color_raw"),
            "forecast": base.get("forecast"),
            "tomorrow_value": base.get("tomorrow_value"),
            "tomorrow_category": base.get("tomorrow_category"),
            "tomorrow_description": base.get("tomorrow_description"),
            "tomorrow_color_hex": base.get("tomorrow_color_hex"),
            "d2_value": base.get("d2_value"),
            "d2_category": base.get("d2_category"),
            "d2_description": base.get("d2_description"),
            "d2_color_hex": base.get("d2_color_hex"),
            "trend": base.get("trend"),
            "expected_peak": base.get("expected_peak"),
        }
        return attrs


class PollenPlantSensor(BasePollenEntity):
    """A sensor for a specific plant/species."""

    @property
    def group_key(self) -> str:
        return "plants"

    def __init__(self, coordinator: PollenCoordinator, code: str):
        super().__init__(coordinator)
        self.code = code
        self._attr_unique_id = f"{self._entry_id}_plant_{self.code.lower()}"
        # name & icon are computed dynamically via properties
        self._attr_name = self.display_name

    @property
    def display_name(self) -> str:
        item = (self.coordinator.data.get("plants") or {}).get(self.code, {})
        return item.get("displayName") or self.code

    @property
    def native_value(self) -> Optional[float]:
        item = (self.coordinator.data.get("plants") or {}).get(self.code, {})
        f0 = next((d for d in item.get("forecast", []) if d["offset"] == 0), None)
        return f0.get("value") if f0 and f0.get("has_index") else None

    @property
    def icon(self) -> str:
        """Compute icon dynamically from latest 'type'."""
        base = (self.coordinator.data.get("plants") or {}).get(self.code, {})
        typ = (base.get("type") or "").upper()
        return PLANT_TYPE_ICONS.get(typ, DEFAULT_ICON)

    @property
    def extra_state_attributes(self) -> dict:
        base = (self.coordinator.data.get("plants") or {}).get(self.code, {})
        f0 = next((d for d in base.get("forecast", []) if d["offset"] == 0), None) or {}
        attrs = {
            **super().extra_state_attributes,
            "category": f0.get("category"),
            "description": f0.get("description"),
            "color_hex": f0.get("color_hex"),
            "color_rgb": f0.get("color_rgb"),
            "color_raw": f0.get("color_raw"),
            "inSeason": base.get("inSeason"),
            "type": base.get("type"),
            "family": base.get("family"),
            "season": base.get("season"),
            "advice": base.get("advice"),
            "cross_reaction": base.get("cross_reaction"),
            "forecast": base.get("forecast"),
            "tomorrow_value": base.get("tomorrow_value"),
            "tomorrow_category": base.get("tomorrow_category"),
            "tomorrow_description": base.get("tomorrow_description"),
            "tomorrow_color_hex": base.get("tomorrow_color_hex"),
            "d2_value": base.get("d2_value"),
            "d2_category": base.get("d2_category"),
            "d2_description": base.get("d2_description"),
            "d2_color_hex": base.get("d2_color_hex"),
            "trend": base.get("trend"),
            "expected_peak": base.get("expected_peak"),
        }
        return attrs


class PollenTypeDaySensor(PollenTypeSensor):
    """Per-day sensor for a pollen TYPE (offset = 1 or 2)."""

    def __init__(self, coordinator: PollenCoordinator, code: str, offset: int):
        super().__init__(coordinator, code)
        self.offset = offset
        self._attr_unique_id = f"{self._entry_id}_type_{self.code.lower()}_d{offset}"
        self._attr_name = f"{self.display_name} (D+{offset})"

    @property
    def native_value(self) -> Optional[float]:
        base = (self.coordinator.data.get("types") or {}).get(self.code, {})
        f = next((d for d in base.get("forecast", []) if d["offset"] == self.offset), None)
        return f.get("value") if f and f.get("has_index") else None

    @property
    def extra_state_attributes(self) -> dict:
        base = (self.coordinator.data.get("types") or {}).get(self.code, {})
        f = next((d for d in base.get("forecast", []) if d["offset"] == self.offset), None) or {}
        attrs = {
            **super().extra_state_attributes,
            "date": f.get("date"),
            "category": f.get("category"),
            "description": f.get("description"),
            "color_hex": f.get("color_hex"),
            "color_rgb": f.get("color_rgb"),
            "color_raw": f.get("color_raw"),
        }
        return attrs


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up sensors from a config entry."""
    coordinator = PollenCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entities: list = []

    # Meta
    entities.append(RegionSensor(coordinator))
    entities.append(DateSensor(coordinator))
    entities.append(LastUpdatedSensor(coordinator))

    # Types
    for tcode, tdata in (coordinator.data.get("types") or {}).items():
        entities.append(PollenTypeSensor(coordinator, tcode))

    # Plants
    for pcode, pdata in (coordinator.data.get("plants") or {}).items():
        entities.append(PollenPlantSensor(coordinator, pcode))

    # Optional per-day sensors for TYPES
    cfs = coordinator.cfs
    offsets: list[int] = []
    if cfs == CFS_D1:
        offsets = [1]
    elif cfs == CFS_D12:
        offsets = [1, 2]

    # Only create offsets that exist in data
    available_offsets = {d["offset"] for d in coordinator.data.get("days", [])}
    offsets = [o for o in offsets if o in available_offsets]

    for tcode in (coordinator.data.get("types") or {}).keys():
        for off in offsets:
            entities.append(PollenTypeDaySensor(coordinator, tcode, off))

    # Cleanup: remove stale per-day sensors if option changed or days reduced
    await _cleanup_stale_type_day_sensors(hass, entry, desired_offsets=set(offsets))

    async_add_entities(entities, update_before_add=False)


async def _cleanup_stale_type_day_sensors(
    hass: HomeAssistant, entry, desired_offsets: set[int]
) -> None:
    """Delete orphaned TYPE per-day sensors from the entity registry.

    This handles:
    - Switching from D+1/D+1+2 to none
    - Reducing forecast_days (e.g., from 3 to 2 => remove all _d2)
    """
    reg = er.async_get(hass)
    prefix = f"{entry.entry_id}_type_"
    # Build a whitelist of allowed suffixes for the current config
    allowed_suffixes = {f"_d{o}" for o in desired_offsets}

    for ent_id in list(reg.entities):
        ent = reg.entities.get(ent_id)
        if ent and ent.platform == DOMAIN and ent.unique_id.startswith(prefix):
            # Filter only per-day entities (unique_id ends with _dN)
            if "_d" in ent.unique_id:
                if not any(ent.unique_id.endswith(suf) for suf in allowed_suffixes):
                    _LOGGER.info("Removing stale per-day entity: %s", ent.unique_id)
                    reg.async_remove(ent.entity_id)
