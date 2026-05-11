"""Direct tests for the Google Pollen API client."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import config_flow test module to reuse its Home Assistant stubs.
import tests.test_config_flow  # noqa: E402,F401  # pylint: disable=unused-import

ha_exceptions = sys.modules["homeassistant.exceptions"]
if not hasattr(ha_exceptions, "ConfigEntryNotReady"):

    class _StubConfigEntryNotReady(Exception):
        pass

    ha_exceptions.ConfigEntryNotReady = _StubConfigEntryNotReady

from custom_components.pollenlevels import client as client_mod  # noqa: E402


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


async def _fetch_with_response(response: FakeResponse, api_key: str = "test") -> None:
    """Execute a direct client fetch using a fake session."""

    client = client_mod.GooglePollenApiClient(FakeSession(response), api_key)
    await client.async_fetch_pollen_data(
        latitude=1.0,
        longitude=2.0,
        days=1,
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
    json_results: list[Exception],
) -> None:
    """Invalid JSON responses should raise the expected UpdateFailed message."""

    response = FakeResponse(json_results=json_results)

    with pytest.raises(
        client_mod.UpdateFailed,
        match="Unexpected API response: invalid JSON",
    ):
        await _fetch_with_response(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], "not an object", 1, None])
async def test_client_non_object_json_raises_update_failed(payload: Any) -> None:
    """JSON payloads must be objects at the direct client boundary."""

    response = FakeResponse(json_results=[payload])

    with pytest.raises(
        client_mod.UpdateFailed,
        match="Unexpected API response: expected JSON object",
    ):
        await _fetch_with_response(response)


@pytest.mark.asyncio
async def test_client_redacts_api_key_from_http_error_body() -> None:
    """HTTP error bodies containing the API key should be redacted."""

    api_key = "AIzaFAKEPLACEHOLDER1234567890"
    response = FakeResponse(
        status=403,
        json_results=[ValueError("invalid JSON")],
        text_body=f"backend echoed key {api_key} while failing",
    )

    with pytest.raises(client_mod.UpdateFailed) as exc_info:
        await _fetch_with_response(response, api_key=api_key)

    message = str(exc_info.value)
    assert api_key not in message
    assert "***" in message
