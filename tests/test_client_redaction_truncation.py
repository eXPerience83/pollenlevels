"""Regression tests for HTTP error redaction before truncation."""

from __future__ import annotations

from types import ModuleType

import pytest

from tests import test_client as client_tests

client_module = client_tests.client_module


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["json", "text"])
async def test_http_error_redacts_key_before_truncation(
    client_module: ModuleType,
    source: str,
) -> None:
    """A key crossing the legacy boundary must be removed before truncation."""

    api_key = "synthetic-secret-key-0123456789"
    prefix = "x" * 290
    raw_message = f"{prefix}{api_key} trailing context"
    response = client_tests.FakeResponse(
        status=400,
        json_results=(
            [{"error": {"message": raw_message}}]
            if source == "json"
            else [ValueError("invalid JSON")]
        ),
        text_body=raw_message if source == "text" else "unused",
    )

    with pytest.raises(client_module.UpdateFailed) as exc_info:
        await client_tests._fetch_with_response(
            client_module,
            response,
            api_key=api_key,
        )

    surfaced = str(exc_info.value)
    detail = surfaced.removeprefix("HTTP 400: ")
    assert api_key not in surfaced
    assert api_key[:10] not in surfaced
    assert "***" in surfaced
    assert len(detail) <= client_module._MAX_HTTP_ERROR_MESSAGE_LENGTH


@pytest.mark.asyncio
async def test_http_error_redacts_coordinate_crossing_truncation_boundary(
    client_module: ModuleType,
) -> None:
    """A standalone coordinate crossing the boundary must not leak a fragment."""

    latitude = 12.3456
    raw_message = f"{'x' * 296}{latitude} trailing context"
    response = client_tests.FakeResponse(
        status=400,
        json_results=[{"error": {"message": raw_message}}],
    )

    with pytest.raises(client_module.UpdateFailed) as exc_info:
        await client_tests._fetch_with_response(
            client_module,
            response,
            latitude=latitude,
        )

    surfaced = str(exc_info.value)
    detail = surfaced.removeprefix("HTTP 400: ")
    coordinate_fragment = str(latitude)[:4]
    assert str(latitude) not in surfaced
    assert coordinate_fragment not in surfaced
    assert "***" in surfaced
    assert len(detail) <= client_module._MAX_HTTP_ERROR_MESSAGE_LENGTH


@pytest.mark.asyncio
async def test_http_error_redacts_url_and_coordinates_before_truncation(
    client_module: ModuleType,
) -> None:
    """Long credential-bearing URLs must remain safe at the message boundary."""

    api_key = "synthetic-url-secret-0123456789"
    latitude = 12.3456
    longitude = -65.4321
    url = (
        "https://pollen.googleapis.com/v1/forecast:lookup?"
        f"key={api_key}&location.latitude={latitude}&"
        f"location.longitude={longitude}&days=5"
    )
    raw_message = f"{'x' * 245} url={url} trailing context"
    response = client_tests.FakeResponse(
        status=400,
        json_results=[ValueError("invalid JSON")],
        text_body=raw_message,
    )

    with pytest.raises(client_module.UpdateFailed) as exc_info:
        await client_tests._fetch_with_response(
            client_module,
            response,
            api_key=api_key,
            latitude=latitude,
            longitude=longitude,
        )

    surfaced = str(exc_info.value)
    detail = surfaced.removeprefix("HTTP 400: ")
    assert api_key not in surfaced
    assert str(latitude) not in surfaced
    assert str(longitude) not in surfaced
    assert "url=***" in surfaced
    assert len(detail) <= client_module._MAX_HTTP_ERROR_MESSAGE_LENGTH
