"""Tests for integration setup exception handling."""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import config_flow test module to reuse its Home Assistant stubs.
import tests.test_config_flow  # noqa: E402,F401  # pylint: disable=unused-import

# Provide the additional stubs required by __init__.
sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))

core_mod = types.ModuleType("homeassistant.core")


class _StubHomeAssistant:  # pragma: no cover - structure only
    pass


class _StubServiceCall:  # pragma: no cover - structure only
    pass


core_mod.HomeAssistant = _StubHomeAssistant
core_mod.ServiceCall = _StubServiceCall
sys.modules.setdefault("homeassistant.core", core_mod)

cv_mod = sys.modules["homeassistant.helpers.config_validation"]
cv_mod.config_entry_only_config_schema = lambda _domain: lambda config: config

vol_mod = sys.modules["voluptuous"]
if not hasattr(vol_mod, "Schema"):
    vol_mod.Schema = lambda *args, **kwargs: None

exceptions_mod = sys.modules.setdefault(
    "homeassistant.exceptions", types.ModuleType("homeassistant.exceptions")
)
if not hasattr(exceptions_mod, "ConfigEntryNotReady"):

    class _StubConfigEntryNotReady(Exception):
        pass

    exceptions_mod.ConfigEntryNotReady = _StubConfigEntryNotReady
if not hasattr(exceptions_mod, "ConfigEntryAuthFailed"):

    class _StubConfigEntryAuthFailed(Exception):
        pass

    exceptions_mod.ConfigEntryAuthFailed = _StubConfigEntryAuthFailed

integration = importlib.import_module(
    "custom_components.pollenlevels.__init__"
)  # noqa: E402


class _FakeConfigEntries:
    def __init__(self, forward_exception: Exception | None = None):
        self._forward_exception = forward_exception
        self.forward_calls: list[tuple[object, list[str]]] = []

    async def async_forward_entry_setups(self, entry, platforms):
        self.forward_calls.append((entry, platforms))
        if self._forward_exception is not None:
            raise self._forward_exception


class _FakeEntry:
    def __init__(self, *, entry_id: str = "entry-1", title: str = "Pollen Levels"):
        self.entry_id = entry_id
        self.title = title
        self._update_listener = None

    def add_update_listener(self, listener):
        self._update_listener = listener
        return listener

    def async_on_unload(self, callback):
        # Store callbacks to mirror Home Assistant behavior during tests.
        self._on_unload = callback  # pragma: no cover - stored for completeness
        return callback


class _FakeHass:
    def __init__(self, *, forward_exception: Exception | None = None):
        self.config_entries = _FakeConfigEntries(forward_exception)
        self.data = {}


def test_setup_entry_propagates_auth_failed() -> None:
    """ConfigEntryAuthFailed should bubble up for reauthentication."""

    hass = _FakeHass(forward_exception=integration.ConfigEntryAuthFailed("bad key"))
    entry = _FakeEntry()

    with pytest.raises(integration.ConfigEntryAuthFailed):
        asyncio.run(integration.async_setup_entry(hass, entry))


def test_setup_entry_wraps_generic_error() -> None:
    """Unexpected errors convert to ConfigEntryNotReady for retries."""

    class _Boom(Exception):
        pass

    hass = _FakeHass(forward_exception=_Boom("boom"))
    entry = _FakeEntry()

    with pytest.raises(integration.ConfigEntryNotReady):
        asyncio.run(integration.async_setup_entry(hass, entry))
