"""Helpers for creating and deleting Home Assistant Repair issues."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DEFAULT_ENTRY_TITLE, DOMAIN

PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID = "per_day_forecast_sensors_removed"


def invalid_stored_location_issue_id(
    entry_id: str, subentry_id: str | None = None
) -> str:
    """Return a deterministic issue ID for an invalid stored location."""
    if subentry_id:
        return f"invalid_stored_location_{entry_id}_{subentry_id}"
    return f"invalid_stored_location_{entry_id}_legacy"


def create_invalid_stored_location_issue(
    hass: HomeAssistant,
    *,
    entry_id: str,
    entry_title: str | None,
    location_title: str | None,
    subentry_id: str | None = None,
) -> None:
    """Create a Repair issue for an invalid stored location."""
    issue_id = invalid_stored_location_issue_id(entry_id, subentry_id)
    entry_title = (entry_title or "").strip() or DEFAULT_ENTRY_TITLE
    location_title = (location_title or "").strip() or entry_title
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="invalid_stored_location",
        translation_placeholders={
            "entry_title": entry_title,
            "location_title": location_title,
        },
    )


def create_per_day_forecast_sensors_removed_issue(hass: HomeAssistant) -> None:
    """Create a Repair issue for removed legacy per-day forecast sensors."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID,
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID,
    )


def create_entry_invalid_stored_location_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Create a Repair issue for an invalid stored location on a config entry."""
    create_invalid_stored_location_issue(
        hass,
        entry_id=entry.entry_id,
        entry_title=entry.title,
        location_title=entry.title,
        subentry_id=None,
    )


def delete_invalid_stored_location_issue(
    hass: HomeAssistant,
    *,
    entry_id: str,
    subentry_id: str | None = None,
) -> None:
    """Delete a Repair issue for an invalid stored location if it exists."""
    issue_id = invalid_stored_location_issue_id(entry_id, subentry_id)
    ir.async_delete_issue(hass, DOMAIN, issue_id)


def delete_entry_invalid_stored_location_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Delete a Repair issue for an invalid stored location on a config entry."""
    delete_invalid_stored_location_issue(
        hass,
        entry_id=entry.entry_id,
        subentry_id=None,
    )
