from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import SnapshotStore
from app.drawdown_history import account_drawdown_history, position_drawdown_history


def test_drawdown_history_queries_return_complete_window(tmp_path: Path) -> None:
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
                ) VALUES (?, 'GBP', 100, 50, 50, 50, 0, 0, ?, '{}')
                """,
                (ts, index * 1.5),
            )
            conn.execute(
                """
                INSERT INTO position_snapshots (
                    ts, ticker, name, currency, quantity, average_price,
                    current_price, cost_local, market_value_local,
                    pnl_local, pnl_pct, raw_json
                ) VALUES (?, 'ABC', 'ABC', 'GBP', 1, 10, 10, 10, 10, 0, ?, '{}')
                """,
                (ts, index * 2.0),
            )

    account = account_drawdown_history(path, hours=1)
    position = position_drawdown_history(path, ticker="ABC", hours=1)

    assert [row["ts"] for row in account] == timestamps
    assert [row["unrealized_pl_pct"] for row in account] == [0.0, 1.5, 3.0, 4.5]
    assert [row["ts"] for row in position] == timestamps
    assert [row["pnl_pct"] for row in position] == [0.0, 2.0, 4.0, 6.0]
