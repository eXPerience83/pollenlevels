"""Handle config & options flow for Pollen Levels integration.

Notes:
- Unified per-day sensors option: 'create_forecast_sensors' -> "none" | "D+1" | "D+1+2".
- Validate coherence with 'forecast_days' (e.g., choosing "D+1+2" requires forecast_days >= 3).

Language code validation (v1.6.3 alpha+):
- Align validation with IETF BCP-47 commonly used patterns:
  * language (2–3 letters)
  * optional script (4 letters)
  * optional region (2 letters OR 3 digits)
  * optional single variant (5–8 alphanum OR 4 starting with digit)
- This accepts tags like: "en", "en-US", "zh-Hant", "zh-Hant-TW", "es-419".
- We intentionally keep it permissive and let the Google API:
    - use the closest match when an exact locale is not available, or
    - reject truly invalid inputs with an HTTP error.

Docs: forecast.lookup says languageCode follows BCP-47 and falls back to closest match.

v1.6.3 alpha4:
- Setup step now mirrors Options behavior: an empty language code is allowed
  (meaning “inherit HA language / let the API pick default”).
  When empty, we skip both validation and sending `languageCode` to the API
  during the connectivity probe. This avoids spurious "empty" errors.
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

# ---------------------------------------------------------------------------
# BCP-47-ish regex:
# - language: 2-3 letters
# - script (optional): 4 letters
# - region (optional): 2 letters OR 3 digits
# - variant (optional): 5-8 alphanum OR 4 starting with a digit
#
# Examples accepted:
#   en, en-US, zh-Hant, zh-Hant-TW, es-419, sr-Cyrl-RS, sl-rozaj
# This is not a full BCP-47 grammar (extensions/privateuse omitted),
# but it covers common real-world tags while keeping the validator simple.
# ---------------------------------------------------------------------------
LANGUAGE_CODE_REGEX = re.compile(
    r"^[A-Za-z]{2,3}"
    r"(?:-[A-Za-z]{4})?"  # optional script
    r"(?:-(?:[A-Za-z]{2}|\d{3}))?"  # optional region
    r"(?:-(?:[A-Za-z0-9]{5,8}|\d[A-Za-z0-9]{3}))?$",  # optional single variant
    re.IGNORECASE,
)


def is_valid_language_code(value: str) -> str:
    """Validate language code format; raise user-friendly HA error keys.

    We accept common BCP-47 patterns and rely on the API to perform:
    - closest-match fallback when a sub-locale is unavailable
    - final validation for totally invalid values
    """
    if not isinstance(value, str):
        raise vol.Invalid("invalid_language")
    norm = value.strip()
    if not norm:
        raise vol.Invalid("empty")
    if not LANGUAGE_CODE_REGEX.match(norm):
        _LOGGER.warning("Invalid language code format (BCP-47-like check): %s", value)
        raise vol.Invalid("invalid_language")
    return norm


class PollenLevelsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Pollen Levels."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        """Return the options flow handler for this entry."""
        return PollenLevelsOptionsFlow(entry)

    async def async_step_user(self, user_input=None):
        """Handle initial step."""
        errors: dict[str, str] = {}

        if user_input:
            # Define upfront to avoid any edge-case scoping issues.
            lat = float(user_input.get(CONF_LATITUDE))
            lon = float(user_input.get(CONF_LONGITUDE))

            # Unique ID by lat/lon to prevent duplicates.
            try:
                await self.async_set_unique_id(f"{lat:.4f}_{lon:.4f}")
                self._abort_if_unique_id_configured()
            except Exception:  # pragma: no cover - defensive
                pass

            try:
                # NEW: Mirror Options behavior — allow blank language (inherit / API default).
                raw_lang = user_input.get(CONF_LANGUAGE_CODE, "")
                lang = raw_lang.strip() if isinstance(raw_lang, str) else ""
                if lang:
                    # Only validate if non-empty
                    is_valid_language_code(lang)

                # Connection check to surface invalid key/quotas early.
                session = async_get_clientsession(self.hass)
                params = {
                    "key": user_input[CONF_API_KEY],
                    "location.latitude": f"{lat:.6f}",
                    "location.longitude": f"{lon:.6f}",
                    "days": 1,
                }
                # Only send languageCode if non-empty (avoids API receiving an empty tag).
                if lang:
                    params["languageCode"] = lang

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
            # Keep default as HA language; user can clear it if desired.
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
                # Note: string type retained; empty string is accepted and handled above.
                vol.Optional(CONF_LANGUAGE_CODE, default=defaults[CONF_LANGUAGE_CODE]): str,
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
                # Language: allow empty (inherit HA language); if provided, validate.
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
                    errors[CONF_FORECAST_DAYS] = "invalid_option_combo"

                # per-day sensors vs number of days
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
                    errors[CONF_CREATE_FORECAST_SENSORS] = "invalid_option_combo"

            except vol.Invalid as ve:
                errors[CONF_LANGUAGE_CODE] = str(ve)
            except Exception as err:  # pragma: no cover - defensive
                _LOGGER.exception("Options validation error: %s", err)
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Defaults: prefer options, fallback to data/HA config
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
