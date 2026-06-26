"""Home Assistant harness tests for Pollen Levels services."""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from aiointercept import aiointercept
from homeassistant.core import HomeAssistant

from custom_components.pollenlevels.const import (
    CONF_API_KEY,
    CONF_LANGUAGE_CODE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.pollenlevels.util import api_key_unique_id
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import (
    async_setup_config_entry,
    location_subentry_data,
    mock_pollen_api,
)


async def test_ha_force_update_refreshes_active_locations_and_skips_stale(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    ha_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """force_update should refresh active subentries and skip stale runtimes."""
    clear_integration_modules()
    ha_config_entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)

        await async_setup_config_entry(hass, ha_config_entry)

        active = ha_config_entry.runtime_data.locations["location-madrid"]
        active_refresh = AsyncMock()
        monkeypatch.setattr(active.coordinator, "async_request_refresh", active_refresh)

        stale_refresh = AsyncMock()
        ha_config_entry.runtime_data.locations["deleted-location"] = SimpleNamespace(
            subentry_id="deleted-location",
            coordinator=SimpleNamespace(async_request_refresh=stale_refresh),
        )

        await hass.services.async_call(DOMAIN, "force_update", {}, blocking=True)
        await hass.async_block_till_done()

    active_refresh.assert_awaited_once()
    stale_refresh.assert_not_awaited()


async def test_ha_force_update_skips_removed_subentry_without_reload(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    sample_location_subentry_data: dict[str, Any],
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """force_update should skip a removed subentry before runtime reloads."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    clear_integration_modules()
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="pollenlevels-entry",
        title="Pollen Levels",
        data={CONF_API_KEY: fake_api_key},
        options={
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_LANGUAGE_CODE: "es",
        },
        unique_id=api_key_unique_id(fake_api_key),
        subentries_data=[
            sample_location_subentry_data,
            location_subentry_data(
                subentry_id="location-barcelona",
                title="Barcelona",
                latitude=41.3874,
                longitude=2.1686,
            ),
        ],
        version=6,
    )
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

        assert set(entry.subentries) == {"location-madrid", "location-barcelona"}
        assert set(entry.runtime_data.locations) == {
            "location-madrid",
            "location-barcelona",
        }

        active_refresh = AsyncMock()
        removed_refresh = AsyncMock()
        monkeypatch.setattr(
            entry.runtime_data.locations["location-madrid"].coordinator,
            "async_request_refresh",
            active_refresh,
        )
        monkeypatch.setattr(
            entry.runtime_data.locations["location-barcelona"].coordinator,
            "async_request_refresh",
            removed_refresh,
        )

        entry.subentries = MappingProxyType(
            {
                subentry_id: subentry
                for subentry_id, subentry in entry.subentries.items()
                if subentry_id != "location-barcelona"
            }
        )
        assert "location-barcelona" in entry.runtime_data.locations
        assert "location-barcelona" not in entry.subentries

        await hass.services.async_call(DOMAIN, "force_update", {}, blocking=True)
        await hass.async_block_till_done()

    active_refresh.assert_awaited_once()
    removed_refresh.assert_not_awaited()


async def test_ha_force_update_refreshes_multiple_location_subentries(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    sample_location_subentry_data: dict[str, Any],
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """force_update should refresh every active location subentry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    clear_integration_modules()
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="pollenlevels-entry",
        title="Pollen Levels",
        data={CONF_API_KEY: fake_api_key},
        options={
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_LANGUAGE_CODE: "es",
        },
        unique_id=api_key_unique_id(fake_api_key),
        subentries_data=[
            sample_location_subentry_data,
            location_subentry_data(
                subentry_id="location-barcelona",
                title="Barcelona",
                latitude=41.3874,
                longitude=2.1686,
            ),
        ],
        version=6,
    )
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

        refreshes = {
            subentry_id: AsyncMock()
            for subentry_id in ("location-madrid", "location-barcelona")
        }
        for subentry_id, refresh in refreshes.items():
            monkeypatch.setattr(
                entry.runtime_data.locations[subentry_id].coordinator,
                "async_request_refresh",
                refresh,
            )

        await hass.services.async_call(DOMAIN, "force_update", {}, blocking=True)
        await hass.async_block_till_done()

    for refresh in refreshes.values():
        refresh.assert_awaited_once()


async def test_ha_force_update_continues_after_one_location_failure(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    sample_location_subentry_data: dict[str, Any],
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """force_update should continue refreshing locations after one failure."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    clear_integration_modules()
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="pollenlevels-entry",
        title="Pollen Levels",
        data={CONF_API_KEY: fake_api_key},
        options={
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_LANGUAGE_CODE: "es",
        },
        unique_id=api_key_unique_id(fake_api_key),
        subentries_data=[
            sample_location_subentry_data,
            location_subentry_data(
                subentry_id="location-barcelona",
                title="Barcelona",
                latitude=41.3874,
                longitude=2.1686,
            ),
        ],
        version=6,
    )
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

        failing_refresh = AsyncMock(side_effect=RuntimeError("boom"))
        ok_refresh = AsyncMock()
        monkeypatch.setattr(
            entry.runtime_data.locations["location-madrid"].coordinator,
            "async_request_refresh",
            failing_refresh,
        )
        monkeypatch.setattr(
            entry.runtime_data.locations["location-barcelona"].coordinator,
            "async_request_refresh",
            ok_refresh,
        )

        await hass.services.async_call(DOMAIN, "force_update", {}, blocking=True)
        await hass.async_block_till_done()

    failing_refresh.assert_awaited_once()
    ok_refresh.assert_awaited_once()


async def test_ha_force_update_parent_without_locations_is_noop(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    fake_api_key: str,
) -> None:
    """force_update should be a safe no-op when a parent has no locations."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    clear_integration_modules()
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="pollenlevels-empty-entry",
        title="Pollen Levels",
        data={CONF_API_KEY: fake_api_key},
        options={
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_LANGUAGE_CODE: "es",
        },
        unique_id=api_key_unique_id(fake_api_key),
        subentries_data=[],
        version=6,
    )
    entry.add_to_hass(hass)

    await async_setup_config_entry(hass, entry)
    assert entry.runtime_data.locations == {}
    assert entry.runtime_data.coordinator is None

    await hass.services.async_call(DOMAIN, "force_update", {}, blocking=True)
    await hass.async_block_till_done()
