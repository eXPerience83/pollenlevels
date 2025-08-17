"""Constants for the Pollen Levels integration."""

DOMAIN = "pollenlevels"

CONF_API_KEY = "api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_LANGUAGE_CODE = "language_code"

# Forecast-related options
CONF_FORECAST_DAYS = "forecast_days"  # int: how many days to request from API
CONF_CREATE_FORECAST_SENSORS = "create_forecast_sensors"  # enum: none, d1, d1_d2

# Defaults
DEFAULT_UPDATE_INTERVAL = 6  # hours
DEFAULT_FORECAST_DAYS = 3  # today + D+1 + D+2 by default
DEFAULT_CREATE_FORECAST_SENSORS = "none"  # do not create per-day sensors by default

# Allowed values for create_forecast_sensors
CREATE_FC_NONE = "none"
CREATE_FC_D1 = "d1"
CREATE_FC_D1_D2 = "d1_d2"
