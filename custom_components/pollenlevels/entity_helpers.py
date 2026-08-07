"""Shared entity helpers for Pollen Levels platforms."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import PollenDataUpdateCoordinator


def add_entities_for_subentry(
    async_add_entities: AddConfigEntryEntitiesCallback,
    entities: Sequence[Any],
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
