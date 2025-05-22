"""Config flow for the Pollen Levels integration."""
import logging
import aiohttp
import voluptuous as vol

from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL,
    CONF_LANGUAGE_CODE
)

_LOGGER = logging.getLogger(__name__)

class PollenLevelsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Pollen Levels."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """First step: ask for API key, location, update interval and language."""
        errors = {}

        if user_input:
            session = async_get_clientsession(self.hass)
            params = {
                "key": user_input[CONF_API_KEY],
                "location.latitude": f"{user_input[CONF_LATITUDE]:.6f}",
                "location.longitude": f"{user_input[CONF_LONGITUDE]:.6f}",
                "days": 1,
                "languageCode": user_input[CONF_LANGUAGE_CODE],
            }
            url = "https://pollen.googleapis.com/v1/forecast:lookup"
            _LOGGER.debug("Validating Pollen API URL: %s params %s", url, params)
            try:
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
            except aiohttp.ClientError as err:
                _LOGGER.error("Connection error: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error: %s", err)
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title="Pollen Levels", data=user_input)

        defaults = {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_LANGUAGE_CODE: self.hass.config.language,
        }

        schema = vol.Schema({
            vol.Required(CONF_API_KEY): str,
            vol.Optional(CONF_LATITUDE, default=defaults[CONF_LATITUDE]): cv.latitude,
            vol.Optional(CONF_LONGITUDE, default=defaults[CONF_LONGITUDE]): cv.longitude,
            vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL):
                vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Optional(CONF_LANGUAGE_CODE, default=defaults[CONF_LANGUAGE_CODE]): cv.string,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors
        )
