"""Handle config & options flow for Pollen Levels integration.

Phase 1.1 notes (v1.6.1):
- Replace two boolean toggles (D+1 and D+2) with a single selector 'create_forecast_sensors':
  values: "none" (default), "D+1", "D+1+2".
- Validate coherence with 'forecast_days' (e.g., choosing "D+1+2" requires forecast_days >= 3).
"""

from __future__ import annotations

import logging
import re

import aiohttp
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    # Forecast options
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    FORECAST_SENSORS_CHOICES,
    MAX_FORECAST_DAYS,
    MIN_FORECAST_DAYS,
)

_LOGGER = logging.getLogger(__name__)

# Regex to support base and region subtags (e.g., "zh", "zh-Hant", "zh-Hant-TW")
LANGUAGE_CODE_REGEX = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?$", re.IGNORECASE)


def is_valid_language_code(value: str) -> str:
    """Validate IETF language code, raising a HA-UI friendly error key."""
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

    async def async_step_user(self, user_input=None):
        """Handle initial step."""
        errors: dict[str, str] = {}

        if user_input:
            # ---- Duplicate prevention -------------------------------------------------
            try:
                lat = float(user_input[CONF_LATITUDE])
                lon = float(user_input[CONF_LONGITUDE])
                await self.async_set_unique_id(f"{lat:.4f}_{lon:.4f}")
                self._abort_if_unique_id_configured()
            except Exception:  # pragma: no cover - defensive
                pass

            # ---- Field validation & API reachability ---------------------------------
            try:
                is_valid_language_code(user_input[CONF_LANGUAGE_CODE])

                session = async_get_clientsession(self.hass)
                params = {
                    "key": user_input[CONF_API_KEY],
                    "location.latitude": f"{lat:.6f}",
                    "location.longitude": f"{lon:.6f}",
                    "days": 1,
                    "languageCode": user_input[CONF_LANGUAGE_CODE],
                }
                url = "https://pollen.googleapis.com/v1/forecast:lookup"
                _LOGGER.debug("Validating Pollen API URL: %s params %s", url, params)
                async with session.get(url, params=params) as resp:
                    text = await resp.text()
                    _LOGGER.debug("Validation HTTP %s — %s", resp.status, text)
                    if resp.status == 403:
                        errors["base"] = "invalid_auth"
                    elif resp.status == 429:
                        errors["base"] = "quota_exceeded"
                    elif resp.status != 200:
                        errors["base"] = "cannot_connect"
                    else:
                        data = await resp.json()
                        if not data.get("dailyInfo"):
                            _LOGGER.warning("Validation: 'dailyInfo' missing")
                            errors["base"] = "cannot_connect"

            except vol.Invalid as ve:
                _LOGGER.warning(
                    "Language code validation failed for '%s': %s",
                    user_input.get(CONF_LANGUAGE_CODE),
                    ve,
                )
                errors[CONF_LANGUAGE_CODE] = str(ve)
            except aiohttp.ClientError as err:
                _LOGGER.error("Connection error: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:  # pragma: no cover - defensive
                _LOGGER.exception("Unexpected error: %s", err)
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title="Pollen Levels", data=user_input)

        defaults = {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_LANGUAGE_CODE: self.hass.config.language,
        }

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Optional(
                    CONF_LATITUDE, default=defaults[CONF_LATITUDE]
                ): cv.latitude,
                vol.Optional(
                    CONF_LONGITUDE, default=defaults[CONF_LONGITUDE]
                ): cv.longitude,
                vol.Optional(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Optional(
                    CONF_LANGUAGE_CODE, default=defaults[CONF_LANGUAGE_CODE]
                ): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class PollenLevelsOptionsFlow(config_entries.OptionsFlow):
    """Handle options for an existing entry."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input=None):
        """Display and process options form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Language validation: allow empty (inherit HA language), if provided validate format.
                lang = user_input.get(
                    CONF_LANGUAGE_CODE,
                    self.entry.options.get(
                        CONF_LANGUAGE_CODE, self.entry.data.get(CONF_LANGUAGE_CODE, "")
                    ),
                )
                if isinstance(lang, str) and lang.strip():
                    is_valid_language_code(lang)

                # forecast_days within supported range 1..5
                days = int(
                    user_input.get(
                        CONF_FORECAST_DAYS,
                        self.entry.options.get(
                            CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS
                        ),
                    )
                )
                if days < MIN_FORECAST_DAYS or days > MAX_FORECAST_DAYS:
                    errors["base"] = "cannot_connect"

                # validate combo for per-day sensors
                mode = user_input.get(
                    CONF_CREATE_FORECAST_SENSORS,
                    self.entry.options.get(CONF_CREATE_FORECAST_SENSORS, "none"),
                )
                needed = 1
                if mode == "D+1":
                    needed = 2
                elif mode == "D+1+2":
                    needed = 3
                if days < needed:
                    # Field-level error to guide the user
                    errors[CONF_CREATE_FORECAST_SENSORS] = "invalid_option_combo"

            except vol.Invalid as ve:
                errors[CONF_LANGUAGE_CODE] = str(ve)
            except Exception as err:  # pragma: no cover - defensive
                _LOGGER.exception("Options validation error: %s", err)
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Defaults: prefer options, fall back to data/const
        current_interval = self.entry.options.get(
            CONF_UPDATE_INTERVAL,
            self.entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        current_lang = self.entry.options.get(
            CONF_LANGUAGE_CODE,
            self.entry.data.get(CONF_LANGUAGE_CODE, self.hass.config.language),
        )
        current_days = self.entry.options.get(
            CONF_FORECAST_DAYS,
            self.entry.data.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS),
        )
        current_mode = self.entry.options.get(CONF_CREATE_FORECAST_SENSORS, "none")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=current_interval
                    ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                    vol.Optional(CONF_LANGUAGE_CODE, default=current_lang): str,
                    vol.Optional(CONF_FORECAST_DAYS, default=current_days): vol.In(
                        list(range(MIN_FORECAST_DAYS, MAX_FORECAST_DAYS + 1))
                    ),
                    vol.Optional(
                        CONF_CREATE_FORECAST_SENSORS, default=current_mode
                    ): vol.In(FORECAST_SENSORS_CHOICES),
                }
            ),
            errors=errors,
        )
