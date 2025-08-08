"""Handle config & options flow for Pollen Levels integration."""

import logging
import aiohttp
import voluptuous as vol
import re

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
)

_LOGGER = logging.getLogger(__name__)

# Improved regex to support base and region subtags:
# - 2-3 character base language codes (e.g., "zh", "cmn")
# - 2-4 character region suffixes (e.g., "zh-Hant", "zh-Hant-TW")
# - Case-insensitive matching (supports "en-US", "en-us", etc.)
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
            # Use a stable unique_id per (lat,lon) with 4 decimal precision so that
            # we avoid duplicate entries for the same location.
            try:
                lat = float(user_input[CONF_LATITUDE])
                lon = float(user_input[CONF_LONGITUDE])
                await self.async_set_unique_id(f"{lat:.4f}_{lon:.4f}")
                self._abort_if_unique_id_configured()
            except Exception:  # pragma: no cover - defensive
                # If something goes off with parsing, proceed; form validators will catch it.
                pass

            # ---- Field validation & API reachability ---------------------------------
            try:
                # Validate language format locally first (UI-friendly errors)
                is_valid_language_code(user_input[CONF_LANGUAGE_CODE])

                # Probe API to verify key/quota/connectivity before creating the entry
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
                # Create the entry with the provided data.
                return self.async_create_entry(title="Pollen Levels", data=user_input)

        # Default values from HA config for the form
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
            # Validate language if provided
            try:
                # Allow empty to "inherit" HA UI language, but if non-empty, validate format.
                lang = user_input.get(
                    CONF_LANGUAGE_CODE,
                    self.entry.options.get(
                        CONF_LANGUAGE_CODE,
                        self.entry.data.get(CONF_LANGUAGE_CODE, ""),
                    ),
                )
                if isinstance(lang, str) and lang.strip():
                    is_valid_language_code(lang)

                # Update interval basic sanity check
                interval = int(
                    user_input.get(
                        CONF_UPDATE_INTERVAL,
                        self.entry.options.get(
                            CONF_UPDATE_INTERVAL,
                            self.entry.data.get(
                                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                            ),
                        ),
                    )
                )
                if interval < 1:
                    errors[CONF_UPDATE_INTERVAL] = "value_error"

            except vol.Invalid as ve:
                errors[CONF_LANGUAGE_CODE] = str(ve)
            except Exception as err:  # pragma: no cover - defensive
                _LOGGER.exception("Options validation error: %s", err)
                errors["base"] = "cannot_connect"

            if not errors:
                # Store options; the integration should reload to apply them.
                return self.async_create_entry(title="", data=user_input)

        # Defaults: prefer options, fall back to data, then HA language
        current_interval = self.entry.options.get(
            CONF_UPDATE_INTERVAL,
            self.entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        current_lang = self.entry.options.get(
            CONF_LANGUAGE_CODE,
            self.entry.data.get(CONF_LANGUAGE_CODE, self.hass.config.language),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=current_interval
                    ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                    vol.Optional(CONF_LANGUAGE_CODE, default=current_lang): str,
                }
            ),
            errors=errors,
        )
