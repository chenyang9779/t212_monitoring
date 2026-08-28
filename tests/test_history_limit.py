from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import SnapshotStore


def _timestamps() -> list[str]:
    now = datetime.now(timezone.utc)
    return [
        (now - timedelta(minutes=3)).isoformat(),
        (now - timedelta(minutes=2)).isoformat(),
        (now - timedelta(minutes=1)).isoformat(),
    ]


def test_history_limit_keeps_newest_rows_in_chronological_order(tmp_path):
    store = SnapshotStore(tmp_path / "monitor.db")
    timestamps = _timestamps()

    with store._connect() as conn:
        conn.executemany(
            """
            INSERT INTO account_snapshots (
                ts, currency, total_value, available_to_trade,
                investments_current_value, investments_total_cost,
                realized_pl, unrealized_pl, unrealized_pl_pct, raw_json
            ) VALUES (?, 'GBP', ?, 0, 0, 0, 0, 0, 0, '{}')
            """,
            [(ts, float(index)) for index, ts in enumerate(timestamps, start=1)],
        )

    rows = store.history(hours=1, limit=2)

    assert [row["ts"] for row in rows] == timestamps[-2:]
    assert [row["total_value"] for row in rows] == [2.0, 3.0]


def test_position_history_limit_keeps_newest_rows_in_chronological_order(tmp_path):
    store = SnapshotStore(tmp_path / "monitor.db")
    timestamps = _timestamps()

    with store._connect() as conn:
        conn.executemany(
            """
            INSERT INTO position_snapshots (
                ts, ticker, name, currency, quantity, average_price,
                current_price, cost_local, market_value_local,
                pnl_local, pnl_pct, raw_json
            ) VALUES (?, 'MSFT_US_EQ', 'Microsoft', 'USD', ?, 100, 110, 100, 110, 10, 10, '{}')
            """,
            [(ts, float(index)) for index, ts in enumerate(timestamps, start=1)],
        )

    rows = store.position_history(ticker="MSFT_US_EQ", hours=1, limit=2)

    assert [row["ts"] for row in rows] == timestamps[-2:]
    assert [row["quantity"] for row in rows] == [2.0, 3.0]
