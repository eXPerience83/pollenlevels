"""Tests for coordinator config-entry ownership."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.pollenlevels.coordinator import PollenDataUpdateCoordinator


class _StubClient:
    """Minimal client placeholder for coordinator construction."""


def test_coordinator_keeps_explicit_config_entry(
    hass: HomeAssistant,
    ha_config_entry: ConfigEntry,
) -> None:
    """The coordinator should retain the parent config entry passed by setup."""
    coordinator = PollenDataUpdateCoordinator(
        hass=hass,
        api_key="dummy",
        lat=0.0,
        lon=0.0,
        hours=12,
        language="en",
        entry_id=ha_config_entry.entry_id,
        client=_StubClient(),
        config_entry=ha_config_entry,
    )

    assert coordinator.config_entry is ha_config_entry
