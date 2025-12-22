"""Shared helpers for the Pollen Levels integration."""

from __future__ import annotations

import logging
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


def redact_api_key(text: object, api_key: str | None) -> str:
    """Return a string representation of *text* with the API key redacted."""

    if text is None:
        return ""

    if isinstance(text, (bytes, bytearray)):
        try:
            s = text.decode()
        except UnicodeDecodeError:
            s = text.decode(errors="replace")
    else:
        s = str(text)

    if api_key:
        s = s.replace(api_key, "***")
    return s


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


# Backwards-compatible alias for modules that still import the private helper name.
_redact_api_key = redact_api_key

__all__ = [
    "extract_error_message",
    "normalize_sensor_mode",
    "redact_api_key",
    "_redact_api_key",
]
