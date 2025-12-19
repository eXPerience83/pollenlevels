"""Pollen data update coordinator."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import GooglePollenApiClient
from .const import (
    DEFAULT_ENTRY_TITLE,
    DOMAIN,
    MAX_FORECAST_DAYS,
    MIN_FORECAST_DAYS,
)
from .util import redact_api_key

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


_LOGGER = logging.getLogger(__name__)


def _normalize_channel(v: Any) -> int | None:
    """Normalize a single channel to 0..255 (accept 0..1 or 0..255 inputs).

    Returns None if the value cannot be interpreted as a number.
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if 0.0 <= f <= 1.0:
        f *= 255.0
    return max(0, min(255, int(round(f))))


def _rgb_from_api(color: dict[str, Any] | None) -> tuple[int, int, int] | None:
    """Build an (R, G, B) tuple from API color dict.

    Rules:
    - If color is not a dict, or an empty dict, or has no numeric channels at all,
      return None (meaning "no color provided by API").
    - If only some channels are present, missing ones are treated as 0 (black baseline)
      but ONLY when at least one channel exists. This preserves partial colors like
      {green, blue} without inventing a color for {}.
    """
    if not isinstance(color, dict) or not color:
        return None

    # Check if any of the channels is actually provided as numeric
    has_any_channel = any(
        isinstance(color.get(k), (int, float)) for k in ("red", "green", "blue")
    )
    if not has_any_channel:
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
        forecast_days: int,
        create_d1: bool,
        create_d2: bool,
        client: GooglePollenApiClient,
        entry_title: str = DEFAULT_ENTRY_TITLE,
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
        self.entry_title = entry_title or DEFAULT_ENTRY_TITLE
        # Clamp defensively for legacy/manual entries to supported range.
        self.forecast_days = max(
            MIN_FORECAST_DAYS, min(MAX_FORECAST_DAYS, int(forecast_days))
        )
        self.create_d1 = create_d1
        self.create_d2 = create_d2
        self._client = client

        self.data: dict[str, dict] = {}
        self.last_updated = None

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
        if isinstance(now_val, (int, float)) and isinstance(tomorrow_val, (int, float)):
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
            if f.get("has_index") and isinstance(f.get("value"), (int, float)):
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
        except Exception as err:  # Keep previous behavior for unexpected errors
            msg = redact_api_key(err, self.api_key)
            _LOGGER.error("Pollen API error: %s", msg)
            raise UpdateFailed(msg) from err

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
                    "color_raw": None,
                }

                candidate = None
                for day_data in daily:
                    candidate = _find_type(day_data, tcode)
                    if isinstance(candidate, dict):
                        base["displayName"] = candidate.get("displayName", tcode)
                        base["inSeason"] = candidate.get("inSeason")
                        base["advice"] = candidate.get("healthRecommendations")
                        break
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
        if _LOGGER.isEnabledFor(logging.DEBUG):
            total = len(new_data)
            types = 0
            plants = 0
            meta = 0
            per_day = 0
            for key, value in new_data.items():
                source = value.get("source")
                if source == "type":
                    types += 1
                elif source == "plant":
                    plants += 1
                else:
                    meta += 1
                if key.endswith(("_d1", "_d2")):
                    per_day += 1
            updated = self.last_updated.isoformat() if self.last_updated else "unknown"
            _LOGGER.debug(
                "Update complete: entries=%d types=%d plants=%d meta=%d per_day=%d "
                "forecast_days=%d d1=%s d2=%s updated=%s",
                total,
                types,
                plants,
                meta,
                per_day,
                self.forecast_days,
                self.create_d1,
                self.create_d2,
                updated,
            )
        return self.data
