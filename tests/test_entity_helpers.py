"""Unit tests for shared platform entity helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from custom_components.pollenlevels.entity_helpers import (
    add_entities_for_subentry,
    device_translation_placeholders,
)


def test_add_entities_for_subentry_passes_config_subentry_id() -> None:
    """Modern callbacks receive the subentry association."""
    first = object()
    second = object()
    calls: list[tuple[list[Any], bool, str | None]] = []

    def _add_entities(
        entities: list[Any],
        update_before_add: bool = False,
        *,
        config_subentry_id: str | None = None,
    ) -> None:
        calls.append((entities, update_before_add, config_subentry_id))

    add_entities_for_subentry(_add_entities, (first, second), "location-home")

    assert calls == [
        ([first, second], False, "location-home"),
    ]


def test_add_entities_for_subentry_reraises_internal_type_error() -> None:
    """Internal callback TypeError should propagate without retry."""
    calls: list[str | None] = []

    def _add_entities(
        entities: list[Any],
        *,
        config_subentry_id: str | None = None,
    ) -> None:
        calls.append(config_subentry_id)
        raise TypeError("internal config_subentry_id setup bug")

    try:
        add_entities_for_subentry(_add_entities, [object()], "location-home")
    except TypeError as err:
        assert str(err) == "internal config_subentry_id setup bug"
    else:  # pragma: no cover - assertion guard
        raise AssertionError("Expected internal TypeError to be reraised")

    assert calls == ["location-home"]


def test_device_translation_placeholders_round_coordinates() -> None:
    """Device placeholders keep titles and expose rounded coordinates."""
    coordinator = SimpleNamespace(
        entry_title="Home",
        lat=39.123456,
        lon=-0.123456,
    )

    assert device_translation_placeholders(coordinator) == {
        "title": "Home",
        "latitude": "39.12",
        "longitude": "-0.12",
    }
