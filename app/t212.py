from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings


class Trading212Error(RuntimeError):
    pass


@dataclass(frozen=True)
class ApiResponse:
    data: Any
    rate_limit: dict[str, str]


class Trading212Client:
    """Read-only Trading 212 client used by the monitoring service."""

    def __init__(self, settings: Settings) -> None:
        if not settings.api_key or not settings.api_secret:
            raise Trading212Error(
                "Missing T212_API_KEY or T212_API_SECRET. Put them in .env; do not hard-code them."
            )
        self._client = httpx.AsyncClient(
            base_url=settings.base_url,
            auth=(settings.api_key, settings.api_secret),
            headers={"Accept": "application/json", "User-Agent": "t212-position-monitor/1.0"},
            timeout=httpx.Timeout(12.0, connect=8.0),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str) -> ApiResponse:
        response = await self._client.get(path)
        if response.status_code == 429:
            reset = response.headers.get("x-ratelimit-reset")
            if reset:
                try:
                    wait = max(0.0, min(10.0, float(reset) - time.time()))
                    if wait:
                        await asyncio.sleep(wait)
                except ValueError:
                    pass
            raise Trading212Error("Trading 212 rate limit reached (HTTP 429)")
        if response.status_code in {401, 403}:
            raise Trading212Error(
                f"Trading 212 authentication/permission error (HTTP {response.status_code})"
            )
        if response.is_error:
            body = response.text[:500]
            raise Trading212Error(f"Trading 212 API error {response.status_code}: {body}")

        rate_limit = {
            key: value
            for key, value in response.headers.items()
            if key.lower().startswith("x-ratelimit-")
        }
        return ApiResponse(data=response.json(), rate_limit=rate_limit)

    async def get_account_summary(self) -> ApiResponse:
        return await self._get("/equity/account/summary")

    async def get_positions(self) -> ApiResponse:
        return await self._get("/equity/positions")
