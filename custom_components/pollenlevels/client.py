from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from .const import POLLEN_API_TIMEOUT
from .util import redact_api_key

_LOGGER = logging.getLogger(__name__)


class GooglePollenApiClient:
    """Thin async client wrapper for the Google Pollen API."""

    def __init__(
        self, session: ClientSession, api_key: str, http_referrer: str | None = None
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._referrer = http_referrer

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

        headers = None
        if self._referrer:
            headers = {"Referer": self._referrer}

        max_retries = 1
        for attempt in range(0, max_retries + 1):
            try:
                async with self._session.get(
                    url,
                    params=params,
                    timeout=ClientTimeout(total=POLLEN_API_TIMEOUT),
                    headers=headers,
                ) as resp:
                    if resp.status in (401, 403):
                        auth_message = await self._extract_auth_message(resp)
                        raise ConfigEntryAuthFailed(auth_message or "Invalid API key")

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
                        raise UpdateFailed("Quota exceeded")

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
                        raise UpdateFailed(f"HTTP {resp.status}")

                    if 400 <= resp.status < 500 and resp.status not in (403, 429):
                        raise UpdateFailed(f"HTTP {resp.status}")

                    if resp.status != 200:
                        raise UpdateFailed(f"HTTP {resp.status}")

                    return await resp.json()

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
            except Exception as err:  # noqa: BLE001
                msg = redact_api_key(err, self._api_key)
                _LOGGER.error("Pollen API error: %s", msg)
                raise UpdateFailed(msg) from err

    async def _extract_auth_message(self, resp) -> str | None:
        """Extract a short authentication error message from the response."""

        raw_text = ""
        try:
            raw_text = await resp.text()
        except Exception:
            try:
                raw_bytes = await resp.read()
                raw_text = raw_bytes.decode(errors="ignore")
            except Exception:
                raw_text = ""

        redacted_text = redact_api_key(raw_text, self._api_key) if raw_text else ""
        message: str | None = None

        if redacted_text:
            try:
                data = json.loads(redacted_text)
            except Exception:
                data = None

            if isinstance(data, dict):
                error_obj = (
                    data.get("error") if isinstance(data.get("error"), dict) else None
                )
                message = None
                if error_obj is not None:
                    message = error_obj.get("message")
                if not message:
                    message = data.get("message")

            if not message:
                message = redacted_text.strip() or None

        if message and len(message) > 160:
            return message[:160]

        return message
