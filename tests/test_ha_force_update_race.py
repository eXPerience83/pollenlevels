"""Home Assistant regression tests for force_update lifecycle races."""

from __future__ import annotations

import asyncio
from typing import Any

from aiointercept import aiointercept
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
from custom_components.pollenlevels.util import (
    api_key_unique_id,
    format_location_unique_id,
)
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import async_setup_config_entry, mock_pollen_api


async def test_ha_force_update_skips_removed_captured_target_and_continues(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """force_update should revalidate captured targets before each refresh."""
    clear_integration_modules()

    locations = (
        ("location-madrid", "Madrid", 40.4168, -3.7038),
        ("location-barcelona", "Barcelona", 41.3874, 2.1686),
        ("location-valencia", "Valencia", 39.4699, -0.3763),
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="pollenlevels-entry",
        title="Pollen Levels",
        unique_id=api_key_unique_id(fake_api_key),
        data={CONF_API_KEY: fake_api_key},
        options={
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_LANGUAGE_CODE: "es",
        },
        subentries_data=[
            {
                "subentry_id": subentry_id,
                "subentry_type": SUBENTRY_TYPE_LOCATION,
                "title": title,
                "unique_id": format_location_unique_id(latitude, longitude),
                "data": {
                    CONF_LATITUDE: latitude,
                    CONF_LONGITUDE: longitude,
                },
            }
            for subentry_id, title, latitude, longitude in locations
        ],
        version=6,
    )
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

        calls: list[str] = []
        first_started = asyncio.Event()
        release_first = asyncio.Event()

        async def _refresh_madrid() -> None:
            calls.append("madrid:start")
            first_started.set()
            await release_first.wait()
            calls.append("madrid:end")

        async def _refresh_barcelona() -> None:
            calls.append("barcelona")

        async def _refresh_valencia() -> None:
            calls.append("valencia")

        monkeypatch.setattr(
            entry.runtime_data.locations["location-madrid"].coordinator,
            "async_request_refresh",
            _refresh_madrid,
        )
        monkeypatch.setattr(
            entry.runtime_data.locations["location-barcelona"].coordinator,
            "async_request_refresh",
            _refresh_barcelona,
        )
        monkeypatch.setattr(
            entry.runtime_data.locations["location-valencia"].coordinator,
            "async_request_refresh",
            _refresh_valencia,
        )

        service_task = asyncio.create_task(
            hass.services.async_call(DOMAIN, "force_update", {}, blocking=True)
        )
        try:
            await asyncio.wait_for(first_started.wait(), timeout=1)

            assert hass.config_entries.async_remove_subentry(
                entry, "location-barcelona"
            )
            assert "location-barcelona" not in entry.subentries
            assert "location-barcelona" in entry.runtime_data.locations
        finally:
            release_first.set()
            await service_task

    assert calls == ["madrid:start", "madrid:end", "valencia"]
