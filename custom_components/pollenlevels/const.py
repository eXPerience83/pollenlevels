from typing import Any

# Define constants for Pollen Levels integration

DOMAIN = "pollenlevels"

CONF_API_KEY = "api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_LANGUAGE_CODE = "language_code"
CONF_HTTP_REFERER = "http_referer"

# Forecast-related options (Phase 1.1: types only)
CONF_FORECAST_DAYS = "forecast_days"
CONF_CREATE_FORECAST_SENSORS = "create_forecast_sensors"
FORECAST_NONE = "none"
FORECAST_D1 = "d1"
FORECAST_D1_2 = "d1_2"
CREATE_FORECAST_OPTIONS = [FORECAST_NONE, FORECAST_D1, FORECAST_D1_2]
SECTION_API_KEY_OPTIONS = "api_key_options"

# Defaults
DEFAULT_UPDATE_INTERVAL = 6
DEFAULT_FORECAST_DAYS = 2  # today + 1 (tomorrow)
DEFAULT_ENTRY_TITLE = "Pollen Levels"
MAX_FORECAST_DAYS = 5
MIN_FORECAST_DAYS = 1
POLLEN_API_TIMEOUT = 10
POLLEN_API_KEY_URL = (
    "https://developers.google.com/maps/documentation/pollen/get-api-key"
)
RESTRICTING_API_KEYS_URL = (
    "https://developers.google.com/maps/api-security-best-practices"
)

# Legacy mapping for backward compatibility
_LEGACY_FORECAST_MAP = {
    "D+1": FORECAST_D1,
    "d+1": FORECAST_D1,
    "D+1+2": FORECAST_D1_2,
    "d+1+2": FORECAST_D1_2,
}


def normalize_create_forecast_sensors(value: Any) -> str:
    """Normalize per-day sensor mode to supported values."""

    if value is None:
        return FORECAST_NONE

    text = str(value).strip()
    if not text:
        return FORECAST_NONE

    if text in CREATE_FORECAST_OPTIONS:
        return text

    mapped = _LEGACY_FORECAST_MAP.get(text)
    if mapped:
        return mapped

    return FORECAST_NONE


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


def normalize_http_referer(value: Any) -> str | None:
    """Normalize HTTP referrer input and reject CR/LF."""

    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    if "\r" in text or "\n" in text:
        raise ValueError("invalid http referer")

    return text
