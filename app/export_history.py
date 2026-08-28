from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_MAX_HOURS = 24 * 30


def _cutoff(hours: int) -> str:
    bounded = min(max(int(hours), 1), _MAX_HOURS)
    return (datetime.now(timezone.utc) - timedelta(hours=bounded)).isoformat()


def account_history_all(path: Path, hours: int = 24) -> list[dict[str, Any]]:
    """Return the complete account-history export window without the UI row cap."""

    cutoff = _cutoff(hours)
    with sqlite3.connect(path, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
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
    """Return the complete position-history export window without the UI row cap."""

    cutoff = _cutoff(hours)
    with sqlite3.connect(path, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
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
