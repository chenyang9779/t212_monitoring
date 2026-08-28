from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class SnapshotStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS account_snapshots (
                    ts TEXT PRIMARY KEY,
                    currency TEXT NOT NULL,
                    total_value REAL,
                    available_to_trade REAL,
                    investments_current_value REAL,
                    investments_total_cost REAL,
                    realized_pl REAL,
                    unrealized_pl REAL,
                    unrealized_pl_pct REAL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS position_snapshots (
                    ts TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    name TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    average_price REAL,
                    current_price REAL,
                    cost_local REAL,
                    market_value_local REAL,
                    pnl_local REAL,
                    pnl_pct REAL,
                    raw_json TEXT NOT NULL,
                    PRIMARY KEY (ts, ticker)
                );

                CREATE INDEX IF NOT EXISTS idx_position_snapshots_ticker_ts
                ON position_snapshots (ticker, ts DESC);

                CREATE TABLE IF NOT EXISTS position_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    quantity_before REAL NOT NULL,
                    quantity_after REAL NOT NULL,
                    delta_quantity REAL NOT NULL,
                    current_price REAL,
                    currency TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_position_events_ts
                ON position_events (ts DESC);

                CREATE INDEX IF NOT EXISTS idx_position_events_ticker_ts
                ON position_events (ticker, ts DESC);

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    rule TEXT NOT NULL,
                    ticker TEXT,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts DESC);
                """
            )

    def save_snapshot(
        self,
        ts: str,
        account: dict[str, Any],
        positions: list[dict[str, Any]],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO account_snapshots (
                    ts, currency, total_value, available_to_trade,
                    investments_current_value, investments_total_cost,
                    realized_pl, unrealized_pl, unrealized_pl_pct, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    account["currency"],
                    account["total_value"],
                    account["available_to_trade"],
                    account["investments_current_value"],
                    account["investments_total_cost"],
                    account["realized_pl"],
                    account["unrealized_pl"],
                    account["unrealized_pl_pct"],
                    json.dumps(account["raw"], ensure_ascii=False),
                ),
            )
            conn.executemany(
                """
                INSERT OR REPLACE INTO position_snapshots (
                    ts, ticker, name, currency, quantity, average_price,
                    current_price, cost_local, market_value_local,
                    pnl_local, pnl_pct, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        ts,
                        p["ticker"],
                        p["name"],
                        p["currency"],
                        p["quantity"],
                        p["average_price"],
                        p["current_price"],
                        p["cost_local"],
                        p["market_value_local"],
                        p["pnl_local"],
                        p["pnl_pct"],
                        json.dumps(p["raw"], ensure_ascii=False),
                    )
                    for p in positions
                ],
            )

    def add_position_event(
        self,
        ts: str,
        ticker: str,
        name: str,
        event_type: str,
        quantity_before: float,
        quantity_after: float,
        delta_quantity: float,
        current_price: float | None,
        currency: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO position_events (
                    ts, ticker, name, event_type, quantity_before,
                    quantity_after, delta_quantity, current_price, currency
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    ticker,
                    name,
                    event_type,
                    quantity_before,
                    quantity_after,
                    delta_quantity,
                    current_price,
                    currency,
                ),
            )

    def position_events(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = min(max(limit, 1), 500)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, ticker, name, event_type, quantity_before,
                       quantity_after, delta_quantity, current_price, currency
                FROM position_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def position_events_since(
        self,
        hours: int = 24,
        ticker: str | None = None,
        limit: int = 100000,
    ) -> list[dict[str, Any]]:
        hours = min(max(hours, 1), 24 * 30)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            if ticker:
                rows = conn.execute(
                    """
                    SELECT id, ts, ticker, name, event_type, quantity_before,
                           quantity_after, delta_quantity, current_price, currency
                    FROM position_events
                    WHERE ts >= ? AND ticker = ?
                    ORDER BY ts ASC, id ASC
                    LIMIT ?
                    """,
                    (cutoff, ticker, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, ts, ticker, name, event_type, quantity_before,
                           quantity_after, delta_quantity, current_price, currency
                    FROM position_events
                    WHERE ts >= ?
                    ORDER BY ts ASC, id ASC
                    LIMIT ?
                    """,
                    (cutoff, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def add_alert(
        self,
        ts: str,
        severity: str,
        rule: str,
        message: str,
        ticker: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alerts (ts, severity, rule, ticker, message, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    severity,
                    rule,
                    ticker,
                    message,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )

    def history(self, hours: int = 24, limit: int = 1500) -> list[dict[str, Any]]:
        hours = min(max(hours, 1), 24 * 30)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ts, currency, total_value, available_to_trade,
                       investments_current_value, investments_total_cost,
                       realized_pl, unrealized_pl, unrealized_pl_pct
                FROM account_snapshots
                WHERE ts >= ?
                ORDER BY ts ASC
                LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def position_history(
        self,
        ticker: str,
        hours: int = 24,
        limit: int = 1500,
    ) -> list[dict[str, Any]]:
        hours = min(max(hours, 1), 24 * 30)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ts, ticker, name, currency, quantity, average_price,
                       current_price, cost_local, market_value_local,
                       pnl_local, pnl_pct
                FROM position_snapshots
                WHERE ticker = ? AND ts >= ?
                ORDER BY ts ASC
                LIMIT ?
                """,
                (ticker, cutoff, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = min(max(limit, 1), 500)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, severity, rule, ticker, message, payload_json
                FROM alerts
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result
