"""Handle config & options flow for Pollen Levels integration.

Phase 2: add forecast_days and create_forecast_sensors in Options.
- Validate CFS option against forecast_days (d1 => >=2, d12 => >=3).
- NEW: Validate API key / location by calling the API during initial setup.
"""

from __future__ import annotations

import logging
import re
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
    API_URL,
)

_LOGGER = logging.getLogger(__name__)

# Regex to support base and region subtags (e.g., "zh", "zh-Hant", "zh-Hant-TW")
LANGUAGE_CODE_REGEX = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?$", re.IGNORECASE)


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

            # Validate language code first (cheap)
            try:
                is_valid_language_code(user_input[CONF_LANGUAGE_CODE])
            except vol.Invalid as ve:
                errors[CONF_LANGUAGE_CODE] = str(ve)

            # Online validation (only if language format OK)
            if not errors:
                api_key = user_input[CONF_API_KEY]
                lat = float(user_input[CONF_LATITUDE])
                lon = float(user_input[CONF_LONGITUDE])
                lang = user_input[CONF_LANGUAGE_CODE] or "en"

                params = {
                    "key": api_key,
                    "location.latitude": f"{lat:.6f}",
                    "location.longitude": f"{lon:.6f}",
                    # Minimal call: 1 day is enough to validate credentials and shape
                    "days": 1,
                    "languageCode": lang,
                }

                session = async_get_clientsession(self.hass)
                try:
                    # NOTE: We specify timeout to avoid hanging the UI.
                    async with session.get(
                        API_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        text = await resp.text()
                        _LOGGER.debug("Validation HTTP %s — %s", resp.status, text[:500])

                        if resp.status == 403:
                            errors["base"] = "invalid_auth"
                        elif resp.status == 429:
                            errors["base"] = "quota_exceeded"
                        elif resp.status != 200:
                            errors["base"] = "cannot_connect"
                        else:
                            # Try parse JSON and check the expected top-level key
                            try:
                                data = await resp.json(content_type=None)
                            except Exception:  # pragma: no cover - defensive
                                _LOGGER.exception("Validation JSON parse error")
                                errors["base"] = "cannot_connect"
                            else:
                                if not data.get("dailyInfo"):
                                    _LOGGER.warning("Validation: 'dailyInfo' missing")
                                    errors["base"] = "cannot_connect"

                except aiohttp.ClientError:
                    _LOGGER.exception("Validation client error")
                    errors["base"] = "cannot_connect"
                except Exception:  # pragma: no cover - defensive
                    _LOGGER.exception("Unexpected validation error")
                    errors["base"] = "cannot_connect"

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

                # Forecast days: clip + validate
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
                if cfs == "d1" and days < 2:
                    errors[CONF_CREATE_FORECAST_SENSORS] = "requires_days_2"
                if cfs == "d12" and days < 3:
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
