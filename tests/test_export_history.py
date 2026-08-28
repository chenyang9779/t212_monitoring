from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import SnapshotStore
from app.export_history import account_history_all, position_history_all


def test_export_history_queries_are_not_capped_at_25000_rows(tmp_path: Path) -> None:
    path = tmp_path / "monitor.db"
    SnapshotStore(path)
    count = 25_001
    base = datetime.now(timezone.utc) - timedelta(hours=8)

    account_rows = []
    position_rows = []
    for index in range(count):
        ts = (base + timedelta(seconds=index)).isoformat()
        account_rows.append((ts, float(index)))
        position_rows.append((ts, float(index)))

    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO account_snapshots (
                ts, currency, total_value, available_to_trade,
                investments_current_value, investments_total_cost,
                realized_pl, unrealized_pl, unrealized_pl_pct, raw_json
            ) VALUES (?, 'GBP', ?, 50, 50, 50, 0, 0, 0, '{}')
            """,
            account_rows,
        )
        conn.executemany(
            """
            INSERT INTO position_snapshots (
                ts, ticker, name, currency, quantity, average_price,
                current_price, cost_local, market_value_local,
                pnl_local, pnl_pct, raw_json
            ) VALUES (?, 'TEST_US_EQ', 'Test', 'USD', 1, 10, ?, 10, 10, 0, 0, '{}')
            """,
            position_rows,
        )

    account = account_history_all(path, hours=24)
    position = position_history_all(path, ticker="TEST_US_EQ", hours=24)

    assert len(account) == count
    assert len(position) == count
    assert account[0]["ts"] < account[-1]["ts"]
    assert position[0]["ts"] < position[-1]["ts"]
