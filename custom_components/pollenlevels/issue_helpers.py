"""Helpers for creating and deleting Home Assistant Repair issues."""

from __future__ import annotations

from collections.abc import Collection, Iterator
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DEFAULT_ENTRY_TITLE, DOMAIN

PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID = "per_day_forecast_sensors_removed"
LOCATION_SETUP_FAILED_TRANSLATION_KEY = "location_setup_failed"


def _issue_id_from_registry_item(key: Any, value: Any) -> str | None:
    """Return this domain's issue id from HA or test registry storage."""
    if isinstance(key, tuple) and len(key) == 2:
        domain, issue_id = key
        if domain != DOMAIN or not isinstance(issue_id, str):
            return None
        return issue_id

    if not isinstance(key, str):
        return None

    domain = (
        value.get("domain")
        if isinstance(value, dict)
        else getattr(value, "domain", None)
    )
    if domain != DOMAIN:
        return None
    return key


def _iter_domain_issue_ids(hass: HomeAssistant) -> Iterator[str]:
    """Yield current issue ids for this integration."""
    registry_getter = getattr(ir, "async_get", None)
    if not callable(registry_getter):
        return

    registry = registry_getter(hass)
    issues = getattr(registry, "issues", {})
    for key, value in list(issues.items()):
        if issue_id := _issue_id_from_registry_item(key, value):
            yield issue_id


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


def location_setup_failed_issue_id(entry_id: str, subentry_id: str) -> str:
    """Return a deterministic issue ID for a local location setup failure."""
    return f"location_setup_failed_{entry_id}_{subentry_id}"


def delete_stale_location_subentry_issues(
    hass: HomeAssistant,
    *,
    entry_id: str,
    active_subentry_ids: Collection[str],
) -> None:
    """Delete location Repair issues for subentries no longer configured."""
    active_ids = set(active_subentry_ids)
    legacy_invalid_issue_id = invalid_stored_location_issue_id(entry_id)
    prefixes = (
        f"invalid_stored_location_{entry_id}_",
        f"location_setup_failed_{entry_id}_",
    )

    for issue_id in _iter_domain_issue_ids(hass):
        if issue_id == legacy_invalid_issue_id:
            continue
        for prefix in prefixes:
            if (
                issue_id.startswith(prefix)
                and issue_id.removeprefix(prefix) not in active_ids
            ):
                ir.async_delete_issue(hass, DOMAIN, issue_id)
                break


def create_location_setup_failed_issue(
    hass: HomeAssistant,
    *,
    entry_id: str,
    entry_title: str | None,
    location_title: str | None,
    subentry_id: str,
    error_type: str,
    reason: str,
) -> None:
    """Create a Repair issue for an isolated location setup failure."""
    issue_id = location_setup_failed_issue_id(entry_id, subentry_id)
    entry_title = (entry_title or "").strip() or DEFAULT_ENTRY_TITLE
    location_title = (location_title or "").strip() or entry_title
    error_type = (error_type or "").strip() or "UnknownError"
    reason = (reason or "").strip() or "Location setup failed"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=LOCATION_SETUP_FAILED_TRANSLATION_KEY,
        translation_placeholders={
            "entry_title": entry_title,
            "location_title": location_title,
            "error_type": error_type,
            "reason": reason,
        },
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


def delete_location_setup_failed_issue(
    hass: HomeAssistant,
    *,
    entry_id: str,
    subentry_id: str,
) -> None:
    """Delete a Repair issue for an isolated location setup failure if present."""
    issue_id = location_setup_failed_issue_id(entry_id, subentry_id)
    ir.async_delete_issue(hass, DOMAIN, issue_id)
