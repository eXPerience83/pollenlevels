"""Direct tests for the Google Pollen API client."""

from __future__ import annotations

import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SENTINEL = object()


class _StubClientError(Exception):
    """Minimal aiohttp ClientError stub."""


class _StubClientSession:
    """Minimal aiohttp ClientSession stub."""


class _StubClientTimeout:
    """Minimal aiohttp ClientTimeout stub."""

    def __init__(self, total: float | None = None) -> None:
        self.total = total


class _StubConfigEntryAuthFailed(Exception):
    """Minimal Home Assistant auth failure stub."""


class _StubUpdateFailed(Exception):
    """Minimal Home Assistant update failure stub."""


def _set_module(
    snapshot: dict[str, object], name: str, module: types.ModuleType
) -> None:
    """Set a temporary module while preserving its previous value."""

    snapshot.setdefault(name, sys.modules.get(name, _SENTINEL))
    sys.modules[name] = module


def _restore_modules(snapshot: dict[str, object]) -> None:
    """Restore modules changed only for importing the client under test."""

    for name, module in reversed(snapshot.items()):
        if module is _SENTINEL:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module  # type: ignore[assignment]


def _install_client_import_stubs() -> dict[str, object]:
    """Install the minimum modules required to import client.py directly."""

    snapshot: dict[str, object] = {}

    custom_components_pkg = types.ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(ROOT / "custom_components")]
    _set_module(snapshot, "custom_components", custom_components_pkg)

    pollenlevels_pkg = types.ModuleType("custom_components.pollenlevels")
    pollenlevels_pkg.__path__ = [str(ROOT / "custom_components" / "pollenlevels")]
    _set_module(snapshot, "custom_components.pollenlevels", pollenlevels_pkg)

    aiohttp_mod = types.ModuleType("aiohttp")
    aiohttp_mod.ClientError = _StubClientError
    aiohttp_mod.ClientSession = _StubClientSession
    aiohttp_mod.ClientTimeout = _StubClientTimeout
    aiohttp_mod.ContentTypeError = ValueError
    _set_module(snapshot, "aiohttp", aiohttp_mod)

    ha_mod = types.ModuleType("homeassistant")
    _set_module(snapshot, "homeassistant", ha_mod)

    exceptions_mod = types.ModuleType("homeassistant.exceptions")
    exceptions_mod.ConfigEntryAuthFailed = _StubConfigEntryAuthFailed
    _set_module(snapshot, "homeassistant.exceptions", exceptions_mod)

    helpers_mod = types.ModuleType("homeassistant.helpers")
    _set_module(snapshot, "homeassistant.helpers", helpers_mod)

    update_coordinator_mod = types.ModuleType(
        "homeassistant.helpers.update_coordinator"
    )
    update_coordinator_mod.UpdateFailed = _StubUpdateFailed
    _set_module(
        snapshot,
        "homeassistant.helpers.update_coordinator",
        update_coordinator_mod,
    )

    util_mod = types.ModuleType("homeassistant.util")
    dt_mod = types.ModuleType("homeassistant.util.dt")
    dt_mod.parse_http_date = lambda _value: None
    dt_mod.utcnow = lambda: datetime.now(UTC)
    util_mod.dt = dt_mod
    _set_module(snapshot, "homeassistant.util", util_mod)
    _set_module(snapshot, "homeassistant.util.dt", dt_mod)

    for name in (
        "custom_components.pollenlevels.client",
        "custom_components.pollenlevels.const",
        "custom_components.pollenlevels.util",
    ):
        snapshot.setdefault(name, sys.modules.get(name, _SENTINEL))

    return snapshot


def _import_client_module() -> types.ModuleType:
    """Import client.py with local stubs and avoid leaking them globally."""

    snapshot = _install_client_import_stubs()
    try:
        from custom_components.pollenlevels import client as imported_client

        return imported_client
    finally:
        pollenlevels_pkg = sys.modules.get("custom_components.pollenlevels")
        if pollenlevels_pkg is not None and hasattr(pollenlevels_pkg, "client"):
            delattr(pollenlevels_pkg, "client")
        _restore_modules(snapshot)


client_mod = _import_client_module()


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


@pytest.mark.asyncio
async def test_client_treats_400_invalid_api_key_as_auth_failure() -> None:
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

    with pytest.raises(client_mod.ConfigEntryAuthFailed) as exc_info:
        await _fetch_with_response(response, api_key=api_key)

    message = str(exc_info.value)
    assert api_key not in message
    assert "***" in message


@pytest.mark.asyncio
async def test_client_treats_400_non_auth_error_as_update_failed() -> None:
    """Non-auth generic 4xx responses should remain update failures."""

    response = FakeResponse(
        status=400,
        json_results=[
            {"error": {"message": "Invalid value at 'days': value is out of range"}}
        ],
    )

    with pytest.raises(client_mod.UpdateFailed, match="HTTP 400"):
        await _fetch_with_response(response)
