from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_MAX_HOURS = 24 * 30


def _cutoff(hours: int) -> str:
    bounded = min(max(int(hours), 1), _MAX_HOURS)
    return (datetime.now(timezone.utc) - timedelta(hours=bounded)).isoformat()


def account_drawdown_history(path: Path, hours: int = 24) -> list[dict[str, Any]]:
    """Return the complete account return series needed for drawdown analytics."""

    cutoff = _cutoff(hours)
    with sqlite3.connect(path, timeout=10) as conn:
        rows = conn.execute(
            """
            SELECT ts, unrealized_pl_pct
            FROM account_snapshots
            WHERE ts >= ?
            ORDER BY ts ASC
            """,
            (cutoff,),
        ).fetchall()
    return [{"ts": str(ts), "unrealized_pl_pct": pnl_pct} for ts, pnl_pct in rows]


def position_drawdown_history(
    path: Path,
    ticker: str,
    hours: int = 24,
) -> list[dict[str, Any]]:
    """Return the complete position return series needed for drawdown analytics."""

    cutoff = _cutoff(hours)
    with sqlite3.connect(path, timeout=10) as conn:
        rows = conn.execute(
            """
            SELECT ts, pnl_pct
            FROM position_snapshots
            WHERE ticker = ? AND ts >= ?
            ORDER BY ts ASC
            """,
            (ticker, cutoff),
        ).fetchall()
    return [{"ts": str(ts), "pnl_pct": pnl_pct} for ts, pnl_pct in rows]
