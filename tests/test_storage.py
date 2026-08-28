from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import SnapshotStore
from app.storage import database_status, prune_raw_data


def _insert_raw_rows(path: Path) -> None:
    old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    new_ts = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as conn:
        for ts in (old_ts, new_ts):
            conn.execute(
                """
                INSERT INTO account_snapshots (
                    ts, currency, total_value, available_to_trade,
                    investments_current_value, investments_total_cost,
                    realized_pl, unrealized_pl, unrealized_pl_pct, raw_json
                ) VALUES (?, 'GBP', 100, 50, 50, 50, 0, 0, 0, '{}')
                """,
                (ts,),
            )
            conn.execute(
                """
                INSERT INTO position_snapshots (
                    ts, ticker, name, currency, quantity, average_price,
                    current_price, cost_local, market_value_local,
                    pnl_local, pnl_pct, raw_json
                ) VALUES (?, 'ABC', 'ABC', 'GBP', 1, 10, 10, 10, 10, 0, 0, '{}')
                """,
                (ts,),
            )
            conn.execute(
                """
                INSERT INTO market_quotes (ts, ticker, isin, name, currency, price, source)
                VALUES (?, 'ABC', '', 'ABC', 'GBP', 10, 't212_position')
                """,
                (ts,),
            )
        conn.execute(
            """
            INSERT INTO position_events (
                ts, ticker, name, event_type, quantity_before,
                quantity_after, delta_quantity, current_price, currency
            ) VALUES (?, 'ABC', 'ABC', 'OPEN', 0, 1, 1, 10, 'GBP')
            """,
            (old_ts,),
        )


def test_database_status_reports_rows_and_retention(tmp_path: Path) -> None:
    path = tmp_path / "monitor.db"
    SnapshotStore(path)
    _insert_raw_rows(path)

    status = database_status(path, retention_days=7)
    tables = {item["table"]: item for item in status["tables"]}

    assert status["retention_enabled"] is True
    assert status["retention_days"] == 7
    assert tables["account_snapshots"]["rows"] == 2
    assert tables["position_snapshots"]["rows"] == 2
    assert tables["market_quotes"]["rows"] == 2
    assert tables["position_events"]["retention_managed"] is False


def test_prune_raw_data_preserves_audit_events(tmp_path: Path) -> None:
    path = tmp_path / "monitor.db"
    SnapshotStore(path)
    _insert_raw_rows(path)

    result = prune_raw_data(path, retention_days=7)
    status = database_status(path, retention_days=7)
    tables = {item["table"]: item for item in status["tables"]}

    assert result["deleted_total"] == 3
    assert tables["account_snapshots"]["rows"] == 1
    assert tables["position_snapshots"]["rows"] == 1
    assert tables["market_quotes"]["rows"] == 1
    assert tables["position_events"]["rows"] == 1
