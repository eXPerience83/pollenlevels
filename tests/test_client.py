"""Direct tests for the Google Pollen API client."""

from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests._ha_stubs import (
    clear_integration_modules,
    stub_aiohttp_module,
    stub_custom_components_packages,
    stub_exceptions,
    stub_homeassistant_package,
    stub_update_coordinator_module,
    stub_util_dt_module,
)

ROOT = Path(__file__).resolve().parents[1]


class _StubConfigEntryAuthFailed(Exception):
    """Minimal Home Assistant auth failure stub."""


class _StubUpdateFailed(Exception):
    """Minimal Home Assistant update failure stub."""

    def __init__(
        self,
        *args: object,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(*args)
        self.retry_after = retry_after


@pytest.fixture
def client_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import the client under test with fixture-scoped Home Assistant stubs."""

    clear_integration_modules(monkeypatch=monkeypatch)
    stub_custom_components_packages(root=ROOT, monkeypatch=monkeypatch)
    stub_aiohttp_module(monkeypatch=monkeypatch)
    stub_homeassistant_package(monkeypatch=monkeypatch)
    stub_exceptions(
        monkeypatch=monkeypatch,
        ConfigEntryAuthFailed=_StubConfigEntryAuthFailed,
    )

    helpers_mod = ModuleType("homeassistant.helpers")
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers_mod)
    stub_update_coordinator_module(
        monkeypatch=monkeypatch,
        update_failed=_StubUpdateFailed,
        data_update_coordinator=object,
        coordinator_entity=object,
    )

    stub_util_dt_module(monkeypatch=monkeypatch)

    imported_client = importlib.import_module("custom_components.pollenlevels.client")
    yield imported_client

    pollenlevels_pkg = sys.modules.get("custom_components.pollenlevels")
    if pollenlevels_pkg is not None and hasattr(pollenlevels_pkg, "client"):
        delattr(pollenlevels_pkg, "client")
    clear_integration_modules()


class FakeResponse:
    """Async context manager response with configurable JSON behavior."""

    def __init__(
        self,
        *,
        status: int = 200,
        json_results: list[Any] | None = None,
        text_body: str = "",
    ) -> None:
        self.status = status
        self.headers: dict[str, str] = {}
        self._json_results = list(json_results or [])
        self._text_body = text_body
        self.in_context = False
        self.exit_calls = 0

    async def json(self, *args: Any, **kwargs: Any) -> Any:
        """Return or raise the next configured JSON result."""

        if not self._json_results:
            return {}

        result = self._json_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def text(self) -> str:
        """Return the configured text body."""

        return self._text_body

    async def __aenter__(self) -> FakeResponse:
        """Support the async context manager protocol."""

        self.in_context = True
        return self

    async def __aexit__(self, exc_type, exc: BaseException | None, tb) -> None:
        """Support the async context manager protocol."""

        self.in_context = False
        self.exit_calls += 1
        return None


class FakeSession:
    """Return a fake aiohttp-like response for each GET call."""

    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls = 0

    def get(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        """Return the configured fake response."""

        self.calls += 1
        return self.response


class SequenceSession:
    """Return a sequence of fake aiohttp-like responses."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def get(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        """Return the next configured response."""

        if self.calls >= len(self.responses):
            raise AssertionError("Unexpected extra HTTP request")
        response = self.responses[self.calls]
        self.calls += 1
        return response


class RaisingSession:
    """Raise an aiohttp-like client error for each GET call."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def get(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        """Raise the configured error."""

        self.calls += 1
        raise self.error


async def _fetch_client(client: Any) -> dict[str, Any]:
    """Execute a representative direct client fetch."""

    return await client.async_fetch_pollen_data(
        latitude=1.0,
        longitude=2.0,
        days=5,
        language_code=None,
    )


async def _fetch_with_response(
    client_module: ModuleType,
    response: FakeResponse,
    api_key: str = "test",
    latitude: float = 1.0,
    longitude: float = 2.0,
) -> None:
    """Execute a direct client fetch using a fake session."""

    client = client_module.GooglePollenApiClient(FakeSession(response), api_key)
    await client.async_fetch_pollen_data(
        latitude=latitude,
        longitude=longitude,
        days=5,
        language_code=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "json_results",
    [
        [ValueError("invalid JSON")],
        [TypeError("content_type unsupported"), ValueError("invalid JSON")],
    ],
)
async def test_client_invalid_json_raises_update_failed(
    client_module: ModuleType,
    json_results: list[Exception],
) -> None:
    """Invalid JSON responses should raise the expected UpdateFailed message."""

    response = FakeResponse(json_results=json_results)

    with pytest.raises(
        client_module.UpdateFailed,
        match="Unexpected API response: invalid JSON",
    ):
        await _fetch_with_response(client_module, response)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], "not an object", 1, None])
async def test_client_non_object_json_raises_update_failed(
    client_module: ModuleType, payload: Any
) -> None:
    """JSON payloads must be objects at the direct client boundary."""

    response = FakeResponse(json_results=[payload])

    with pytest.raises(
        client_module.UpdateFailed,
        match="Unexpected API response: expected JSON object",
    ):
        await _fetch_with_response(client_module, response)


@pytest.mark.asyncio
async def test_client_redacts_api_key_from_http_error_body(
    client_module: ModuleType,
) -> None:
    """HTTP error bodies containing the API key should be redacted."""

    api_key = "AIzaFAKEPLACEHOLDER1234567890"
    response = FakeResponse(
        status=403,
        json_results=[ValueError("invalid JSON")],
        text_body=f"backend echoed key {api_key} while failing",
    )

    with pytest.raises(client_module.UpdateFailed) as exc_info:
        await _fetch_with_response(client_module, response, api_key=api_key)

    message = str(exc_info.value)
    assert api_key not in message
    assert "***" in message


@pytest.mark.asyncio
async def test_client_redacts_sensitive_values_from_url_like_http_error(
    client_module: ModuleType,
) -> None:
    """URL-like HTTP error messages should not expose secrets or coordinates."""

    api_key = "bad-key"
    latitude = 40.4168
    longitude = -3.7038
    url = (
        "https://pollen.googleapis.com/v1/forecast:lookup?"
        f"key={api_key}&location.latitude={latitude}&"
        f"location.longitude={longitude}&days=5"
    )
    response = FakeResponse(
        status=400,
        json_results=[ValueError("invalid JSON")],
        text_body=f"Backend rejected request URL {url}",
    )

    with pytest.raises(client_module.UpdateFailed) as exc_info:
        await _fetch_with_response(
            client_module,
            response,
            api_key=api_key,
            latitude=latitude,
            longitude=longitude,
        )

    message = str(exc_info.value)
    assert api_key not in message
    assert str(latitude) not in message
    assert str(longitude) not in message
    assert "***" in message


@pytest.mark.asyncio
async def test_client_redacts_sensitive_values_from_client_error(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ClientError messages should not expose secrets or coordinates."""

    monkeypatch.setattr(client_module, "MAX_RETRIES", 0)
    api_key = "bad-key"
    latitude = 40.4168
    longitude = -3.7038
    error = client_module.ClientError(
        "request failed: "
        "https://pollen.googleapis.com/v1/forecast:lookup?"
        f"key={api_key}&location.latitude={latitude}&"
        f"location.longitude={longitude}&days=5"
    )
    client = client_module.GooglePollenApiClient(RaisingSession(error), api_key)

    with pytest.raises(client_module.UpdateFailed) as exc_info:
        await client.async_fetch_pollen_data(
            latitude=latitude,
            longitude=longitude,
            days=5,
            language_code=None,
        )

    message = str(exc_info.value)
    assert api_key not in message
    assert str(latitude) not in message
    assert str(longitude) not in message
    assert "***" in message


@pytest.mark.asyncio
@pytest.mark.parametrize("error_name", ["TimeoutError", "ClientError"])
async def test_client_exhausted_transport_error_keeps_retry_and_redaction(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    error_name: str,
) -> None:
    """Exhausted transport attempts should retain retry and redaction behavior."""
    api_key = "synthetic-secret-key"
    latitude = 40.4168
    longitude = -3.7038
    message = (
        "request failed: "
        "https://pollen.googleapis.com/v1/forecast:lookup?"
        f"key={api_key}&location.latitude={latitude}&"
        f"location.longitude={longitude}&days=5"
    )
    error_type = (
        TimeoutError if error_name == "TimeoutError" else client_module.ClientError
    )
    session = RaisingSession(error_type(message))
    client = client_module.GooglePollenApiClient(session, api_key)
    sleep_delays: list[float] = []

    async def _sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(client_module.random, "uniform", lambda *_args: 0.0)
    monkeypatch.setattr(client_module.asyncio, "sleep", _sleep)

    with pytest.raises(client_module.PollenTransportError) as exc_info:
        await client.async_fetch_pollen_data(
            latitude=latitude,
            longitude=longitude,
            days=5,
            language_code=None,
        )

    assert isinstance(exc_info.value, client_module.UpdateFailed)
    assert session.calls == 2
    assert sleep_delays == pytest.approx([0.8])
    raised_message = str(exc_info.value)
    assert api_key not in raised_message
    assert str(latitude) not in raised_message
    assert str(longitude) not in raised_message
    assert "***" in raised_message


@pytest.mark.asyncio
@pytest.mark.parametrize("error_name", ["TimeoutError", "ClientError"])
async def test_client_transport_retry_backoff_propagates_cancelled_error(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    error_name: str,
) -> None:
    """Cancellation during transport retry backoff should propagate unchanged."""
    error_type = (
        TimeoutError if error_name == "TimeoutError" else client_module.ClientError
    )
    session = RaisingSession(error_type("transport unavailable"))
    client = client_module.GooglePollenApiClient(session, "synthetic-key")

    async def _cancel_sleep(_delay: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(client_module.asyncio, "sleep", _cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await _fetch_client(client)

    assert session.calls == 1


@pytest.mark.asyncio
async def test_client_treats_403_invalid_api_key_as_auth_failure(
    client_module: ModuleType,
) -> None:
    """Invalid-key messages on HTTP 403 responses should trigger re-auth."""

    api_key = "bad-key"
    response = FakeResponse(
        status=403,
        json_results=[
            {
                "error": {
                    "message": f"API key not valid. Please pass a valid API key: {api_key}"
                }
            }
        ],
    )

    with pytest.raises(client_module.ConfigEntryAuthFailed) as exc_info:
        await _fetch_with_response(client_module, response, api_key=api_key)

    message = str(exc_info.value)
    assert api_key not in message
    assert "***" in message


@pytest.mark.asyncio
async def test_client_treats_400_invalid_api_key_as_auth_failure(
    client_module: ModuleType,
) -> None:
    """Invalid-key messages on generic 4xx responses should trigger re-auth."""

    api_key = "bad-key"
    response = FakeResponse(
        status=400,
        json_results=[
            {
                "error": {
                    "message": f"API key not valid. Please pass a valid API key: {api_key}"
                }
            }
        ],
    )

    with pytest.raises(client_module.ConfigEntryAuthFailed) as exc_info:
        await _fetch_with_response(client_module, response, api_key=api_key)

    message = str(exc_info.value)
    assert api_key not in message
    assert "***" in message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "API key expired. Please renew the API key.",
        "aPi KeY eXpIrEd. PlEaSe ReNeW tHe ApI kEy.",
    ],
)
async def test_client_treats_400_expired_api_key_as_auth_failure(
    client_module: ModuleType,
    message: str,
) -> None:
    """Expired-key messages on HTTP 400 responses should trigger re-auth."""

    response = FakeResponse(
        status=400,
        json_results=[{"error": {"message": message}}],
    )

    with pytest.raises(client_module.ConfigEntryAuthFailed, match="HTTP 400"):
        await _fetch_with_response(client_module, response)


@pytest.mark.asyncio
async def test_client_treats_400_non_auth_error_as_update_failed(
    client_module: ModuleType,
) -> None:
    """Non-auth generic 4xx responses should remain update failures."""

    response = FakeResponse(
        status=400,
        json_results=[
            {"error": {"message": "Invalid value at 'days': value is out of range"}}
        ],
    )

    with pytest.raises(client_module.UpdateFailed, match="HTTP 400"):
        await _fetch_with_response(client_module, response)


@pytest.mark.asyncio
async def test_client_short_numeric_retry_after_retries_inline(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Short numeric Retry-After should wait at least that long and retry once."""

    first = FakeResponse(status=429)
    first.headers["Retry-After"] = "1.5"
    second = FakeResponse(json_results=[{"ok": True}])
    session = SequenceSession([first, second])
    client = client_module.GooglePollenApiClient(session, "test")
    sleep_delays: list[float] = []

    async def _sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(client_module.random, "uniform", lambda *_args: 0.0)
    monkeypatch.setattr(client_module.asyncio, "sleep", _sleep)

    assert await _fetch_client(client) == {"ok": True}
    assert sleep_delays == pytest.approx([1.5])
    assert session.calls == 2
    assert first.exit_calls == 1
    assert second.exit_calls == 1


@pytest.mark.asyncio
async def test_client_http_date_retry_after_retries_inline(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A short HTTP-date Retry-After should behave like a numeric delay."""

    now = datetime(2026, 8, 11, 13, 0, tzinfo=UTC)
    first = FakeResponse(status=429)
    first.headers["Retry-After"] = format_datetime(
        now + timedelta(seconds=3),
        usegmt=True,
    )
    second = FakeResponse(json_results=[{"ok": True}])
    session = SequenceSession([first, second])
    client = client_module.GooglePollenApiClient(session, "test")
    sleep_delays: list[float] = []

    async def _sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(client_module.dt_util, "utcnow", lambda: now)
    monkeypatch.setattr(client_module.random, "uniform", lambda *_args: 0.0)
    monkeypatch.setattr(client_module.asyncio, "sleep", _sleep)

    assert await _fetch_client(client) == {"ok": True}
    assert sleep_delays == pytest.approx([3.0])
    assert session.calls == 2


@pytest.mark.asyncio
async def test_client_long_retry_after_sets_cooldown_without_inline_sleep(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Long Retry-After should fail fast with a coordinator-visible cooldown."""

    api_key = "AIzaFAKEPLACEHOLDER1234567890"
    response = FakeResponse(
        status=429,
        json_results=[{"error": {"message": f"Quota exceeded for {api_key}"}}],
    )
    response.headers["Retry-After"] = "60"
    session = FakeSession(response)
    client = client_module.GooglePollenApiClient(session, api_key)

    async def _unexpected_sleep(_delay: float) -> None:
        raise AssertionError("Long Retry-After must not sleep inline")

    monkeypatch.setattr(client_module, "monotonic", lambda: 100.0)
    monkeypatch.setattr(client_module.asyncio, "sleep", _unexpected_sleep)

    with pytest.raises(client_module.PollenQuotaExceededError) as exc_info:
        await _fetch_client(client)

    assert exc_info.value.retry_after == pytest.approx(60.0)
    assert api_key not in str(exc_info.value)
    assert session.calls == 1
    assert response.exit_calls == 1


@pytest.mark.asyncio
async def test_client_active_cooldown_blocks_sibling_without_http_request(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shared client cooldown should block sibling calls without network I/O."""

    response = FakeResponse(status=429)
    response.headers["Retry-After"] = "60"
    session = FakeSession(response)
    client = client_module.GooglePollenApiClient(session, "test")
    now = [100.0]

    monkeypatch.setattr(client_module, "monotonic", lambda: now[0])

    with pytest.raises(client_module.PollenQuotaExceededError) as first_error:
        await _fetch_client(client)
    assert first_error.value.retry_after == pytest.approx(60.0)
    assert session.calls == 1

    now[0] = 110.0
    with pytest.raises(client_module.PollenQuotaExceededError) as sibling_error:
        await _fetch_client(client)

    assert sibling_error.value.retry_after == pytest.approx(50.0)
    assert session.calls == 1


@pytest.mark.asyncio
async def test_client_cooldown_expires_and_allows_next_request(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired cooldown should clear and permit the next HTTP request."""

    limited = FakeResponse(status=429)
    limited.headers["Retry-After"] = "60"
    healthy = FakeResponse(json_results=[{"ok": True}])
    session = SequenceSession([limited, healthy])
    client = client_module.GooglePollenApiClient(session, "test")
    now = [100.0]

    monkeypatch.setattr(client_module, "monotonic", lambda: now[0])

    with pytest.raises(client_module.PollenQuotaExceededError):
        await _fetch_client(client)
    assert session.calls == 1

    now[0] = 161.0
    assert await _fetch_client(client) == {"ok": True}
    assert session.calls == 2


@pytest.mark.asyncio
async def test_client_cooldown_does_not_block_different_client(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cooldown must remain scoped to one client/API-key runtime."""

    limited_response = FakeResponse(status=429)
    limited_response.headers["Retry-After"] = "60"
    limited_session = FakeSession(limited_response)
    limited_client = client_module.GooglePollenApiClient(limited_session, "key-a")

    healthy_response = FakeResponse(json_results=[{"ok": True}])
    healthy_session = FakeSession(healthy_response)
    healthy_client = client_module.GooglePollenApiClient(healthy_session, "key-b")

    monkeypatch.setattr(client_module, "monotonic", lambda: 100.0)

    with pytest.raises(client_module.PollenQuotaExceededError):
        await _fetch_client(limited_client)

    assert await _fetch_client(healthy_client) == {"ok": True}
    assert limited_session.calls == 1
    assert healthy_session.calls == 1


@pytest.mark.asyncio
async def test_client_exhausted_short_retry_after_sets_cooldown(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exhausted short Retry-After should create a shared cooldown."""

    first = FakeResponse(status=429)
    first.headers["Retry-After"] = "2"
    second = FakeResponse(status=429)
    second.headers["Retry-After"] = "2"
    session = SequenceSession([first, second])
    client = client_module.GooglePollenApiClient(session, "test")
    now = [100.0]
    sleep_delays: list[float] = []

    async def _sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(client_module, "monotonic", lambda: now[0])
    monkeypatch.setattr(client_module.random, "uniform", lambda *_args: 0.0)
    monkeypatch.setattr(client_module.asyncio, "sleep", _sleep)

    with pytest.raises(client_module.PollenQuotaExceededError) as exc_info:
        await _fetch_client(client)

    assert sleep_delays == pytest.approx([2.0])
    assert exc_info.value.retry_after == pytest.approx(2.0)
    assert session.calls == 2
    assert first.exit_calls == 1
    assert second.exit_calls == 1

    now[0] = 101.0
    with pytest.raises(client_module.PollenQuotaExceededError) as sibling_error:
        await _fetch_client(client)

    assert sibling_error.value.retry_after == pytest.approx(1.0)
    assert session.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "retry_after_raw",
    [None, "not-a-date", "-1", "0", "nan", "inf"],
)
async def test_client_invalid_retry_after_uses_short_fallback(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    retry_after_raw: str | None,
) -> None:
    """Missing or malformed Retry-After should keep the short fallback retry."""

    first = FakeResponse(status=429)
    if retry_after_raw is not None:
        first.headers["Retry-After"] = retry_after_raw
    second = FakeResponse(json_results=[{"ok": True}])
    session = SequenceSession([first, second])
    client = client_module.GooglePollenApiClient(session, "test")
    sleep_delays: list[float] = []

    async def _sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(client_module.random, "uniform", lambda *_args: 0.0)
    monkeypatch.setattr(client_module.asyncio, "sleep", _sleep)

    assert await _fetch_client(client) == {"ok": True}
    assert sleep_delays == pytest.approx([2.0])
    assert session.calls == 2


@pytest.mark.asyncio
async def test_client_final_invalid_retry_after_does_not_create_cooldown(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A final malformed Retry-After should not invent a cooldown."""

    monkeypatch.setattr(client_module, "MAX_RETRIES", 0)
    first = FakeResponse(status=429)
    first.headers["Retry-After"] = "not-a-date"
    second = FakeResponse(json_results=[{"ok": True}])
    session = SequenceSession([first, second])
    client = client_module.GooglePollenApiClient(session, "test")

    with pytest.raises(client_module.PollenQuotaExceededError) as exc_info:
        await _fetch_client(client)

    assert exc_info.value.retry_after is None
    assert await _fetch_client(client) == {"ok": True}
    assert session.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_error_name"),
    [
        (429, "PollenQuotaExceededError"),
        (503, "UpdateFailed"),
    ],
)
async def test_client_releases_retry_response_before_backoff(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    expected_error_name: str,
) -> None:
    """Retryable HTTP responses should exit their context before backoff."""

    response = FakeResponse(status=status)
    session = FakeSession(response)
    client = client_module.GooglePollenApiClient(session, "test")
    sleep_observations: list[tuple[bool, int, int]] = []

    async def _sleep(_delay: float) -> None:
        sleep_observations.append(
            (response.in_context, response.exit_calls, session.calls)
        )

    monkeypatch.setattr(client_module.asyncio, "sleep", _sleep)

    expected_error = getattr(client_module, expected_error_name)
    with pytest.raises(expected_error) as exc_info:
        await client.async_fetch_pollen_data(
            latitude=1.0,
            longitude=2.0,
            days=5,
            language_code=None,
        )

    assert not isinstance(exc_info.value, client_module.PollenTransportError)
    assert sleep_observations == [(False, 1, 1)]
    assert session.calls == 2
    assert response.exit_calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 503])
async def test_client_retry_backoff_propagates_cancelled_error(
    client_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    """Cancellation during HTTP retry backoff should propagate unchanged."""

    response = FakeResponse(status=status)
    session = FakeSession(response)
    client = client_module.GooglePollenApiClient(session, "test")

    async def _cancel_sleep(_delay: float) -> None:
        assert response.in_context is False
        assert response.exit_calls == 1
        raise asyncio.CancelledError

    monkeypatch.setattr(client_module.asyncio, "sleep", _cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await client.async_fetch_pollen_data(
            latitude=1.0,
            longitude=2.0,
            days=5,
            language_code=None,
        )

    assert session.calls == 1
    assert response.exit_calls == 1
