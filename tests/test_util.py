"""Tests for shared utilities."""

import importlib
import sys
from collections.abc import Iterator
from types import ModuleType

import pytest

from tests._ha_stubs import clear_integration_modules, stub_custom_components_packages


@pytest.fixture
def util_module(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import util.py with local package stubs scoped to each test."""

    clear_integration_modules(monkeypatch=monkeypatch)
    stub_custom_components_packages(monkeypatch=monkeypatch)

    imported_util = importlib.import_module("custom_components.pollenlevels.util")
    try:
        yield imported_util
    finally:
        pollenlevels_pkg = sys.modules.get("custom_components.pollenlevels")
        if pollenlevels_pkg is not None and hasattr(pollenlevels_pkg, "util"):
            delattr(pollenlevels_pkg, "util")
        clear_integration_modules()


def test_redact_api_key_handles_non_utf8_bytes(util_module):
    """Bytes payloads with invalid UTF-8 are decoded with replacement and redacted."""

    api_key = "SECRET"
    payload = b"\xff" + api_key.encode() + b"\xfe"

    redacted = util_module.redact_api_key(payload, api_key)

    assert "SECRET" not in redacted
    assert "***" in redacted
    # Replacement characters should be preserved for undecodable bytes
    assert "\ufffd" in redacted


def test_redact_api_key_returns_empty_string_for_none(util_module):
    """None inputs should yield an empty string."""

    assert util_module.redact_api_key(None, "anything") == ""


def test_redact_sensitive_values_returns_empty_string_for_none(util_module):
    """None inputs should yield an empty string."""

    assert util_module.redact_sensitive_values(None, api_key="SECRET") == ""


def test_redact_sensitive_values_redacts_exact_api_key(util_module):
    """Exact API key values should be redacted."""

    redacted = util_module.redact_sensitive_values(
        "API key SECRET failed", api_key="SECRET"
    )

    assert "SECRET" not in redacted
    assert "***" in redacted


def test_redact_sensitive_values_redacts_unquoted_key_query_parameter(util_module):
    """Unquoted key query parameters should have their values redacted."""

    redacted = util_module.redact_sensitive_values(
        "https://example.test/?key=bad-key&days=5"
    )

    assert "bad-key" not in redacted
    assert "key=***" in redacted
    assert "days=5" in redacted


def test_redact_sensitive_values_redacts_quoted_key_query_parameters(util_module):
    """Quoted key parameters should be redacted while preserving quotes."""

    redacted = util_module.redact_sensitive_values(
        "key=\"secret-one\" key='secret-two'"
    )

    assert 'key="***"' in redacted
    assert "key='***'" in redacted
    assert "secret-one" not in redacted
    assert "secret-two" not in redacted


def test_redact_sensitive_values_redacts_urlencoded_unquoted_key_parameter(util_module):
    """URL-encoded key parameters should have their values redacted."""

    redacted = util_module.redact_sensitive_values(
        "https://example.test/?key%3Dsecret-three"
    )

    assert "key%3D***" in redacted
    assert "secret-three" not in redacted


def test_redact_sensitive_values_redacts_coordinate_query_parameters(util_module):
    """Coordinate query parameters should have their values redacted."""

    redacted = util_module.redact_sensitive_values(
        "location.latitude=40.4168&location.longitude=-3.7038&days=5"
    )

    assert "40.4168" not in redacted
    assert "-3.7038" not in redacted
    assert "location.latitude=***" in redacted
    assert "location.longitude=***" in redacted
    assert "days=5" in redacted


def test_redact_sensitive_values_redacts_url_encoded_coordinate_parameters(util_module):
    """URL-encoded coordinate parameters should have their values redacted."""

    redacted = util_module.redact_sensitive_values(
        "location.latitude%3D40.4168&location.longitude%3D-3.7038"
    )

    assert "40.4168" not in redacted
    assert "-3.7038" not in redacted
    assert "location.latitude%3D***" in redacted
    assert "location.longitude%3D***" in redacted


def test_redact_sensitive_values_redacts_explicit_coordinates(util_module):
    """Explicit coordinate values should be redacted when they appear in text."""

    redacted = util_module.redact_sensitive_values(
        "Coordinates 40.416800 and -3.703800 failed",
        latitude=40.4168,
        longitude=-3.7038,
    )

    assert "40.416800" not in redacted
    assert "-3.703800" not in redacted
    assert redacted.count("***") == 2


def test_redact_sensitive_values_redacts_single_quoted_url_assignment(util_module):
    """Single-quoted URL assignment should keep quotes while redacting URL contents."""

    redacted = util_module.redact_sensitive_values(
        "url='https://example.test/pollen?token=secret-token&key=bad-key'"
    )

    assert "url='***'" in redacted
    assert "https://example.test" not in redacted
    assert "token=secret-token" not in redacted
    assert "key=bad-key" not in redacted


def test_redact_sensitive_values_redacts_double_quoted_url_assignment(util_module):
    """Double-quoted URL assignment should keep quotes while redacting URL contents."""

    redacted = util_module.redact_sensitive_values(
        'url="https://example.test/pollen?token=secret-token&api_key=secret-token"',
        api_key="secret-token",
    )

    assert 'url="***"' in redacted
    assert "https://example.test" not in redacted
    assert "token=secret-token" not in redacted
    assert "api_key=secret-token" not in redacted


def test_redact_sensitive_values_redacts_unquoted_url_assignment(util_module):
    """Unquoted URL assignment should be redacted without exposing query values."""

    redacted = util_module.redact_sensitive_values(
        "url=https://example.test/pollen?token=abc&key=bad-key&api_key=zzz&days=3"
    )

    assert "url=***" in redacted
    assert "https://example.test" not in redacted
    assert "token=abc" not in redacted
    assert "key=bad-key" not in redacted
    assert "api_key=zzz" not in redacted


def test_redact_sensitive_values_redacts_payload_line_without_swallowing_following_lines(
    util_module,
):
    """Payload line is redacted while later lines are still independently sanitized."""

    redacted = util_module.redact_sensitive_values(
        "payload=line1\nkey=abc123\nlocation.latitude=40.4168",
        latitude=40.4168,
    )

    assert "payload=line1" not in redacted
    assert "payload=***" in redacted
    assert "abc123" not in redacted
    assert "key=***" in redacted
    assert "40.4168" not in redacted
    assert "location.latitude=***" in redacted


def test_redact_sensitive_values_preserves_unrelated_numbers(util_module):
    """Unrelated numbers should not be redacted."""

    redacted = util_module.redact_sensitive_values("HTTP 400 days=5 Retry-After: 30")

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
    util_module, message, latitude
):
    """Explicit integer coordinates should not redact partial numeric matches."""

    assert util_module.redact_sensitive_values(message, latitude=latitude) == message


@pytest.mark.parametrize("message", ["value 140.0", "value 40.01"])
def test_redact_sensitive_values_does_not_redact_partial_decimal_coordinates(
    util_module, message
):
    """Explicit decimal coordinates should not redact partial decimal matches."""

    assert util_module.redact_sensitive_values(message, latitude=40.0) == message


@pytest.mark.parametrize("coordinate", ["40.0", "40.000000"])
def test_redact_sensitive_values_still_redacts_exact_coordinate_values(
    util_module, coordinate
):
    """Exact explicit coordinate values should still be redacted."""

    redacted = util_module.redact_sensitive_values(
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
def test_safe_parse_int(util_module, value, expected):
    """safe_parse_int accepts integer-like values and rejects invalid input."""

    assert util_module.safe_parse_int(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0.0),
        (12.5, 12.5),
        ("12.5", 12.5),
        (" -3 ", -3.0),
    ],
)
def test_parse_finite_float_accepts_numeric_values(util_module, value, expected):
    """parse_finite_float returns normalized floats for finite numeric input."""

    assert util_module.parse_finite_float(value) == expected


@pytest.mark.parametrize(
    "value",
    [None, True, False, "not-a-number", "nan", "inf", float("nan"), float("inf")],
)
def test_parse_finite_float_rejects_invalid_values(util_module, value):
    """parse_finite_float rejects bools, empty values, and non-finite numbers."""

    assert util_module.parse_finite_float(value) is None


@pytest.mark.parametrize("value", [-90, -90.0, "-90", 0, "12.5", 90, "90"])
def test_validate_latitude_accepts_valid_values(util_module, value):
    """validate_latitude accepts numeric and numeric-string values in range."""

    assert util_module.validate_latitude(value) == float(value)


@pytest.mark.parametrize("value", [-180, -180.0, "-180", 0, "12.5", 180, "180"])
def test_validate_longitude_accepts_valid_values(util_module, value):
    """validate_longitude accepts numeric and numeric-string values in range."""

    assert util_module.validate_longitude(value) == float(value)


@pytest.mark.parametrize(
    "value",
    [None, True, False, "not-a-number", "nan", "inf", -90.1, 90.1],
)
def test_validate_latitude_rejects_invalid_values(util_module, value):
    """validate_latitude rejects invalid, non-finite, and out-of-range values."""

    assert util_module.validate_latitude(value) is None


@pytest.mark.parametrize(
    "value",
    [None, True, False, "not-a-number", "nan", "inf", -180.1, 180.1],
)
def test_validate_longitude_rejects_invalid_values(util_module, value):
    """validate_longitude rejects invalid, non-finite, and out-of-range values."""

    assert util_module.validate_longitude(value) is None


def test_validate_location_pair_accepts_valid_pair(util_module):
    """validate_location_pair returns normalized floats for valid coordinates."""

    assert util_module.validate_location_pair("40.4168", "-3.7038") == (
        40.4168,
        -3.7038,
    )


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(None, 1), (1, None), (91, 1), (1, 181), (True, 1), (1, "bad")],
)
def test_validate_location_pair_rejects_invalid_pair(util_module, latitude, longitude):
    """validate_location_pair rejects pairs with any invalid coordinate."""

    assert util_module.validate_location_pair(latitude, longitude) is None
