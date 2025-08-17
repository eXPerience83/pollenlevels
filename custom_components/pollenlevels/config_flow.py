"""Handle config & options flow for Pollen Levels integration.

Phase 2:
- Keep forecast_days and create_forecast_sensors in Options.
- REVERT: Persist 'create_forecast_sensors' values to published style "D+1" / "D+1+2".
- Validate CFS option against forecast_days (D+1 => >=2, D+1+2 => >=3).
- Preserve initial-setup online validation: 403→invalid_auth, 429→quota_exceeded, others→cannot_connect.
"""

from __future__ import annotations

import logging
import re
from http import HTTPStatus
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ALLOWED_CFS,
    API_URL,
    CONF_API_KEY,
    CONF_CREATE_FORECAST_SENSORS,
    CONF_FORECAST_DAYS,
    CONF_LANGUAGE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_CREATE_FORECAST_SENSORS,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_DAYS_FOR_D1,
    MIN_DAYS_FOR_D12,
    MIN_FORECAST_DAYS,
    MAX_FORECAST_DAYS,
)

_LOGGER = logging.getLogger(__name__)

# Regex to support base and region subtags (e.g., "zh", "zh-Hant", "zh-Hant-TW")
LANGUAGE_CODE_REGEX = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?$", re.IGNORECASE)


def is_valid_language_code(value: str) -> str:
    """Validate IETF language code, raising HA-UI friendly keys."""
    if not isinstance(value, str):
        raise vol.Invalid("invalid_language")
    if not value.strip():
        raise vol.Invalid("empty")
    if not LANGUAGE_CODE_REGEX.match(value):
        _LOGGER.warning("Invalid language code format: %s", value)
        raise vol.Invalid("invalid_language")
    return value


class PollenLevelsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Implement config flow for Pollen Levels."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        """Return the options flow handler for this entry."""
        return PollenLevelsOptionsFlow(entry)

    # ----------------------------- Helpers (reduce branches/statements) -----------------------------

    async def _validate_online(
        self, *, api_key: str, lat: float, lon: float, lang: str
    ) -> str | None:
        """Hit API once to validate credentials/location/language.

        Returns an error-key string for the HA UI ("invalid_auth", "quota_exceeded",
        "cannot_connect") or None when OK.
        Designed to have a single return to avoid PLR0911.
        """
        error: str | None = None
        params = {
            "key": api_key,
            "location.latitude": f"{lat:.6f}",
            "location.longitude": f"{lon:.6f}",
            # Minimal call: 1 day is enough to validate credentials and payload shape
            "days": 1,
            "languageCode": lang or "en",
        }
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                API_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                text = await resp.text()
                _LOGGER.debug("Validation HTTP %s — %s", resp.status, text[:500])

                if resp.status == HTTPStatus.FORBIDDEN:
                    error = "invalid_auth"
                elif resp.status == HTTPStatus.TOO_MANY_REQUESTS:
                    error = "quota_exceeded"
                elif resp.status != HTTPStatus.OK:
                    error = "cannot_connect"
                else:
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:  # pragma: no cover - defensive
                        _LOGGER.exception("Validation JSON parse error")
                        error = "cannot_connect"
                    else:
                        if not data.get("dailyInfo"):
                            _LOGGER.warning("Validation: 'dailyInfo' missing")
                            error = "cannot_connect"
        except aiohttp.ClientError:
            _LOGGER.exception("Validation client error")
            error = "cannot_connect"
        except Exception:  # pragma: no cover - defensive
            _LOGGER.exception("Unexpected validation error")
            error = "cannot_connect"

        return error

    def _maybe_set_unique_id_from_coords(self, user_input: dict[str, Any]) -> None:
        """Derive stable unique_id from (lat, lon); ignore failures."""
        try:
            lat = float(user_input[CONF_LATITUDE])
            lon = float(user_input[CONF_LONGITUDE])
            # Note: async_set_unique_id is awaited in the step method.
            # We only format here.
            uid = f"{lat:.4f}_{lon:.4f}"
        except Exception:  # pragma: no cover - defensive
            return

        async def _set():
            try:
                await self.async_set_unique_id(uid)
                self._abort_if_unique_id_configured()
            except Exception:  # pragma: no cover - defensive
                # Avoid blocking the flow if unique id couldn't be set
                pass

        # Schedule the awaitable into the step method using create_task from caller.
        # We'll call this helper only inside the step where we can await.
        self._pending_uid = _set  # type: ignore[attr-defined]

    # ----------------------------------------- Steps ------------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial configuration step."""
        errors: dict[str, str] = {}

        if user_input:
            # Unique ID (stable by coordinates)
            self._maybe_set_unique_id_from_coords(user_input)
            if getattr(self, "_pending_uid", None):
                await self._pending_uid()  # type: ignore[misc]
                self._pending_uid = None  # type: ignore[attr-defined]

            # Validate language format first (cheap, UI-friendly)
            try:
                is_valid_language_code(user_input[CONF_LANGUAGE_CODE])
            except vol.Invalid as ve:
                errors[CONF_LANGUAGE_CODE] = str(ve)

            # Online validation only when no language errors
            if not errors:
                api_key = user_input[CONF_API_KEY]
                lat = float(user_input[CONF_LATITUDE])
                lon = float(user_input[CONF_LONGITUDE])
                lang = user_input[CONF_LANGUAGE_CODE] or "en"

                base_err = await self._validate_online(
                    api_key=api_key, lat=lat, lon=lon, lang=lang
                )
                if base_err:
                    errors["base"] = base_err

            # Create entry when everything is fine
            if not errors:
                return self.async_create_entry(title="Pollen Levels", data=user_input)

        # Defaults from HA config
        defaults = {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_LANGUAGE_CODE: self.hass.config.language or "en",
        }

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Optional(
                    CONF_LATITUDE, default=defaults[CONF_LATITUDE]
                ): cv.latitude,
                vol.Optional(
                    CONF_LONGITUDE, default=defaults[CONF_LONGITUDE]
                ): cv.longitude,
                vol.Optional(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Optional(
                    CONF_LANGUAGE_CODE, default=defaults[CONF_LANGUAGE_CODE]
                ): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class PollenLevelsOptionsFlow(config_entries.OptionsFlow):
    """Options: update interval, language, forecast days, per-day sensors for TYPES."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Display and process options form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Language optional: if filled, validate
                lang = user_input.get(
                    CONF_LANGUAGE_CODE,
                    self.entry.options.get(
                        CONF_LANGUAGE_CODE, self.entry.data.get(CONF_LANGUAGE_CODE, "")
                    ),
                )
                if isinstance(lang, str) and lang.strip():
                    is_valid_language_code(lang)

                # Forecast days: range validation (avoid magic numbers)
                days = int(
                    user_input.get(
                        CONF_FORECAST_DAYS,
                        self.entry.options.get(
                            CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS
                        ),
                    )
                )
                if days < MIN_FORECAST_DAYS or days > MAX_FORECAST_DAYS:
                    raise vol.Invalid("invalid_days")

                # CFS validation per days (values are "none" | "D+1" | "D+1+2")
                cfs = user_input.get(
                    CONF_CREATE_FORECAST_SENSORS,
                    self.entry.options.get(
                        CONF_CREATE_FORECAST_SENSORS, DEFAULT_CREATE_FORECAST_SENSORS
                    ),
                )
                if cfs not in ALLOWED_CFS:
                    raise vol.Invalid("invalid_cfs")
                if cfs == "D+1" and days < MIN_DAYS_FOR_D1:
                    errors[CONF_CREATE_FORECAST_SENSORS] = "requires_days_2"
                if cfs == "D+1+2" and days < MIN_DAYS_FOR_D12:
                    errors[CONF_CREATE_FORECAST_SENSORS] = "requires_days_3"

            except vol.Invalid as ve:
                # Map non-field-specific errors
                if str(ve) in ("invalid_days", "invalid_cfs"):
                    errors["base"] = str(ve)
                else:
                    errors[CONF_LANGUAGE_CODE] = str(ve)
            except Exception:  # pragma: no cover - defensive
                _LOGGER.exception("Options validation error")
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Defaults (prefer options) — defensively coerce unknown values to 'none'
        current_interval = self.entry.options.get(
            CONF_UPDATE_INTERVAL,
            self.entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        current_lang = self.entry.options.get(
            CONF_LANGUAGE_CODE,
            self.entry.data.get(CONF_LANGUAGE_CODE, self.hass.config.language),
        )
        current_days = self.entry.options.get(CONF_FORECAST_DAYS, DEFAULT_FORECAST_DAYS)
        raw_cfs = self.entry.options.get(
            CONF_CREATE_FORECAST_SENSORS, DEFAULT_CREATE_FORECAST_SENSORS
        )
        current_cfs = (
            raw_cfs if raw_cfs in ALLOWED_CFS else DEFAULT_CREATE_FORECAST_SENSORS
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=current_interval
                    ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                    vol.Optional(CONF_LANGUAGE_CODE, default=current_lang): str,
                    vol.Optional(
                        CONF_FORECAST_DAYS, default=current_days
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_FORECAST_DAYS, max=MAX_FORECAST_DAYS),
                    ),
                    vol.Optional(
                        CONF_CREATE_FORECAST_SENSORS, default=current_cfs
                    ): vol.In(tuple(ALLOWED_CFS)),
                }
            ),
            errors=errors,
        )
