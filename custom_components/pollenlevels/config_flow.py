"""Handle config & options flow for Pollen Levels integration.

Phase 2 (v1.6.4.x): keep forecast options and preserve initial online validation
for API key / location:
- 403 → invalid_auth
- 429 → quota_exceeded
- other non-200 → cannot_connect

This file also:
- Reverts 'create_forecast_sensors' accepted values to the published ones
  ("D+1", "D+1+2") so we don't need legacy mapping.
- Validates that selected 'create_forecast_sensors' is compatible with the
  chosen 'forecast_days' (D+1 requires >= 2 days, D+1+2 requires >= 3 days).
"""

from __future__ import annotations

import logging
import re
from http import HTTPStatus
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    CONF_LANGUAGE_CODE,
    CONF_FORECAST_DAYS,
    CONF_CREATE_FORECAST_SENSORS,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_CREATE_FORECAST_SENSORS,
    ALLOWED_CFS,
)

# NOTE: We import API_URL from sensor to reuse the exact endpoint that powers
# the coordinator. This avoids divergence between validation and runtime.
# If at some point you move API_URL to const.py, just switch the import.
from .sensor import API_URL  # type: ignore  # import-time dependency is intentional

_LOGGER = logging.getLogger(__name__)

# Regex to support base and region subtags (e.g., "zh", "zh-Hant", "zh-Hant-TW")
LANGUAGE_CODE_REGEX = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?$", re.IGNORECASE)

# Constants to avoid magic numbers in validation logic.
MIN_DAYS_FOR_D1 = 2
MIN_DAYS_FOR_D12 = 3


def is_valid_language_code(value: str) -> str:
    """Validate IETF language code, raising HA-UI friendly keys."""
    if not isinstance(value, str):
        raise vol.Invalid("invalid_language")
    if not value.strip():
        raise vol.Invalid("empty")
    if not LANGUAGE_CODE_REGEX.match(value):
        _LOGGER.warning("Invalid language code format: %s", value)
        raise vol.Invalid("invalid_language")
    return value


async def _validate_online(
    hass, *, api_key: str, lat: float, lon: float, lang: str
) -> str | None:
    """Do a cheap online check to validate API key and coordinates.

    Returns one of:
    - "invalid_auth"    → 403
    - "quota_exceeded"  → 429
    - "cannot_connect"  → other problems
    - None              → looks OK
    """
    # Keep a single return at the end to satisfy PLR0911.
    err: str | None = None

    session = async_get_clientsession(hass)
    params = {"lat": f"{lat:.4f}", "lon": f"{lon:.4f}", "lang": (lang or "en").strip()}
    headers = {"X-API-Key": api_key.strip()}

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with session.get(API_URL, params=params, headers=headers, timeout=timeout) as resp:
            text = await resp.text()
            _LOGGER.debug("Validation HTTP %s — %s", resp.status, text)

            if resp.status == HTTPStatus.FORBIDDEN:
                err = "invalid_auth"
            elif resp.status == HTTPStatus.TOO_MANY_REQUESTS:
                err = "quota_exceeded"
            elif resp.status != HTTPStatus.OK:
                err = "cannot_connect"
            else:
                # Some servers don't send application/json content-type strictly.
                data = await resp.json(content_type=None)
                if not data.get("dailyInfo"):
                    _LOGGER.warning("Validation: 'dailyInfo' missing in response")
                    err = "cannot_connect"

    except aiohttp.ClientError:
        _LOGGER.exception("Validation network error")
        err = "cannot_connect"
    except Exception:  # pragma: no cover - safety net
        _LOGGER.exception("Unexpected validation error")
        err = "cannot_connect"

    return err


class PollenLevelsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Implement config flow for Pollen Levels."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        """Return the options flow handler for this entry."""
        return PollenLevelsOptionsFlow(entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial configuration step."""
        errors: dict[str, str] = {}

        if user_input:
            # Stable unique_id by (lat, lon)
            try:
                lat = float(user_input[CONF_LATITUDE])
                lon = float(user_input[CONF_LONGITUDE])
                await self.async_set_unique_id(f"{lat:.4f}_{lon:.4f}")
                self._abort_if_unique_id_configured()
            except Exception:  # pragma: no cover - defensive
                pass

            # Validate language field (if provided)
            try:
                is_valid_language_code(user_input.get(CONF_LANGUAGE_CODE, "") or "en")
            except vol.Invalid as ve:
                errors[CONF_LANGUAGE_CODE] = str(ve)

            # Keep the online validation (auth/quotas/connectivity) before creating the entry
            if not errors:
                lang = user_input.get(CONF_LANGUAGE_CODE) or (self.hass.config.language or "en")
                err = await _validate_online(
                    self.hass,
                    api_key=str(user_input[CONF_API_KEY]),
                    lat=float(user_input[CONF_LATITUDE]),
                    lon=float(user_input[CONF_LONGITUDE]),
                    lang=str(lang),
                )
                if err:
                    errors["base"] = err

            if not errors:
                return self.async_create_entry(title="Pollen Levels", data=user_input)

        # Defaults from HA config
        defaults = {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_LANGUAGE_CODE: self.hass.config.language or "en",
        }

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Optional(CONF_LATITUDE, default=defaults[CONF_LATITUDE]): cv.latitude,
                vol.Optional(CONF_LONGITUDE, default=defaults[CONF_LONGITUDE]): cv.longitude,
                vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=1)
                ),
                vol.Optional(CONF_LANGUAGE_CODE, default=defaults[CONF_LANGUAGE_CODE]): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class PollenLevelsOptionsFlow(config_entries.OptionsFlow):
    """Options: update interval, language, forecast days, per-day sensors for TYPES."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Display and process options form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Language optional: if filled, validate
                lang = user_input.get(
                    CONF_LANGUAGE_CODE,
                    self.entry.options.get(
                        CONF_LANGUAGE_CODE, self.entry.data.get(CONF_LANGUAGE_CODE, "")
                    ),
                )
                if isinstance(lang, str) and lang.strip():
                    is_valid_language_code(lang)

                # Forecast days: clip + validate in a simple, explicit way
                days = int(
                    user_input.get(
                        CONF_FORECAST_DAYS,
                        self.entry.options.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS),
                    )
                )
                if days < 1 or days > 5:
                    raise vol.Invalid("invalid_days")

                # CFS validation per days
                cfs = user_input.get(
                    CONF_CREATE_FORECAST_SENSORS,
                    self.entry.options.get(
                        CONF_CREATE_FORECAST_SENSORS, DEFAULT_CREATE_FORECAST_SENSORS
                    ),
                )
                if cfs not in ALLOWED_CFS:
                    raise vol.Invalid("invalid_cfs")
                if cfs == "D+1" and days < MIN_DAYS_FOR_D1:
                    errors[CONF_CREATE_FORECAST_SENSORS] = "requires_days_2"
                if cfs == "D+1+2" and days < MIN_DAYS_FOR_D12:
                    errors[CONF_CREATE_FORECAST_SENSORS] = "requires_days_3"

            except vol.Invalid as ve:
                # Map non-field-specific errors
                if str(ve) in ("invalid_days", "invalid_cfs"):
                    errors["base"] = str(ve)
                else:
                    errors[CONF_LANGUAGE_CODE] = str(ve)
            except Exception:  # pragma: no cover - defensive
                _LOGGER.exception("Options validation error")
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Defaults (prefer options)
        current_interval = self.entry.options.get(
            CONF_UPDATE_INTERVAL, self.entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )
        current_lang = self.entry.options.get(
            CONF_LANGUAGE_CODE, self.entry.data.get(CONF_LANGUAGE_CODE, self.hass.config.language)
        )
        current_days = self.entry.options.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS)
        current_cfs = self.entry.options.get(
            CONF_CREATE_FORECAST_SENSORS, DEFAULT_CREATE_FORECAST_SENSORS
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_UPDATE_INTERVAL, default=current_interval): vol.All(
                        vol.Coerce(int), vol.Range(min=1)
                    ),
                    vol.Optional(CONF_LANGUAGE_CODE, default=current_lang): str,
                    vol.Optional(CONF_FORECAST_DAYS, default=current_days): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=5)
                    ),
                    vol.Optional(CONF_CREATE_FORECAST_SENSORS, default=current_cfs): vol.In(
                        tuple(ALLOWED_CFS)
                    ),
                }
            ),
            errors=errors,
        )
        
