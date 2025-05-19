"""Config flow for the Pollen Levels integration, with credential validation."""
import logging
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
    CONF_ALLERGENS,
    CONF_UPDATE_INTERVAL,
    ALLERGEN_OPTIONS,
    DEFAULT_UPDATE_INTERVAL
)

_LOGGER = logging.getLogger(__name__)

class PollenLevelsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Pollen Levels with initial API check."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Initial configuration step."""
        errors = {}

        if user_input:
            session = async_get_clientsession(self.hass)

            # URL según doc de forecast:lookup :contentReference[oaicite:1]{index=1}
            url = (
                f"https://pollen.googleapis.com/v1/forecast:lookup?"
                f"key={user_input[CONF_API_KEY]}"
                f"&location.longitude={user_input[CONF_LONGITUDE]:.6f}"
                f"&location.latitude={user_input[CONF_LATITUDE]:.6f}"
                f"&days=1"
            )
            _LOGGER.debug("Validating Pollen API URL: %s", url)

            try:
                async with session.get(url) as resp:
                    body = await resp.text()
                    _LOGGER.debug("HTTP %s — %s", resp.status, body)

                    if resp.status == 403:
                        errors["base"] = "invalid_auth"
                    elif resp.status == 429:
                        errors["base"] = "quota_exceeded"
                    elif resp.status != 200:
                        errors["base"] = "cannot_connect"
                    else:
                        data = await resp.json()
                        # El array correcto es dailyInfo :contentReference[oaicite:2]{index=2}
                        if not data.get("dailyInfo"):
                            _LOGGER.warning("Missing 'dailyInfo' in response")
                            errors["base"] = "cannot_connect"
            except aiohttp.ClientError as err:
                _LOGGER.error("Connection error: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error: %s", err)
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(
                    title=f"Pollen Levels ({user_input[CONF_LATITUDE]:.4f}, "
                          f"{user_input[CONF_LONGITUDE]:.4f})",
                    data=user_input
                )

        defaults = {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude
        }
        schema = vol.Schema({
            vol.Required(CONF_API_KEY): str,
            vol.Optional(CONF_LATITUDE, default=defaults[CONF_LATITUDE]): cv.latitude,
            vol.Optional(CONF_LONGITUDE, default=defaults[CONF_LONGITUDE]): cv.longitude,
            vol.Optional(CONF_ALLERGENS, default=ALLERGEN_OPTIONS):
                cv.multi_select({opt: opt.capitalize() for opt in ALLERGEN_OPTIONS}),
            vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL):
                vol.All(vol.Coerce(int), vol.Range(min=1)),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors
        )
