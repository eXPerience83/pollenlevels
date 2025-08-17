# Define constants for Pollen Levels integration
# Revert create_forecast_sensors values back to the published 1.6.3 style:
#   "none" | "D+1" | "D+1+2"
# This removes the need for legacy normalization (d1/d12) introduced in alphas.

DOMAIN = "pollenlevels"

CONF_API_KEY = "api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_LANGUAGE_CODE = "language_code"

# Forecast / options (Phase 2)
CONF_FORECAST_DAYS = "forecast_days"  # 1..5 days for forecast
# Persisted values are historical ("D+1", "D+1+2") to match v1.6.3 behavior
CONF_CREATE_FORECAST_SENSORS = "create_forecast_sensors"

# Defaults
DEFAULT_UPDATE_INTERVAL = 6  # hours
DEFAULT_FORECAST_DAYS = 3
DEFAULT_CREATE_FORECAST_SENSORS = "none"

# Allowed values for per-day sensors option (published form)
CFS_NONE = "none"
CFS_D1 = "D+1"
CFS_D12 = "D+1+2"
ALLOWED_CFS = {CFS_NONE, CFS_D1, CFS_D12}

# Types for convenience
POLLEN_TYPES = ("GRASS", "TREE", "WEED")

# Public API endpoint (shared by config_flow and sensors)
API_URL = "https://pollen.googleapis.com/v1/forecast:lookup"

# Minimum/maximum forecast days allowed by the API
MIN_FORECAST_DAYS: int = 1
MAX_FORECAST_DAYS: int = 5

# Minimum forecast days required by each 'create_forecast_sensors' option
MIN_DAYS_FOR_D1: int = 2
MIN_DAYS_FOR_D12: int = 3
