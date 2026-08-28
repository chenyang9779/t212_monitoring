from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def account_snapshot_timestamps(path: Path, hours: int = 24) -> list[dict[str, str]]:
    """Return the complete account-snapshot timestamp series for quality checks.

    Chart/history endpoints intentionally cap richer rows for UI responsiveness.
    Data-quality continuity checks only need timestamps, so this lightweight query
    reads the full requested window without inheriting the 25k chart-row limit.
    """

    hours = min(max(int(hours), 1), 168)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with sqlite3.connect(path, timeout=10) as conn:
        rows = conn.execute(
            """
            SELECT ts
            FROM account_snapshots
            WHERE ts >= ?
            ORDER BY ts ASC
            """,
            (cutoff,),
        ).fetchall()
    return [{"ts": str(row[0])} for row in rows]
