"""Config flow for the Pollen Levels integration."""
import voluptuous as vol
from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv

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
            # Crear la entrada de configuración con los datos recogidos
            return self.async_create_entry(
                title=f"Pollen Levels ({user_input[CONF_LATITUDE]}, {user_input[CONF_LONGITUDE]})",
                data=user_input
            )

        # Valores por defecto de Home Assistant
        default_lat = self.hass.config.latitude
        default_lon = self.hass.config.longitude

        data_schema = vol.Schema({
            vol.Required(CONF_API_KEY): str,
            vol.Optional(CONF_LATITUDE, default=default_lat): cv.latitude,
            vol.Optional(CONF_LONGITUDE, default=default_lon): cv.longitude,
            vol.Optional(CONF_ALLERGENS, default=ALLERGEN_OPTIONS): cv.multi_select({opt: opt for opt in ALLERGEN_OPTIONS}),
            vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=1))
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors
        )
