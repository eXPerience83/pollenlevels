"""Shared entity helpers for Pollen Levels platforms."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from .const import DOMAIN
from .util import coordinator_device_id

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import DeviceInfo
    from homeassistant.helpers.entity import Entity
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import PollenDataUpdateCoordinator


def add_entities_for_subentry(
    async_add_entities: AddConfigEntryEntitiesCallback,
    entities: Sequence[Entity],
    subentry_id: str,
) -> None:
    """Add entities with their location subentry association."""
    async_add_entities(
        list(entities),
        config_subentry_id=subentry_id,
    )


def device_translation_placeholders(
    coordinator: PollenDataUpdateCoordinator,
) -> dict[str, str]:
    """Return privacy-preserving placeholders for translated device names."""
    return {
        "title": coordinator.entry_title,
        "latitude": f"{coordinator.lat:.2f}",
        "longitude": f"{coordinator.lon:.2f}",
    }


def build_device_info(
    coordinator: PollenDataUpdateCoordinator,
    group: str,
    translation_key: str,
) -> DeviceInfo:
    """Build fresh device info without selecting a group or caching values."""
    return {
        "identifiers": {(DOMAIN, coordinator_device_id(coordinator, group))},
        "manufacturer": "Google",
        "model": "Pollen API",
        "translation_key": translation_key,
        "translation_placeholders": device_translation_placeholders(coordinator),
    }
