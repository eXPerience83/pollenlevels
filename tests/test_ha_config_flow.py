"""Home Assistant harness tests for config and subentry flows."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from aioresponses import aioresponses
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_LOCATION, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pollenlevels.const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SUBENTRY_TYPE_LOCATION,
)
from custom_components.pollenlevels.util import api_key_unique_id
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import assert_fixed_forecast_days, mock_pollen_api


def _location_input(
    *,
    name: str = "Madrid",
    latitude: float = 40.4168,
    longitude: float = -3.7038,
) -> dict[str, Any]:
    """Return user input for a location selector."""
    return {
        CONF_NAME: name,
        CONF_LOCATION: {
            CONF_LATITUDE: latitude,
            CONF_LONGITUDE: longitude,
        },
    }


async def test_ha_user_flow_creates_parent_entry_with_location_subentry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    fake_api_key: str,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """User flow should create a parent entry with the first location subentry."""
    clear_integration_modules()
    captured_params: list[dict[str, Any]] = []

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with aioresponses() as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload, captured_params)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: f" {fake_api_key} ",
                CONF_LANGUAGE_CODE: " es ",
                CONF_UPDATE_INTERVAL: 8,
                **_location_input(name=" Casa "),
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert_fixed_forecast_days(captured_params)

    entry = result["result"]
    assert entry.domain == DOMAIN
    assert entry.title == "Casa"
    assert entry.unique_id == api_key_unique_id(fake_api_key)
    assert entry.data == {CONF_API_KEY: fake_api_key}
    assert entry.options == {
        CONF_LANGUAGE_CODE: "es",
        CONF_UPDATE_INTERVAL: 8,
    }

    assert len(entry.subentries) == 1
    subentry = next(iter(entry.subentries.values()))
    assert subentry.subentry_type == SUBENTRY_TYPE_LOCATION
    assert subentry.title == "Casa"
    assert subentry.unique_id == "40.4168_-3.7038"
    assert dict(subentry.data) == {
        CONF_LATITUDE: 40.4168,
        CONF_LONGITUDE: -3.7038,
    }


async def test_ha_user_flow_rejects_duplicate_parent_api_key(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    fake_api_key: str,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """User flow should reject another parent with the same API-key identity."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    clear_integration_modules()
    MockConfigEntry(
        domain=DOMAIN,
        title="Existing",
        data={CONF_API_KEY: fake_api_key},
        unique_id=api_key_unique_id(fake_api_key),
        version=6,
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with aioresponses() as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: fake_api_key,
                CONF_LANGUAGE_CODE: "en",
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                **_location_input(),
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "api_key_already_configured"


async def test_ha_options_flow_saves_supported_options_only(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    ha_config_entry,
) -> None:
    """Options flow should persist supported options and drop legacy keys."""
    clear_integration_modules()
    ha_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        ha_config_entry,
        options={
            CONF_LANGUAGE_CODE: "es",
            CONF_UPDATE_INTERVAL: 8,
            CONF_FORECAST_DAYS: 1,
            CONF_CREATE_FORECAST_SENSORS: "D+1",
        },
    )

    result = await hass.config_entries.options.async_init(ha_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_LANGUAGE_CODE: " en ",
            CONF_UPDATE_INTERVAL: 12,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert ha_config_entry.options == {
        CONF_LANGUAGE_CODE: "en",
        CONF_UPDATE_INTERVAL: 12,
    }


async def test_ha_location_subentry_flow_creates_subentry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    fake_api_key: str,
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """Location subentry flow should persist a new location on the parent entry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    clear_integration_modules()
    captured_params: list[dict[str, Any]] = []
    scheduled_reloads: list[str] = []
    original_schedule_reload = hass.config_entries.async_schedule_reload

    def _capture_schedule_reload(entry_id: str) -> None:
        scheduled_reloads.append(entry_id)
        original_schedule_reload(entry_id)

    monkeypatch.setattr(
        hass.config_entries, "async_schedule_reload", _capture_schedule_reload
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="parent-entry",
        title="Pollen Levels",
        data={CONF_API_KEY: fake_api_key},
        options={CONF_LANGUAGE_CODE: "es"},
        unique_id=api_key_unique_id(fake_api_key),
        version=6,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_LOCATION),
        context={"source": SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with aioresponses() as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload, captured_params)
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            _location_input(name="Garden", latitude=41.3874, longitude=2.1686),
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert_fixed_forecast_days(captured_params)
    assert captured_params[0]["languageCode"] == "es"
    assert scheduled_reloads == [entry.entry_id]
    assert len(entry.subentries) == 1

    subentry = next(iter(entry.subentries.values()))
    assert subentry.subentry_type == SUBENTRY_TYPE_LOCATION
    assert subentry.title == "Garden"
    assert subentry.unique_id == "41.3874_2.1686"
    assert dict(subentry.data) == {
        CONF_LATITUDE: 41.3874,
        CONF_LONGITUDE: 2.1686,
    }


async def test_ha_location_subentry_flow_rejects_duplicate_location(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    ha_config_entry,
) -> None:
    """Location subentry flow should reject duplicate coordinate identities."""
    clear_integration_modules()
    ha_config_entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (ha_config_entry.entry_id, SUBENTRY_TYPE_LOCATION),
        context={"source": SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        _location_input(name="Duplicate"),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "already_configured"}
    assert len(ha_config_entry.subentries) == 1


async def test_ha_location_subentry_reconfigure_updates_entry_and_schedules_reload(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    ha_config_entry,
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
) -> None:
    """Location subentry reconfigure should update stored data and schedule reload."""
    clear_integration_modules()
    captured_params: list[dict[str, Any]] = []
    ha_config_entry.add_to_hass(hass)
    subentry = ha_config_entry.subentries["location-madrid"]
    scheduled_reloads: list[str] = []
    original_schedule_reload = hass.config_entries.async_schedule_reload

    def _capture_schedule_reload(entry_id: str) -> None:
        scheduled_reloads.append(entry_id)
        original_schedule_reload(entry_id)

    monkeypatch.setattr(
        hass.config_entries, "async_schedule_reload", _capture_schedule_reload
    )

    result = await hass.config_entries.subentries.async_init(
        (ha_config_entry.entry_id, SUBENTRY_TYPE_LOCATION),
        context={
            "source": SOURCE_RECONFIGURE,
            "subentry_id": subentry.subentry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    with aioresponses() as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload, captured_params)
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            _location_input(name="Barcelona", latitude=41.3874, longitude=2.1686),
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert_fixed_forecast_days(captured_params)

    updated = ha_config_entry.subentries["location-madrid"]
    assert updated.title == "Barcelona"
    assert updated.unique_id == "41.3874_2.1686"
    assert updated.data == MappingProxyType(
        {
            CONF_LATITUDE: 41.3874,
            CONF_LONGITUDE: 2.1686,
        }
    )
    assert scheduled_reloads == [ha_config_entry.entry_id]
