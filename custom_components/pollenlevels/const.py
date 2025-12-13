# Define constants for Pollen Levels integration

DOMAIN = "pollenlevels"

CONF_API_KEY = "api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_LANGUAGE_CODE = "language_code"
CONF_HTTP_REFERRER = "http_referrer"

# Forecast-related options (Phase 1.1: types only)
CONF_FORECAST_DAYS = "forecast_days"
CONF_CREATE_FORECAST_SENSORS = (
    "create_forecast_sensors"  # values: "none" | "D+1" | "D+1+2"
)

# Defaults
DEFAULT_UPDATE_INTERVAL = 6
DEFAULT_FORECAST_DAYS = 2  # today + 1 (tomorrow)
DEFAULT_ENTRY_TITLE = "Pollen Levels"
MAX_FORECAST_DAYS = 5
MIN_FORECAST_DAYS = 1
POLLEN_API_TIMEOUT = 10
SECTION_API_KEY_OPTIONS = "api_key_options"

# Allowed values for create_forecast_sensors selector
FORECAST_SENSORS_CHOICES = ["none", "D+1", "D+1+2"]
