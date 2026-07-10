"""Pollen data update coordinator."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import GooglePollenApiClient
from .const import (
    DEFAULT_ENTRY_TITLE,
    DOMAIN,
    FORECAST_DAYS,
)
from .forecast import attach_forecast_attributes
from .util import (
    normalize_language_code,
    redact_sensitive_values,
    safe_parse_int,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


_LOGGER = logging.getLogger(__name__)
STALE_DATA_TTL = timedelta(hours=24)


def _normalize_channel(v: Any) -> int | None:
    """Normalize a single channel to 0..255 (accept 0..1 or 0..255 inputs).

    Returns None if the value cannot be interpreted as a number.
    """
    try:
        f = float(v)
    except TypeError, ValueError, OverflowError:
        return None
    if not math.isfinite(f):
        return None
    if 0.0 <= f <= 1.0:
        f *= 255.0
    return max(0, min(255, int(round(f))))


def _rgb_from_api(color: dict[str, Any] | None) -> tuple[int, int, int] | None:
    """Build an (R, G, B) tuple from API color dict.

    Rules:
    - If color is not a dict, or an empty dict, return None
      (meaning "no color provided by API").
    - If only some channels are present, missing ones are treated as 0 (zero baseline)
      but ONLY when at least one channel exists. This preserves partial colors like
      {green, blue} without inventing a color for {}.
    """
    if not isinstance(color, dict) or not color:
        return None

    r = _normalize_channel(color.get("red"))
    g = _normalize_channel(color.get("green"))
    b = _normalize_channel(color.get("blue"))

    # If all channels are None, treat as no color
    if r is None and g is None and b is None:
        return None

    # Replace missing channels with 0 (only when at least one exists)
    return (r or 0, g or 0, b or 0)


def _rgb_to_hex_triplet(rgb: tuple[int, int, int] | None) -> str | None:
    """Convert (R,G,B) 0..255 to #RRGGBB."""
    if rgb is None:
        return None
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


def _normalize_plant_code(code: Any) -> str:
    """Normalize plant code for cross-day map lookups."""
    if code is None:
        return ""
    return str(code).strip().upper()


def _extract_api_date(day: dict[str, Any]) -> str | None:
    """Extract a YYYY-MM-DD date string from one API dailyInfo item."""
    date_obj = day.get("date") or {}
    if not isinstance(date_obj, dict):
        return None

    year = safe_parse_int(date_obj.get("year"))
    month = safe_parse_int(date_obj.get("month"))
    day_num = safe_parse_int(date_obj.get("day"))
    if year is None or month is None or day_num is None:
        return None
    return f"{year:04d}-{month:02d}-{day_num:02d}"


def _build_forecast_entry(
    offset: int, date: str | None, item: dict[str, Any]
) -> dict[str, Any]:
    """Build one behavior-preserving forecast entry from an API item."""
    idx_raw = item.get("indexInfo")
    idx = idx_raw if isinstance(idx_raw, dict) else {}
    has_index = bool(idx)
    rgb = _rgb_from_api(idx.get("color")) if has_index else None
    return {
        "offset": offset,
        "date": date,
        "has_index": has_index,
        "value": idx.get("value") if has_index else None,
        "category": idx.get("category") if has_index else None,
        "description": idx.get("indexDescription") if has_index else None,
        "color_hex": _rgb_to_hex_triplet(rgb) if has_index else None,
        "color_rgb": list(rgb) if (has_index and rgb is not None) else None,
    }


def _build_forecast_list(
    daily: list[dict[str, Any]],
    item_by_day_code: list[dict[str, dict[str, Any]]],
    code: str,
    forecast_days: int,
) -> list[dict[str, Any]]:
    """Build forecast entries for one pollen type or plant code."""
    forecast_list: list[dict[str, Any]] = []
    for offset, day in enumerate(daily[1:], start=1):
        if offset >= forecast_days:
            break
        date_str = _extract_api_date(day)
        item = item_by_day_code[offset].get(code) or {}
        forecast_list.append(_build_forecast_entry(offset, date_str, item))
    return forecast_list


class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinate pollen data fetch with forecast support for TYPES and PLANTS."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        lat: float,
        lon: float,
        hours: int,
        language: str | None,
        entry_id: str,
        client: GooglePollenApiClient,
        entry_title: str = DEFAULT_ENTRY_TITLE,
        subentry_id: str | None = None,
        legacy_entry_id: str | None = None,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize coordinator with configuration and interval."""
        explicit_subentry = subentry_id is not None
        subentry_id = subentry_id or entry_id
        update_interval = timedelta(hours=hours)
        coordinator_kwargs: dict[str, Any] = {
            "name": f"{DOMAIN}_{entry_id}_{subentry_id}",
            "update_interval": update_interval,
        }
        if config_entry is not None:
            coordinator_kwargs["config_entry"] = config_entry
        try:
            super().__init__(
                hass,
                _LOGGER,
                **coordinator_kwargs,
            )
        except TypeError as err:
            if "config_entry" not in coordinator_kwargs or "config_entry" not in str(
                err
            ):
                raise
            coordinator_kwargs.pop("config_entry")
            super().__init__(
                hass,
                _LOGGER,
                **coordinator_kwargs,
            )
        self.api_key = api_key
        self.lat = lat
        self.lon = lon

        normalized_language = normalize_language_code(language)
        if (
            normalized_language is None
            and isinstance(language, str)
            and language.strip()
        ):
            _LOGGER.warning("Ignoring invalid stored API language code")
        self.language = normalized_language

        self.entry_id = entry_id
        self.subentry_id = subentry_id
        self.legacy_entry_id = legacy_entry_id
        self.entity_identity_id = legacy_entry_id or (
            f"{entry_id}_{subentry_id}" if explicit_subentry else entry_id
        )
        self.device_identity_id = self.entity_identity_id
        self.entry_title = entry_title or DEFAULT_ENTRY_TITLE
        self.forecast_days = FORECAST_DAYS
        self._client = client
        self._missing_dailyinfo_warned = False
        self._stale_dailyinfo_warned = False

        self.data: dict[str, dict[str, Any]] = {}
        self.last_updated: datetime | None = None

    def _utcnow(self) -> datetime:
        """Return the current UTC time."""
        return dt_util.utcnow()

    def _stale_data_ttl(self) -> timedelta:
        """Return the fixed maximum stale-data retention, currently 24 hours."""
        return STALE_DATA_TTL

    def _has_fresh_cached_data(self) -> bool:
        """Return whether cached data is still within the stale-data tolerance."""
        if not self.data or self.last_updated is None:
            return False
        return self._utcnow() - self.last_updated <= self._stale_data_ttl()

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch pollen data and extract sensors for current day and forecast."""
        try:
            payload = await self._client.async_fetch_pollen_data(
                latitude=self.lat,
                longitude=self.lon,
                days=self.forecast_days,
                language_code=self.language,
            )
        except ConfigEntryAuthFailed:
            raise
        except UpdateFailed:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as err:  # Keep previous behavior for unexpected errors
            msg = redact_sensitive_values(
                err,
                api_key=self.api_key,
                latitude=self.lat,
                longitude=self.lon,
            )
            _LOGGER.error("Pollen API error: %s", msg)
            raise UpdateFailed(msg) from err

        new_data: dict[str, dict[str, Any]] = {}

        # region
        if region := payload.get("regionCode"):
            new_data["region"] = {"source": "meta", "value": region}

        daily_raw = payload.get("dailyInfo")
        daily = daily_raw if isinstance(daily_raw, list) else None
        # Keep day offsets stable: if any element is invalid, treat the payload as
        # malformed instead of compacting/reindexing list positions.
        if daily is not None and any(not isinstance(item, dict) for item in daily):
            daily = None

        if not daily:
            if self._has_fresh_cached_data():
                if not self._missing_dailyinfo_warned:
                    cache_age = self._utcnow() - self.last_updated
                    _LOGGER.warning(
                        "API response missing or invalid dailyInfo; "
                        "keeping last successful data within TTL "
                        "(cache_age=%s, ttl=%s)",
                        cache_age,
                        self._stale_data_ttl(),
                    )
                    self._missing_dailyinfo_warned = True
                return self.data
            if self.data:
                if not self._stale_dailyinfo_warned:
                    _LOGGER.warning(
                        "API response missing or invalid dailyInfo; cached data expired"
                    )
                    self._stale_dailyinfo_warned = True
                raise UpdateFailed(
                    "API response missing or invalid dailyInfo; cached data expired"
                )
            raise UpdateFailed("API response missing or invalid dailyInfo")
        self._missing_dailyinfo_warned = False
        self._stale_dailyinfo_warned = False

        # date (today)
        first_day = daily[0]
        date_str = _extract_api_date(first_day)
        if date_str is not None:
            new_data["date"] = {"source": "meta", "value": date_str}

        type_codes: set[str] = set()
        type_by_day_code: list[dict[str, dict[str, Any]]] = []
        plant_by_day_code: list[dict[str, dict[str, Any]]] = []
        for day in daily:
            day_types: dict[str, dict[str, Any]] = {}
            for item in day.get("pollenTypeInfo", []) or []:
                if not isinstance(item, dict):
                    continue
                code = (item.get("code") or "").upper()
                if code:
                    day_types[code] = item
                    type_codes.add(code)
            type_by_day_code.append(day_types)

            day_plants: dict[str, dict[str, Any]] = {}
            for item in day.get("plantInfo", []) or []:
                if not isinstance(item, dict):
                    continue
                code = _normalize_plant_code(item.get("code"))
                if code:
                    day_plants[code] = item
            plant_by_day_code.append(day_plants)

        # Current-day TYPES
        for tcode in sorted(type_codes):
            titem = type_by_day_code[0].get(tcode) or {}
            idx_raw = titem.get("indexInfo")
            idx = idx_raw if isinstance(idx_raw, dict) else {}
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
            }

        plant_keys: list[str] = []

        # Current-day PLANTS
        for _norm_code, pitem in sorted(plant_by_day_code[0].items()):
            # NOTE: plant_by_day_code[0] is built using normalized, non-empty plant codes as keys,
            # so `_norm_code` is guaranteed to be a stable non-empty identifier.
            # We still derive `code` from the raw API field (stripped) for attributes, while
            # using lowercased `code` for the sensor key to keep entity creation deterministic.
            idx_raw = pitem.get("indexInfo")
            idx = idx_raw if isinstance(idx_raw, dict) else {}
            desc_raw = pitem.get("plantDescription")
            desc = desc_raw if isinstance(desc_raw, dict) else {}
            rgb = _rgb_from_api(idx.get("color"))
            raw_code = pitem.get("code")
            code = str(raw_code).strip() if raw_code is not None else ""
            key = f"plants_{code.lower()}"
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
                "picture": desc.get("picture"),
                "picture_closeup": desc.get("pictureCloseup"),
            }
            plant_keys.append(key)

        # Forecast for TYPES
        for tcode in sorted(type_codes):
            type_key = f"type_{tcode.lower()}"
            existing = new_data.get(type_key)
            needs_skeleton = not existing or (
                existing.get("source") == "type"
                and existing.get("value") is None
                and existing.get("category") is None
                and existing.get("description") is None
            )
            base = existing or {}
            if needs_skeleton:
                base = {
                    "source": "type",
                    "displayName": tcode,
                    "inSeason": None,
                    "advice": None,
                    "value": None,
                    "category": None,
                    "description": None,
                    "color_hex": None,
                    "color_rgb": None,
                }

                candidate = None
                for day_idx, _day_data in enumerate(daily):
                    candidate = type_by_day_code[day_idx].get(tcode)
                    if isinstance(candidate, dict):
                        base["displayName"] = candidate.get("displayName", tcode)
                        base["inSeason"] = candidate.get("inSeason")
                        base["advice"] = candidate.get("healthRecommendations")
                        break
            forecast_list = _build_forecast_list(
                daily, type_by_day_code, tcode, self.forecast_days
            )
            # Attach common forecast attributes (convenience, trend, expected_peak)
            base = attach_forecast_attributes(base, forecast_list)
            new_data[type_key] = base

        # Forecast for PLANTS (attributes only; no per-day plant sensors)
        for key in plant_keys:
            base = new_data.get(key) or {}
            pcode = _normalize_plant_code(base.get("code"))
            if not pcode:
                # Safety: skip if for some reason code is missing
                continue

            forecast_list = _build_forecast_list(
                daily, plant_by_day_code, pcode, self.forecast_days
            )

            # Attach common forecast attributes (convenience, trend, expected_peak)
            base = attach_forecast_attributes(base, forecast_list)
            new_data[key] = base

        self.data = new_data
        self.last_updated = self._utcnow()
        if _LOGGER.isEnabledFor(logging.DEBUG):
            total = len(new_data)
            types = 0
            plants = 0
            meta = 0
            for value in new_data.values():
                source = value.get("source")
                if source == "type":
                    types += 1
                elif source == "plant":
                    plants += 1
                else:
                    meta += 1
            updated = self.last_updated.isoformat() if self.last_updated else "unknown"
            _LOGGER.debug(
                "Update complete: entries=%d types=%d plants=%d meta=%d "
                "forecast_days=%d updated=%s",
                total,
                types,
                plants,
                meta,
                self.forecast_days,
                updated,
            )
        return self.data
