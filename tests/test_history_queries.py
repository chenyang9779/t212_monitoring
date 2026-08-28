from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import SnapshotStore
from app.event_queries import position_events_all, position_events_page
from app.history_queries import (
    account_history_all,
    account_history_recent,
    account_snapshot_count,
    account_snapshot_timestamps,
    position_history_all,
    position_history_recent,
    position_snapshot_count,
)


def _seed_history(path: Path) -> list[str]:
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
                ) VALUES (?, 'GBP', ?, 50, ?, 50, 0, ?, ?, '{}')
                """,
                (ts, 100 + index, 50 + index, index, index / 10),
            )
            conn.execute(
                """
                INSERT INTO position_snapshots (
                    ts, ticker, name, currency, quantity, average_price,
                    current_price, cost_local, market_value_local,
                    pnl_local, pnl_pct, raw_json
                ) VALUES (?, 'ABC', 'ABC', 'GBP', 1, 10, ?, 10, ?, ?, ?, '{}')
                """,
                (ts, 10 + index, 10 + index, index, index / 10),
            )
            conn.execute(
                """
                INSERT INTO position_events (
                    ts, ticker, name, event_type, quantity_before,
                    quantity_after, delta_quantity, current_price, currency
                ) VALUES (?, 'ABC', 'ABC', ?, ?, ?, 1, 10, 'GBP')
                """,
                (ts, "OPEN" if index == 0 else "ADD", index, index + 1),
            )

    return timestamps


def test_complete_history_queries_are_not_ui_limited(tmp_path: Path) -> None:
    path = tmp_path / "monitor.db"
    SnapshotStore(path)
    timestamps = _seed_history(path)

    assert account_snapshot_count(path, hours=1) == 4
    assert position_snapshot_count(path, ticker="ABC", hours=1) == 4
    assert [row["ts"] for row in account_snapshot_timestamps(path, hours=1)] == timestamps
    assert [row["ts"] for row in account_history_all(path, hours=1)] == timestamps
    assert [row["ts"] for row in position_history_all(path, ticker="ABC", hours=1)] == timestamps


def test_recent_history_queries_keep_newest_rows_and_chronological_order(tmp_path: Path) -> None:
    path = tmp_path / "monitor.db"
    SnapshotStore(path)
    timestamps = _seed_history(path)

    account_rows = account_history_recent(path, hours=1, limit=2)
    position_rows = position_history_recent(path, ticker="ABC", hours=1, limit=2)

    assert [row["ts"] for row in account_rows] == timestamps[-2:]
    assert [row["ts"] for row in position_rows] == timestamps[-2:]


def test_position_event_keyset_pagination_and_complete_log(tmp_path: Path) -> None:
    path = tmp_path / "monitor.db"
    SnapshotStore(path)
    _seed_history(path)

    first = position_events_page(path, limit=2)
    assert [item["id"] for item in first["items"]] == [4, 3]
    assert first["has_more"] is True
    assert first["next_before_id"] == 3

    second = position_events_page(path, limit=2, before_id=first["next_before_id"])
    assert [item["id"] for item in second["items"]] == [2, 1]
    assert second["has_more"] is False
    assert second["next_before_id"] is None

    assert [item["id"] for item in position_events_all(path)] == [1, 2, 3, 4]
