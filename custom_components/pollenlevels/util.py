"""Shared helpers for the Pollen Levels integration."""

from __future__ import annotations


async def extract_error_message(resp: object, default: str = "") -> str:
    """Extract and normalize an HTTP error message without secrets."""

    message: str | None = None
    try:
        json_obj = await resp.json()
        if isinstance(json_obj, dict):
            error = json_obj.get("error")
            if isinstance(error, dict):
                raw_msg = error.get("message")
                if isinstance(raw_msg, str):
                    message = raw_msg.strip()
    except Exception:  # noqa: BLE001
        message = None

    if not message:
        try:
            text = await resp.text()
            if isinstance(text, str):
                message = text.strip()
        except Exception:  # noqa: BLE001
            message = None

    message = (message or "").strip() or default
    if len(message) > 300:
        message = message[:300]
    return message


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


# Backwards-compatible alias for modules that still import the private helper name.
_redact_api_key = redact_api_key

__all__ = ["extract_error_message", "redact_api_key", "_redact_api_key"]
