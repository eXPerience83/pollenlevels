"""Regression tests for generic Google Pollen API client failures."""

from __future__ import annotations

import logging
from types import ModuleType

import pytest

from tests import test_client as client_tests

client_module = client_tests.client_module


async def _fetch(
    module: ModuleType,
    session: object,
    *,
    api_key: str,
    latitude: float,
    longitude: float,
) -> None:
    """Execute a representative client fetch with explicit sensitive values."""

    client = module.GooglePollenApiClient(session, api_key)
    await client.async_fetch_pollen_data(
        latitude=latitude,
        longitude=longitude,
        days=5,
        language_code=None,
    )


@pytest.mark.asyncio
async def test_client_generic_non_200_redacts_sensitive_message(
    client_module: ModuleType,
) -> None:
    """Generic non-200 responses should fail without exposing request secrets."""

    api_key = "synthetic-api-key"
    latitude = 12.3456
    longitude = -65.4321
    response = client_tests.FakeResponse(
        status=302,
        json_results=[ValueError("invalid JSON")],
        text_body=(
            "Redirected request: "
            "https://pollen.googleapis.com/v1/forecast:lookup?"
            f"key={api_key}&location.latitude={latitude}&"
            f"location.longitude={longitude}&days=5"
        ),
    )

    with pytest.raises(client_module.UpdateFailed) as exc_info:
        await _fetch(
            client_module,
            client_tests.FakeSession(response),
            api_key=api_key,
            latitude=latitude,
            longitude=longitude,
        )

    message = str(exc_info.value)
    assert message.startswith("HTTP 302")
    assert api_key not in message
    assert str(latitude) not in message
    assert str(longitude) not in message
    assert "***" in message


@pytest.mark.asyncio
async def test_client_unexpected_error_is_redacted_and_logged(
    client_module: ModuleType,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unexpected exceptions should become redacted UpdateFailed errors."""

    api_key = "synthetic-api-key"
    latitude = 12.3456
    longitude = -65.4321
    error_message = (
        "unexpected request failure: "
        "https://pollen.googleapis.com/v1/forecast:lookup?"
        f"key={api_key}&location.latitude={latitude}&"
        f"location.longitude={longitude}&days=5"
    )

    with caplog.at_level(logging.ERROR, logger=client_module.__name__):
        with pytest.raises(client_module.UpdateFailed) as exc_info:
            await _fetch(
                client_module,
                client_tests.RaisingSession(RuntimeError(error_message)),
                api_key=api_key,
                latitude=latitude,
                longitude=longitude,
            )

    raised_message = str(exc_info.value)
    logged_message = caplog.text
    for sensitive_value in (api_key, str(latitude), str(longitude)):
        assert sensitive_value not in raised_message
        assert sensitive_value not in logged_message
    assert "***" in raised_message
    assert "Pollen API error:" in logged_message
    assert "***" in logged_message


@pytest.mark.asyncio
async def test_client_unexpected_empty_error_uses_safe_fallback(
    client_module: ModuleType,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An empty unexpected exception should use the bounded safe fallback."""

    with caplog.at_level(logging.ERROR, logger=client_module.__name__):
        with pytest.raises(
            client_module.UpdateFailed,
            match="Unexpected error while calling the Google Pollen API",
        ):
            await _fetch(
                client_module,
                client_tests.RaisingSession(RuntimeError()),
                api_key="synthetic-api-key",
                latitude=12.3456,
                longitude=-65.4321,
            )

    assert (
        "Pollen API error: Unexpected error while calling the Google Pollen API"
        in caplog.text
    )
