"""Home Assistant harness tests for diagnostics."""

from __future__ import annotations

import importlib
import json
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qsl

from aiointercept import CallbackResult, aiointercept
from homeassistant.core import HomeAssistant

from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import (
    POLLEN_API_URL_RE,
    async_setup_config_entry,
    mock_pollen_api,
)


async def test_ha_diagnostics_redacts_secrets_and_summarizes_runtime(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    ha_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """Diagnostics should use real HA registries while redacting sensitive data."""
    clear_integration_modules()
    ha_config_entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)

        await async_setup_config_entry(hass, ha_config_entry)

        diagnostics_module = importlib.import_module(
            "custom_components.pollenlevels.diagnostics"
        )
        diagnostics = await diagnostics_module.async_get_config_entry_diagnostics(
            hass, ha_config_entry
        )

    serialized = json.dumps(diagnostics, sort_keys=True)
    assert fake_api_key not in serialized
    assert "40.4168" not in serialized
    assert "-3.7038" not in serialized

    assert diagnostics["runtime_summary"] == {
        "stale_location_count": 0,
        "stale_location_ids": [],
        "failed_location_count": 0,
        "failed_location_ids": [],
    }
    assert "registry_summary" in diagnostics

    location = diagnostics["locations"]["location-madrid"]
    assert location["request_params_example"]["key"] == "***"
    assert location["request_params_example"]["days"] == 5
    assert location["request_params_example"]["location.latitude"] == 40.4
    assert location["request_params_example"]["location.longitude"] == -3.7
    assert location["approximate_location"] == {
        "label": "approximate_location (rounded)",
        "latitude_rounded": 40.4,
        "longitude_rounded": -3.7,
    }


async def test_ha_diagnostics_summarizes_stale_and_failed_locations(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    ha_two_location_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """Diagnostics should summarize stale and failed locations from real runtime."""
    clear_integration_modules()
    entry = ha_two_location_config_entry
    entry.add_to_hass(hass)
    monkeypatch.setattr(
        hass.config_entries, "async_schedule_reload", lambda _entry_id: None
    )

    def _callback(url, **_kwargs):
        params = dict(parse_qsl(url.query_string))
        if float(params["location.latitude"]) == 41.3874:
            return CallbackResult(status=200, payload={"dailyInfo": []})
        return CallbackResult(status=200, payload=google_pollen_5_day_payload)

    async with aiointercept(mock_external_urls=True) as mocked:
        mocked.get(POLLEN_API_URL_RE, callback=_callback, repeat=True)
        await async_setup_config_entry(hass, entry)

        entry.runtime_data.locations["deleted-location"] = SimpleNamespace(
            subentry_id="deleted-location",
            coordinator=SimpleNamespace(
                entry_id=entry.entry_id,
                subentry_id="deleted-location",
                language="es",
                last_updated=None,
                lat=12.345678,
                lon=-98.765432,
                entry_title="Deleted secret 12.345678",
                data={},
            ),
        )

        diagnostics_module = importlib.import_module(
            "custom_components.pollenlevels.diagnostics"
        )
        diagnostics = await diagnostics_module.async_get_config_entry_diagnostics(
            hass, entry
        )

    assert set(diagnostics["locations"]) == {"location-madrid"}
    assert set(diagnostics["failed_locations"]) == {"location-barcelona"}
    assert diagnostics["runtime_summary"] == {
        "stale_location_count": 1,
        "stale_location_ids": ["deleted-location"],
        "failed_location_count": 1,
        "failed_location_ids": ["location-barcelona"],
    }
    assert diagnostics["failed_locations"]["location-barcelona"]["error_type"]
    assert (
        diagnostics["failed_locations"]["location-barcelona"]["will_retry_on_reload"]
        is True
    )

    serialized = json.dumps(diagnostics, sort_keys=True)
    assert fake_api_key not in serialized
    assert "41.3874" not in serialized
    assert "2.1686" not in serialized
    assert "12.345678" not in serialized
    assert "-98.765432" not in serialized


async def test_ha_diagnostics_reports_stale_payload_per_active_location(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    ha_two_location_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """A stale payload for one active location must not affect another location."""

    clear_integration_modules()
    entry = ha_two_location_config_entry
    entry.add_to_hass(hass)
    serve_invalid_barcelona = False

    def _callback(url, **_kwargs):
        params = dict(parse_qsl(url.query_string))
        if serve_invalid_barcelona and float(params["location.latitude"]) == 41.3874:
            return CallbackResult(status=200, payload={"dailyInfo": []})
        return CallbackResult(status=200, payload=google_pollen_5_day_payload)

    async with aiointercept(mock_external_urls=True) as mocked:
        mocked.get(POLLEN_API_URL_RE, callback=_callback, repeat=True)
        await async_setup_config_entry(hass, entry)

        serve_invalid_barcelona = True
        barcelona = entry.runtime_data.locations["location-barcelona"].coordinator
        madrid = entry.runtime_data.locations["location-madrid"].coordinator
        await barcelona.async_refresh()

        diagnostics_module = importlib.import_module(
            "custom_components.pollenlevels.diagnostics"
        )
        diagnostics = await diagnostics_module.async_get_config_entry_diagnostics(
            hass, entry
        )

    assert barcelona.last_update_success is True
    assert barcelona.using_stale_data is True
    assert barcelona.last_payload_valid is False
    assert madrid.using_stale_data is False
    assert madrid.last_payload_valid is True
    barcelona_diagnostics = diagnostics["locations"]["location-barcelona"][
        "coordinator"
    ]
    madrid_diagnostics = diagnostics["locations"]["location-madrid"]["coordinator"]
    assert barcelona_diagnostics["using_stale_data"] is True
    assert barcelona_diagnostics["last_payload_valid"] is False
    assert madrid_diagnostics["using_stale_data"] is False
    assert madrid_diagnostics["last_payload_valid"] is True
    assert diagnostics["runtime_summary"] == {
        "stale_location_count": 0,
        "stale_location_ids": [],
        "failed_location_count": 0,
        "failed_location_ids": [],
    }
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert fake_api_key not in serialized
    assert "41.3874" not in serialized
    assert "2.1686" not in serialized


async def test_ha_diagnostics_registry_summary_uses_real_registries(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    ha_two_location_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """Diagnostics should summarize real entity and device registry links."""
    clear_integration_modules()
    entry = ha_two_location_config_entry
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

        diagnostics_module = importlib.import_module(
            "custom_components.pollenlevels.diagnostics"
        )
        diagnostics = await diagnostics_module.async_get_config_entry_diagnostics(
            hass, entry
        )

    registry_summary = diagnostics["registry_summary"]
    assert registry_summary["entities"]["total"] > 0
    assert registry_summary["entities"]["without_subentry"] == 0
    assert set(registry_summary["entities"]["by_subentry_id"]) == {
        "location-madrid",
        "location-barcelona",
    }
    assert registry_summary["devices"]["total"] > 0
    assert registry_summary["devices"]["without_subentry"] == 0
    assert set(registry_summary["devices"]["by_subentry_id"]) == {
        "location-madrid",
        "location-barcelona",
    }

    serialized = json.dumps(diagnostics, sort_keys=True)
    assert fake_api_key not in serialized
    assert "pollenlevels-entry_location-madrid" not in serialized
    assert "pollenlevels-entry_location-barcelona" not in serialized
    assert "40.4168" not in serialized
    assert "-3.7038" not in serialized
    assert "41.3874" not in serialized
    assert "2.1686" not in serialized
