"""Tests for shared utilities."""

import pytest

from custom_components.pollenlevels.util import redact_api_key, safe_parse_int


def test_redact_api_key_handles_non_utf8_bytes():
    """Bytes payloads with invalid UTF-8 are decoded with replacement and redacted."""

    api_key = "SECRET"
    payload = b"\xff" + api_key.encode() + b"\xfe"

    redacted = redact_api_key(payload, api_key)

    assert "SECRET" not in redacted
    assert "***" in redacted
    # Replacement characters should be preserved for undecodable bytes
    assert "\ufffd" in redacted


def test_redact_api_key_returns_empty_string_for_none():
    """None inputs should yield an empty string."""

    assert redact_api_key(None, "anything") == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (3, 3),
        (3.0, 3),
        ("3", 3),
        ("3.0", 3),
        (True, None),
        (False, None),
        (None, None),
        ("3.5", None),
        (3.5, None),
        ("nan", None),
        ("inf", None),
    ],
)
def test_safe_parse_int(value, expected):
    """safe_parse_int accepts integer-like values and rejects invalid input."""

    assert safe_parse_int(value) == expected
