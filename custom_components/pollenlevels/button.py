"""Button platform for per-location manual updates."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity_helpers import add_entities_for_subentry, device_translation_placeholders
from .runtime import PollenLevelsConfigEntry
from .util import (
    coordinator_device_id,
    coordinator_identity_id,
    stale_runtime_location_filter,
)

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PollenDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: PollenLevelsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Pollen Levels update buttons for all configured locations."""
    runtime = getattr(config_entry, "runtime_data", None)
    if runtime is None:
        raise ConfigEntryNotReady("Runtime data not ready")
    locations = getattr(runtime, "locations", None) or {}
    if not locations:
        coordinator = getattr(runtime, "coordinator", None)
        if coordinator is not None:
            async_add_entities([PollenLevelsUpdateButton(coordinator)])
            return
        _LOGGER.debug("No location subentries configured; no update buttons to add")
        return

    active_subentry_ids, filter_stale_locations = stale_runtime_location_filter(
        config_entry
    )
    for location in locations.values():
        if filter_stale_locations and location.subentry_id not in active_subentry_ids:
            _LOGGER.debug(
                "Skipping stale Pollen Levels button runtime location %s",
                location.subentry_id,
            )
            continue
        add_entities_for_subentry(
            async_add_entities,
            [PollenLevelsUpdateButton(location.coordinator)],
            location.subentry_id,
        )


class PollenLevelsUpdateButton(CoordinatorEntity, ButtonEntity):
    """Button entity to manually refresh a single location."""

    _attr_has_entity_name = True
    _attr_translation_key = "update_now"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PollenDataUpdateCoordinator) -> None:
        """Initialize update button entity."""
        super().__init__(coordinator)
        identity_id = coordinator_identity_id(coordinator)
        self._attr_unique_id = f"{identity_id}_update_now"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator_device_id(coordinator, "meta"))},
            "manufacturer": "Google",
            "model": "Pollen API",
            "translation_key": "info",
            "translation_placeholders": device_translation_placeholders(coordinator),
        }

    @property
    def available(self) -> bool:
        """Return whether the button is available."""
        return True

    async def async_press(self) -> None:
        """Refresh this config entry's coordinator."""
        try:
            await self.coordinator.async_request_refresh()
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Manual update button refresh failed for entry %s (%s)",
                self.coordinator.entry_id,
                type(err).__name__,
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="refresh_failed",
            ) from err

        if self.coordinator.last_update_success:
            return

        last_exception = getattr(self.coordinator, "last_exception", None)
        error_type = type(last_exception).__name__ if last_exception else "UnknownError"
        _LOGGER.warning(
            "Manual update button refresh failed for entry %s (%s)",
            self.coordinator.entry_id,
            error_type,
        )
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="refresh_failed",
        )
