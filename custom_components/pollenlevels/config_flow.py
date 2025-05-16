import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN  # Asegúrate de tener un archivo const.py con DOMAIN definido

@config_entries.HANDLERS.register(DOMAIN)
class PollenLevelsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Pollen Levels integration."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Aquí puedes validar la entrada si lo necesitas
            return self.async_create_entry(title="Niveles de Polen", data=user_input)

        # Define los campos que se le piden al usuario
        data_schema = vol.Schema({
            vol.Required("location"): str,
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PollenLevelsOptionsFlowHandler(config_entry)

class PollenLevelsOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema({
            vol.Optional("update_interval", default=self.config_entry.options.get("update_interval", 60)): int,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema
        )
