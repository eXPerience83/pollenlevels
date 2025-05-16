"""
Config flow for Pollen Levels integration
"""
import voluptuous as vol
from homeassistant import config_entries
from .const import (
    DOMAIN, CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE,
    CONF_ALLERGENS, CONF_UPDATE_INTERVAL, ALLERGEN_OPTIONS,
    DEFAULT_UPDATE_INTERVAL
)

class PollenConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            return self.async_create_entry(
                title=f"Pollen ({user_input[CONF_LATITUDE]}, {user_input[CONF_LONGITUDE]})",
                data=user_input
            )

        schema = vol.Schema({
            vol.Required(CONF_API_KEY): str,
            vol.Required(CONF_LATITUDE, default=self.hass.config.latitude): float,
            vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): float,
            vol.Required(CONF_ALLERGENS, default=ALLERGEN_OPTIONS): vol.All(list, [vol.In(ALLERGEN_OPTIONS)]),
            vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.Coerce(int),
        })

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )
```
