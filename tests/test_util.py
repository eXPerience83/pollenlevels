"""Tests for shared utilities."""

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
custom_components_pkg = sys.modules.setdefault(
    "custom_components", types.ModuleType("custom_components")
)
custom_components_pkg.__path__ = [str(ROOT / "custom_components")]
pollenlevels_pkg = sys.modules.setdefault(
    "custom_components.pollenlevels", types.ModuleType("custom_components.pollenlevels")
)
pollenlevels_pkg.__path__ = [str(ROOT / "custom_components" / "pollenlevels")]

from custom_components.pollenlevels.util import (  # noqa: E402
    redact_api_key,
    redact_sensitive_values,
    safe_parse_int,
)


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


def test_redact_sensitive_values_returns_empty_string_for_none():
    """None inputs should yield an empty string."""

    assert redact_sensitive_values(None, api_key="SECRET") == ""


def test_redact_sensitive_values_redacts_exact_api_key():
    """Exact API key values should be redacted."""

    redacted = redact_sensitive_values("API key SECRET failed", api_key="SECRET")

    assert "SECRET" not in redacted
    assert "***" in redacted


def test_redact_sensitive_values_redacts_key_query_parameter():
    """Key query parameters should have their values redacted."""

    redacted = redact_sensitive_values("https://example.test/?key=bad-key&days=5")

    assert "bad-key" not in redacted
    assert "key=***" in redacted
    assert "days=5" in redacted


def test_redact_sensitive_values_redacts_coordinate_query_parameters():
    """Coordinate query parameters should have their values redacted."""

    redacted = redact_sensitive_values(
        "location.latitude=40.4168&location.longitude=-3.7038&days=5"
    )

    assert "40.4168" not in redacted
    assert "-3.7038" not in redacted
    assert "location.latitude=***" in redacted
    assert "location.longitude=***" in redacted
    assert "days=5" in redacted


def test_redact_sensitive_values_redacts_url_encoded_coordinate_parameters():
    """URL-encoded coordinate parameters should have their values redacted."""

    redacted = redact_sensitive_values(
        "location.latitude%3D40.4168&location.longitude%3D-3.7038"
    )

    assert "40.4168" not in redacted
    assert "-3.7038" not in redacted
    assert "location.latitude%3D***" in redacted
    assert "location.longitude%3D***" in redacted


def test_redact_sensitive_values_redacts_explicit_coordinates():
    """Explicit coordinate values should be redacted when they appear in text."""

    redacted = redact_sensitive_values(
        "Coordinates 40.416800 and -3.703800 failed",
        latitude=40.4168,
        longitude=-3.7038,
    )

    assert "40.416800" not in redacted
    assert "-3.703800" not in redacted
    assert redacted.count("***") == 2


def test_redact_sensitive_values_preserves_unrelated_numbers():
    """Unrelated numbers should not be redacted."""

    redacted = redact_sensitive_values("HTTP 400 days=5 Retry-After: 30")

    assert redacted == "HTTP 400 days=5 Retry-After: 30"


@pytest.mark.parametrize(
    ("message", "latitude"),
    [
        ("HTTP 404", "40"),
        ("value 140", "40"),
        ("value -40", "40"),
    ],
)
def test_redact_sensitive_values_does_not_redact_partial_integer_coordinates(
    message, latitude
):
    """Explicit integer coordinates should not redact partial numeric matches."""

    assert redact_sensitive_values(message, latitude=latitude) == message


@pytest.mark.parametrize("message", ["value 140.0", "value 40.01"])
def test_redact_sensitive_values_does_not_redact_partial_decimal_coordinates(message):
    """Explicit decimal coordinates should not redact partial decimal matches."""

    assert redact_sensitive_values(message, latitude=40.0) == message


@pytest.mark.parametrize("coordinate", ["40.0", "40.000000"])
def test_redact_sensitive_values_still_redacts_exact_coordinate_values(coordinate):
    """Exact explicit coordinate values should still be redacted."""

    redacted = redact_sensitive_values(
        f"Coordinates {coordinate} failed", latitude=40.0
    )

    assert coordinate not in redacted
    assert "***" in redacted


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
