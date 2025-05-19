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

            # Construir la URL según docs de forecast:lookup
            url = (
                f"https://pollen.googleapis.com/v1/forecast:lookup?"
                f"key={user_input[CONF_API_KEY]}"
                f"&location.longitude={user_input[CONF_LONGITUDE]:.6f}"
                f"&location.latitude={user_input[CONF_LATITUDE]:.6f}"
                f"&days=1"
            )
            _LOGGER.debug("Pollen ConfigFlow validating URL: %s", url)

            try:
                async with session.get(url) as resp:
                    body = await resp.text()
                    _LOGGER.debug(
                        "Pollen ConfigFlow HTTP status: %s, response: %s",
                        resp.status, body
                    )

                    if resp.status == 403:
                        errors["base"] = "invalid_auth"
                    elif resp.status == 429:
                        errors["base"] = "quota_exceeded"
                    elif resp.status != 200:
                        errors["base"] = "cannot_connect"
                    else:
                        data = await resp.json()
                        # Comprobar existencia de dailyInfo
                        if not data.get("dailyInfo"):
                            _LOGGER.warning("Pollen ConfigFlow: 'dailyInfo' missing")
                            errors["base"] = "cannot_connect"
            except aiohttp.ClientError as err:
                _LOGGER.error("Connection error validating Pollen API: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error in Pollen ConfigFlow: %s", err)
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(
                    title=f"Pollen Levels ({user_input[CONF_LATITUDE]:.4f}, {user_input[CONF_LONGITUDE]:.4f})",
                    data=user_input
                )

        # Show form
        default_lat = self.hass.config.latitude
        default_lon = self.hass.config.longitude
        schema = vol.Schema({
            vol.Required(CONF_API_KEY): str,
            vol.Optional(CONF_LATITUDE, default=default_lat): cv.latitude,
            vol.Optional(CONF_LONGITUDE, default=default_lon): cv.longitude,
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
