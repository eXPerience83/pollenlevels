from __future__ import annotations

import asyncio
import logging
import math
import random
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout, ContentTypeError
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from .const import MAX_RETRIES, POLLEN_API_TIMEOUT, is_invalid_api_key_message
from .util import extract_error_message, redact_sensitive_values

_LOGGER = logging.getLogger(__name__)
_DEFAULT_429_RETRY_DELAY = 2.0
_MAX_INLINE_RETRY_AFTER = 5.0


def _format_http_message(status: int, raw_message: str | None) -> str:
    """Format an HTTP status and optional message consistently."""

    cleaned = raw_message.strip() if raw_message else ""
    if cleaned:
        return f"HTTP {status}: {cleaned}"
    return f"HTTP {status}"


def _raise_auth_failed_if_invalid_api_key(
    raw_message: str | None, formatted_message: str
) -> None:
    """Raise an auth failure when the API response indicates an invalid key."""

    if is_invalid_api_key_message(raw_message):
        raise ConfigEntryAuthFailed(formatted_message)


class PollenQuotaExceededError(UpdateFailed):
    """Raised when the Google Pollen API quota is exceeded (HTTP 429).

    Inherits from UpdateFailed to stay compatible with existing client/coordinator
    error handling while still allowing explicit quota classification in config flow.
    """

    def __init__(
        self,
        *args: object,
        retry_after: float | None = None,
    ) -> None:
        """Initialize a quota error with an optional server-requested delay."""

        super().__init__(*args)
        self.retry_after = retry_after


class GooglePollenApiClient:
    """Thin async client wrapper for the Google Pollen API."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key
        self._request_lock = asyncio.Lock()
        self._quota_cooldown_until: float | None = None

    def _parse_retry_after(self, retry_after_raw: str) -> float | None:
        """Translate a usable Retry-After header into a delay in seconds."""

        try:
            parsed = float(retry_after_raw)
            if math.isfinite(parsed) and parsed > 0:
                return parsed
            return None
        except TypeError, ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after_raw)
            except TypeError, ValueError, IndexError, OverflowError:
                return None

            if retry_at is None or retry_at.tzinfo is None:
                return None

            delay = (retry_at - dt_util.utcnow()).total_seconds()
            if math.isfinite(delay) and delay > 0:
                return delay

        return None

    def _set_quota_cooldown(self, retry_after: float) -> None:
        """Record the longest active server-requested quota cooldown."""

        if not math.isfinite(retry_after) or retry_after <= 0:
            return

        deadline = monotonic() + retry_after
        if self._quota_cooldown_until is None or deadline > self._quota_cooldown_until:
            self._quota_cooldown_until = deadline

    def _quota_cooldown_remaining(self) -> float | None:
        """Return the active quota cooldown delay, clearing expired state."""

        if self._quota_cooldown_until is None:
            return None

        remaining = self._quota_cooldown_until - monotonic()
        if not math.isfinite(remaining) or remaining <= 0:
            self._quota_cooldown_until = None
            return None

        return remaining

    async def _async_backoff(
        self,
        *,
        attempt: int,
        max_retries: int,
        message: str,
        base_args: tuple[Any, ...] = (),
    ) -> None:
        """Log a retry warning with jittered backoff and sleep."""

        delay = 0.8 * (2**attempt) + random.uniform(0.0, 0.3)
        _LOGGER.warning(message, *base_args, delay, attempt + 1, max_retries)
        await asyncio.sleep(delay)

    def _redact_sensitive_message(
        self,
        value: object,
        *,
        latitude: float | str | None,
        longitude: float | str | None,
    ) -> str:
        """Redact sensitive values from messages surfaced by the API client."""

        return redact_sensitive_values(
            value,
            api_key=self._api_key,
            latitude=latitude,
            longitude=longitude,
        )

    async def _async_redacted_http_message(
        self,
        resp: Any,
        *,
        default: str,
        latitude: float | str | None,
        longitude: float | str | None,
    ) -> tuple[str, str]:
        """Extract, redact, and format an HTTP error response message."""

        raw_message = self._redact_sensitive_message(
            await extract_error_message(resp, default=default),
            latitude=latitude,
            longitude=longitude,
        )
        return raw_message, _format_http_message(resp.status, raw_message or None)

    async def async_fetch_pollen_data(
        self,
        *,
        latitude: float,
        longitude: float,
        days: int,
        language_code: str | None,
    ) -> dict[str, Any]:
        """Fetch pollen data while serializing requests through this client."""

        async with self._request_lock:
            if (retry_after := self._quota_cooldown_remaining()) is not None:
                _LOGGER.debug(
                    "Pollen API quota cooldown active — skipping request for %.2fs",
                    retry_after,
                )
                raise PollenQuotaExceededError(
                    "HTTP 429",
                    retry_after=retry_after,
                )

            return await self._async_fetch_pollen_data(
                latitude=latitude,
                longitude=longitude,
                days=days,
                language_code=language_code,
            )

    async def _async_fetch_pollen_data(
        self,
        *,
        latitude: float,
        longitude: float,
        days: int,
        language_code: str | None,
    ) -> dict[str, Any]:
        """Perform the HTTP call and return the decoded payload."""

        url = "https://pollen.googleapis.com/v1/forecast:lookup"
        params = {
            "key": self._api_key,
            "location.latitude": f"{latitude:.6f}",
            "location.longitude": f"{longitude:.6f}",
            "days": days,
        }
        if language_code:
            params["languageCode"] = language_code

        _LOGGER.debug(
            "Fetching forecast (days=%s, lang_set=%s)", days, bool(language_code)
        )

        max_retries = MAX_RETRIES
        for attempt in range(0, max_retries + 1):
            try:
                retry_429_delay: float | None = None
                retry_5xx_status: int | None = None
                quota_retry_after: float | None = None
                quota_error_message: str | None = None

                async with self._session.get(
                    url,
                    params=params,
                    timeout=ClientTimeout(total=POLLEN_API_TIMEOUT),
                ) as resp:
                    if resp.status == 401:
                        _, message = await self._async_redacted_http_message(
                            resp,
                            default="",
                            latitude=latitude,
                            longitude=longitude,
                        )
                        raise ConfigEntryAuthFailed(message)

                    if resp.status == 403:
                        raw_message, message = await self._async_redacted_http_message(
                            resp,
                            default="",
                            latitude=latitude,
                            longitude=longitude,
                        )
                        _raise_auth_failed_if_invalid_api_key(raw_message, message)
                        raise UpdateFailed(message)

                    if resp.status == 429:
                        retry_after_raw = resp.headers.get("Retry-After")
                        retry_after = (
                            self._parse_retry_after(retry_after_raw)
                            if retry_after_raw is not None
                            else None
                        )

                        if retry_after is not None and (
                            retry_after > _MAX_INLINE_RETRY_AFTER
                            or attempt >= max_retries
                        ):
                            (
                                _,
                                quota_error_message,
                            ) = await self._async_redacted_http_message(
                                resp,
                                default="",
                                latitude=latitude,
                                longitude=longitude,
                            )
                            quota_retry_after = retry_after
                        elif attempt < max_retries:
                            delay = (
                                retry_after
                                if retry_after is not None
                                else _DEFAULT_429_RETRY_DELAY
                            )
                            delay += random.uniform(0.0, 0.4)
                            retry_429_delay = max(
                                0.0,
                                min(delay, _MAX_INLINE_RETRY_AFTER),
                            )
                        else:
                            _, message = await self._async_redacted_http_message(
                                resp,
                                default="",
                                latitude=latitude,
                                longitude=longitude,
                            )
                            raise PollenQuotaExceededError(message)

                    elif 500 <= resp.status <= 599:
                        if attempt < max_retries:
                            retry_5xx_status = resp.status
                        else:
                            _, message = await self._async_redacted_http_message(
                                resp,
                                default="",
                                latitude=latitude,
                                longitude=longitude,
                            )
                            raise UpdateFailed(message)

                    elif 400 <= resp.status < 500 and resp.status not in (403, 429):
                        raw_message, message = await self._async_redacted_http_message(
                            resp,
                            default="",
                            latitude=latitude,
                            longitude=longitude,
                        )
                        _raise_auth_failed_if_invalid_api_key(raw_message, message)
                        raise UpdateFailed(message)

                    elif resp.status != 200:
                        _, message = await self._async_redacted_http_message(
                            resp,
                            default="",
                            latitude=latitude,
                            longitude=longitude,
                        )
                        raise UpdateFailed(message)

                    else:
                        try:
                            try:
                                payload = await resp.json(content_type=None)
                            except TypeError:
                                payload = await resp.json()
                        except (ContentTypeError, TypeError, ValueError) as err:
                            raise UpdateFailed(
                                "Unexpected API response: invalid JSON"
                            ) from err

                        if not isinstance(payload, dict):
                            raise UpdateFailed(
                                "Unexpected API response: expected JSON object"
                            )

                        return payload

                if quota_error_message is not None and quota_retry_after is not None:
                    self._set_quota_cooldown(quota_retry_after)
                    _LOGGER.warning(
                        "Pollen API 429 — deferring requests for %.2fs",
                        quota_retry_after,
                    )
                    raise PollenQuotaExceededError(
                        quota_error_message,
                        retry_after=quota_retry_after,
                    )

                if retry_429_delay is not None:
                    _LOGGER.warning(
                        "Pollen API 429 — retrying in %.2fs (attempt %d/%d)",
                        retry_429_delay,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(retry_429_delay)
                    continue

                if retry_5xx_status is not None:
                    await self._async_backoff(
                        attempt=attempt,
                        max_retries=max_retries,
                        message=(
                            "Pollen API HTTP %s — retrying in %.2fs (attempt %d/%d)"
                        ),
                        base_args=(retry_5xx_status,),
                    )
                    continue

            except ConfigEntryAuthFailed:
                raise
            except TimeoutError as err:
                if attempt < max_retries:
                    await self._async_backoff(
                        attempt=attempt,
                        max_retries=max_retries,
                        message=(
                            "Pollen API timeout — retrying in %.2fs (attempt %d/%d)"
                        ),
                    )
                    continue
                msg = (
                    self._redact_sensitive_message(
                        err, latitude=latitude, longitude=longitude
                    )
                    or "Google Pollen API call timed out"
                )
                raise UpdateFailed(f"Timeout: {msg}") from err
            except ClientError as err:
                if attempt < max_retries:
                    await self._async_backoff(
                        attempt=attempt,
                        max_retries=max_retries,
                        message=(
                            "Network error to Pollen API — retrying in %.2fs "
                            "(attempt %d/%d)"
                        ),
                    )
                    continue
                msg = (
                    self._redact_sensitive_message(
                        err, latitude=latitude, longitude=longitude
                    )
                    or "Network error while calling the Google Pollen API"
                )
                raise UpdateFailed(msg) from err
            except UpdateFailed:
                raise
            except Exception as err:  # noqa: BLE001
                msg = self._redact_sensitive_message(
                    err, latitude=latitude, longitude=longitude
                )
                if not msg:
                    msg = "Unexpected error while calling the Google Pollen API"
                _LOGGER.error("Pollen API error: %s", msg)
                raise UpdateFailed(msg) from err
