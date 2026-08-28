from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlparse

import httpx

from .config import Settings


class Trading212Error(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ApiResponse:
    data: Any
    rate_limit: dict[str, str]


def _pagination_params(next_page_path: str, expected_path: str) -> dict[str, str]:
    """Validate a Trading 212 nextPagePath and return only its query parameters."""

    parsed = urlparse(next_page_path)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise Trading212Error("Invalid Trading 212 pagination path")

    accepted_paths = {expected_path, f"/api/v0{expected_path}"}
    if parsed.path not in accepted_paths:
        raise Trading212Error("Trading 212 pagination path does not match the requested endpoint")

    return dict(parse_qsl(parsed.query, keep_blank_values=False))


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

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> ApiResponse:
        response = await self._client.get(path, params=params)
        if response.status_code == 429:
            reset = response.headers.get("x-ratelimit-reset")
            if reset:
                try:
                    wait = max(0.0, min(10.0, float(reset) - time.time()))
                    if wait:
                        await asyncio.sleep(wait)
                except ValueError:
                    pass
            raise Trading212Error("Trading 212 rate limit reached (HTTP 429)", 429)
        if response.status_code in {401, 403}:
            raise Trading212Error(
                f"Trading 212 authentication/permission error (HTTP {response.status_code})",
                response.status_code,
            )
        if response.is_error:
            body = response.text[:500]
            raise Trading212Error(
                f"Trading 212 API error {response.status_code}: {body}",
                response.status_code,
            )

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

    async def get_instruments_metadata(self) -> ApiResponse:
        return await self._get("/equity/metadata/instruments")

    async def get_exchanges_metadata(self) -> ApiResponse:
        return await self._get("/equity/metadata/exchanges")

    async def get_pending_orders(self) -> ApiResponse:
        return await self._get("/equity/orders")

    async def get_historical_orders(
        self,
        limit: int = 50,
        ticker: str | None = None,
        next_page_path: str | None = None,
    ) -> ApiResponse:
        path = "/equity/history/orders"
        if next_page_path:
            params: dict[str, Any] = _pagination_params(next_page_path, path)
        else:
            params = {"limit": min(max(limit, 1), 50)}
            if ticker:
                params["ticker"] = ticker
        return await self._get(path, params=params)

    async def get_transactions(
        self,
        limit: int = 50,
        next_page_path: str | None = None,
    ) -> ApiResponse:
        path = "/equity/history/transactions"
        params: dict[str, Any]
        if next_page_path:
            params = _pagination_params(next_page_path, path)
        else:
            params = {"limit": min(max(limit, 1), 50)}
        return await self._get(path, params=params)
