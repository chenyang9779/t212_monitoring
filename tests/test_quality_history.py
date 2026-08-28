from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import SnapshotStore
from app.quality_history import account_snapshot_timestamps


def test_quality_timestamp_query_returns_complete_requested_window(tmp_path: Path) -> None:
    path = tmp_path / "monitor.db"
    SnapshotStore(path)
    base = datetime.now(timezone.utc) - timedelta(minutes=4)
    timestamps = [(base + timedelta(minutes=index)).isoformat() for index in range(4)]

    with sqlite3.connect(path) as conn:
        for index, ts in enumerate(timestamps):
            conn.execute(
                """
                INSERT INTO account_snapshots (
                    ts, currency, total_value, available_to_trade,
                    investments_current_value, investments_total_cost,
                    realized_pl, unrealized_pl, unrealized_pl_pct, raw_json
                ) VALUES (?, 'GBP', ?, 50, 50, 50, 0, 0, 0, '{}')
                """,
                (ts, 100 + index),
            )

    result = account_snapshot_timestamps(path, hours=1)
    assert [row["ts"] for row in result] == timestamps
