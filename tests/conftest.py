"""Pytest configuration for lightweight async test support."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.pollenlevels.const import (
    CONF_API_KEY,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SUBENTRY_TYPE_LOCATION,
)
from custom_components.pollenlevels.util import api_key_unique_id

TESTS_DIR = Path(__file__).resolve().parent


def pytest_configure(config: pytest.Config) -> None:
    """Register the asyncio marker used for lightweight async tests."""

    config.addinivalue_line(
        "markers", "asyncio: run test in an event loop without external plugins"
    )


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run @pytest.mark.asyncio tests locally when no other async plugin is active."""

    marker = pyfuncitem.get_closest_marker("asyncio")
    if marker is None or not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None

    # If another asyncio-aware plugin is active, let it handle the test.
    plugin_manager = pyfuncitem.config.pluginmanager
    if plugin_manager.hasplugin("asyncio") or plugin_manager.hasplugin(
        "pytest-asyncio"
    ):
        return None

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        running_loop = False
    else:
        running_loop = True

    if running_loop:
        raise RuntimeError(
            "Detected a running event loop without an asyncio-aware pytest plugin. "
            "Disable conflicting plugins or install/enable pytest-asyncio."
        )

    try:
        previous_loop = asyncio.get_event_loop()
    except RuntimeError:
        previous_loop = None

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        signature = inspect.signature(pyfuncitem.obj)
        declared_funcargs = {
            name: pyfuncitem.funcargs[name]
            for name in signature.parameters
            if name in pyfuncitem.funcargs
        }
        loop.run_until_complete(pyfuncitem.obj(**declared_funcargs))
    finally:
        # Ensure all tasks and async generators are properly cleaned up
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:
            # Continue teardown even if cleanup raises
            pass
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            finally:
                loop.close()
                try:
                    asyncio.set_event_loop(previous_loop)
                except Exception:
                    asyncio.set_event_loop(None)

    return True


@pytest.fixture
def fake_api_key() -> str:
    """Return a fake Google Pollen API key for harness tests."""
    return "test-api-key"


@pytest.fixture
def sample_location() -> dict[str, Any]:
    """Return a sample location using public integration constants."""
    return {
        "title": "Madrid",
        CONF_LATITUDE: 40.4168,
        CONF_LONGITUDE: -3.7038,
        "subentry_id": "location-madrid",
    }


@pytest.fixture
def sample_location_subentry_data(sample_location: dict[str, Any]) -> dict[str, Any]:
    """Return ConfigSubentryData-compatible location data."""
    latitude = sample_location[CONF_LATITUDE]
    longitude = sample_location[CONF_LONGITUDE]
    return {
        "subentry_id": sample_location["subentry_id"],
        "subentry_type": SUBENTRY_TYPE_LOCATION,
        "title": sample_location["title"],
        "unique_id": f"{latitude:.4f}_{longitude:.4f}",
        "data": {
            CONF_LATITUDE: latitude,
            CONF_LONGITUDE: longitude,
        },
    }


@pytest.fixture
def ha_config_entry(
    fake_api_key: str,
    sample_location_subentry_data: dict[str, Any],
):
    """Return a parent MockConfigEntry with one location subentry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="pollenlevels-entry",
        title="Pollen Levels",
        unique_id=api_key_unique_id(fake_api_key),
        data={CONF_API_KEY: fake_api_key},
        options={
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_LANGUAGE_CODE: "es",
        },
        subentries_data=[sample_location_subentry_data],
        version=6,
    )


@pytest.fixture
def google_pollen_5_day_payload() -> dict[str, Any]:
    """Return the sanitized real 5-day Google Pollen fixture."""
    fixture_path = TESTS_DIR / "fixtures" / "google_pollen_forecast_5_days.json"
    return json.loads(fixture_path.read_text(encoding="ascii"))
