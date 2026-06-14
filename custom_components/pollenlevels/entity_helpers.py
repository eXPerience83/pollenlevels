"""Shared entity helpers for Pollen Levels platforms."""

from __future__ import annotations

from annotationlib import Format
from collections.abc import Sequence
from inspect import Parameter, signature
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PollenDataUpdateCoordinator


def add_entities_for_subentry(
    async_add_entities: AddEntitiesCallback,
    entities: Sequence[Any],
    subentry_id: str,
) -> None:
    """Add entities with subentry association when supported by Home Assistant."""
    entity_list = list(entities)
    supports_subentry_id = _supports_config_subentry_id(async_add_entities)
    if supports_subentry_id is False:
        async_add_entities(entity_list)
        return

    try:
        async_add_entities(entity_list, config_subentry_id=subentry_id)
    except TypeError as err:
        if supports_subentry_id is not None or not (
            _is_unsupported_config_subentry_id_type_error(err)
        ):
            raise
        async_add_entities(entity_list)


def _supports_config_subentry_id(callback: AddEntitiesCallback) -> bool | None:
    """Return callback support for config_subentry_id, or None when ambiguous."""
    try:
        parameters = signature(
            callback, annotation_format=Format.STRING
        ).parameters.values()
    except TypeError, ValueError:
        return None

    accepts_var_kwargs = False
    for parameter in parameters:
        if parameter.name == "config_subentry_id":
            return True
        if parameter.kind is Parameter.VAR_KEYWORD:
            accepts_var_kwargs = True
    return None if accepts_var_kwargs else False


def _is_unsupported_config_subentry_id_type_error(err: TypeError) -> bool:
    """Return whether ``err`` is from an unsupported config_subentry_id kwarg."""
    message = str(err)
    return "config_subentry_id" in message and "unexpected keyword argument" in message


def device_translation_placeholders(
    coordinator: PollenDataUpdateCoordinator,
) -> dict[str, str]:
    """Return privacy-preserving placeholders for translated device names."""
    return {
        "title": coordinator.entry_title,
        "latitude": f"{coordinator.lat:.2f}",
        "longitude": f"{coordinator.lon:.2f}",
    }
