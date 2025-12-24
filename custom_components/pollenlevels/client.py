from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

try:  # pragma: no cover - fallback for environments with stubbed aiohttp
    from aiohttp import ContentTypeError
except ImportError:  # pragma: no cover - tests stub aiohttp without ContentTypeError
    ContentTypeError = ValueError  # type: ignore[misc,assignment]
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from .const import MAX_RETRIES, POLLEN_API_TIMEOUT, is_invalid_api_key_message
from .util import extract_error_message, redact_api_key

_LOGGER = logging.getLogger(__name__)


def _format_http_message(status: int, raw_message: str | None) -> str:
    """Format an HTTP status and optional message consistently."""

    if raw_message:
        return f"HTTP {status}: {raw_message}"
    return f"HTTP {status}"


class GooglePollenApiClient:
    """Thin async client wrapper for the Google Pollen API."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    def _parse_retry_after(self, retry_after_raw: str) -> float:
        """Translate a Retry-After header into a delay in seconds."""

        try:
            return float(retry_after_raw)
        except (TypeError, ValueError):
            retry_at = dt_util.parse_http_date(retry_after_raw)
            if retry_at is not None:
                delay = (retry_at - dt_util.utcnow()).total_seconds()
                if delay > 0:
                    return delay

        return 2.0

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

    async def async_fetch_pollen_data(
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
                async with self._session.get(
                    url,
                    params=params,
                    timeout=ClientTimeout(total=POLLEN_API_TIMEOUT),
                ) as resp:
                    if resp.status == 401:
                        raw_message = redact_api_key(
                            await extract_error_message(resp, default=""), self._api_key
                        )
                        message = _format_http_message(resp.status, raw_message or None)
                        raise ConfigEntryAuthFailed(message)

                    if resp.status == 403:
                        raw_message = redact_api_key(
                            await extract_error_message(resp, default=""), self._api_key
                        )
                        message = _format_http_message(resp.status, raw_message or None)
                        if is_invalid_api_key_message(raw_message):
                            raise ConfigEntryAuthFailed(message)
                        raise UpdateFailed(message)

                    if resp.status == 429:
                        if attempt < max_retries:
                            retry_after_raw = resp.headers.get("Retry-After")
                            delay = 2.0
                            if retry_after_raw:
                                delay = self._parse_retry_after(retry_after_raw)
                            delay = min(delay, 5.0) + random.uniform(0.0, 0.4)
                            _LOGGER.warning(
                                "Pollen API 429 — retrying in %.2fs (attempt %d/%d)",
                                delay,
                                attempt + 1,
                                max_retries,
                            )
                            await asyncio.sleep(delay)
                            continue
                        raw_message = redact_api_key(
                            await extract_error_message(resp, default=""), self._api_key
                        )
                        message = _format_http_message(resp.status, raw_message or None)
                        raise UpdateFailed(message)

                    if 500 <= resp.status <= 599:
                        if attempt < max_retries:
                            await self._async_backoff(
                                attempt=attempt,
                                max_retries=max_retries,
                                message=(
                                    "Pollen API HTTP %s — retrying in %.2fs "
                                    "(attempt %d/%d)"
                                ),
                                base_args=(resp.status,),
                            )
                            continue
                        raw_message = redact_api_key(
                            await extract_error_message(resp, default=""), self._api_key
                        )
                        message = _format_http_message(resp.status, raw_message or None)
                        raise UpdateFailed(message)

                    if 400 <= resp.status < 500 and resp.status not in (403, 429):
                        raw_message = redact_api_key(
                            await extract_error_message(resp, default=""), self._api_key
                        )
                        message = _format_http_message(resp.status, raw_message or None)
                        raise UpdateFailed(message)

                    if resp.status != 200:
                        raw_message = redact_api_key(
                            await extract_error_message(resp, default=""), self._api_key
                        )
                        message = _format_http_message(resp.status, raw_message or None)
                        raise UpdateFailed(message)

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

            except ConfigEntryAuthFailed:
                raise
            except TimeoutError as err:
                if attempt < max_retries:
                    await self._async_backoff(
                        attempt=attempt,
                        max_retries=max_retries,
                        message=(
                            "Pollen API timeout — retrying in %.2fs " "(attempt %d/%d)"
                        ),
                    )
                    continue
                msg = (
                    redact_api_key(err, self._api_key)
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
                msg = redact_api_key(err, self._api_key) or (
                    "Network error while calling the Google Pollen API"
                )
                raise UpdateFailed(msg) from err
            except UpdateFailed:
                raise
            except Exception as err:  # noqa: BLE001
                msg = redact_api_key(err, self._api_key)
                if not msg:
                    msg = "Unexpected error while calling the Google Pollen API"
                _LOGGER.error("Pollen API error: %s", msg)
                raise UpdateFailed(msg) from err
