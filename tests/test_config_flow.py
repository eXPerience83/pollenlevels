"""Tests for the Pollen Levels config flow language validation."""

# ruff: noqa: E402

from __future__ import annotations

import ast
import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Minimal package and dependency stubs so the config flow can be imported.
# ---------------------------------------------------------------------------
custom_components_pkg = ModuleType("custom_components")
custom_components_pkg.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components_pkg)

pollenlevels_pkg = ModuleType("custom_components.pollenlevels")
pollenlevels_pkg.__path__ = [str(ROOT / "custom_components" / "pollenlevels")]
sys.modules.setdefault("custom_components.pollenlevels", pollenlevels_pkg)

ha_mod = ModuleType("homeassistant")
sys.modules.setdefault("homeassistant", ha_mod)

config_entries_mod = ModuleType("homeassistant.config_entries")

data_entry_flow_mod = ModuleType("homeassistant.data_entry_flow")


class _SectionConfig:
    def __init__(self, collapsed: bool | None = None):
        self.collapsed = collapsed


def section(key: str, config: _SectionConfig):  # noqa: ARG001
    return key


data_entry_flow_mod.SectionConfig = _SectionConfig
data_entry_flow_mod.section = section
sys.modules.setdefault("homeassistant.data_entry_flow", data_entry_flow_mod)


class _StubConfigFlow:
    def __init_subclass__(cls, **_kwargs):
        return super().__init_subclass__()

    async def async_set_unique_id(self, *_args, **_kwargs):
        return None

    def _abort_if_unique_id_configured(self):
        return None

    def async_abort(self, *, reason=None):
        return {"type": "abort", "reason": reason}

    def async_show_form(self, *args, **kwargs):  # pragma: no cover - not used
        return {"step_id": kwargs.get("step_id") or (args[0] if args else None)}

    def async_create_entry(self, *args, **kwargs):  # pragma: no cover - not used
        return {"title": kwargs.get("title"), "data": kwargs.get("data")}

    def add_suggested_values_to_schema(self, schema, suggested_values):
        return schema


class _StubOptionsFlow:
    pass


class _StubConfigEntry:
    def __init__(self, data=None, options=None, entry_id="stub-entry"):
        self.data = data or {}
        self.options = options or {}
        self.entry_id = entry_id
        raw = self.data.get("name", "Pollen Levels") or ""
        self.title = raw.strip() or "Pollen Levels"


config_entries_mod.ConfigFlow = _StubConfigFlow
config_entries_mod.OptionsFlow = _StubOptionsFlow
config_entries_mod.ConfigEntry = _StubConfigEntry
sys.modules.setdefault("homeassistant.config_entries", config_entries_mod)

const_mod = ModuleType("homeassistant.const")
const_mod.CONF_LATITUDE = "latitude"
const_mod.CONF_LOCATION = "location"
const_mod.CONF_LONGITUDE = "longitude"
const_mod.CONF_NAME = "name"
sys.modules.setdefault("homeassistant.const", const_mod)

helpers_mod = ModuleType("homeassistant.helpers")
sys.modules.setdefault("homeassistant.helpers", helpers_mod)

config_validation_mod = ModuleType("homeassistant.helpers.config_validation")


def _latitude(value=None):
    try:
        lat = float(value)
    except (TypeError, ValueError):
        # Mirror Home Assistant's cv.latitude behavior for invalid types
        raise cf.vol.Invalid("latitude_type") from None
    if lat < -90 or lat > 90:
        raise cf.vol.Invalid("latitude_range")
    return lat


def _longitude(value=None):
    try:
        lon = float(value)
    except (TypeError, ValueError):
        # Mirror Home Assistant's cv.longitude behavior for invalid types
        raise cf.vol.Invalid("longitude_type") from None

    if lon < -180 or lon > 180:
        raise cf.vol.Invalid("longitude_range")

    return lon


config_validation_mod.latitude = _latitude
config_validation_mod.longitude = _longitude
config_validation_mod.string = lambda value=None: value
sys.modules.setdefault("homeassistant.helpers.config_validation", config_validation_mod)

aiohttp_client_mod = ModuleType("homeassistant.helpers.aiohttp_client")


class _StubResponse:
    """Async response stub matching aiohttp.ClientResponse for tests."""

    def __init__(self, *, status: int = 200, body: bytes = b"{}") -> None:
        self.status = status
        self._body = body

    async def read(self) -> bytes:
        """Return the fake response body."""

        return self._body

    async def __aenter__(self) -> _StubResponse:
        """Support the async context manager protocol."""

        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """Support the async context manager protocol."""

        return None


class _StubSession:
    """Async session stub exposing a get() method."""

    def __init__(self, *, status: int = 200, body: bytes = b"{}") -> None:
        self._status = status
        self._body = body

    def get(self, *args, **kwargs) -> _StubResponse:
        """Return an async context manager response stub."""

        return _StubResponse(status=self._status, body=self._body)


aiohttp_client_mod.async_get_clientsession = lambda hass: _StubSession()
sys.modules.setdefault("homeassistant.helpers.aiohttp_client", aiohttp_client_mod)

selector_mod = ModuleType("homeassistant.helpers.selector")


class _LocationSelectorConfig:
    def __init__(self, *, radius: bool | None = None):
        self.radius = radius


class _LocationSelector:
    def __init__(self, config: _LocationSelectorConfig):
        self.config = config


class _NumberSelectorConfig:
    def __init__(
        self,
        *,
        min: float | None = None,
        max: float | None = None,
        step: float | None = None,
        mode: str | None = None,
        unit_of_measurement: str | None = None,
    ) -> None:
        self.min = min
        self.max = max
        self.step = step
        self.mode = mode
        self.unit_of_measurement = unit_of_measurement


class _NumberSelectorMode:
    BOX = "BOX"


class _NumberSelector:
    def __init__(self, config: _NumberSelectorConfig):
        self.config = config


class _TextSelectorConfig:
    def __init__(self, *, type: str | None = None):  # noqa: A003
        self.type = type


class _TextSelectorType:
    TEXT = "TEXT"


class _TextSelector:
    def __init__(self, config: _TextSelectorConfig):
        self.config = config


class _SelectSelectorConfig:
    def __init__(self, *, mode: str | None = None, options=None):
        self.mode = mode
        self.options = options


class _SelectSelectorMode:
    DROPDOWN = "DROPDOWN"


class _SelectSelector:
    def __init__(self, config: _SelectSelectorConfig):
        self.config = config


selector_mod.LocationSelector = _LocationSelector
selector_mod.LocationSelectorConfig = _LocationSelectorConfig
selector_mod.NumberSelector = _NumberSelector
selector_mod.NumberSelectorConfig = _NumberSelectorConfig
selector_mod.NumberSelectorMode = _NumberSelectorMode
selector_mod.TextSelector = _TextSelector
selector_mod.TextSelectorConfig = _TextSelectorConfig
selector_mod.TextSelectorType = _TextSelectorType
selector_mod.SelectSelector = _SelectSelector
selector_mod.SelectSelectorConfig = _SelectSelectorConfig
selector_mod.SelectSelectorMode = _SelectSelectorMode
sys.modules.setdefault("homeassistant.helpers.selector", selector_mod)

ha_mod.helpers = helpers_mod
ha_mod.config_entries = config_entries_mod
ha_mod.data_entry_flow = data_entry_flow_mod

aiohttp_mod = ModuleType("aiohttp")


class _StubClientError(Exception):
    pass


class _StubClientTimeout:
    def __init__(self, *, total: float | int):
        self.total = total


aiohttp_mod.ClientError = _StubClientError
aiohttp_mod.ClientTimeout = _StubClientTimeout
sys.modules.setdefault("aiohttp", aiohttp_mod)

vol_mod = ModuleType("voluptuous")


class _StubInvalid(Exception):
    def __init__(self, error_message=""):
        super().__init__(error_message)
        self.error_message = error_message


class _StubSchema:
    def __init__(self, schema):
        self.schema = schema


vol_mod.Invalid = _StubInvalid
vol_mod.Schema = lambda schema, **kwargs: _StubSchema(schema)
vol_mod.Optional = lambda key, **kwargs: key
vol_mod.Required = lambda key, **kwargs: key
vol_mod.All = lambda *args, **kwargs: None
vol_mod.Coerce = lambda *args, **kwargs: None
vol_mod.Range = lambda *args, **kwargs: None
vol_mod.In = lambda *args, **kwargs: None
sys.modules.setdefault("voluptuous", vol_mod)

from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
)

from custom_components.pollenlevels import config_flow as cf
from custom_components.pollenlevels.config_flow import (
    PollenLevelsConfigFlow,
    _language_error_to_form_key,
)
from custom_components.pollenlevels.const import (
    CONF_API_KEY,
    CONF_HTTP_REFERER,
    CONF_LANGUAGE_CODE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    normalize_http_referer,
)


class _StubResponse:
    def __init__(self, status: int, body: bytes | None = None) -> None:
        self.status = status
        self._body = body or b"{}"

    async def __aenter__(self):  # pragma: no cover - trivial
        return self

    async def __aexit__(self, exc_type, exc, tb):  # pragma: no cover - trivial
        return None

    async def read(self) -> bytes:
        return self._body

    async def json(self):
        import json as _json

        return _json.loads(self._body.decode())

    async def text(self) -> str:
        return self._body.decode()


class _SequenceSession:
    def __init__(self, responses: list[_StubResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[tuple, dict]] = []

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def _collect_error_keys_from_config_flow() -> set[str]:
    """Parse the config flow to extract all error keys used in forms."""

    source = (ROOT / "custom_components" / "pollenlevels" / "config_flow.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    language_error_returns: set[str] = set()

    class _LanguageErrorVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if node.name == "_language_error_to_form_key":
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Return)
                        and isinstance(child.value, ast.Constant)
                        and isinstance(child.value.value, str)
                    ):
                        language_error_returns.add(child.value.value)

    _LanguageErrorVisitor().visit(tree)

    error_keys: set[str] = set()

    def _extract_error_values(value: ast.AST) -> set[str]:
        values: set[str] = set()
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.add(value.value)
        elif (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "_language_error_to_form_key"
        ):
            values.update(language_error_returns)
        return values

    class _ErrorsVisitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
            for target in node.targets:
                self._record_errors(target, node.value)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
            self._record_errors(node.target, node.value)
            self.generic_visit(node)

        def _record_errors(self, target: ast.AST, value: ast.AST | None) -> None:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "errors"
                and value is not None
            ):
                error_keys.update(_extract_error_values(value))

    _ErrorsVisitor().visit(tree)
    return error_keys


def test_validate_input_invalid_language_key_mapping() -> None:
    """Invalid language formats should surface the translation key."""

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                CONF_API_KEY: "test-key",
                CONF_LOCATION: {CONF_LATITUDE: "1", CONF_LONGITUDE: "2"},
                CONF_LANGUAGE_CODE: "bad code",
            },
            check_unique_id=False,
        )
    )

    assert errors == {CONF_LANGUAGE_CODE: "invalid_language_format"}
    assert normalized is None


def test_validate_input_empty_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank or whitespace API keys should be rejected without HTTP calls."""

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    session_called = False

    def _raise_session(hass):
        nonlocal session_called
        session_called = True
        raise AssertionError("async_get_clientsession should not be called")

    monkeypatch.setattr(cf, "async_get_clientsession", _raise_session)

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                CONF_API_KEY: "   ",
                CONF_LOCATION: {CONF_LATITUDE: 1.0, CONF_LONGITUDE: 2.0},
            },
            check_unique_id=False,
        )
    )

    assert errors == {CONF_API_KEY: "empty"}
    assert normalized is None
    assert session_called is False


def test_language_error_to_form_key_mapping() -> None:
    """voluptuous error messages map to localized form keys."""

    assert _language_error_to_form_key(cf.vol.Invalid("empty")) == "empty"
    assert (
        _language_error_to_form_key(cf.vol.Invalid("invalid_language"))
        == "invalid_language_format"
    )


def test_validate_input_invalid_coordinates() -> None:
    """Non-numeric coordinates should surface a dedicated error."""

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                CONF_API_KEY: "test-key",
                CONF_LOCATION: {CONF_LATITUDE: "north", CONF_LONGITUDE: "west"},
            },
            check_unique_id=False,
        )
    )

    assert errors == {CONF_LOCATION: "invalid_coordinates"}
    assert normalized is None


def test_validate_input_out_of_range_coordinates() -> None:
    """Coordinates outside valid ranges should be rejected."""

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                CONF_API_KEY: "test-key",
                CONF_LOCATION: {CONF_LATITUDE: "200", CONF_LONGITUDE: "-300"},
            },
            check_unique_id=False,
        )
    )

    assert errors == {CONF_LOCATION: "invalid_coordinates"}
    assert normalized is None


def test_validate_input_missing_longitude() -> None:
    """Missing longitude should trigger an invalid_coordinates error."""

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {CONF_API_KEY: "test-key", CONF_LOCATION: {CONF_LATITUDE: 10.0}},
            check_unique_id=False,
        )
    )

    assert errors == {CONF_LOCATION: "invalid_coordinates"}
    assert normalized is None


def test_validate_input_non_dict_location() -> None:
    """Non-dictionary location payloads are invalid."""

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {CONF_API_KEY: "test-key", CONF_LOCATION: "not-a-dict"},
            check_unique_id=False,
        )
    )

    assert errors == {CONF_LOCATION: "invalid_coordinates"}
    assert normalized is None


def _patch_client_session(monkeypatch: pytest.MonkeyPatch, response: _StubResponse):
    session = _SequenceSession([response])
    monkeypatch.setattr(cf, "async_get_clientsession", lambda hass: session)
    return session


def _base_user_input() -> dict:
    return {
        CONF_API_KEY: "test-key",
        CONF_NAME: "Test Location",
        CONF_LOCATION: {CONF_LATITUDE: "1.0", CONF_LONGITUDE: "2.0"},
    }


def test_async_step_user_persists_http_referer() -> None:
    """HTTP referrer should be trimmed and persisted when provided."""

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(latitude=1.0, longitude=2.0, language="en")
    )

    async def fake_validate(
        user_input, *, check_unique_id, description_placeholders=None
    ):
        http_referer = normalize_http_referer(user_input.get(CONF_HTTP_REFERER))
        assert http_referer == "https://example.com"
        normalized = {
            CONF_API_KEY: user_input[CONF_API_KEY],
            CONF_LATITUDE: 1.0,
            CONF_LONGITUDE: 2.0,
            CONF_LANGUAGE_CODE: "en",
            CONF_HTTP_REFERER: http_referer,
        }
        return {}, normalized

    flow._async_validate_input = fake_validate  # type: ignore[assignment]

    user_input = {
        **_base_user_input(),
        CONF_UPDATE_INTERVAL: 6,
        CONF_LANGUAGE_CODE: "en",
        CONF_HTTP_REFERER: " https://example.com ",
    }

    result = asyncio.run(flow.async_step_user(user_input))

    assert result["data"][CONF_HTTP_REFERER] == "https://example.com"


def test_async_step_user_drops_blank_http_referer() -> None:
    """Blank HTTP referrer values should not be persisted."""

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(latitude=1.0, longitude=2.0, language="en")
    )

    async def fake_validate(
        user_input, *, check_unique_id, description_placeholders=None
    ):
        http_referer = normalize_http_referer(user_input.get(CONF_HTTP_REFERER))
        assert http_referer is None
        normalized = {
            CONF_API_KEY: user_input[CONF_API_KEY],
            CONF_LATITUDE: 1.0,
            CONF_LONGITUDE: 2.0,
            CONF_LANGUAGE_CODE: "en",
        }
        return {}, normalized

    flow._async_validate_input = fake_validate  # type: ignore[assignment]

    user_input = {
        **_base_user_input(),
        CONF_UPDATE_INTERVAL: 6,
        CONF_LANGUAGE_CODE: "en",
        CONF_HTTP_REFERER: "   ",
    }

    result = asyncio.run(flow.async_step_user(user_input))

    assert CONF_HTTP_REFERER not in result["data"]


def test_async_step_user_invalid_http_referer_sets_field_error() -> None:
    """Newlines in HTTP referrer should surface a field-level error."""

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(latitude=1.0, longitude=2.0, language="en")
    )

    captured: dict[str, Any] = {}

    def fake_show_form(*args, **kwargs):
        captured.update(kwargs)
        return kwargs

    flow.async_show_form = fake_show_form  # type: ignore[assignment]

    user_input = {
        **_base_user_input(),
        CONF_UPDATE_INTERVAL: 6,
        CONF_LANGUAGE_CODE: "en",
        CONF_HTTP_REFERER: "http://example.com/\npath",
    }

    asyncio.run(flow.async_step_user(user_input))

    assert captured.get("errors") == {CONF_HTTP_REFERER: "invalid_http_referrer"}


def test_validate_input_sends_referer_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validation should forward the Referer header when provided."""

    session = _patch_client_session(
        monkeypatch, _StubResponse(200, b'{"dailyInfo": [{"indexInfo": []}]}')
    )

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    user_input = {**_base_user_input(), CONF_HTTP_REFERER: "https://example.com"}

    errors, normalized = asyncio.run(
        flow._async_validate_input(user_input, check_unique_id=False)
    )

    assert errors == {}
    assert normalized is not None
    assert session.calls
    _, kwargs = session.calls[0]
    assert kwargs.get("headers") == {"Referer": "https://example.com"}


def test_validate_input_update_interval_below_min_sets_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sub-1 update intervals should surface a field error and skip I/O."""

    session = _patch_client_session(monkeypatch, _StubResponse(200))

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    user_input = {**_base_user_input(), CONF_UPDATE_INTERVAL: 0}

    errors, normalized = asyncio.run(
        flow._async_validate_input(user_input, check_unique_id=False)
    )

    assert errors == {CONF_UPDATE_INTERVAL: "invalid_update_interval"}
    assert normalized is None
    assert not session.calls


def test_validate_input_update_interval_float_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Float-like strings should coerce to int and allow validation to proceed."""

    session = _patch_client_session(
        monkeypatch, _StubResponse(200, b'{"dailyInfo": [{"indexInfo": []}]}')
    )

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    user_input = {**_base_user_input(), CONF_UPDATE_INTERVAL: "1.0"}

    errors, normalized = asyncio.run(
        flow._async_validate_input(user_input, check_unique_id=False)
    )

    assert errors == {}
    assert normalized is not None
    assert normalized[CONF_UPDATE_INTERVAL] == 1
    assert session.calls


def test_validate_input_update_interval_non_numeric_sets_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-numeric update intervals should surface a field error and skip I/O."""

    session = _patch_client_session(monkeypatch, _StubResponse(200))

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    user_input = {**_base_user_input(), CONF_UPDATE_INTERVAL: "abc"}

    errors, normalized = asyncio.run(
        flow._async_validate_input(user_input, check_unique_id=False)
    )

    assert errors == {CONF_UPDATE_INTERVAL: "invalid_update_interval"}
    assert normalized is None
    assert not session.calls


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, {"base": "invalid_auth"}),
        (403, {"base": "cannot_connect"}),
    ],
)
def test_validate_input_http_auth_errors_map_correctly(
    monkeypatch: pytest.MonkeyPatch, status: int, expected: dict
) -> None:
    """HTTP auth failures during validation should map correctly."""

    session = _patch_client_session(monkeypatch, _StubResponse(status))

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(_base_user_input(), check_unique_id=False)
    )

    assert session.calls
    assert errors == expected
    assert normalized is None


def test_validate_input_http_429_sets_quota_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 429 during validation should map to quota_exceeded."""

    session = _patch_client_session(monkeypatch, _StubResponse(429))

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(_base_user_input(), check_unique_id=False)
    )

    assert session.calls
    assert errors == {"base": "quota_exceeded"}
    assert normalized is None


def test_validate_input_http_500_sets_cannot_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected HTTP failures should map to cannot_connect."""

    session = _patch_client_session(monkeypatch, _StubResponse(500))

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(_base_user_input(), check_unique_id=False)
    )

    assert session.calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None


def test_validate_input_http_500_sets_error_message_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 500 should populate the cannot_connect error_message placeholder."""

    session = _patch_client_session(monkeypatch, _StubResponse(500))

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert session.calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None
    assert placeholders.get("error_message")


def test_validate_input_http_403_sets_error_message_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 403 should populate the cannot_connect error_message placeholder."""

    body = b'{"error": {"message": "Forbidden for this project"}}'
    session = _patch_client_session(monkeypatch, _StubResponse(status=403, body=body))

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert session.calls
    assert errors == {"base": "cannot_connect"}
    assert normalized is None
    assert "Forbidden" in placeholders.get("error_message", "")


def test_validate_input_http_403_invalid_key_maps_to_invalid_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 403 invalid API key messages should behave like invalid_auth."""

    body = b'{"error": {"message": "API key not valid. Please pass a valid API key."}}'
    session = _patch_client_session(monkeypatch, _StubResponse(status=403, body=body))

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()
    placeholders: dict[str, str] = {}

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            _base_user_input(),
            check_unique_id=False,
            description_placeholders=placeholders,
        )
    )

    assert session.calls
    assert errors == {"base": "invalid_auth"}
    assert normalized is None
    assert "api key not valid" in placeholders.get("error_message", "").lower()


def test_validate_input_unexpected_exception_sets_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected exceptions should map to an unknown error."""

    def _raise_session(hass):
        raise RuntimeError("boom")

    monkeypatch.setattr(cf, "async_get_clientsession", _raise_session)

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(_base_user_input(), check_unique_id=False)
    )

    assert errors == {"base": "unknown"}
    assert normalized is None


def test_validate_input_happy_path_sets_unique_id_and_normalizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful validation should normalize data and set unique ID."""

    body = b'{"dailyInfo": [{"day": "D0"}]}'
    session = _patch_client_session(monkeypatch, _StubResponse(200, body))

    class _TrackingFlow(PollenLevelsConfigFlow):
        def __init__(self) -> None:
            super().__init__()
            self.unique_ids: list[str] = []
            self.abort_calls = 0

        async def async_set_unique_id(self, uid: str, raise_on_progress: bool = False):
            self.unique_ids.append(uid)
            return None

        def _abort_if_unique_id_configured(self):
            self.abort_calls += 1
            return None

    flow = _TrackingFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(),
    )

    user_input = {
        **_base_user_input(),
        CONF_LANGUAGE_CODE: " es ",
    }

    errors, normalized = asyncio.run(
        flow._async_validate_input(user_input, check_unique_id=True)
    )

    assert session.calls
    assert errors == {}
    assert normalized is not None
    assert normalized[CONF_LATITUDE] == pytest.approx(1.0)
    assert normalized[CONF_LONGITUDE] == pytest.approx(2.0)
    assert normalized[CONF_LANGUAGE_CODE] == "es"
    assert flow.unique_ids == ["1.0000_2.0000"]
    assert flow.abort_calls == 1


def test_reauth_confirm_updates_and_reloads_entry() -> None:
    """Re-auth confirmation should update stored credentials and reload the entry."""

    entry = cf.config_entries.ConfigEntry(
        data={
            CONF_API_KEY: "old-key",
            CONF_LATITUDE: 1.0,
            CONF_LONGITUDE: 2.0,
            CONF_LANGUAGE_CODE: "en",
        },
        entry_id="entry-id",
    )

    class _Recorder:
        def __init__(self) -> None:
            self.updated = None
            self.reloaded = None

        def async_get_entry(self, entry_id: str):
            return entry if entry_id == entry.entry_id else None

        def async_update_entry(self, entry_to_update, *, data):
            self.updated = (entry_to_update, data)

        async def async_reload(self, entry_id: str):
            self.reloaded = entry_id

    recorder = _Recorder()

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(config_entries=recorder)
    flow.context = {"entry_id": "entry-id"}

    normalized = {
        CONF_API_KEY: "new-key",
        CONF_LATITUDE: 1.0,
        CONF_LONGITUDE: 2.0,
        CONF_LANGUAGE_CODE: "en",
    }

    async def fake_validate(
        user_input, *, check_unique_id, description_placeholders=None
    ):
        return {}, normalized

    flow._async_validate_input = fake_validate  # type: ignore[assignment]

    async def run_flow():
        await flow.async_step_reauth(entry.data)
        return await flow.async_step_reauth_confirm({CONF_API_KEY: "new-key"})

    result = asyncio.run(run_flow())

    assert result == {"type": "abort", "reason": "reauth_successful"}
    assert recorder.updated == (entry, normalized)
    assert recorder.reloaded == "entry-id"


def test_async_step_user_uses_custom_entry_name() -> None:
    """Config flow should honor a custom entry title provided by the user."""

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(latitude=1.0, longitude=2.0, language="en")
    )

    normalized = {
        CONF_API_KEY: "test-key",
        CONF_LATITUDE: 1.0,
        CONF_LONGITUDE: 2.0,
        CONF_LANGUAGE_CODE: "en",
    }

    async def fake_validate(
        user_input, *, check_unique_id, description_placeholders=None
    ):
        assert check_unique_id is True
        assert user_input[CONF_NAME].strip() == "Custom Name"
        return {}, normalized

    flow._async_validate_input = fake_validate  # type: ignore[assignment]

    user_input = {
        CONF_API_KEY: "test-key",
        CONF_NAME: " Custom Name ",
        CONF_LOCATION: {CONF_LATITUDE: 1.0, CONF_LONGITUDE: 2.0},
        CONF_UPDATE_INTERVAL: 6,
        CONF_LANGUAGE_CODE: "en",
    }

    result = asyncio.run(flow.async_step_user(user_input))

    assert result["title"] == "Custom Name"
    assert result["data"] == normalized


def test_async_step_user_defaults_entry_name() -> None:
    """Blank entry names should fall back to the default integration title."""

    flow = PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(latitude=1.0, longitude=2.0, language="en")
    )

    normalized = {
        CONF_API_KEY: "test-key",
        CONF_LATITUDE: 1.0,
        CONF_LONGITUDE: 2.0,
        CONF_LANGUAGE_CODE: "en",
    }

    async def fake_validate(
        user_input, *, check_unique_id, description_placeholders=None
    ):
        assert user_input[CONF_NAME] == "   "
        return {}, normalized

    flow._async_validate_input = fake_validate  # type: ignore[assignment]

    user_input = {
        CONF_API_KEY: "test-key",
        CONF_NAME: "   ",
        CONF_LOCATION: {CONF_LATITUDE: 1.0, CONF_LONGITUDE: 2.0},
        CONF_UPDATE_INTERVAL: 6,
        CONF_LANGUAGE_CODE: "en",
    }

    result = asyncio.run(flow.async_step_user(user_input))

    assert result["title"] == DEFAULT_ENTRY_TITLE
    assert result["data"] == normalized
