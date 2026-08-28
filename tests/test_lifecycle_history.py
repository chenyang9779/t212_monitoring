from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import SnapshotStore
from app.lifecycle_history import position_events_all


def test_lifecycle_event_query_is_not_capped_at_500(tmp_path: Path) -> None:
    path = tmp_path / "monitor.db"
    SnapshotStore(path)
    base = datetime.now(timezone.utc) - timedelta(minutes=10)

    rows = []
    for index in range(501):
        ts = (base + timedelta(seconds=index)).isoformat()
        rows.append(
            (
                ts,
                "ABC",
                "ABC",
                "OPEN" if index == 0 else "ADD",
                float(index),
                float(index + 1),
                1.0,
                10.0,
                "GBP",
            )
        )

    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO position_events (
                ts, ticker, name, event_type, quantity_before,
                quantity_after, delta_quantity, current_price, currency
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    result = position_events_all(path)
    assert len(result) == 501
    assert result[0]["id"] == 1
    assert result[-1]["id"] == 501
