from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_MAX_HISTORY_HOURS = 24 * 30


def _cutoff(hours: int) -> str:
    bounded_hours = min(max(int(hours), 1), _MAX_HISTORY_HOURS)
    return (datetime.now(timezone.utc) - timedelta(hours=bounded_hours)).isoformat()


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def account_snapshot_timestamps(path: Path, hours: int = 24) -> list[dict[str, str]]:
    """Return every account-snapshot timestamp in the requested window.

    This deliberately has no UI-oriented row cap. Data-quality continuity checks
    need the complete timestamp series even when chart/history endpoints sample or
    limit richer rows.
    """

    cutoff = _cutoff(hours)
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT ts
            FROM account_snapshots
            WHERE ts >= ?
            ORDER BY ts ASC
            """,
            (cutoff,),
        ).fetchall()
    return [{"ts": str(row["ts"])} for row in rows]


def account_snapshot_count(path: Path, hours: int = 24) -> int:
    cutoff = _cutoff(hours)
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM account_snapshots WHERE ts >= ?",
            (cutoff,),
        ).fetchone()
    return int(row["count"] if row is not None else 0)


def position_snapshot_count(path: Path, ticker: str, hours: int = 24) -> int:
    cutoff = _cutoff(hours)
    with _connect(path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM position_snapshots
            WHERE ticker = ? AND ts >= ?
            """,
            (ticker, cutoff),
        ).fetchone()
    return int(row["count"] if row is not None else 0)


def account_history_all(path: Path, hours: int = 24) -> list[dict[str, Any]]:
    """Return complete account history for analytics/export consumers."""

    cutoff = _cutoff(hours)
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT ts, currency, total_value, available_to_trade,
                   investments_current_value, investments_total_cost,
                   realized_pl, unrealized_pl, unrealized_pl_pct
            FROM account_snapshots
            WHERE ts >= ?
            ORDER BY ts ASC
            """,
            (cutoff,),
        ).fetchall()
    return [dict(row) for row in rows]


def position_history_all(
    path: Path,
    ticker: str,
    hours: int = 24,
) -> list[dict[str, Any]]:
    """Return complete position history for analytics/export consumers."""

    cutoff = _cutoff(hours)
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT ts, ticker, name, currency, quantity, average_price,
                   current_price, cost_local, market_value_local,
                   pnl_local, pnl_pct
            FROM position_snapshots
            WHERE ticker = ? AND ts >= ?
            ORDER BY ts ASC
            """,
            (ticker, cutoff),
        ).fetchall()
    return [dict(row) for row in rows]
