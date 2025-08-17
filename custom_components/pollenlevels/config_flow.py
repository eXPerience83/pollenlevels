"""Config & options flow for Pollen Levels (Google Pollen API).

This version restores the published option values for
`create_forecast_sensors` ("D+1", "D+1+2") to avoid legacy migration, and
keeps the initial online validation (API key / location):
- HTTP 403 → "invalid_auth"
- HTTP 429 → "quota_exceeded"
- Other non-200 → "cannot_connect"
"""

from __future__ import annotations

from http import HTTPStatus
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
)

_LOGGER = logging.getLogger(__name__)

# Regex supports base and region subtags (e.g., "zh", "zh-Hant", "zh-Hant-TW").
LANGUAGE_CODE_REGEX = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?$", re.IGNORECASE)

# Avoid "magic numbers" in validations.
MAX_FORECAST_DAYS = 5

# Endpoint used to validate credentials and location with a minimal request.
# We only ask for one day to keep it lightweight.
GOOGLE_POLLEN_URL = "https://pollen.googleapis.com/v1/forecast:lookup"


def _is_valid_language_code(value: str) -> str:
    """Validate IETF language code and raise HA-UI friendly keys."""
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
    """Ping the Google Pollen endpoint to validate API key and location.

    Returns an error key or None if everything looks ok.
    """
    session = async_get_clientsession(hass)
    params = {
        "key": api_key,
        "location.latitude": lat,
        "location.longitude": lon,
        "days": 1,
        "languageCode": lang,
    }

    try:
        async with session.get(GOOGLE_POLLEN_URL, params=params) as resp:
            text = await resp.text()
            _LOGGER.debug("Validation HTTP %s — %s", resp.status, text)

            if resp.status == HTTPStatus.FORBIDDEN:  # 403
                return "invalid_auth"
            if resp.status == HTTPStatus.TOO_MANY_REQUESTS:  # 429
                return "quota_exceeded"
            if resp.status != HTTPStatus.OK:  # != 200
                return "cannot_connect"

            data = await resp.json()
    except aiohttp.ClientError:
        _LOGGER.exception("Validation network error")
        return "cannot_connect"
    except Exception:  # pragma: no cover - defensive
        _LOGGER.exception("Unexpected error during validation")
        return "cannot_connect"

    if not data or not data.get("dailyInfo"):
        _LOGGER.warning("Validation: 'dailyInfo' missing")
        return "cannot_connect"

    return None


class PollenLevelsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Pollen Levels."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        """Return the options flow handler for this entry."""
        return PollenLevelsOptionsFlow(entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial configuration step."""
        errors: dict[str, str] = {}

        if user_input:
            # Stable unique_id by (lat, lon).
            try:
                lat = float(user_input[CONF_LATITUDE])
                lon = float(user_input[CONF_LONGITUDE])
                await self.async_set_unique_id(f"{lat:.4f}_{lon:.4f}")
                self._abort_if_unique_id_configured()
            except Exception:  # pragma: no cover - defensive
                pass

            # Validate language.
            try:
                _is_valid_language_code(user_input[CONF_LANGUAGE_CODE])
            except vol.Invalid as ve:
                errors[CONF_LANGUAGE_CODE] = str(ve)

            # Online validation (API key / location).
            if not errors:
                api_key = user_input[CONF_API_KEY]
                try:
                    lat = float(user_input[CONF_LATITUDE])
                    lon = float(user_input[CONF_LONGITUDE])
                except Exception:
                    errors["base"] = "cannot_connect"
                else:
                    err = await _validate_online(
                        self.hass,
                        api_key=api_key,
                        lat=lat,
                        lon=lon,
                        lang=user_input[CONF_LANGUAGE_CODE],
                    )
                    if err:
                        errors["base"] = err

            if not errors:
                return self.async_create_entry(title="Pollen Levels", data=user_input)

        # Defaults from HA config.
        defaults = {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_LANGUAGE_CODE: self.hass.config.language or "en",
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
    """Options: interval, language, forecast days, and per-day forecast sensors."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Display and process the options form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Optional language: if filled, validate.
                lang = user_input.get(
                    CONF_LANGUAGE_CODE,
                    self.entry.options.get(
                        CONF_LANGUAGE_CODE, self.entry.data.get(CONF_LANGUAGE_CODE, "")
                    ),
                )
                if isinstance(lang, str) and lang.strip():
                    _is_valid_language_code(lang)

                # Forecast days: clip + validate.
                days = int(
                    user_input.get(
                        CONF_FORECAST_DAYS,
                        self.entry.options.get(
                            CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS
                        ),
                    )
                )
                if days < 1 or days > MAX_FORECAST_DAYS:
                    raise vol.Invalid("invalid_days")

                # CFS validation per days.
                cfs = user_input.get(
                    CONF_CREATE_FORECAST_SENSORS,
                    self.entry.options.get(
                        CONF_CREATE_FORECAST_SENSORS, DEFAULT_CREATE_FORECAST_SENSORS
                    ),
                )
                if cfs not in ALLOWED_CFS:
                    raise vol.Invalid("invalid_cfs")
                if cfs == "D+1" and days < 2:
                    errors[CONF_CREATE_FORECAST_SENSORS] = "requires_days_2"
                if cfs == "D+1+2" and days < 3:
                    errors[CONF_CREATE_FORECAST_SENSORS] = "requires_days_3"

            except vol.Invalid as ve:
                # Map non-field-specific errors.
                if str(ve) in ("invalid_days", "invalid_cfs"):
                    errors["base"] = str(ve)
                else:
                    errors[CONF_LANGUAGE_CODE] = str(ve)
            except Exception:  # pragma: no cover - defensive
                _LOGGER.exception("Options validation error")
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Defaults (prefer options).
        current_interval = self.entry.options.get(
            CONF_UPDATE_INTERVAL,
            self.entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        current_lang = self.entry.options.get(
            CONF_LANGUAGE_CODE,
            self.entry.data.get(CONF_LANGUAGE_CODE, self.hass.config.language),
        )
        current_days = self.entry.options.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS)
        current_cfs = self.entry.options.get(
            CONF_CREATE_FORECAST_SENSORS, DEFAULT_CREATE_FORECAST_SENSORS
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=current_interval
                    ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                    vol.Optional(CONF_LANGUAGE_CODE, default=current_lang): str,
                    vol.Optional(CONF_FORECAST_DAYS, default=current_days): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=MAX_FORECAST_DAYS)
                    ),
                    vol.Optional(
                        CONF_CREATE_FORECAST_SENSORS, default=current_cfs
                    ): vol.In(tuple(ALLOWED_CFS)),
                }
            ),
            errors=errors,
        )
