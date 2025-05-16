"""
Config flow for the Pollen Levels integration.
Collects API key, location coordinates, allergens, and update interval from the user.
"""
import voluptuous as vol
from homeassistant import config_entries
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

@config_entries.HANDLERS.register(DOMAIN)
class PollenLevelsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Pollen Levels."""
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Initial configuration step."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title=f"Pollen Levels ({user_input[CONF_LATITUDE]}, {user_input[CONF_LONGITUDE]})",
                data=user_input
            )

        schema = vol.Schema({
            vol.Required(CONF_API_KEY): str,
            vol.Required(
                CONF_LATITUDE,
                default=self.hass.config.latitude
            ): float,
            vol.Required(
                CONF_LONGITUDE,
                default=self.hass.config.longitude
            ): float,
            vol.Required(
                CONF_ALLERGENS,
                default=ALLERGEN_OPTIONS
            ): vol.All(list, [vol.In(ALLERGEN_OPTIONS)]),
            vol.Optional(
                CONF_UPDATE_INTERVAL,
                default=DEFAULT_UPDATE_INTERVAL
            ): vol.All(int, vol.Range(min=1))
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors
        )

