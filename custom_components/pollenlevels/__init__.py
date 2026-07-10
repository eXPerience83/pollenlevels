"""Initialize Pollen Levels integration.

Notes:
- Adds a top-level DEBUG log when the force_update service is invoked to aid debugging.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol  # Service schema validation
from homeassistant.config_entries import ConfigEntry, ConfigSubentry as ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import GooglePollenApiClient
from .const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS as CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS as CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LEGACY_ENTRY_ID,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL_HOURS,
    MIN_UPDATE_INTERVAL_HOURS,
    SUBENTRY_TYPE_LOCATION,
)
from .coordinator import PollenDataUpdateCoordinator
from .issue_helpers import (
    create_invalid_stored_location_issue,
    create_location_setup_failed_issue,
    create_per_day_forecast_sensors_removed_issue,
    delete_entry_invalid_stored_location_issue,
    delete_entry_location_issues,
    delete_invalid_stored_location_issue,
    delete_location_setup_failed_issue,
    delete_stale_location_subentry_issues,
    invalid_stored_location_issue_id as invalid_stored_location_issue_id,
)
from .migration import (
    CONF_MERGED_INTO_ENTRY_ID,
    async_handle_entry_migration,
    is_entry_merged,
)
from .runtime import (
    PollenLevelsConfigEntry,
    PollenLevelsRuntimeData,
    PollenLocationRuntime,
    PollenLocationSetupFailure,
)
from .util import (
    active_location_subentry_ids,
    api_key_unique_id as api_key_unique_id,
    has_legacy_per_day_option,
    redact_sensitive_values,
    safe_parse_int,
    stale_runtime_location_filter,
    strip_legacy_forecast_options,
    validate_location_pair,
)

# Ensure YAML config is entry-only for this domain (no YAML schema).
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)
TARGET_ENTRY_VERSION = 6
_FORCE_UPDATE_CONCURRENCY_LIMIT = 1
_SETUP_FAILURE_REASON_MAX_LENGTH = 240
_SETUP_RETRY_FAILURES_DATA_KEY = "setup_retry_failures"
_NON_RETRYABLE_SETUP_FAILURE_TYPES = frozenset({"InvalidStoredLocation"})
PLATFORMS = ["sensor", "button"]


def _drop_legacy_parent_options(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove obsolete parent data/options from earlier v3 prereleases."""
    data = dict(entry.data or {})
    options = dict(entry.options or {})
    found_per_day_option = has_legacy_per_day_option(data, options)
    cleaned_data = strip_legacy_forecast_options(data)
    cleaned = strip_legacy_forecast_options(options)
    updates: dict[str, Any] = {}
    if cleaned_data != data:
        updates["data"] = cleaned_data
    if cleaned != options:
        updates["options"] = cleaned
    if not updates:
        return found_per_day_option

    hass.config_entries.async_update_entry(entry, **updates)
    return found_per_day_option


def _iter_location_subentries(
    entry: ConfigEntry,
) -> list[tuple[str, str, dict[str, Any], str | None]]:
    """Return location configuration tuples for setup."""
    subentries = getattr(entry, "subentries", {}) or {}
    locations: list[tuple[str, str, dict[str, Any], str | None]] = []
    for subentry in subentries.values():
        if getattr(subentry, "subentry_type", None) != SUBENTRY_TYPE_LOCATION:
            continue
        data = dict(getattr(subentry, "data", {}) or {})
        legacy_entry_id = data.get(CONF_LEGACY_ENTRY_ID)
        if not isinstance(legacy_entry_id, str) or not legacy_entry_id:
            legacy_entry_id = None
        locations.append(
            (
                subentry.subentry_id,
                (subentry.title or "").strip() or DEFAULT_ENTRY_TITLE,
                data,
                legacy_entry_id,
            )
        )

    if locations:
        return locations

    # Compatibility fallback for not-yet-migrated or test entries.
    data = dict(entry.data or {})
    if CONF_LATITUDE in data and CONF_LONGITUDE in data:
        locations.append(
            (
                entry.entry_id,
                (entry.title or "").strip() or DEFAULT_ENTRY_TITLE,
                data,
                entry.entry_id,
            )
        )
    return locations


def _location_issue_subentry_id(entry: ConfigEntry, subentry_id: str) -> str | None:
    """Return the Repair subentry id for a setup location."""
    subentries = getattr(entry, "subentries", {}) or {}
    return subentry_id if subentry_id in subentries else None


def _truncate_setup_failure_reason(reason: str) -> str:
    """Return a single-line setup failure reason bounded for Repairs."""
    cleaned = " ".join(reason.split()).strip()
    if len(cleaned) <= _SETUP_FAILURE_REASON_MAX_LENGTH:
        return cleaned
    return f"{cleaned[: _SETUP_FAILURE_REASON_MAX_LENGTH - 3]}..."


def _safe_setup_failure_text(
    value: Any,
    *,
    api_key: str | None,
    latitude: Any = None,
    longitude: Any = None,
    fallback: str,
) -> str:
    """Redact sensitive setup failure text before storing or surfacing it."""
    if value is None:
        return fallback
    redacted = redact_sensitive_values(
        value,
        api_key=api_key,
        latitude=latitude,
        longitude=longitude,
    )
    redacted = _truncate_setup_failure_reason(redacted)
    return redacted or fallback


def _coordinator_has_usable_initial_data(coordinator: Any) -> bool:
    """Return whether a first refresh produced enough data to build sensors."""
    data = getattr(coordinator, "data", None) or {}
    if not isinstance(data, dict):
        return False
    return ("date" in data) or any(
        isinstance(key, str) and key.startswith(("type_", "plant_", "plants_"))
        for key in data
    )


def _location_setup_failure(
    *,
    subentry_id: str,
    title: str,
    error_type: str,
    reason: str,
    api_key: str | None,
    latitude: Any = None,
    longitude: Any = None,
) -> PollenLocationSetupFailure:
    """Build redacted runtime metadata for an isolated setup failure."""
    safe_title = _safe_setup_failure_text(
        title,
        api_key=api_key,
        latitude=latitude,
        longitude=longitude,
        fallback=DEFAULT_ENTRY_TITLE,
    )
    safe_reason = _safe_setup_failure_text(
        reason,
        api_key=api_key,
        latitude=latitude,
        longitude=longitude,
        fallback="Location setup failed",
    )
    return PollenLocationSetupFailure(
        subentry_id=subentry_id,
        title=safe_title,
        reason=safe_reason,
        error_type=error_type or "UnknownError",
    )


def _entry_setup_retry_failures(hass: HomeAssistant, entry_id: str) -> set[str]:
    """Return setup failures that already received an automatic retry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    retry_failures = domain_data.setdefault(_SETUP_RETRY_FAILURES_DATA_KEY, {})
    return retry_failures.setdefault(entry_id, set())


def _mark_setup_retry_failure(
    hass: HomeAssistant, entry_id: str, subentry_id: str
) -> None:
    """Remember that a setup failure already received an automatic retry."""
    _entry_setup_retry_failures(hass, entry_id).add(subentry_id)


def _setup_retry_failure_seen(
    hass: HomeAssistant, entry_id: str, subentry_id: str
) -> bool:
    """Return whether this setup failure already received an automatic retry."""
    return subentry_id in _entry_setup_retry_failures(hass, entry_id)


def _clear_setup_retry_failure(
    hass: HomeAssistant, entry_id: str, subentry_id: str
) -> None:
    """Clear retry bookkeeping for a location that no longer needs it."""
    domain_data = hass.data.get(DOMAIN, {})
    retry_failures = domain_data.get(_SETUP_RETRY_FAILURES_DATA_KEY, {})
    entry_failures = retry_failures.get(entry_id)
    if not entry_failures:
        return
    entry_failures.discard(subentry_id)
    if not entry_failures:
        retry_failures.pop(entry_id, None)


def _prune_setup_retry_failures(
    hass: HomeAssistant, entry_id: str, active_subentry_ids: set[str]
) -> None:
    """Drop retry bookkeeping for locations that are no longer configured."""
    domain_data = hass.data.get(DOMAIN, {})
    retry_failures = domain_data.get(_SETUP_RETRY_FAILURES_DATA_KEY, {})
    entry_failures = retry_failures.get(entry_id)
    if not entry_failures:
        return
    entry_failures.intersection_update(active_subentry_ids)
    if not entry_failures:
        retry_failures.pop(entry_id, None)


def _setup_failure_is_retryable(failure: PollenLocationSetupFailure) -> bool:
    """Return whether a local setup failure can be retried by reloading."""
    return failure.error_type not in _NON_RETRYABLE_SETUP_FAILURE_TYPES


def _schedule_parent_reload(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Schedule a parent config entry reload when supported by the runtime."""
    schedule_reload = getattr(hass.config_entries, "async_schedule_reload", None)
    if callable(schedule_reload):
        schedule_reload(entry.entry_id)
        return True

    async_reload = getattr(hass.config_entries, "async_reload", None)
    if not callable(async_reload):
        return False

    result = async_reload(entry.entry_id)
    if asyncio.iscoroutine(result):
        create_task = getattr(hass, "async_create_task", None)
        if not callable(create_task):
            result.close()
            return False
        create_task(result, name=f"pollenlevels setup retry {entry.entry_id}")
    return True


# ---- Service -------------------------------------------------------------


def _log_force_update_failure(
    entry: ConfigEntry,
    subentry_id: str,
    coordinator: Any,
    result: BaseException | None,
) -> None:
    """Log one redacted force_update location failure."""
    api_key = (entry.data or {}).get(CONF_API_KEY)
    latitude = getattr(
        coordinator,
        "lat",
        (entry.data or {}).get(CONF_LATITUDE),
    )
    longitude = getattr(
        coordinator,
        "lon",
        (entry.data or {}).get(CONF_LONGITUDE),
    )
    if result is not None:
        safe_message = redact_sensitive_values(
            result,
            api_key=api_key,
            latitude=latitude,
            longitude=longitude,
        )
        error_type = type(result).__name__
    else:
        safe_message = "coordinator reported an unsuccessful update"
        error_type = "UpdateFailed"
    safe_text = safe_message or "no error details"
    if subentry_id == entry.entry_id:
        _LOGGER.warning(
            "Manual refresh failed for entry %s (%s): %s",
            entry.entry_id,
            error_type,
            safe_text,
        )
    else:
        _LOGGER.warning(
            "Manual refresh failed for entry %s subentry %s (%s): %s",
            entry.entry_id,
            subentry_id,
            error_type,
            safe_text,
        )


async def _refresh_force_update_target(
    entry: ConfigEntry, subentry_id: str, coordinator: Any
) -> None:
    """Refresh one force_update target and log local failures."""
    try:
        await coordinator.async_request_refresh()
    except asyncio.CancelledError:
        _LOGGER.debug(
            "Manual refresh cancelled for entry %s subentry %s",
            entry.entry_id,
            subentry_id,
        )
        raise
    except Exception as result:  # noqa: BLE001
        _log_force_update_failure(entry, subentry_id, coordinator, result)
        return

    if getattr(coordinator, "last_update_success", True) is not False:
        return
    last_exception = getattr(coordinator, "last_exception", None)
    if not isinstance(last_exception, BaseException):
        last_exception = None
    _log_force_update_failure(entry, subentry_id, coordinator, last_exception)


async def _refresh_force_update_targets(
    targets: list[tuple[ConfigEntry, str, Any]],
) -> None:
    """Refresh force_update targets with an explicit concurrency limit."""
    semaphore = asyncio.Semaphore(_FORCE_UPDATE_CONCURRENCY_LIMIT)

    async def _refresh(target: tuple[ConfigEntry, str, Any]) -> None:
        async with semaphore:
            await _refresh_force_update_target(*target)

    await asyncio.gather(*(_refresh(target) for target in targets))


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy entries to the v3 parent/subentry storage model."""
    return await async_handle_entry_migration(hass, entry, TARGET_ENTRY_VERSION)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register force_update service."""
    _LOGGER.debug("PollenLevels async_setup called")

    async def handle_force_update_service(call: ServiceCall) -> None:
        """Refresh pollen data for all entries."""
        _LOGGER.debug("Executing force_update service for all Pollen Levels entries")
        entries = list(hass.config_entries.async_entries(DOMAIN))
        targets: list[tuple[ConfigEntry, str, Any]] = []
        for entry in entries:
            runtime = getattr(entry, "runtime_data", None)
            locations = getattr(runtime, "locations", None) or {}
            if not locations:
                coordinator = getattr(runtime, "coordinator", None)
                if coordinator:
                    targets.append((entry, entry.entry_id, coordinator))
                    continue
                _LOGGER.debug(
                    "Skipping force_update for entry %s (no location coordinators)",
                    entry.entry_id,
                )
                continue

            active_subentry_ids, filter_stale_locations = stale_runtime_location_filter(
                entry
            )
            for location in locations.values():
                subentry_id = location.subentry_id
                if filter_stale_locations and subentry_id not in active_subentry_ids:
                    _LOGGER.debug(
                        "Skipping stale Pollen Levels runtime location %s for entry %s",
                        subentry_id,
                        entry.entry_id,
                    )
                    continue
                coordinator = getattr(location, "coordinator", None)
                if not coordinator:
                    continue
                targets.append((entry, subentry_id, coordinator))

        if not targets:
            _LOGGER.debug("No coordinators available for force_update")
            return

        await _refresh_force_update_targets(targets)

    # Enforce empty payload for the service; reject unknown fields for clearer errors.
    hass.services.async_register(
        DOMAIN, "force_update", handle_force_update_service, schema=vol.Schema({})
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: PollenLevelsConfigEntry
) -> bool:
    """Forward config entry to sensor platform."""
    _LOGGER.debug(
        "PollenLevels async_setup_entry for entry_id=%s",
        entry.entry_id,
    )
    if is_entry_merged(entry):
        _LOGGER.debug(
            "Skipping setup for merged entry %s (merged into %s)",
            entry.entry_id,
            entry.data.get(CONF_MERGED_INTO_ENTRY_ID),
        )
        return True

    legacy_per_day_option_detected = _drop_legacy_parent_options(hass, entry)
    if legacy_per_day_option_detected:
        create_per_day_forecast_sensors_removed_issue(hass)

    options = entry.options or {}

    parsed_hours = safe_parse_int(
        options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
    )
    hours = parsed_hours if parsed_hours is not None else DEFAULT_UPDATE_INTERVAL
    hours = max(MIN_UPDATE_INTERVAL_HOURS, min(MAX_UPDATE_INTERVAL_HOURS, hours))
    language = options.get(CONF_LANGUAGE_CODE, entry.data.get(CONF_LANGUAGE_CODE))

    api_key = entry.data.get(CONF_API_KEY)
    if not isinstance(api_key, str) or not api_key.strip():
        raise ConfigEntryAuthFailed("Invalid API key")
    api_key = api_key.strip()

    session = async_get_clientsession(hass)
    client = GooglePollenApiClient(session, api_key)

    location_configs = _iter_location_subentries(entry)
    active_subentry_ids = active_location_subentry_ids(entry)
    delete_stale_location_subentry_issues(
        hass,
        entry_id=entry.entry_id,
        active_subentry_ids=active_subentry_ids,
    )
    _prune_setup_retry_failures(hass, entry.entry_id, active_subentry_ids)

    locations: dict[str, PollenLocationRuntime] = {}
    failed_locations: dict[str, PollenLocationSetupFailure] = {}
    has_legacy_invalid_location_issue = False
    for subentry_id, title, data, legacy_entry_id in location_configs:
        raw_lat = data.get(CONF_LATITUDE)
        raw_lon = data.get(CONF_LONGITUDE)
        latlon = validate_location_pair(raw_lat, raw_lon)
        issue_subentry_id = _location_issue_subentry_id(entry, subentry_id)
        if latlon is None:
            create_invalid_stored_location_issue(
                hass,
                entry_id=entry.entry_id,
                entry_title=entry.title,
                location_title=title,
                subentry_id=issue_subentry_id,
            )
            if issue_subentry_id is None:
                has_legacy_invalid_location_issue = True
            delete_location_setup_failed_issue(
                hass,
                entry_id=entry.entry_id,
                subentry_id=subentry_id,
            )
            _clear_setup_retry_failure(hass, entry.entry_id, subentry_id)
            failed_locations[subentry_id] = _location_setup_failure(
                subentry_id=subentry_id,
                title=title,
                error_type="InvalidStoredLocation",
                reason="Pollen Levels location has invalid stored coordinates",
                api_key=api_key,
                latitude=raw_lat,
                longitude=raw_lon,
            )
            _LOGGER.warning(
                "Invalid coordinates for Pollen Levels entry %s subentry %s; "
                "skipping this location until the stored location is fixed",
                entry.entry_id,
                subentry_id,
            )
            continue

        delete_invalid_stored_location_issue(
            hass,
            entry_id=entry.entry_id,
            subentry_id=issue_subentry_id,
        )
        lat, lon = latlon
        coordinator = PollenDataUpdateCoordinator(
            hass=hass,
            api_key=api_key,
            lat=lat,
            lon=lon,
            hours=hours,
            language=language,
            entry_id=entry.entry_id,
            subentry_id=subentry_id,
            entry_title=title,
            legacy_entry_id=legacy_entry_id,
            config_entry=entry,
            client=client,
        )

        try:
            await coordinator.async_config_entry_first_refresh()
        except ConfigEntryAuthFailed:
            raise
        except ConfigEntryNotReady as err:
            safe_message = redact_sensitive_values(
                err, api_key=api_key, latitude=lat, longitude=lon
            )
            _LOGGER.warning(
                "Initial data refresh failed for entry %s subentry %s (%s): %s",
                entry.entry_id,
                subentry_id,
                type(err).__name__,
                safe_message or "no error details",
            )
            failed_locations[subentry_id] = _location_setup_failure(
                subentry_id=subentry_id,
                title=title,
                error_type=type(err).__name__,
                reason=safe_message or "Pollen Levels location is not ready",
                api_key=api_key,
                latitude=lat,
                longitude=lon,
            )
            continue
        except Exception as err:
            safe_message = redact_sensitive_values(
                err, api_key=api_key, latitude=lat, longitude=lon
            )
            _LOGGER.warning(
                "Initial data refresh failed for entry %s subentry %s (%s): %s",
                entry.entry_id,
                subentry_id,
                type(err).__name__,
                safe_message or "no error details",
            )
            failed_locations[subentry_id] = _location_setup_failure(
                subentry_id=subentry_id,
                title=title,
                error_type=type(err).__name__,
                reason=safe_message or "Pollen Levels location setup failed",
                api_key=api_key,
                latitude=lat,
                longitude=lon,
            )
            continue

        if not _coordinator_has_usable_initial_data(coordinator):
            reason = "API response missing usable pollen data"
            _LOGGER.warning(
                "Initial data refresh for entry %s subentry %s produced no usable "
                "pollen data; skipping this location",
                entry.entry_id,
                subentry_id,
            )
            failed_locations[subentry_id] = _location_setup_failure(
                subentry_id=subentry_id,
                title=title,
                error_type="UpdateFailed",
                reason=reason,
                api_key=api_key,
                latitude=lat,
                longitude=lon,
            )
            continue

        locations[subentry_id] = PollenLocationRuntime(
            subentry_id=subentry_id,
            coordinator=coordinator,
            legacy_entry_id=legacy_entry_id,
        )
        delete_location_setup_failed_issue(
            hass,
            entry_id=entry.entry_id,
            subentry_id=subentry_id,
        )
        _clear_setup_retry_failure(hass, entry.entry_id, subentry_id)

    if not has_legacy_invalid_location_issue:
        delete_entry_invalid_stored_location_issue(hass, entry)

    if location_configs and not locations:
        raise ConfigEntryNotReady(
            "No Pollen Levels locations could be loaded"
        ) from None

    entry.runtime_data = PollenLevelsRuntimeData(
        client=client,
        locations=locations,
        failed_locations=failed_locations,
    )

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except ConfigEntryAuthFailed, ConfigEntryNotReady:
        entry.runtime_data = None
        raise
    except Exception as err:
        entry.runtime_data = None
        _LOGGER.exception("Error forwarding entry setups: %s", err)
        raise ConfigEntryNotReady from err

    retry_reload_needed = False
    first_retry_failures: list[PollenLocationSetupFailure] = []
    for failure in failed_locations.values():
        if not _setup_failure_is_retryable(failure):
            continue
        if not _setup_retry_failure_seen(hass, entry.entry_id, failure.subentry_id):
            _mark_setup_retry_failure(hass, entry.entry_id, failure.subentry_id)
            first_retry_failures.append(failure)
            retry_reload_needed = True
            continue
        create_location_setup_failed_issue(
            hass,
            entry_id=entry.entry_id,
            entry_title=entry.title,
            location_title=failure.title,
            subentry_id=failure.subentry_id,
            error_type=failure.error_type,
            reason=failure.reason,
        )

    if retry_reload_needed and not _schedule_parent_reload(hass, entry):
        for failure in first_retry_failures:
            create_location_setup_failed_issue(
                hass,
                entry_id=entry.entry_id,
                entry_title=entry.title,
                location_title=failure.title,
                subentry_id=failure.subentry_id,
                error_type=failure.error_type,
                reason=failure.reason,
            )

    _LOGGER.info("PollenLevels integration loaded successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry and remove coordinator reference."""
    _LOGGER.debug(
        "PollenLevels async_unload_entry called for entry_id=%s", entry.entry_id
    )
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data = None
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete entry-owned location Repairs and retry bookkeeping."""
    delete_entry_location_issues(hass, entry_id=entry.entry_id)
    _prune_setup_retry_failures(hass, entry.entry_id, set())
