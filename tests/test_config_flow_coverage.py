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


@pytest.mark.parametrize(
    ("builder", "submitted", "stored", "home_coords", "expected"),
    [
        ("user", None, None, (12.5, -1.5), {"latitude": 12.5, "longitude": -1.5}),
        ("subentry", None, None, (12.5, -1.5), {"latitude": 12.5, "longitude": -1.5}),
        (
            "subentry",
            None,
            {"latitude": 4.0, "longitude": 5.0},
            (12.5, -1.5),
            {"latitude": 4.0, "longitude": 5.0},
        ),
        (
            "subentry",
            {"latitude": 1.0, "longitude": 2.0},
            {"latitude": 4.0, "longitude": 5.0},
            (12.5, -1.5),
            {"latitude": 1.0, "longitude": 2.0},
        ),
        ("subentry", {}, {"latitude": 4.0, "longitude": 5.0}, (12.5, -1.5), {}),
        ("user", None, None, (12.5, None), _MISSING),
        ("user", None, None, (None, -1.5), _MISSING),
    ],
)
def test_location_schema_preserves_default_priority(
    config_flow_stubs: config_flow_tests.ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
    builder: str,
    submitted: dict[str, float] | None,
    stored: dict[str, float] | None,
    home_coords: tuple[float | None, float | None],
    expected: object,
) -> None:
    """Preserve submitted, stored, then HA defaults in both location forms."""
    module = config_flow_stubs.config_flow
    capture: list[object] = []
    original_required = module.vol.Required

    def _capture_required(key: object, **kwargs: object) -> object:
        if key == config_flow_stubs.CONF_LOCATION:
            capture.append(kwargs.get("default", _MISSING))
        return original_required(key, **kwargs)

    monkeypatch.setattr(module.vol, "Required", _capture_required)
    hass = SimpleNamespace(
        config=SimpleNamespace(
            latitude=home_coords[0],
            longitude=home_coords[1],
            language="en",
            location_name="Home",
        )
    )
    input_values = (
        {config_flow_stubs.CONF_LOCATION: submitted} if submitted is not None else {}
    )
    if builder == "user":
        schema = module._build_step_user_schema(hass, input_values)
    else:
        schema = module._build_location_subentry_schema(
            hass, input_values, location_default=stored
        )

    assert capture == [expected]
    selector = schema.schema[config_flow_stubs.CONF_LOCATION]
    assert selector.config.radius is False


def test_shared_interval_selector_keeps_hours_contract(
    config_flow_stubs: config_flow_tests.ConfigFlowStubs,
) -> None:
    """Setup and options selectors use the same hours bounds and box mode."""
    module = config_flow_stubs.config_flow
    selector = module._update_interval_selector()
    assert isinstance(selector, module.NumberSelector)
    assert selector.config.min == module.MIN_UPDATE_INTERVAL_HOURS
    assert selector.config.max == module.MAX_UPDATE_INTERVAL_HOURS
    assert selector.config.step == 1
    assert selector.config.mode == module.NumberSelectorMode.BOX
    assert selector.config.unit_of_measurement == "h"


@pytest.mark.parametrize(
    ("current_subentry_id", "expected_valid"),
    [
        (None, False),
        ("another-location", False),
        ("location-1", True),
    ],
)
def test_location_validation_preserves_current_subentry_duplicate_exemption(
    config_flow_stubs: config_flow_tests.ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
    current_subentry_id: str | None,
    expected_valid: bool,
) -> None:
    """Only reconfigure may reuse its own coordinate identity."""
    module = config_flow_stubs.config_flow
    existing = module.config_entries.ConfigSubentry(
        subentry_id="location-1",
        unique_id="1.0000_2.0000",
        data={
            config_flow_stubs.CONF_LATITUDE: 1.0,
            config_flow_stubs.CONF_LONGITUDE: 2.0,
        },
    )
    entry = config_flow_stubs.StubConfigEntry(
        data={config_flow_stubs.CONF_API_KEY: "key"},
        subentries={existing.subentry_id: existing},
    )
    calls: list[tuple[float, float]] = []

    async def _accept_location(_hass, **kwargs):
        calls.append((kwargs["latitude"], kwargs["longitude"]))
        return True

    monkeypatch.setattr(module, "_async_validate_api_location", _accept_location)
    errors: dict[str, str] = {}
    placeholders: dict[str, str] = {}
    result = asyncio.run(
        module._async_validate_subentry_location(
            SimpleNamespace(),
            entry,
            {
                config_flow_stubs.CONF_NAME: " Location ",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: 1.0,
                    config_flow_stubs.CONF_LONGITUDE: 2.0,
                },
            },
            errors,
            placeholders,
            current_subentry_id=current_subentry_id,
        )
    )

    if expected_valid:
        assert result == ("Location", 1.0, 2.0, "1.0000_2.0000")
        assert errors == {}
        assert calls == [(1.0, 2.0)]
    else:
        assert result is None
        assert errors == {"base": "already_configured"}
        assert calls == []
    assert placeholders == {}


def test_duplicate_location_scan_ignores_matching_unrelated_subentry(
    config_flow_stubs: config_flow_tests.ConfigFlowStubs,
) -> None:
    """A matching non-location subentry should not be treated as a duplicate."""

    module = config_flow_stubs.config_flow
    config_subentry = module.config_entries.ConfigSubentry
    target_unique_id = "12.3456_-65.4321"
    entry = config_flow_stubs.StubConfigEntry(
        subentries={
            "unrelated": config_subentry(
                subentry_id="unrelated",
                subentry_type="other",
                unique_id=target_unique_id,
            )
        }
    )

    assert not module._has_duplicate_location(entry, target_unique_id)


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
    assert calls[0]["latitude"] == 1.0
    assert calls[0]["longitude"] == 2.0


def test_location_reconfigure_step_recovers_after_invalid_coordinates(
    config_flow_stubs: config_flow_tests.ConfigFlowStubs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defensive reconfigure branch should accept corrected direct input."""

    module = config_flow_stubs.config_flow
    config_subentry = module.config_entries.ConfigSubentry
    subentry = config_subentry(
        subentry_id="location-madrid",
        subentry_type="location",
        title="Madrid",
        unique_id="40.4168_-3.7038",
        data={
            config_flow_stubs.CONF_LATITUDE: 40.4168,
            config_flow_stubs.CONF_LONGITUDE: -3.7038,
        },
    )
    entry = config_flow_stubs.StubConfigEntry(
        data={config_flow_stubs.CONF_API_KEY: "synthetic-api-key"},
        subentries={subentry.subentry_id: subentry},
    )
    scheduled_reloads: list[str] = []
    calls = config_flow_tests._patch_client_fetch(config_flow_stubs, monkeypatch)
    flow = module.PollenLevelsLocationSubentryFlow()
    flow.hass = SimpleNamespace(
        config=SimpleNamespace(
            latitude=40.4168,
            longitude=-3.7038,
            language="en",
            location_name="Home",
        ),
        config_entries=SimpleNamespace(async_schedule_reload=scheduled_reloads.append),
    )
    flow._get_entry = lambda: entry  # type: ignore[method-assign]
    flow._get_reconfigure_subentry = lambda: subentry  # type: ignore[method-assign]

    result = asyncio.run(
        flow.async_step_reconfigure(
            {
                config_flow_stubs.CONF_NAME: "Broken",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: "north",
                    config_flow_stubs.CONF_LONGITUDE: 2.1686,
                },
            }
        )
    )

    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {config_flow_stubs.CONF_LOCATION: "invalid_coordinates"}
    assert calls == []
    assert scheduled_reloads == []

    result = asyncio.run(
        flow.async_step_reconfigure(
            {
                config_flow_stubs.CONF_NAME: "Barcelona",
                config_flow_stubs.CONF_LOCATION: {
                    config_flow_stubs.CONF_LATITUDE: 41.3874,
                    config_flow_stubs.CONF_LONGITUDE: 2.1686,
                },
            }
        )
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert subentry.title == "Barcelona"
    assert subentry.unique_id == "41.3874_2.1686"
    assert subentry.data == {
        config_flow_stubs.CONF_LATITUDE: 41.3874,
        config_flow_stubs.CONF_LONGITUDE: 2.1686,
    }
    assert scheduled_reloads == [entry.entry_id]
    assert len(calls) == 1
    assert calls[0]["latitude"] == 41.3874
    assert calls[0]["longitude"] == 2.1686
