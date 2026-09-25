from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .db import SnapshotStore
from .exposure import normalize_instrument_metadata
from .metrics import normalize_account, normalize_position
from .storage import prune_raw_data
from .streaming import EventBroker
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
    instrument_metadata: list[dict[str, Any]] = field(default_factory=list)
    instrument_metadata_refreshed_at: str | None = None
    instrument_metadata_error: str | None = None


class MonitorService:
    def __init__(
        self,
        settings: Settings,
        store: SnapshotStore,
        events: EventBroker | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.events = events
        self.state = MonitorState()
        self._client: Trading212Client | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._last_snapshot_monotonic = 0.0
        self._last_maintenance_monotonic = 0.0
        self._instrument_metadata_monotonic = 0.0
        self._active_alert_keys: set[str] = set()
        self._previous_positions: dict[str, dict[str, Any]] | None = None
        self._demo_mode = settings.demo_mode

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        if self.events is not None:
            self.events.publish(event, data)

    async def start(self) -> None:
        self._stop.clear()
        if self._demo_mode:
            # In demo mode we seed a synthetic portfolio and load state
            # directly from the local database.  No broker connection is made.
            await self._seed_demo()
            self.state.last_error = None
            return
        try:
            self._client = Trading212Client(self.settings)
        except Exception as exc:
            self.state.last_error = str(exc)
            self._publish("monitor_error", {"error": self.state.last_error})
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

    async def _seed_demo(self) -> None:
        """Seed the database with synthetic data and load the latest state."""

        def _do_seed() -> dict[str, Any] | None:
            from .demo import seed_demo_data

            seed_demo_data(self.store.path)
            # Return latest account from database so the dashboard has data
            rows = self.store.history(hours=1)
            if rows:
                return rows[-1]
            return None

        latest_row = await asyncio.to_thread(_do_seed)

        if latest_row is None:
            self.state.last_error = "Demo seed produced no account snapshot"
            self._publish("monitor_error", {"error": self.state.last_error})
            return

        self.state.account = latest_row
        self.state.last_sync = datetime.now(timezone.utc).isoformat()
        self.state.last_error = None

        # Load current positions from the database
        # (we query the most recent position snapshot per ticker)
        from .db import SnapshotStore

        pos_rows: list[dict[str, Any]] = []
        with sqlite3.connect(self.store.path, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            # Get the latest snapshot per ticker
            cur = conn.execute(
                """
                SELECT ts, ticker, name, currency, quantity, average_price,
                       current_price, cost_local, market_value_local,
                       pnl_local, pnl_pct
                FROM position_snapshots
                WHERE ts = (
                    SELECT MAX(ts) FROM position_snapshots ps2
                    WHERE ps2.ticker = position_snapshots.ticker
                )
                AND quantity > 0
                ORDER BY ticker
                """
            ).fetchall()
            for row in cur:
                pos_rows.append(dict(row))

        self.state.positions = pos_rows

        if self.events is not None:
            self._publish(
                "portfolio",
                {
                    "account": latest_row,
                    "positions": pos_rows,
                    "last_sync": self.state.last_sync,
                },
            )

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

                self._publish(
                    "portfolio",
                    {
                        "account": account,
                        "positions": positions,
                        "last_sync": now,
                    },
                )

                if loop.time() - self._last_snapshot_monotonic >= self.settings.snapshot_seconds:
                    await asyncio.to_thread(self.store.save_snapshot, now, account, positions)
                    self._last_snapshot_monotonic = loop.time()
                    self._publish(
                        "snapshot",
                        {
                            "ts": now,
                            "position_count": len(positions),
                        },
                    )

                await self._run_storage_maintenance(loop.time())
                await self._evaluate_alerts(now, account, positions)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.state.last_error = str(exc)
                self._publish("monitor_error", {"error": self.state.last_error})

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
            self._publish(
                "maintenance",
                {
                    "ts": self.state.last_maintenance,
                    "deleted_total": self.state.maintenance_deleted_total,
                },
            )
        except Exception as exc:
            self.state.maintenance_error = str(exc)
            self._publish("maintenance_error", {"error": self.state.maintenance_error})

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
            self._publish(
                "position_event",
                {
                    "ts": now,
                    "ticker": ticker,
                    "name": reference["name"],
                    "event_type": event_type,
                    "quantity_before": quantity_before,
                    "quantity_after": quantity_after,
                    "delta_quantity": delta,
                    "current_price": reference.get("current_price"),
                    "currency": reference.get("currency") or "",
                },
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
                self._publish(
                    "alert",
                    {
                        "ts": now,
                        "severity": severity,
                        "rule": key.split(":", 1)[0],
                        "ticker": ticker,
                        "message": message,
                        "payload": payload,
                    },
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
            "demo_mode": self._demo_mode,
            "poll_seconds": self.settings.poll_seconds,
            "snapshot_seconds": self.settings.snapshot_seconds,
            "last_sync": self.state.last_sync,
            "last_error": self.state.last_error,
            "connected": self.state.last_sync is not None
            and self.state.last_error is None,
            "account_rate_limit": self.state.account_rate_limit,
            "positions_rate_limit": self.state.positions_rate_limit,
            "raw_retention_days": self.settings.raw_retention_days,
            "last_maintenance": self.state.last_maintenance,
            "maintenance_error": self.state.maintenance_error,
            "maintenance_deleted_total": self.state.maintenance_deleted_total,
            "instrument_metadata_refreshed_at": self.state.instrument_metadata_refreshed_at,
            "instrument_metadata_error": self.state.instrument_metadata_error,
        }

    def _require_client(self) -> Trading212Client:
        if self._client is None:
            raise Trading212Error("Trading 212 client is not initialized")
        return self._client

    async def instruments_metadata(self, force: bool = False) -> dict[str, Any]:
        cache_seconds = 21600.0
        cache_fresh = (
            bool(self.state.instrument_metadata)
            and self._instrument_metadata_monotonic > 0
            and time.monotonic() - self._instrument_metadata_monotonic < cache_seconds
        )
        if cache_fresh and not force:
            return {
                "available": True,
                "items": self.state.instrument_metadata,
                "refreshed_at": self.state.instrument_metadata_refreshed_at,
                "stale": False,
                "error": None,
            }

        try:
            response = await self._require_client().get_instruments_metadata()
            raw_items = response.data if isinstance(response.data, list) else []
            items = [
                normalized
                for raw in raw_items
                if isinstance(raw, dict)
                for normalized in [normalize_instrument_metadata(raw)]
                if normalized is not None
            ]
            self.state.instrument_metadata = items
            self.state.instrument_metadata_refreshed_at = datetime.now(timezone.utc).isoformat()
            self.state.instrument_metadata_error = None
            self._instrument_metadata_monotonic = time.monotonic()
            return {
                "available": True,
                "items": items,
                "refreshed_at": self.state.instrument_metadata_refreshed_at,
                "stale": False,
                "error": None,
            }
        except Trading212Error as exc:
            self.state.instrument_metadata_error = str(exc)
            if self.state.instrument_metadata:
                return {
                    "available": True,
                    "items": self.state.instrument_metadata,
                    "refreshed_at": self.state.instrument_metadata_refreshed_at,
                    "stale": True,
                    "error": str(exc),
                    "status_code": exc.status_code,
                }
            return {
                "available": False,
                "items": [],
                "refreshed_at": None,
                "stale": False,
                "error": str(exc),
                "status_code": exc.status_code,
            }

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
