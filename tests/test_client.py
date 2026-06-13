"""Direct tests for the Google Pollen API client."""

from __future__ import annotations

import importlib
import sys
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

        return self

    async def __aexit__(self, exc_type, exc: BaseException | None, tb) -> None:
        """Support the async context manager protocol."""

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


class RaisingSession:
    """Raise an aiohttp-like client error for each GET call."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def get(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        """Raise the configured error."""

        raise self.error


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
