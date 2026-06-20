"""Helpers for creating and deleting Home Assistant Repair issues."""

from __future__ import annotations

from collections.abc import Collection

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DEFAULT_ENTRY_TITLE, DOMAIN

PER_DAY_FORECAST_SENSORS_REMOVED_ISSUE_ID = "per_day_forecast_sensors_removed"
LOCATION_SETUP_FAILED_TRANSLATION_KEY = "location_setup_failed"
_LOCATION_REPAIR_ISSUES_DATA_KEY = "location_repair_issue_ids"


def _entry_location_issue_ids(hass: HomeAssistant, entry_id: str) -> set[str]:
    """Return location Repair issue ids owned by this runtime entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    issue_ids = domain_data.setdefault(_LOCATION_REPAIR_ISSUES_DATA_KEY, {})
    return issue_ids.setdefault(entry_id, set())


def _known_entry_location_issue_ids(
    hass: HomeAssistant, entry_id: str
) -> set[str] | None:
    """Return known location Repair issue ids without creating bookkeeping."""
    domain_data = hass.data.get(DOMAIN, {})
    issue_ids = domain_data.get(_LOCATION_REPAIR_ISSUES_DATA_KEY, {})
    return issue_ids.get(entry_id)


def _remember_location_issue(hass: HomeAssistant, entry_id: str, issue_id: str) -> None:
    """Remember a location Repair issue created by this integration runtime."""
    _entry_location_issue_ids(hass, entry_id).add(issue_id)


def _forget_location_issue(hass: HomeAssistant, entry_id: str, issue_id: str) -> None:
    """Forget a location Repair issue after it has been cleared."""
    domain_data = hass.data.get(DOMAIN, {})
    issue_ids = domain_data.get(_LOCATION_REPAIR_ISSUES_DATA_KEY, {})
    entry_issue_ids = issue_ids.get(entry_id)
    if not entry_issue_ids:
        return
    entry_issue_ids.discard(issue_id)
    if entry_issue_ids:
        return
    issue_ids.pop(entry_id, None)
    if not issue_ids:
        domain_data.pop(_LOCATION_REPAIR_ISSUES_DATA_KEY, None)


def _subentry_id_from_location_issue_id(entry_id: str, issue_id: str) -> str | None:
    """Return the subentry id encoded in a known location Repair issue id."""
    prefixes = (
        f"invalid_stored_location_{entry_id}_",
        f"location_setup_failed_{entry_id}_",
    )
    for prefix in prefixes:
        if issue_id.startswith(prefix):
            return issue_id.removeprefix(prefix) or None
    return None


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
    if subentry_id:
        _remember_location_issue(hass, entry_id, issue_id)


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
    entry_issue_ids = _known_entry_location_issue_ids(hass, entry_id)
    if not entry_issue_ids:
        return

    for issue_id in tuple(entry_issue_ids):
        subentry_id = _subentry_id_from_location_issue_id(entry_id, issue_id)
        if subentry_id is None or subentry_id in active_ids:
            continue
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        _forget_location_issue(hass, entry_id, issue_id)


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
    _remember_location_issue(hass, entry_id, issue_id)


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
    if subentry_id:
        _forget_location_issue(hass, entry_id, issue_id)


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
    _forget_location_issue(hass, entry_id, issue_id)
