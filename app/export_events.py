from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def position_events_all(path: Path) -> list[dict[str, Any]]:
    """Return the complete local position-event log for export."""

    with sqlite3.connect(path, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, ts, ticker, name, event_type, quantity_before,
                   quantity_after, delta_quantity, current_price, currency
            FROM position_events
            ORDER BY id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]
