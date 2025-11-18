"""Setup-related tests that rely on Home Assistant's helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pollenlevels import __init__ as integration
from custom_components.pollenlevels.const import DOMAIN


@pytest.mark.asyncio
async def test_setup_entry_propagates_auth_failed(hass):
    """Auth errors from platform forwarding must bubble up for reauth."""

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass.config_entries.async_forward_entry_setups = AsyncMock(
        side_effect=ConfigEntryAuthFailed("bad key")
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await integration.async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_setup_entry_wraps_generic_error(hass):
    """Unexpected exceptions convert to ConfigEntryNotReady for retries."""

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass.config_entries.async_forward_entry_setups = AsyncMock(
        side_effect=RuntimeError("boom")
    )

    with pytest.raises(ConfigEntryNotReady):
        await integration.async_setup_entry(hass, entry)
