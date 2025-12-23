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
from collections.abc import Awaitable
from datetime import date  # Added `date` for DATE device class native_value
from enum import StrEnum
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
    try:
        val = float(opts.get(CONF_FORECAST_DAYS, coordinator.forecast_days))
        if val != val or val in (float("inf"), float("-inf")):
            raise ValueError
        forecast_days = int(val)
    except (TypeError, ValueError, OverflowError):
        forecast_days = coordinator.forecast_days
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
        except (ValueError, TypeError):
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
