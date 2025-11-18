"""Home Assistant-style tests for the Pollen Levels config flow."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pollenlevels import config_flow
from custom_components.pollenlevels.const import (
    CONF_API_KEY,
    CONF_ENTRY_NAME,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENTRY_TITLE,
    DOMAIN,
)

API_URL = "https://pollen.googleapis.com/v1/forecast:lookup"


@pytest.fixture
def flow_handler(hass):
    """Build a config flow handler with Home Assistant context."""

    hass.config.latitude = 40.0
    hass.config.longitude = -105.0
    hass.config.language = "en"
    flow = config_flow.PollenLevelsConfigFlow()
    flow.hass = hass
    flow.context = {}
    return flow


def _valid_user_input(**overrides):
    payload = {
        CONF_API_KEY: "test-key",
        CONF_ENTRY_NAME: "Backyard",
        CONF_LATITUDE: 40.0,
        CONF_LONGITUDE: -105.0,
        CONF_UPDATE_INTERVAL: 2,
        CONF_LANGUAGE_CODE: "en",
    }
    payload.update(overrides)
    return payload


def _mock_success(aioclient_mock):
    aioclient_mock.get(
        API_URL,
        json={
            "dailyInfo": [
                {
                    "date": {"year": 2025, "month": 6, "day": 1},
                    "pollenTypeInfo": [],
                }
            ]
        },
    )


@pytest.mark.asyncio
async def test_validate_input_invalid_language_key_mapping(flow_handler):
    """vol.Invalid errors use translation-friendly keys."""

    user_input = _valid_user_input(CONF_LANGUAGE_CODE="bad code")
    errors, normalized = await flow_handler._async_validate_input(
        user_input, check_unique_id=False
    )

    assert errors[CONF_LANGUAGE_CODE] == "invalid_language_format"
    assert normalized is None


@pytest.mark.asyncio
async def test_validate_input_invalid_coordinates(flow_handler):
    """Non-numeric coordinates surface the invalid_coordinates error."""

    user_input = _valid_user_input(CONF_LATITUDE="not-a-number")
    errors, normalized = await flow_handler._async_validate_input(
        user_input, check_unique_id=False
    )

    assert errors["base"] == "invalid_coordinates"
    assert normalized is None


@pytest.mark.asyncio
async def test_validate_input_out_of_range_coordinates(flow_handler):
    """Coordinates outside Earth bounds surface invalid_coordinates."""

    user_input = _valid_user_input(CONF_LATITUDE=200)
    errors, normalized = await flow_handler._async_validate_input(
        user_input, check_unique_id=False
    )

    assert errors["base"] == "invalid_coordinates"
    assert normalized is None


@pytest.mark.asyncio
async def test_reauth_confirm_updates_and_reloads_entry(hass, aioclient_mock):
    """Reauthentication updates the entry data and reloads the integration."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_KEY: "old",
            CONF_LATITUDE: 40.0,
            CONF_LONGITUDE: -105.0,
            CONF_UPDATE_INTERVAL: 2,
        },
        entry_id="reauth-entry",
    )
    entry.add_to_hass(hass)

    flow = config_flow.PollenLevelsConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}

    result = await flow.async_step_reauth(entry.data)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    _mock_success(aioclient_mock)

    reload_mock = AsyncMock()
    with (
        patch.object(hass.config_entries, "async_reload", reload_mock),
        patch.object(hass.config_entries, "async_update_entry") as update_mock,
    ):
        confirm = await flow.async_step_reauth_confirm({CONF_API_KEY: "new"})

    assert confirm["type"] == FlowResultType.ABORT
    assert confirm["reason"] == "reauth_successful"
    update_mock.assert_called_once()
    reload_mock.assert_awaited_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_async_step_user_uses_custom_entry_name(flow_handler, aioclient_mock):
    """Users can persist a friendly title alongside unique coordinates."""

    _mock_success(aioclient_mock)
    result = await flow_handler.async_step_user(user_input=_valid_user_input())

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Backyard"


@pytest.mark.asyncio
async def test_async_step_user_defaults_entry_name(flow_handler, aioclient_mock):
    """Blank entry names fall back to the default title for legacy parity."""

    _mock_success(aioclient_mock)
    payload = _valid_user_input(CONF_ENTRY_NAME="")
    result = await flow_handler.async_step_user(user_input=payload)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == DEFAULT_ENTRY_TITLE


def test_translations_define_required_error_keys():
    """Every translation file exposes the new validation errors and labels."""

    translations = Path("custom_components/pollenlevels/translations")
    required_paths = [
        ("config", "error", "invalid_coordinates"),
        ("config", "step", "reauth_confirm", "title"),
        ("config", "step", "reauth_confirm", "description"),
        ("config", "step", "user", "data", "entry_name"),
    ]

    for path in translations.glob("*.json"):
        content = json.loads(path.read_text())
        for req in required_paths:
            node = content
            for key in req:
                assert key in node, f"Missing {'.'.join(req)} in {path.name}"
                node = node[key]
