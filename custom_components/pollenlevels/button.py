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
from .runtime import PollenLevelsConfigEntry

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PollenDataUpdateCoordinator
    from .runtime import PollenLocationRuntime

_LOGGER = logging.getLogger(__name__)


def _coordinator_identity_id(coordinator: PollenDataUpdateCoordinator) -> str:
    """Return the stable identity used for entity unique IDs."""
    return getattr(coordinator, "entity_identity_id", None) or coordinator.entry_id


def _coordinator_device_id(coordinator: PollenDataUpdateCoordinator, group: str) -> str:
    """Return the stable device identifier for a location/group pair."""
    identity_id = getattr(coordinator, "device_identity_id", None) or (
        getattr(coordinator, "entity_identity_id", None) or coordinator.entry_id
    )
    return f"{identity_id}_{group}"


def _add_button_for_location(
    async_add_entities: AddEntitiesCallback,
    location: PollenLocationRuntime,
) -> None:
    """Add a location button with subentry association when supported."""
    entities = [PollenLevelsUpdateButton(location.coordinator)]
    try:
        async_add_entities(entities, config_subentry_id=location.subentry_id)
    except TypeError:
        async_add_entities(entities)


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: PollenLevelsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Pollen Levels update buttons for all configured locations."""
    runtime = config_entry.runtime_data
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

    for location in locations.values():
        _add_button_for_location(async_add_entities, location)


class PollenLevelsUpdateButton(CoordinatorEntity, ButtonEntity):
    """Button entity to manually refresh a single location."""

    _attr_has_entity_name = True
    _attr_translation_key = "update_now"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PollenDataUpdateCoordinator) -> None:
        """Initialize update button entity."""
        super().__init__(coordinator)
        identity_id = _coordinator_identity_id(coordinator)
        self._attr_unique_id = f"{identity_id}_update_now"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, _coordinator_device_id(coordinator, "meta"))},
            "manufacturer": "Google",
            "model": "Pollen API",
            "translation_key": "info",
            "translation_placeholders": {
                "title": coordinator.entry_title,
                "latitude": f"{coordinator.lat:.2f}",
                "longitude": f"{coordinator.lon:.2f}",
            },
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
