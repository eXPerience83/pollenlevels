"""Diagnostics support for Pollen Levels.

This exposes non-sensitive runtime details useful for support:
- Entry data/options (with API key and location redacted)
- Coordinator snapshot (last_updated, forecast_days, language, flags)
- A sample of the request params with the API key redacted

No network I/O is performed.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)

TO_REDACT = {CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry with secrets redacted."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    options = dict(entry.options or {})
    data = dict(entry.data or {})

    # Build a safe params example (no network I/O)
    params_example = {
        "key": "***",
        "location.latitude": data.get(CONF_LATITUDE),
        "location.longitude": data.get(CONF_LONGITUDE),
        "days": options.get(CONF_FORECAST_DAYS, data.get(CONF_FORECAST_DAYS, 2)),
    }
    lang = options.get(CONF_LANGUAGE_CODE, data.get(CONF_LANGUAGE_CODE))
    if lang:
        params_example["languageCode"] = lang

    coord_info: dict[str, Any] = {}
    if coordinator is not None:
        coord_info = {
            "entry_id": getattr(coordinator, "entry_id", None),
            "forecast_days": getattr(coordinator, "forecast_days", None),
            "language": getattr(coordinator, "language", None),
            "create_d1": getattr(coordinator, "create_d1", None),
            "create_d2": getattr(coordinator, "create_d2", None),
            "last_updated": getattr(coordinator, "last_updated", None),
            "data_keys": list(getattr(coordinator, "data", {}).keys()),
        }

    diag = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "options": {
                CONF_UPDATE_INTERVAL: options.get(CONF_UPDATE_INTERVAL),
                CONF_LANGUAGE_CODE: options.get(CONF_LANGUAGE_CODE),
                CONF_FORECAST_DAYS: options.get(CONF_FORECAST_DAYS),
                CONF_CREATE_FORECAST_SENSORS: options.get(CONF_CREATE_FORECAST_SENSORS),
            },
            "data": {
                CONF_LATITUDE: data.get(CONF_LATITUDE),
                CONF_LONGITUDE: data.get(CONF_LONGITUDE),
                CONF_LANGUAGE_CODE: data.get(CONF_LANGUAGE_CODE),
            },
        },
        "coordinator": coord_info,
        "request_params_example": params_example,
    }

    return async_redact_data(diag, TO_REDACT)
