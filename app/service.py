from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .db import SnapshotStore
from .metrics import normalize_account, normalize_position
from .storage import prune_raw_data
from .t212 import Trading212Client, Trading212Error


@dataclass
class MonitorState:
    account: dict[str, Any] | None = None
    positions: list[dict[str, Any]] = field(default_factory=list)
    last_sync: str | None = None
    last_error: str | None = None
    account_rate_limit: dict[str, str] = field(default_factory=dict)
    positions_rate_limit: dict[str, str] = field(default_factory=dict)
    last_maintenance: str | None = None
    maintenance_error: str | None = None
    maintenance_deleted_total: int = 0


class MonitorService:
    def __init__(self, settings: Settings, store: SnapshotStore) -> None:
        self.settings = settings
        self.store = store
        self.state = MonitorState()
        self._client: Trading212Client | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._last_snapshot_monotonic = 0.0
        self._last_maintenance_monotonic = 0.0
        self._active_alert_keys: set[str] = set()
        self._previous_positions: dict[str, dict[str, Any]] | None = None

    async def start(self) -> None:
        self._stop.clear()
        try:
            self._client = Trading212Client(self.settings)
        except Exception as exc:
            self.state.last_error = str(exc)
            return
        self._task = asyncio.create_task(self._run(), name="t212-monitor")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.close()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            started = loop.time()
            try:
                assert self._client is not None
                account_response = await self._client.get_account_summary()
                positions_response = await self._client.get_positions()
                now = datetime.now(timezone.utc).isoformat()
                account = normalize_account(account_response.data)
                positions = [normalize_position(p) for p in positions_response.data]

                await self._record_position_events(now, positions)

                self.state.account = account
                self.state.positions = positions
                self.state.last_sync = now
                self.state.last_error = None
                self.state.account_rate_limit = account_response.rate_limit
                self.state.positions_rate_limit = positions_response.rate_limit

                if loop.time() - self._last_snapshot_monotonic >= self.settings.snapshot_seconds:
                    await asyncio.to_thread(self.store.save_snapshot, now, account, positions)
                    self._last_snapshot_monotonic = loop.time()

                await self._run_storage_maintenance(loop.time())
                await self._evaluate_alerts(now, account, positions)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.state.last_error = str(exc)

            elapsed = loop.time() - started
            sleep_for = max(0.2, self.settings.poll_seconds - elapsed)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=sleep_for)
            except asyncio.TimeoutError:
                pass

    async def _run_storage_maintenance(self, monotonic_now: float) -> None:
        retention_days = self.settings.raw_retention_days
        if retention_days is None:
            return
        # Run once shortly after startup and then at most every six hours.
        if self._last_maintenance_monotonic and monotonic_now - self._last_maintenance_monotonic < 21600:
            return

        self._last_maintenance_monotonic = monotonic_now
        try:
            result = await asyncio.to_thread(
                prune_raw_data,
                self.store.path,
                retention_days,
            )
            self.state.last_maintenance = datetime.now(timezone.utc).isoformat()
            self.state.maintenance_error = None
            self.state.maintenance_deleted_total = int(result.get("deleted_total") or 0)
        except Exception as exc:
            # Retention failures must not make portfolio monitoring appear disconnected.
            self.state.maintenance_error = str(exc)

    async def _record_position_events(
        self,
        now: str,
        positions: list[dict[str, Any]],
    ) -> None:
        current = {position["ticker"]: position for position in positions}

        if self._previous_positions is None:
            self._previous_positions = current
            return

        previous = self._previous_positions
        epsilon = 1e-12

        for ticker in sorted(set(previous) | set(current)):
            before_position = previous.get(ticker)
            after_position = current.get(ticker)
            quantity_before = float(before_position["quantity"]) if before_position else 0.0
            quantity_after = float(after_position["quantity"]) if after_position else 0.0
            delta = quantity_after - quantity_before

            if abs(delta) <= epsilon:
                continue

            if quantity_before <= epsilon and quantity_after > epsilon:
                event_type = "OPEN"
            elif quantity_before > epsilon and quantity_after <= epsilon:
                event_type = "CLOSE"
            elif delta > 0:
                event_type = "ADD"
            else:
                event_type = "REDUCE"

            reference = after_position or before_position
            assert reference is not None
            await asyncio.to_thread(
                self.store.add_position_event,
                now,
                ticker,
                reference["name"],
                event_type,
                quantity_before,
                quantity_after,
                delta,
                reference.get("current_price"),
                reference.get("currency") or "",
            )

        self._previous_positions = current

    async def _evaluate_alerts(
        self,
        now: str,
        account: dict[str, Any],
        positions: list[dict[str, Any]],
    ) -> None:
        triggered: dict[str, tuple[str, str, str | None, dict[str, Any]]] = {}

        threshold = self.settings.position_loss_alert_pct
        if threshold is not None:
            for position in positions:
                pnl_pct = position.get("pnl_pct")
                if pnl_pct is not None and pnl_pct <= -threshold:
                    key = f"position_loss:{position['ticker']}"
                    triggered[key] = (
                        "warning",
                        f"{position['ticker']} unrealized return is {pnl_pct:.2f}%",
                        position["ticker"],
                        {"pnl_pct": pnl_pct, "threshold": threshold},
                    )

        total_threshold = self.settings.total_loss_alert_pct
        total_pnl_pct = account.get("unrealized_pl_pct")
        if (
            total_threshold is not None
            and total_pnl_pct is not None
            and total_pnl_pct <= -total_threshold
        ):
            triggered["portfolio_loss"] = (
                "critical",
                f"Portfolio unrealized return is {total_pnl_pct:.2f}%",
                None,
                {"pnl_pct": total_pnl_pct, "threshold": total_threshold},
            )

        for key, (severity, message, ticker, payload) in triggered.items():
            if key not in self._active_alert_keys:
                await asyncio.to_thread(
                    self.store.add_alert,
                    now,
                    severity,
                    key.split(":", 1)[0],
                    message,
                    ticker,
                    payload,
                )

        self._active_alert_keys = set(triggered)

    def latest(self) -> dict[str, Any]:
        return {
            "account": self.state.account,
            "positions": self.state.positions,
            "last_sync": self.state.last_sync,
            "last_error": self.state.last_error,
        }

    def status(self) -> dict[str, Any]:
        return {
            "environment": self.settings.environment,
            "poll_seconds": self.settings.poll_seconds,
            "snapshot_seconds": self.settings.snapshot_seconds,
            "last_sync": self.state.last_sync,
            "last_error": self.state.last_error,
            "connected": self.state.last_sync is not None and self.state.last_error is None,
            "account_rate_limit": self.state.account_rate_limit,
            "positions_rate_limit": self.state.positions_rate_limit,
            "raw_retention_days": self.settings.raw_retention_days,
            "last_maintenance": self.state.last_maintenance,
            "maintenance_error": self.state.maintenance_error,
            "maintenance_deleted_total": self.state.maintenance_deleted_total,
        }

    def _require_client(self) -> Trading212Client:
        if self._client is None:
            raise Trading212Error("Trading 212 client is not initialized")
        return self._client

    async def pending_orders(self) -> dict[str, Any]:
        try:
            response = await self._require_client().get_pending_orders()
            data = response.data if isinstance(response.data, list) else []
            return {"available": True, "items": data, "error": None}
        except Trading212Error as exc:
            return {
                "available": False,
                "items": [],
                "error": str(exc),
                "status_code": exc.status_code,
            }

    async def historical_orders(
        self,
        limit: int = 50,
        ticker: str | None = None,
        next_page_path: str | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._require_client().get_historical_orders(
                limit=limit,
                ticker=ticker,
                next_page_path=next_page_path,
            )
            payload = response.data if isinstance(response.data, dict) else {}
            return {
                "available": True,
                "items": payload.get("items") or [],
                "next_page_path": payload.get("nextPagePath"),
                "error": None,
            }
        except Trading212Error as exc:
            return {
                "available": False,
                "items": [],
                "next_page_path": None,
                "error": str(exc),
                "status_code": exc.status_code,
            }

    async def transactions(
        self,
        limit: int = 50,
        next_page_path: str | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._require_client().get_transactions(
                limit=limit,
                next_page_path=next_page_path,
            )
            payload = response.data if isinstance(response.data, dict) else {}
            return {
                "available": True,
                "items": payload.get("items") or [],
                "next_page_path": payload.get("nextPagePath"),
                "error": None,
            }
        except Trading212Error as exc:
            return {
                "available": False,
                "items": [],
                "next_page_path": None,
                "error": str(exc),
                "status_code": exc.status_code,
            }
