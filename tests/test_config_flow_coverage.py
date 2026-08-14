"""Focused coverage tests for supported config-flow helper behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from tests import test_config_flow as config_flow_tests

config_flow_stubs = config_flow_tests.config_flow_stubs_fixture

_MISSING = object()


@pytest.mark.parametrize("value", [None, 123, "   "])
def test_language_validator_rejects_invalid_input_types_and_blank_values(
    config_flow_stubs: config_flow_tests.ConfigFlowStubs,
    value: object,
) -> None:
    """Language validation should reject non-strings and blank strings."""

    with pytest.raises(config_flow_stubs.config_flow.vol.Invalid):
        config_flow_stubs.config_flow.is_valid_language_code(value)


def test_user_schema_preserves_submitted_location_default(
    config_flow_stubs: config_flow_tests.ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A redisplayed user form should preserve the submitted location."""

    module = config_flow_stubs.config_flow
    submitted_location = {
        config_flow_stubs.CONF_LATITUDE: 12.3456,
        config_flow_stubs.CONF_LONGITUDE: -65.4321,
    }
    captured_defaults: list[object] = []
    original_required = module.vol.Required

    def _capture_required(key: object, **kwargs: object) -> object:
        if key == config_flow_stubs.CONF_LOCATION:
            captured_defaults.append(kwargs.get("default", _MISSING))
        return original_required(key, **kwargs)

    monkeypatch.setattr(module.vol, "Required", _capture_required)
    hass = SimpleNamespace(
        config=SimpleNamespace(
            latitude=None,
            longitude=None,
            language="en",
            location_name="Home",
        )
    )

    module._build_step_user_schema(
        hass,
        {config_flow_stubs.CONF_LOCATION: submitted_location},
    )

    assert captured_defaults == [submitted_location]


@pytest.mark.parametrize("builder", ["user", "subentry"])
def test_location_schema_supports_missing_home_assistant_default(
    config_flow_stubs: config_flow_tests.ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
    builder: str,
) -> None:
    """Location forms should render without a Home Assistant coordinate default."""

    module = config_flow_stubs.config_flow
    captured_defaults: list[object] = []
    original_required = module.vol.Required

    def _capture_required(key: object, **kwargs: object) -> object:
        if key == config_flow_stubs.CONF_LOCATION:
            captured_defaults.append(kwargs.get("default", _MISSING))
        return original_required(key, **kwargs)

    monkeypatch.setattr(module.vol, "Required", _capture_required)
    hass = SimpleNamespace(
        config=SimpleNamespace(
            latitude=None,
            longitude=None,
            language="en",
            location_name="Home",
        )
    )

    if builder == "user":
        module._build_step_user_schema(hass, {})
    else:
        module._build_location_subentry_schema(hass, {})

    assert captured_defaults == [_MISSING]


def test_duplicate_location_scan_ignores_unrelated_subentries(
    config_flow_stubs: config_flow_tests.ConfigFlowStubs,
) -> None:
    """Duplicate detection should skip non-location subentries and keep scanning."""

    module = config_flow_stubs.config_flow
    config_subentry = module.config_entries.ConfigSubentry
    target_unique_id = "12.3456_-65.4321"
    entry = config_flow_stubs.StubConfigEntry(
        subentries={
            "unrelated": config_subentry(
                subentry_id="unrelated",
                subentry_type="other",
                unique_id=target_unique_id,
            ),
            "other-location": config_subentry(
                subentry_id="other-location",
                subentry_type="location",
                unique_id="1.0000_2.0000",
            ),
            "target-location": config_subentry(
                subentry_id="target-location",
                subentry_type="location",
                unique_id=target_unique_id,
            ),
        }
    )

    assert module._has_duplicate_location(entry, target_unique_id)


def test_legacy_coordinate_validation_recovers_after_malformed_input(
    config_flow_stubs: config_flow_tests.ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy coordinate validation should recover on corrected resubmission."""

    module = config_flow_stubs.config_flow
    calls = config_flow_tests._patch_client_fetch(config_flow_stubs, monkeypatch)
    flow = config_flow_stubs.PollenLevelsConfigFlow()
    flow.hass = SimpleNamespace()

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                config_flow_stubs.CONF_API_KEY: "synthetic-api-key",
                config_flow_stubs.CONF_LATITUDE: "north",
                config_flow_stubs.CONF_LONGITUDE: 2.0,
            }
        )
    )

    assert errors == {"base": "invalid_coordinates"}
    assert normalized is None
    assert calls == []

    errors, normalized = asyncio.run(
        flow._async_validate_input(
            {
                config_flow_stubs.CONF_API_KEY: "synthetic-api-key",
                config_flow_stubs.CONF_LATITUDE: 1.0,
                config_flow_stubs.CONF_LONGITUDE: 2.0,
            }
        )
    )

    assert errors == {}
    assert normalized is not None
    assert normalized[config_flow_stubs.CONF_LATITUDE] == 1.0
    assert normalized[config_flow_stubs.CONF_LONGITUDE] == 2.0
    assert len(calls) == 1
