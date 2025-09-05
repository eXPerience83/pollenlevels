"""Pollen Levels sensors with multi-day forecast (types & plants).

Key points:
- Cleans up stale per-day sensors (D+1/D+2) in Entity Registry on reload.
- Normalizes language (trim/omit when empty) before calling the API.
- Redacts API keys in debug logs.
- Minimal safe backoff: single retry on transient errors (Timeout/5xx/429).
- Timeout handling: on Python 3.11, built-in `TimeoutError` also covers `asyncio.TimeoutError`,
  so catching `TimeoutError` is sufficient and preferred.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import timedelta
from typing import Any

import aiohttp  # For explicit ClientTimeout and ClientError

# NEW: modern sensor base + enums
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.helpers import entity_registry as er  # entity-registry cleanup
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
# Plants reuse the same icon mapping by type.
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
    """Remove stale per-day entities (D+1/D+2) from the Entity Registry.

    HA keeps entity registry entries across reloads. If options disable per-day
    sensors (or forecast_days is insufficient), we proactively remove registry
    entries to avoid "Unavailable" ghosts in the UI.
    """
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry_id)
    removed = 0

    def _matches(uid: str, suffix: str) -> bool:
        """Check if a unique_id belongs to this entry and ends with suffix."""
        if not uid.startswith(f"{entry_id}_"):
            return False
        return uid.endswith(suffix)

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
    """Create coordinator and build sensors."""
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

    # Proactively remove stale D+ entities from the Entity Registry
    await _cleanup_per_day_entities(
        hass, entry.entry_id, allow_d1=allow_d1, allow_d2=allow_d2
    )

    coordinator = PollenDataUpdateCoordinator(
        hass=hass,
        api_key=api_key,
        lat=lat,
        lon=lon,
        hours=interval,
        language=lang,  # normalized in the coordinator
        entry_id=entry.entry_id,
        forecast_days=forecast_days,
        create_d1=allow_d1,  # pass effective flags
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
    """Coordinate pollen data fetch with forecast support for TYPES and PLANTS."""

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

        # Normalize language once at runtime:
        # - Trim whitespace
        # - Use None if empty after normalization (skip sending languageCode)
        if isinstance(language, str):
            language = language.strip()
        self.language = language if language else None

        self.entry_id = entry_id
        self.forecast_days = max(1, min(5, int(forecast_days)))
        self.create_d1 = create_d1
        self.create_d2 = create_d2

        self.data: dict[str, dict] = {}
        self.last_updated = None
        self._session = async_get_clientsession(hass)

    # ------------------------------
    # DRY helper for forecast attrs
    # ------------------------------
    def _process_forecast_attributes(
        self, base: dict[str, Any], forecast_list: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Attach common forecast attributes to a base sensor dict.

        This keeps TYPE and PLANT processing consistent without duplicating code.

        Adds:
          - 'forecast' list
          - Convenience: tomorrow_* / d2_*
          - Derived: trend, expected_peak

        Does NOT touch per-day TYPE sensor creation (kept elsewhere).
        """
        base["forecast"] = forecast_list

        def _set_convenience(prefix: str, off: int) -> None:
            f = next((d for d in forecast_list if d["offset"] == off), None)
            base[f"{prefix}_has_index"] = f.get("has_index") if f else False
            base[f"{prefix}_value"] = (
                f.get("value") if f and f.get("has_index") else None
            )
            base[f"{prefix}_category"] = (
                f.get("category") if f and f.get("has_index") else None
            )
            base[f"{prefix}_description"] = (
                f.get("description") if f and f.get("has_index") else None
            )
            base[f"{prefix}_color_hex"] = (
                f.get("color_hex") if f and f.get("has_index") else None
            )

        _set_convenience("tomorrow", 1)
        _set_convenience("d2", 2)

        # Trend (today vs tomorrow)
        now_val = base.get("value")
        tomorrow_val = base.get("tomorrow_value")
        if isinstance(now_val, int | float) and isinstance(tomorrow_val, int | float):
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
        return base

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

        # Redact API key in logs
        safe_params = dict(params)
        if "key" in safe_params:
            safe_params["key"] = "***"
        _LOGGER.debug("Fetching with params: %s", safe_params)

        # --- Minimal, safe retry policy (single retry) -----------------------
        max_retries = 1  # Keep it minimal to reduce cost/latency
        for attempt in range(0, max_retries + 1):
            try:
                # Explicit total timeout for network call
                async with self._session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    # Non-retryable auth logic first
                    if resp.status == 403:
                        raise UpdateFailed("Invalid API key")

                    # 429: may be transient — respect Retry-After if present
                    if resp.status == 429:
                        if attempt < max_retries:
                            retry_after_raw = resp.headers.get("Retry-After")
                            delay = 2.0
                            if retry_after_raw:
                                try:
                                    delay = float(retry_after_raw)
                                except (TypeError, ValueError):
                                    delay = 2.0
                            # Cap delay and add small jitter to avoid herding
                            delay = min(delay, 5.0) + random.uniform(0.0, 0.4)
                            _LOGGER.warning(
                                "Pollen API 429 — retrying in %.2fs (attempt %d/%d)",
                                delay,
                                attempt + 1,
                                max_retries,
                            )
                            await asyncio.sleep(delay)
                            continue
                        raise UpdateFailed("Quota exceeded")

                    # 5xx -> retry once with short backoff
                    if 500 <= resp.status <= 599:
                        if attempt < max_retries:
                            delay = 0.8 * (2**attempt) + random.uniform(0.0, 0.3)
                            _LOGGER.warning(
                                "Pollen API HTTP %s — retrying in %.2fs (attempt %d/%d)",
                                resp.status,
                                delay,
                                attempt + 1,
                                max_retries,
                            )
                            await asyncio.sleep(delay)
                            continue
                        raise UpdateFailed(f"HTTP {resp.status}")

                    # Other 4xx (client errors except 403/429) are not retried
                    if 400 <= resp.status < 500 and resp.status not in (403, 429):
                        raise UpdateFailed(f"HTTP {resp.status}")

                    if resp.status != 200:
                        raise UpdateFailed(f"HTTP {resp.status}")

                    payload = await resp.json()
                    break  # exit retry loop on success

            except TimeoutError as err:
                # Catch built-in TimeoutError; on Python 3.11 this also covers asyncio.TimeoutError.
                if attempt < max_retries:
                    delay = 0.8 * (2**attempt) + random.uniform(0.0, 0.3)
                    _LOGGER.warning(
                        "Pollen API timeout — retrying in %.2fs (attempt %d/%d)",
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                msg = str(err)
                if self.api_key:
                    msg = msg.replace(self.api_key, "***")
                raise UpdateFailed(f"Timeout: {msg}") from err

            except aiohttp.ClientError as err:
                # Transient client-side issues (DNS reset, connector errors, etc.)
                if attempt < max_retries:
                    delay = 0.8 * (2**attempt) + random.uniform(0.0, 0.3)
                    _LOGGER.warning(
                        "Network error to Pollen API — retrying in %.2fs (attempt %d/%d)",
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                msg = str(err)
                if self.api_key:
                    msg = msg.replace(self.api_key, "***")
                raise UpdateFailed(msg) from err

            except Exception as err:  # Keep previous behavior for unexpected errors
                msg = str(err)
                if self.api_key:
                    msg = msg.replace(self.api_key, "***")
                _LOGGER.error("Pollen API error: %s", msg)
                raise UpdateFailed(msg) from err
        # --------------------------------------------------------------------

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
            """Find a pollen TYPE entry by code inside a day's 'pollenTypeInfo'."""
            for item in day.get("pollenTypeInfo", []) or []:
                if (item.get("code") or "").upper() == code:
                    return item
            return None

        def _find_plant(day: dict, code: str) -> dict | None:
            """Find a PLANT entry by code inside a day's 'plantInfo'."""
            for item in day.get("plantInfo", []) or []:
                if (item.get("code") or "") == code:
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

        # Current-day PLANTS
        for pitem in first_day.get("plantInfo", []) or []:
            code = pitem.get("code")
            # Safety: skip plants without a stable 'code' to avoid duplicate 'plants_' keys
            # and silent overwrites. This is robust and avoids creating unstable entities.
            if not code:
                continue
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
        def _extract_day_info(day: dict) -> tuple[str | None, dict | None]:
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
            # Attach common forecast attributes (convenience, trend, expected_peak)
            base = self._process_forecast_attributes(base, forecast_list)
            new_data[type_key] = base

            # Optional per-day sensors (only if requested and day exists)
            def _add_day_sensor(
                off: int,
                *,
                _forecast_list=forecast_list,
                _base=base,
                _tcode=tcode,
                _type_key=type_key,
            ) -> None:
                """Create a per-day type sensor for a given offset."""
                f = next((d for d in _forecast_list if d["offset"] == off), None)
                if not f:
                    return

                # Use day-specific 'inSeason' and 'advice' from the forecast day.
                try:
                    day_obj = daily[off]
                except (IndexError, TypeError):
                    day_obj = None
                day_item = _find_type(day_obj, _tcode) if day_obj else None
                day_in_season = (
                    day_item.get("inSeason") if isinstance(day_item, dict) else None
                )
                day_advice = (
                    day_item.get("healthRecommendations")
                    if isinstance(day_item, dict)
                    else None
                )

                dname = f"{_base.get('displayName', _tcode)} (D+{off})"
                new_data[f"{_type_key}_d{off}"] = {
                    "source": "type",
                    "displayName": dname,
                    "value": f.get("value") if f.get("has_index") else None,
                    "category": f.get("category") if f.get("has_index") else None,
                    "description": f.get("description") if f.get("has_index") else None,
                    "inSeason": day_in_season,
                    "advice": day_advice,
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

        # Forecast for PLANTS (attributes only; no per-day plant sensors)
        for key, base in list(new_data.items()):
            if base.get("source") != "plant":
                continue
            pcode = base.get("code")
            if not pcode:
                # Safety: skip if for some reason code is missing
                continue

            forecast_list: list[dict[str, Any]] = []
            for offset, day in enumerate(daily[1:], start=1):
                if offset >= self.forecast_days:
                    break
                date_str, _ = _extract_day_info(day)
                item = _find_plant(day, pcode) or {}
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

            # Attach common forecast attributes (convenience, trend, expected_peak)
            base = self._process_forecast_attributes(base, forecast_list)
            new_data[key] = base

        self.data = new_data
        self.last_updated = dt_util.utcnow()
        _LOGGER.debug("Updated data: %s", self.data)
        return self.data


class PollenSensor(CoordinatorEntity, SensorEntity):
    """Represent a pollen sensor for a type, plant, or per-day type."""

    # Enable long-term statistics for numeric pollen index values
    _attr_state_class = SensorStateClass.MEASUREMENT
    # NEW: Hint the UI to show integers (does not affect recorder/statistics)
    _attr_suggested_display_precision = 0  # type: ignore[assignment]

    def __init__(self, coordinator: PollenDataUpdateCoordinator, code: str):
        """Initialize pollen sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.code = code

    @property
    def unique_id(self) -> str:
        """Return unique ID for sensor."""
        # Uses the internal config entry_id (UUID-like, no dots) plus the code
        return f"{self.coordinator.entry_id}_{self.code}"

    @property
    def name(self) -> str:
        """Return display name of sensor."""
        info = self.coordinator.data.get(self.code, {})
        return info.get("displayName", self.code)

    @property
    def native_value(self):
        """Return current pollen index value as the sensor's native value."""
        info = self.coordinator.data.get(self.code, {})
        return info.get("value")

    @property
    def icon(self) -> str:
        """Return icon for sensor."""
        info = self.coordinator.data.get(self.code, {})
        if info.get("source") == "type":
            base_key = self.code.split("_", 1)[1].split("_d", 1)[0].upper()
            return TYPE_ICONS.get(base_key, DEFAULT_ICON)
        # Normalize plant 'type' to uppercase to map icons reliably
        ptype = (info.get("type") or "").upper()
        return PLANT_TYPE_ICONS.get(ptype, DEFAULT_ICON)

    @property
    def extra_state_attributes(self):
        """Return extra attributes for sensor."""
        info = self.coordinator.data.get(self.code, {}) or {}
        attrs = {
            "category": info.get("category"),
            # Always include explicit public attribution on all pollen sensors.
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

        # Only include forecast-related attributes if more than 1 day was requested.
        include_forecast = getattr(self.coordinator, "forecast_days", 1) > 1

        # Forecast-related attributes:
        # - For TYPE sensors: include on main sensors only (not per-day _d1/_d2)
        # - For PLANT sensors: include as attributes (no per-day plant sensors)
        if info.get("source") == "type" and not self.code.endswith(("_d1", "_d2")):
            if include_forecast:
                # Add forecast attributes only when forecast is enabled.
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

        if info.get("source") == "plant":
            # Plant-specific metadata
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

            # Plant forecast attributes (attributes-only, no per-day plant sensors)
            if include_forecast:
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

        return attrs

    @property
    def device_info(self):
        """Return device info with translation support for the group."""
        info = self.coordinator.data.get(self.code, {}) or {}
        group = info.get("source")
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


class _BaseMetaSensor(CoordinatorEntity, SensorEntity):
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

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose a public attribution on all metadata sensors.

        This mirrors PollenSensor's attribution so *all* sensors in this
        integration consistently show the data source.
        """
        return {ATTR_ATTRIBUTION: "Data provided by Google Maps Pollen API"}


class RegionSensor(_BaseMetaSensor):
    """Represent region code sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "region"
    # NEW: This is metadata; classify as diagnostic for better UI grouping.
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return unique ID for region sensor."""
        return f"{self.coordinator.entry_id}_region"

    @property
    def native_value(self):
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
    # NEW: This is metadata; classify as diagnostic for better UI grouping.
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return unique ID for date sensor."""
        return f"{self.coordinator.entry_id}_date"

    @property
    def native_value(self):
        """Return forecast date as ISO string 'YYYY-MM-DD' (kept as string)."""
        # Keeping string to avoid changing device_class/semantics in a minimal change.
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
    # NEW: use TIMESTAMP so the frontend formats the datetime automatically
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def unique_id(self) -> str:
        """Return unique ID for last updated sensor."""
        return f"{self.coordinator.entry_id}_last_updated"

    @property
    def native_value(self):
        """Return UTC datetime of last update; frontend will localize/format."""
        # Coordinator stores an aware UTC datetime; HA expects a datetime object
        # for TIMESTAMP sensors. The UI will render it as local time.
        return self.coordinator.last_updated

    @property
    def icon(self):
        """Return icon for last updated sensor."""
        return "mdi:clock-check"
