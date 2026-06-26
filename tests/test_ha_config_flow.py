"""Home Assistant harness tests for config and subentry flows."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest
from aiointercept import aiointercept
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_LOCATION, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.pollenlevels.const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LEGACY_ENTRY_ID,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SUBENTRY_TYPE_LOCATION,
)
from custom_components.pollenlevels.util import api_key_unique_id
from tests._ha_stubs import clear_integration_modules
from tests.ha_helpers import (
    assert_fixed_forecast_days,
    async_setup_config_entry,
    mock_pollen_api,
)


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


async def _start_parent_api_key_flow(entry, hass: HomeAssistant, source: str):
    """Start a parent API-key flow through the real Home Assistant manager."""
    if source == SOURCE_REAUTH:
        return await entry.start_reauth_flow(hass)
    if source == SOURCE_RECONFIGURE:
        return await entry.start_reconfigure_flow(hass)
    raise AssertionError(f"Unsupported source: {source}")


def _parent_entry_snapshot(entry) -> dict[str, Any]:
    """Return persisted parent state relevant to API-key flow compatibility."""
    return {
        "entry_id": entry.entry_id,
        "data": dict(entry.data),
        "unique_id": entry.unique_id,
        "options": dict(entry.options),
        "subentries": {
            subentry_id: {
                "title": subentry.title,
                "unique_id": subentry.unique_id,
                "data": dict(subentry.data),
            }
            for subentry_id, subentry in entry.subentries.items()
        },
    }


async def test_ha_user_flow_creates_parent_entry_with_location_subentry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
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

    async with aiointercept(mock_external_urls=True) as mocked:
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
    socket_enabled: None,
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

    async with aiointercept(mock_external_urls=True) as mocked:
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
    monkeypatch,
) -> None:
    """Options flow should persist supported options and schedule a reload."""
    clear_integration_modules()
    ha_config_entry.add_to_hass(hass)
    scheduled_reloads: list[str] = []

    def _capture_schedule_reload(entry_id: str) -> None:
        scheduled_reloads.append(entry_id)

    monkeypatch.setattr(
        hass.config_entries, "async_schedule_reload", _capture_schedule_reload
    )
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
    assert scheduled_reloads == [ha_config_entry.entry_id]


@pytest.mark.parametrize(
    ("source", "step_id", "reason"),
    [
        (SOURCE_REAUTH, "reauth_confirm", "reauth_successful"),
        (SOURCE_RECONFIGURE, "reconfigure", "reconfigure_successful"),
    ],
)
@pytest.mark.parametrize(
    "legacy_entry_id",
    [
        pytest.param(None, id="clean-v3"),
        pytest.param("legacy-location-entry", id="migrated-v2"),
    ],
)
async def test_ha_parent_api_key_flow_updates_entry_and_schedules_reload(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    fake_api_key: str,
    sample_location_subentry_data: dict[str, Any],
    google_pollen_5_day_payload: dict[str, Any],
    monkeypatch,
    source: str,
    step_id: str,
    reason: str,
    legacy_entry_id: str | None,
) -> None:
    """Parent API-key changes must preserve location registry identities."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    clear_integration_modules()
    location_subentry_data = {
        **sample_location_subentry_data,
        "data": {
            **sample_location_subentry_data["data"],
            **(
                {CONF_LEGACY_ENTRY_ID: legacy_entry_id}
                if legacy_entry_id is not None
                else {}
            ),
        },
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=f"parent-{source}",
        title="Pollen Levels",
        data={CONF_API_KEY: "old-key"},
        options={
            CONF_LANGUAGE_CODE: "es",
            CONF_UPDATE_INTERVAL: 8,
            CONF_FORECAST_DAYS: 1,
            CONF_CREATE_FORECAST_SENSORS: "D+1",
        },
        unique_id=api_key_unique_id("old-key"),
        subentries_data=[location_subentry_data],
        version=6,
    )
    entry.add_to_hass(hass)

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

    entry_id_before = entry.entry_id
    options_before = dict(entry.options)
    subentry_before = next(iter(entry.subentries.values()))
    subentry_id_before = subentry_before.subentry_id
    subentry_data_before = dict(subentry_before.data)

    def _registry_identity_snapshot() -> dict[str, Any]:
        entity_entries = [
            entity
            for entity in er.async_entries_for_config_entry(
                er.async_get(hass), entry.entry_id
            )
            if entity.platform == DOMAIN
        ]
        device_entries = dr.async_entries_for_config_entry(
            dr.async_get(hass), entry.entry_id
        )
        return {
            "sensor_entities": {
                (
                    entity.entity_id,
                    entity.unique_id,
                    getattr(entity, "config_subentry_id", None),
                )
                for entity in entity_entries
                if entity.domain == "sensor"
            },
            "button_entities": {
                (
                    entity.entity_id,
                    entity.unique_id,
                    getattr(entity, "config_subentry_id", None),
                )
                for entity in entity_entries
                if entity.domain == "button"
            },
            "device_identifiers": {
                device.id: frozenset(device.identifiers) for device in device_entries
            },
            "device_subentries": {
                device.id: {
                    config_entry_id: frozenset(subentry_ids)
                    for config_entry_id, subentry_ids in getattr(
                        device, "config_entries_subentries", {}
                    ).items()
                }
                for device in device_entries
            },
        }

    identities_before = _registry_identity_snapshot()
    assert identities_before["sensor_entities"]
    assert len(identities_before["button_entities"]) == 1
    assert identities_before["device_identifiers"]

    scheduled_reloads: list[str] = []

    def _capture_schedule_reload(entry_id: str) -> None:
        scheduled_reloads.append(entry_id)

    monkeypatch.setattr(
        hass.config_entries, "async_schedule_reload", _capture_schedule_reload
    )

    result = await _start_parent_api_key_flow(entry, hass, source)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == step_id

    new_api_key = f"{fake_api_key}-{source}"
    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: new_api_key},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason
    assert entry.data == {CONF_API_KEY: new_api_key}
    assert entry.unique_id == api_key_unique_id(new_api_key)
    assert entry.entry_id == entry_id_before
    subentry_after_update = entry.subentries[subentry_id_before]
    assert subentry_after_update.subentry_id == subentry_id_before
    assert dict(subentry_after_update.data) == subentry_data_before
    assert dict(entry.options) == options_before
    assert scheduled_reloads == [entry.entry_id]

    assert await hass.config_entries.async_unload(entry.entry_id)
    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        await async_setup_config_entry(hass, entry)

    assert _registry_identity_snapshot() == identities_before


@pytest.mark.parametrize(
    ("source", "step_id"),
    [
        (SOURCE_REAUTH, "reauth_confirm"),
        (SOURCE_RECONFIGURE, "reconfigure"),
    ],
)
async def test_ha_parent_api_key_flow_rejects_duplicate_parent_unique_id(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
    sample_location_subentry_data: dict[str, Any],
    google_pollen_5_day_payload: dict[str, Any],
    source: str,
    step_id: str,
) -> None:
    """Parent reauth/reconfigure should reject another parent's API key."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    clear_integration_modules()
    duplicate = MockConfigEntry(
        domain=DOMAIN,
        entry_id="duplicate-parent",
        title="Duplicate Parent",
        data={CONF_API_KEY: "taken-key"},
        unique_id=api_key_unique_id("taken-key"),
        version=6,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=f"parent-{source}",
        title="Pollen Levels",
        data={CONF_API_KEY: "old-key"},
        unique_id=api_key_unique_id("old-key"),
        subentries_data=[sample_location_subentry_data],
        version=6,
    )
    duplicate.add_to_hass(hass)
    entry.add_to_hass(hass)
    duplicate_before = _parent_entry_snapshot(duplicate)
    entry_before = _parent_entry_snapshot(entry)

    result = await _start_parent_api_key_flow(entry, hass, source)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == step_id

    async with aiointercept(mock_external_urls=True) as mocked:
        mock_pollen_api(mocked, google_pollen_5_day_payload)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "taken-key"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == step_id
    assert result["errors"] == {"base": "api_key_already_configured"}
    assert _parent_entry_snapshot(entry) == entry_before
    assert _parent_entry_snapshot(duplicate) == duplicate_before


async def test_ha_location_subentry_flow_creates_subentry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    socket_enabled: None,
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

    async with aiointercept(mock_external_urls=True) as mocked:
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
    socket_enabled: None,
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

    async with aiointercept(mock_external_urls=True) as mocked:
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
