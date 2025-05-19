"""Config flow for the Pollen Levels integration, with credential validation."""
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

class PollenLevelsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Pollen Levels with initial API check."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Initial configuration step."""
        errors = {}

        if user_input:
            session = async_get_clientsession(self.hass)
            url = (
                f"https://pollenws.googleapis.com/v1/pollen?"
                f"latitude={user_input[CONF_LATITUDE]:.6f}&"
                f"longitude={user_input[CONF_LONGITUDE]:.6f}&"
                f"key={user_input[CONF_API_KEY]}"
            )
            try:
                async with session.get(url) as resp:
                    if resp.status == 403:
                        errors["base"] = "invalid_auth"
                    elif resp.status == 429:
                        errors["base"] = "quota_exceeded"
                    elif resp.status != 200:
                        errors["base"] = "cannot_connect"
            except Exception:
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
            vol.Optional(CONF_ALLERGENS, default=ALLERGEN_OPTIONS): cv.multi_select(
                {opt: opt.capitalize() for opt in ALLERGEN_OPTIONS}
            ),
            vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL):
                vol.All(vol.Coerce(int), vol.Range(min=1)),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors
        )
