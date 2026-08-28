from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db import SnapshotStore
from app.export_events import position_events_all


def test_position_event_export_query_is_not_capped_at_500(tmp_path: Path) -> None:
    path = tmp_path / "monitor.db"
    SnapshotStore(path)

    rows = [
        (
            f"2026-08-28T12:{index // 60:02d}:{index % 60:02d}+00:00",
            "MSFT_US_EQ",
            "Microsoft",
            "ADD",
            float(index),
            float(index + 1),
            1.0,
            500.0,
            "USD",
        )
        for index in range(501)
    ]

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
