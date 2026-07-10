from __future__ import annotations

# Define constants for Pollen Levels integration

DOMAIN = "pollenlevels"

CONF_API_KEY = "api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_LANGUAGE_CODE = "language_code"
CONF_LEGACY_ENTRY_ID = "legacy_entry_id"

# Legacy option keys kept only to ignore/remove stored options from releases
# where forecast days and per-day type forecast sensors were configurable.
CONF_FORECAST_DAYS = "forecast_days"
CONF_CREATE_FORECAST_SENSORS = "create_forecast_sensors"
FORECAST_DAYS = 5

# Defaults
DEFAULT_UPDATE_INTERVAL = 6
MIN_UPDATE_INTERVAL_HOURS = 1
MAX_UPDATE_INTERVAL_HOURS = 24
DEFAULT_ENTRY_TITLE = "Pollen Levels"
POLLEN_API_TIMEOUT = 10
MAX_RETRIES = 1
POLLEN_API_KEY_URL = (
    "https://developers.google.com/maps/documentation/pollen/get-api-key"
)
RESTRICTING_API_KEYS_URL = (
    "https://developers.google.com/maps/api-security-best-practices"
)

ATTRIBUTION = "Google Maps — Source: Includes pollen data from Google"
SUBENTRY_TYPE_LOCATION = "location"


def is_invalid_api_key_message(message: str | None) -> bool:
    """Return True if *message* strongly indicates an invalid API key."""

    if not message:
        return False

    msg = message.casefold()
    signals = (
        "api key not valid",
        "invalid api key",
        "api_key_invalid",
        "apikeynotvalid",
        "api key is not valid",
    )
    return any(signal in msg for signal in signals)
