"""Home Assistant harness coverage for config-flow recovery behavior."""

from __future__ import annotations

from typing import Any

import pytest
from aiointercept import aiointercept
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_LOCATION, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

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
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import mock_pollen_api


def _location_input(
    *,
    name: str = "Madrid",
    latitude: float | str = 40.4168,
    longitude: float | str = -3.7038,
) -> dict[str, Any]:
    """Return one location-selector submission."""

    return {
        CONF_NAME: name,
        CONF_LOCATION: {
            CONF_LATITUDE: latitude,
            CONF_LONGITUDE: longitude,
        },
    }


async def _start_parent_api_key_flow(entry: Any, hass: HomeAssistant, source: str):
    """Start a parent API-key flow through Home Assistant."""

    if source == SOURCE_REAUTH:
        return await entry.start_reauth_flow(hass)
    if source == SOURCE_RECONFIGURE:
        return await entry.start_reconfigure_flow(hass)
    raise AssertionError(f"Unsupported source: {source}")


async def test_ha_user_flow_recovers_after_invalid_language(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """User setup should remain usable after a validation error."""

    clear_integration_modules()
    user_input = {
        CONF_API_KEY: fake_api_key,
        CONF_LANGUAGE_CODE: "bad code",
        CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
        **_location_input(),
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {CONF_LANGUAGE_CODE: "invalid_language_format"}

    corrected_input = {**user_input, CONF_LANGUAGE_CODE: "es"}
    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], corrected_input
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data == {CONF_API_KEY: fake_api_key}
    assert entry.options[CONF_LANGUAGE_CODE] == "es"
    assert len(entry.subentries) == 1


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        (SOURCE_REAUTH, "reauth_successful"),
        (SOURCE_RECONFIGURE, "reconfigure_successful"),
    ],
)
async def test_ha_parent_api_key_flow_tries_next_location_after_invalid_coordinates(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    google_pollen_5_day_payload: dict[str, Any],
    source: str,
    reason: str,
) -> None:
    """Parent key validation should skip a corrupt location and try the next one."""

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    clear_integration_modules()
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=f"parent-{source}",
        title="Pollen Levels",
        data={CONF_API_KEY: "old-key"},
        unique_id=api_key_unique_id("old-key"),
        subentries_data=[
            {
                "subentry_id": "location-corrupt",
                "subentry_type": SUBENTRY_TYPE_LOCATION,
                "title": "Corrupt",
                "unique_id": "corrupt-location",
                "data": {
                    CONF_LATITUDE: "north",
                    CONF_LONGITUDE: -3.7038,
                },
            },
            {
                "subentry_id": "location-valid",
                "subentry_type": SUBENTRY_TYPE_LOCATION,
                "title": "Valid",
                "unique_id": "41.3874_2.1686",
                "data": {
                    CONF_LATITUDE: 41.3874,
                    CONF_LONGITUDE: 2.1686,
                },
            },
        ],
        version=6,
    )
    entry.add_to_hass(hass)

    result = await _start_parent_api_key_flow(entry, hass, source)
    assert result["type"] is FlowResultType.FORM

    new_api_key = f"{fake_api_key}-{source}"
    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: new_api_key}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason
    assert entry.data == {CONF_API_KEY: new_api_key}
    assert entry.unique_id == api_key_unique_id(new_api_key)


@pytest.mark.parametrize(
    "stored_data",
    [
        pytest.param({}, id="missing-key"),
        pytest.param({CONF_API_KEY: 123}, id="non-string-key"),
    ],
)
async def test_ha_location_subentry_user_recovers_after_invalid_parent_api_key(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    google_pollen_5_day_payload: dict[str, Any],
    stored_data: dict[str, Any],
) -> None:
    """Location creation should recover after the parent API key is repaired."""

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    clear_integration_modules()
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="parent-location-create",
        title="Pollen Levels",
        data=stored_data,
        version=6,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_LOCATION),
        context={"source": SOURCE_USER},
    )
    user_input = _location_input(name="Garden", latitude=41.3874, longitude=2.1686)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert result["description_placeholders"] == {"error_message": "Invalid API key."}

    hass.config_entries.async_update_entry(
        entry,
        data={CONF_API_KEY: fake_api_key},
        unique_id=api_key_unique_id(fake_api_key),
    )
    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], user_input
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(entry.subentries) == 1


async def test_ha_location_subentry_reconfigure_recovers_after_invalid_parent_key(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    sample_location_subentry_data: dict[str, Any],
    google_pollen_5_day_payload: dict[str, Any],
) -> None:
    """Location reconfigure should recover after the parent key is repaired."""

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    clear_integration_modules()
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="parent-location-reconfigure",
        title="Pollen Levels",
        data={},
        subentries_data=[sample_location_subentry_data],
        version=6,
    )
    entry.add_to_hass(hass)
    subentry = entry.subentries["location-madrid"]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_LOCATION),
        context={
            "source": SOURCE_RECONFIGURE,
            "subentry_id": subentry.subentry_id,
        },
    )
    user_input = _location_input(
        name="Barcelona",
        latitude=41.3874,
        longitude=2.1686,
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert result["description_placeholders"] == {"error_message": "Invalid API key."}

    hass.config_entries.async_update_entry(
        entry,
        data={CONF_API_KEY: fake_api_key},
        unique_id=api_key_unique_id(fake_api_key),
    )
    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], user_input
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries["location-madrid"].title == "Barcelona"
