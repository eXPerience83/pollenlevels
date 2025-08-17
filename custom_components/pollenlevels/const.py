# Define constants for Pollen Levels integration

DOMAIN = "pollenlevels"

CONF_API_KEY = "api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_LANGUAGE_CODE = "language_code"

# Forecast / options (Phase 2)
CONF_FORECAST_DAYS = "forecast_days"  # 1..5 days for forecast
CONF_CREATE_FORECAST_SENSORS = "create_forecast_sensors"  # none | d1 | d12

# Defaults
DEFAULT_UPDATE_INTERVAL = 6  # hours
DEFAULT_FORECAST_DAYS = 3
DEFAULT_CREATE_FORECAST_SENSORS = "none"

# Allowed values for per-day sensors option
CFS_NONE = "none"
CFS_D1 = "d1"
CFS_D12 = "d12"
ALLOWED_CFS = {CFS_NONE, CFS_D1, CFS_D12}

# Types for convenience
POLLEN_TYPES = ("GRASS", "TREE", "WEED")

# Public API endpoint (shared by config_flow and sensors)
API_URL = "https://pollen.googleapis.com/v1/forecast:lookup"
