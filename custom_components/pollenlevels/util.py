"""Shared helpers for the Pollen Levels integration."""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING, Any

from .const import FORECAST_SENSORS_CHOICES

if TYPE_CHECKING:  # pragma: no cover - typing-only import
    from aiohttp import ClientResponse
else:  # pragma: no cover - runtime fallback for test environments without aiohttp
    ClientResponse = Any


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
_KEY_PARAM_RE = re.compile(r"(?i)(^|[?&\s])(key(?:=|%3d))([^&\s\"']+)")
_LOCATION_PARAM_RE = re.compile(
    r"(?i)(location\.(?:latitude|longitude)(?:=|%3d))(-?\d+(?:\.\d+)?)"
)
_URL_ASSIGN_RE = re.compile(r"(?i)(url\s*=\s*)([\"']?)https?://[^\s\"']+([\"']?)")
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
        lambda match: (f"{match.group(1)}{match.group(2)}{_REDACTION_PLACEHOLDER}"),
        s,
    )
    s = _LOCATION_PARAM_RE.sub(
        lambda match: f"{match.group(1)}{_REDACTION_PLACEHOLDER}",
        s,
    )

    s = _URL_ASSIGN_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}***{match.group(3)}", s
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


def parse_finite_float(value: Any) -> float | None:
    """Parse a finite float value, rejecting bools and invalid input."""
    if value is None or isinstance(value, bool):
        return None

    try:
        parsed = float(value)
    except TypeError, ValueError, OverflowError:
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


def normalize_sensor_mode(mode: Any, logger: logging.Logger) -> str:
    """Normalize sensor mode, defaulting and logging a warning if invalid."""
    raw_mode = getattr(mode, "value", mode)
    mode_str = None if raw_mode is None else str(raw_mode).strip()
    if not mode_str:
        mode_str = None
    if mode_str in FORECAST_SENSORS_CHOICES:
        return mode_str

    if "none" in FORECAST_SENSORS_CHOICES:
        default_mode = "none"
    else:
        default_mode = (
            FORECAST_SENSORS_CHOICES[0] if FORECAST_SENSORS_CHOICES else "none"
        )
    if mode_str is not None:
        logger.warning(
            "Invalid stored per-day sensor mode '%s'; defaulting to '%s'",
            mode_str,
            default_mode,
        )
    return default_mode


def safe_parse_int(value: Any) -> int | None:
    """Parse an integer-like value, rejecting non-finite and decimal numbers."""
    if value is None or isinstance(value, bool):
        return None

    try:
        parsed_float = float(value)
    except TypeError, ValueError, OverflowError:
        return None

    if not math.isfinite(parsed_float) or not parsed_float.is_integer():
        return None

    return int(parsed_float)


# Backwards-compatible alias for modules that still import the private helper name.
_redact_api_key = redact_api_key

__all__ = [
    "extract_error_message",
    "normalize_sensor_mode",
    "parse_finite_float",
    "redact_api_key",
    "redact_sensitive_values",
    "safe_parse_int",
    "validate_latitude",
    "validate_location_pair",
    "validate_longitude",
    "_redact_api_key",
]
