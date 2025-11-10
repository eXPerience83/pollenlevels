"""Shared helpers for the Pollen Levels integration."""

from __future__ import annotations


def redact_api_key(text: object, api_key: str | None) -> str:
    """Return a string representation of *text* with the API key redacted."""

    if text is None:
        return ""

    if isinstance(text, bytes | bytearray):
        s = text.decode()
    else:
        s = str(text)

    if api_key:
        return s.replace(api_key, "***")
    return s


# Backwards-compatible alias for modules that still import the private helper name.
_redact_api_key = redact_api_key

__all__ = ["redact_api_key", "_redact_api_key"]
