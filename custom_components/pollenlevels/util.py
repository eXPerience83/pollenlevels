"""Shared helpers for the Pollen Levels integration."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from .const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    SUBENTRY_TYPE_LOCATION,
)

if TYPE_CHECKING:  # pragma: no cover - typing-only import
    from aiohttp import ClientResponse

    from .coordinator import PollenDataUpdateCoordinator
else:  # pragma: no cover - runtime fallback for test environments without aiohttp
    ClientResponse = Any


LEGACY_FORECAST_OPTION_KEYS = frozenset(
    {
        CONF_FORECAST_DAYS,
        CONF_CREATE_FORECAST_SENSORS,
    }
)
LEGACY_ACTIVE_PER_DAY_SENSOR_MODES = frozenset({"D+1", "D+1+2"})


def strip_legacy_forecast_options(
    mapping: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return *mapping* without obsolete forecast configuration keys."""
    return {
        key: value
        for key, value in dict(mapping or {}).items()
        if key not in LEGACY_FORECAST_OPTION_KEYS
    }


def has_legacy_per_day_option(*mappings: Mapping[str, Any] | None) -> bool:
    """Return whether any mapping stores an active removed per-day sensor mode."""
    return any(
        (mapping or {}).get(CONF_CREATE_FORECAST_SENSORS)
        in LEGACY_ACTIVE_PER_DAY_SENSOR_MODES
        for mapping in mappings
    )


def coordinator_identity_id(coordinator: PollenDataUpdateCoordinator) -> str:
    """Return the stable identity used for entity unique IDs."""
    return getattr(coordinator, "entity_identity_id", None) or coordinator.entry_id


def coordinator_device_id(coordinator: PollenDataUpdateCoordinator, group: str) -> str:
    """Return the stable device identifier for a location/group pair."""
    identity_id = getattr(coordinator, "device_identity_id", None) or (
        getattr(coordinator, "entity_identity_id", None) or coordinator.entry_id
    )
    return f"{identity_id}_{group}"


def entry_api_key(entry: Any) -> str | None:
    """Return a stripped parent API key or None when unavailable."""
    data = getattr(entry, "data", {}) or {}
    raw_api_key = data.get(CONF_API_KEY)
    if not isinstance(raw_api_key, str):
        return None
    api_key = raw_api_key.strip()
    return api_key or None


def format_location_unique_id(lat: float, lon: float) -> str:
    """Format a coordinate pair as a location unique ID."""
    return f"{lat:.4f}_{lon:.4f}"


def active_location_subentry_ids(entry: Any) -> set[str]:
    """Return active location subentry ids for a config entry."""
    subentries = getattr(entry, "subentries", {}) or {}
    active_ids: set[str] = set()
    for subentry in subentries.values():
        if getattr(subentry, "subentry_type", None) != SUBENTRY_TYPE_LOCATION:
            continue
        subentry_id = getattr(subentry, "subentry_id", None)
        if isinstance(subentry_id, str) and subentry_id:
            active_ids.add(subentry_id)
    return active_ids


def has_legacy_location_data(entry: Any) -> bool:
    """Return True when entry data contains a valid legacy fallback location."""
    data = getattr(entry, "data", {}) or {}
    if CONF_LATITUDE not in data or CONF_LONGITUDE not in data:
        return False
    return (
        validate_location_pair(data.get(CONF_LATITUDE), data.get(CONF_LONGITUDE))
        is not None
    )


def stale_runtime_location_filter(entry: Any) -> tuple[set[str], bool]:
    """Return active location ids and whether stale runtime locations should skip."""
    active_subentry_ids = active_location_subentry_ids(entry)
    filter_stale_locations = bool(active_subentry_ids) or not has_legacy_location_data(
        entry
    )
    return active_subentry_ids, filter_stale_locations


async def extract_error_message(resp: ClientResponse, default: str = "") -> str:
    """Extract and normalize an HTTP error message without secrets."""

    message: str | None = None
    try:
        try:
            json_obj = await resp.json(content_type=None)
        except TypeError:
            json_obj = await resp.json()
        if isinstance(json_obj, dict):
            error = json_obj.get("error")
            if isinstance(error, dict):
                raw_msg = error.get("message")
                if isinstance(raw_msg, str):
                    message = raw_msg
    except Exception:  # noqa: BLE001
        message = None

    if not message:
        try:
            text = await resp.text()
            if isinstance(text, str):
                message = text
        except Exception:  # noqa: BLE001
            message = None

    normalized = " ".join(
        (message or "").replace("\r", " ").replace("\n", " ").split()
    ).strip()

    if len(normalized) > 300:
        normalized = normalized[:300]

    return normalized or default


_REDACTION_PLACEHOLDER = "***"
_KEY_PARAM_RE = re.compile(
    r"(?i)(^|[?&\s])(key(?:=|%3d))(?:\"([^\"]*)\"|'([^']*)'|([^&\s\"']+))"
)
_LOCATION_PARAM_RE = re.compile(
    r"(?i)(location\.(?:latitude|longitude)(?:=|%3d))(-?\d+(?:\.\d+)?)"
)
_URL_ASSIGN_RE = re.compile(
    r"(?i)(url\s*=\s*)(?:\"https?://([^\"]*)\"|'https?://([^']*)'|(https?://[^\s\"']+))"
)
_PAYLOAD_RE = re.compile(r"(?i)(payload\s*=\s*)([^\r\n]*)")


def _stringify_for_redaction(value: object) -> str:
    """Return a string representation of *value* for safe redaction."""

    if value is None:
        return ""

    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode()
        except UnicodeDecodeError:
            return value.decode(errors="replace")

    return str(value)


def _coordinate_values(value: float | str | None) -> set[str]:
    """Return stable coordinate string forms that may appear in URLs/errors."""

    if value is None:
        return set()

    value_str = str(value)
    values = {value_str}
    try:
        parsed = float(value_str)
    except ValueError:
        return {item for item in values if item}

    if math.isfinite(parsed):
        values.add(f"{parsed:.6f}")

    return {item for item in values if item}


def redact_sensitive_values(
    value: object,
    api_key: str | None = None,
    latitude: float | str | None = None,
    longitude: float | str | None = None,
) -> str:
    """Return *value* as text with API keys and precise coordinates redacted."""

    s = _stringify_for_redaction(value)
    if not s:
        return ""

    if api_key:
        s = s.replace(api_key, _REDACTION_PLACEHOLDER)

    s = _KEY_PARAM_RE.sub(
        lambda match: (
            f'{match.group(1)}{match.group(2)}"{_REDACTION_PLACEHOLDER}"'
            if match.group(3) is not None
            else (
                f"{match.group(1)}{match.group(2)}'{_REDACTION_PLACEHOLDER}'"
                if match.group(4) is not None
                else f"{match.group(1)}{match.group(2)}{_REDACTION_PLACEHOLDER}"
            )
        ),
        s,
    )
    s = _LOCATION_PARAM_RE.sub(
        lambda match: f"{match.group(1)}{_REDACTION_PLACEHOLDER}",
        s,
    )

    s = _URL_ASSIGN_RE.sub(
        lambda match: (
            f'{match.group(1)}"{_REDACTION_PLACEHOLDER}"'
            if match.group(2) is not None
            else (
                f"{match.group(1)}'{_REDACTION_PLACEHOLDER}'"
                if match.group(3) is not None
                else f"{match.group(1)}{_REDACTION_PLACEHOLDER}"
            )
        ),
        s,
    )
    s = _PAYLOAD_RE.sub(r"\1***", s)

    coordinates = sorted(
        _coordinate_values(latitude) | _coordinate_values(longitude),
        key=len,
        reverse=True,
    )
    if coordinates:
        pattern = "|".join(re.escape(coordinate) for coordinate in coordinates)
        s = re.sub(
            rf"(?<![\d.+-])({pattern})(?![\d.])",
            _REDACTION_PLACEHOLDER,
            s,
        )

    return s


def redact_api_key(text: object, api_key: str | None) -> str:
    """Return a string representation of *text* with the API key redacted."""

    return redact_sensitive_values(text, api_key=api_key)


def api_key_unique_id(api_key: str) -> str:
    """Return a stable, non-secret unique ID for one shared API key."""
    return f"api_key_{sha256(api_key.encode()).hexdigest()[:16]}"


def parse_finite_float(value: Any) -> float | None:
    """Parse a finite float value, rejecting bools and invalid input."""
    if value is None or isinstance(value, bool):
        return None

    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(parsed):
        return None

    return parsed


def validate_latitude(value: Any) -> float | None:
    """Return a normalized latitude float or None when invalid."""
    parsed = parse_finite_float(value)
    if parsed is None or not -90.0 <= parsed <= 90.0:
        return None

    return parsed


def validate_longitude(value: Any) -> float | None:
    """Return a normalized longitude float or None when invalid."""
    parsed = parse_finite_float(value)
    if parsed is None or not -180.0 <= parsed <= 180.0:
        return None

    return parsed


def validate_location_pair(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    """Return a normalized coordinate pair or None when either value is invalid."""
    parsed_latitude = validate_latitude(latitude)
    parsed_longitude = validate_longitude(longitude)
    if parsed_latitude is None or parsed_longitude is None:
        return None

    return parsed_latitude, parsed_longitude


def safe_parse_int(value: Any) -> int | None:
    """Parse an integer-like value, rejecting non-finite and decimal numbers."""
    if value is None or isinstance(value, bool):
        return None

    try:
        parsed_float = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(parsed_float) or not parsed_float.is_integer():
        return None

    return int(parsed_float)


# Backwards-compatible alias for modules that still import the private helper name.
_redact_api_key = redact_api_key

__all__ = [
    "api_key_unique_id",
    "coordinator_device_id",
    "coordinator_identity_id",
    "entry_api_key",
    "extract_error_message",
    "format_location_unique_id",
    "has_legacy_per_day_option",
    "LEGACY_FORECAST_OPTION_KEYS",
    "parse_finite_float",
    "redact_api_key",
    "redact_sensitive_values",
    "safe_parse_int",
    "stale_runtime_location_filter",
    "strip_legacy_forecast_options",
    "validate_latitude",
    "validate_location_pair",
    "validate_longitude",
    "_redact_api_key",
]
