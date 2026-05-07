"""Pollen Levels sensors with multi-day forecast (types & plants).

Key points:
- Cleans up stale per-day sensors (D+1/D+2) in Entity Registry on reload.
- Normalizes language (trim/omit when empty) before calling the API.
- Redacts API keys in debug logs.
- Minimal safe backoff: single retry on transient errors (Timeout/5xx/429).
- Timeout handling: on modern Python (3.11+), built-in `TimeoutError` also covers
  `asyncio.TimeoutError`, so catching `TimeoutError` is sufficient and preferred.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable
from datetime import date  # Added `date` for DATE device class native_value
from enum import StrEnum
from numbers import Real
from typing import TYPE_CHECKING, Any, cast

# Modern sensor base + enums
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er  # entity-registry cleanup
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTRIBUTION,
    CONF_API_KEY,
    CONF_FORECAST_DAYS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_FORECAST_DAYS,
    MIN_FORECAST_DAYS,
)
from .coordinator import PollenDataUpdateCoordinator
from .runtime import PollenLevelsConfigEntry, PollenLevelsRuntimeData
from .util import safe_parse_int

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "CONF_API_KEY",
    "CONF_LATITUDE",
    "CONF_LONGITUDE",
    "CONF_UPDATE_INTERVAL",
    "DEFAULT_FORECAST_DAYS",
    "DEFAULT_UPDATE_INTERVAL",
]

# ---- Icons ---------------------------------------------------------------

TYPE_ICONS = {
    "GRASS": "mdi:grass",
    "TREE": "mdi:tree",
    "WEED": "mdi:flower-tulip",
}
# Plants reuse the same icon mapping by type.
PLANT_TYPE_ICONS = TYPE_ICONS
DEFAULT_ICON = "mdi:flower-pollen"


def _normalize_code(code: Any) -> str:
    """Return a stable normalized code for deterministic ordering."""
    return str(code or "").casefold()


def _is_finite_number(value: Any) -> bool:
    """Return whether a value is a finite non-boolean number."""
    return (
        isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)
    )


def _entry_code(key: str, info: dict[str, Any]) -> str:
    """Return the API code for a coordinator data entry."""
    if info.get("code") is not None:
        return str(info["code"])
    if key.startswith("type_"):
        return key.removeprefix("type_")
    if key.startswith("plants_"):
        return key.removeprefix("plants_")
    return key


def _display_name(code: str, info: dict[str, Any]) -> str:
    """Return a user-facing display name for a coordinator data entry."""
    return str(info.get("displayName") or info.get("name") or code)


def _current_type_entries(
    data: dict[str, Any],
) -> list[tuple[str, str, str, dict[str, Any]]]:
    """Return current-day pollen type entries sorted by normalized type code."""
    entries: list[tuple[str, str, str, dict[str, Any]]] = []
    for key, raw_info in data.items():
        if key.endswith(("_d1", "_d2")) or not isinstance(raw_info, dict):
            continue
        info = raw_info
        if info.get("source") != "type":
            continue
        code = _entry_code(key, info)
        entries.append((key, code, _display_name(code, info), info))
    entries.sort(key=lambda item: _normalize_code(item[1]))
    return entries


def _current_plant_entries(
    data: dict[str, Any],
) -> list[tuple[str, str, str, dict[str, Any]]]:
    """Return current-day plant entries sorted by normalized plant code."""
    entries: list[tuple[str, str, str, dict[str, Any]]] = []
    for key, raw_info in data.items():
        if not isinstance(raw_info, dict) or raw_info.get("source") != "plant":
            continue
        code = _entry_code(key, raw_info)
        entries.append((key, code, _display_name(code, raw_info), raw_info))
    entries.sort(key=lambda item: _normalize_code(item[1]))
    return entries


def _top_type_entries(
    data: dict[str, Any],
) -> tuple[float | int | None, list[tuple[str, str, str, dict[str, Any]]]]:
    """Return the maximum current-day type value and all entries tied for it."""
    valid_entries = [
        entry
        for entry in _current_type_entries(data)
        if _is_finite_number(entry[3].get("value"))
    ]
    if not valid_entries:
        return None, []
    top_value = max(entry[3]["value"] for entry in valid_entries)
    return top_value, [
        entry for entry in valid_entries if entry[3]["value"] == top_value
    ]


class ForecastSensorMode(StrEnum):
    """Options for forecast sensor creation."""

    NONE = "none"
    D1 = "D+1"
    D1_D2 = "D+1+2"


async def _cleanup_per_day_entities(
    hass: HomeAssistant, entry_id: str, allow_d1: bool, allow_d2: bool
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

    removals: list[Awaitable[Any]] = []

    for ent in entries:
        if ent.domain != "sensor" or ent.platform != DOMAIN:
            continue
        if not allow_d1 and _matches(ent.unique_id, "_d1"):
            _LOGGER.debug(
                "Removing stale D+1 entity from registry: %s (%s)",
                ent.entity_id,
                ent.unique_id,
            )
            removal = registry.async_remove(ent.entity_id)
            if asyncio.iscoroutine(removal):
                removals.append(removal)
            removed += 1
            continue
        if not allow_d2 and _matches(ent.unique_id, "_d2"):
            _LOGGER.debug(
                "Removing stale D+2 entity from registry: %s (%s)",
                ent.entity_id,
                ent.unique_id,
            )
            removal = registry.async_remove(ent.entity_id)
            if asyncio.iscoroutine(removal):
                removals.append(removal)
            removed += 1

    if removals:
        await asyncio.gather(*removals)

    if removed:
        _LOGGER.info(
            "Entity Registry cleanup: removed %d per-day sensors for entry %s",
            removed,
            entry_id,
        )
    return removed


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: PollenLevelsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create coordinator and build sensors."""
    runtime = cast(
        PollenLevelsRuntimeData | None, getattr(config_entry, "runtime_data", None)
    )
    if runtime is None:
        raise ConfigEntryNotReady("Runtime data not ready")
    coordinator = runtime.coordinator

    opts = config_entry.options or {}
    raw_days = opts.get(CONF_FORECAST_DAYS, coordinator.forecast_days)
    parsed = safe_parse_int(raw_days)
    if parsed is None:
        _LOGGER.warning(
            "Invalid forecast_days '%s' for entry %s; defaulting to %s",
            raw_days,
            config_entry.entry_id,
            coordinator.forecast_days,
        )
    forecast_days = parsed if parsed is not None else coordinator.forecast_days
    forecast_days = max(MIN_FORECAST_DAYS, min(MAX_FORECAST_DAYS, forecast_days))
    create_d1 = coordinator.create_d1
    create_d2 = coordinator.create_d2

    allow_d1 = create_d1 and forecast_days >= 2
    allow_d2 = create_d2 and forecast_days >= 3

    data = coordinator.data or {}
    has_daily = ("date" in data) or any(
        key.startswith(("type_", "plants_")) for key in data
    )
    if not has_daily:
        message = "No pollen data found during initial setup"
        _LOGGER.warning(message)
        raise ConfigEntryNotReady(message)

    # Proactively remove stale D+ entities from the Entity Registry
    await _cleanup_per_day_entities(
        hass, config_entry.entry_id, allow_d1=allow_d1, allow_d2=allow_d2
    )

    sensors: list[CoordinatorEntity] = []
    for code in data:
        if code in ("region", "date"):
            continue
        if code.endswith("_d1") and not allow_d1:
            continue
        if code.endswith("_d2") and not allow_d2:
            continue
        sensors.append(PollenSensor(coordinator, code))

    sensors.extend(
        [
            PlantsInSeasonTodaySensor(coordinator),
            OverallPollenRiskTodaySensor(coordinator),
            TopPollenTypesTodaySensor(coordinator),
            RegionSensor(coordinator),
            DateSensor(coordinator),
            LastUpdatedSensor(coordinator),
        ]
    )

    if _LOGGER.isEnabledFor(logging.DEBUG):
        ids = [getattr(s, "unique_id", None) for s in sensors]
        preview = ids[:10]
        extra = max(0, len(ids) - len(preview))
        suffix = f", +{extra} more" if extra else ""
        _LOGGER.debug(
            "Creating %d sensors (preview=%s%s)",
            len(ids),
            preview,
            suffix,
        )
    async_add_entities(sensors, True)


class PollenSensor(CoordinatorEntity, SensorEntity):
    """Represent a pollen sensor for a type, plant, or per-day type."""

    # Enable long-term statistics for numeric pollen index values
    _attr_state_class = SensorStateClass.MEASUREMENT
    # Hint the UI to show integers (does not affect recorder/statistics)
    _attr_suggested_display_precision = 0  # type: ignore[assignment]
    # Modern friendly name composition: Device name + Entity short name
    _attr_has_entity_name = True

    def __init__(self, coordinator: PollenDataUpdateCoordinator, code: str):
        """Initialize pollen sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.code = code
        # Pre-compute a stable unique_id; this never changes for the entity.
        self._attr_unique_id = f"{self.coordinator.entry_id}_{self.code}"

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
        """Return icon for sensor.

        Kept as a property: the icon depends on the sensor's sub-type.
        """
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
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

        for k in (
            "description",
            "inSeason",
            "advice",
            "color_hex",
            "color_rgb",
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
        if not group:
            if self.code.startswith("type_"):
                group = "type"
            elif self.code.startswith(("plant_", "plants_")):
                group = "plant"
            else:
                group = "meta"

        device_id = f"{self.coordinator.entry_id}_{group}"
        translation_keys = {"type": "types", "plant": "plants", "meta": "info"}
        translation_key = translation_keys.get(group, "info")
        return {
            "identifiers": {(DOMAIN, device_id)},
            "manufacturer": "Google",
            "model": "Pollen API",
            "translation_key": translation_key,
            "translation_placeholders": {
                "title": self.coordinator.entry_title or DEFAULT_ENTRY_TITLE,
                "latitude": f"{self.coordinator.lat:.6f}",
                "longitude": f"{self.coordinator.lon:.6f}",
            },
        }


class _BaseSummarySensor(CoordinatorEntity, SensorEntity):
    """Provide base behavior for daily summary sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PollenDataUpdateCoordinator, group: str) -> None:
        """Initialize a daily summary sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator

        device_id = f"{self.coordinator.entry_id}_{group}"
        translation_keys = {"type": "types", "plant": "plants"}
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "manufacturer": "Google",
            "model": "Pollen API",
            "translation_key": translation_keys[group],
            "translation_placeholders": {
                "title": self.coordinator.entry_title or DEFAULT_ENTRY_TITLE,
                "latitude": f"{self.coordinator.lat:.6f}",
                "longitude": f"{self.coordinator.lon:.6f}",
            },
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common daily summary attributes."""
        return {ATTR_ATTRIBUTION: ATTRIBUTION}


class PlantsInSeasonTodaySensor(_BaseSummarySensor):
    """Represent the daily count of plants currently in season."""

    _attr_translation_key = "plants_in_season_today"
    _attr_icon = "mdi:sprout"

    def __init__(self, coordinator: PollenDataUpdateCoordinator):
        """Initialize the plants in season summary sensor."""
        super().__init__(coordinator, "plant")
        self._attr_unique_id = f"{self.coordinator.entry_id}_plants_in_season_today"

    def _season_counts(self) -> dict[str, Any]:
        """Return deterministic plant season counts and lists."""
        entries = _current_plant_entries(self.coordinator.data or {})
        plant_codes: list[str] = []
        plant_names: list[str] = []
        unknown_codes: list[str] = []
        unknown_names: list[str] = []
        in_season_count = 0
        out_of_season_count = 0
        unknown_season_count = 0

        for _key, code, name, info in entries:
            plant_codes.append(code)
            plant_names.append(name)
            in_season = info.get("inSeason")
            if in_season is True:
                in_season_count += 1
            elif in_season is False:
                out_of_season_count += 1
            else:
                unknown_season_count += 1
                unknown_codes.append(code)
                unknown_names.append(name)

        return {
            "plant_codes": plant_codes,
            "plant_names": plant_names,
            "in_season_count": in_season_count,
            "out_of_season_count": out_of_season_count,
            "unknown_season_count": unknown_season_count,
            "total_plant_count": len(entries),
            "unknown_season_codes": unknown_codes,
            "unknown_season_names": unknown_names,
        }

    @property
    def native_value(self) -> int | None:
        """Return the number of plants explicitly marked as in season."""
        counts = self._season_counts()
        known_count = counts["in_season_count"] + counts["out_of_season_count"]
        if counts["total_plant_count"] == 0 or known_count == 0:
            return None
        return counts["in_season_count"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return plant season summary attributes."""
        return super().extra_state_attributes | self._season_counts()


class OverallPollenRiskTodaySensor(_BaseSummarySensor):
    """Represent the highest current-day pollen type index."""

    _attr_translation_key = "overall_pollen_risk_today"
    _attr_icon = DEFAULT_ICON
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0  # type: ignore[assignment]

    def __init__(self, coordinator: PollenDataUpdateCoordinator):
        """Initialize the overall pollen risk summary sensor."""
        super().__init__(coordinator, "type")
        self._attr_unique_id = f"{self.coordinator.entry_id}_overall_pollen_risk_today"

    @property
    def native_value(self) -> float | int | None:
        """Return the maximum valid current-day pollen type value."""
        top_value, _entries = _top_type_entries(self.coordinator.data or {})
        return top_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return overall pollen risk summary attributes."""
        _top_value, entries = _top_type_entries(self.coordinator.data or {})
        first_info = entries[0][3] if entries else {}
        return super().extra_state_attributes | {
            "category": first_info.get("category"),
            "description": first_info.get("description"),
            "top_pollen_codes": [entry[1] for entry in entries],
            "top_pollen_names": [entry[2] for entry in entries],
            "top_pollen_categories": [entry[3].get("category") for entry in entries],
            "tie_count": len(entries),
        }


class TopPollenTypesTodaySensor(_BaseSummarySensor):
    """Represent the highest current-day pollen type names."""

    _attr_translation_key = "top_pollen_types_today"
    _attr_icon = DEFAULT_ICON

    def __init__(self, coordinator: PollenDataUpdateCoordinator):
        """Initialize the top pollen types summary sensor."""
        super().__init__(coordinator, "type")
        self._attr_unique_id = f"{self.coordinator.entry_id}_top_pollen_types_today"

    @property
    def native_value(self) -> str | None:
        """Return the top pollen type name or comma-separated tied names."""
        _top_value, entries = _top_type_entries(self.coordinator.data or {})
        if not entries:
            return None
        return ", ".join(entry[2] for entry in entries)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return top pollen type summary attributes."""
        top_value, entries = _top_type_entries(self.coordinator.data or {})
        return super().extra_state_attributes | {
            "top_value": top_value,
            "top_pollen_codes": [entry[1] for entry in entries],
            "top_pollen_names": [entry[2] for entry in entries],
            "top_pollen_categories": [entry[3].get("category") for entry in entries],
            "tie_count": len(entries),
        }


class _BaseMetaSensor(CoordinatorEntity, SensorEntity):
    """Provide base for metadata sensors."""

    def __init__(self, coordinator: PollenDataUpdateCoordinator):
        """Initialize metadata sensor.

        Static attributes are precomputed as `_attr_*` to avoid repeated property calls.
        """
        super().__init__(coordinator)
        self.coordinator = coordinator

        device_id = f"{self.coordinator.entry_id}_meta"
        # Precompute device_info; location and identifiers are stable for the entry.
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "manufacturer": "Google",
            "model": "Pollen API",
            "translation_key": "info",
            "translation_placeholders": {
                "title": self.coordinator.entry_title or DEFAULT_ENTRY_TITLE,
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
        return {ATTR_ATTRIBUTION: ATTRIBUTION}


class RegionSensor(_BaseMetaSensor):
    """Represent region code sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "region"
    # Metadata; classify as diagnostic for better UI grouping.
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PollenDataUpdateCoordinator):
        """Initialize region sensor with static attributes."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.coordinator.entry_id}_region"
        self._attr_icon = "mdi:earth"

    @property
    def native_value(self):
        """Return region code."""
        return self.coordinator.data.get("region", {}).get("value")


class DateSensor(_BaseMetaSensor):
    """Represent forecast date sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "date"
    # Metadata; classify as diagnostic for better UI grouping.
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # Use DATE so the frontend applies date semantics/formatting.
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: PollenDataUpdateCoordinator):
        """Initialize date sensor with static attributes."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.coordinator.entry_id}_date"
        self._attr_icon = "mdi:calendar"

    @property
    def native_value(self) -> date | None:
        """Return forecast date as a `datetime.date` object (required for DATE).

        The coordinator stores an ISO 'YYYY-MM-DD' string; we parse it here.
        """
        date_str = self.coordinator.data.get("date", {}).get("value")
        if not date_str:
            return None
        try:
            y, m, d = map(int, date_str.split("-"))
            return date(y, m, d)
        except ValueError, TypeError:
            _LOGGER.error("Invalid date format received: %s", date_str)
            return None


class LastUpdatedSensor(_BaseMetaSensor):
    """Represent timestamp of last successful update."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "last_updated"
    # Use TIMESTAMP so the frontend formats the datetime automatically
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: PollenDataUpdateCoordinator):
        """Initialize last updated sensor with static attributes."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.coordinator.entry_id}_last_updated"
        self._attr_icon = "mdi:clock-check"

    @property
    def native_value(self):
        """Return UTC datetime of last update; frontend will localize/format."""
        # Coordinator stores an aware UTC datetime; HA expects a datetime object
        # for TIMESTAMP sensors. The UI will render it as local time.
        return self.coordinator.last_updated
