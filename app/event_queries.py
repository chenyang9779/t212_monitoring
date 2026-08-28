from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def position_events_page(
    path: Path,
    limit: int = 100,
    before_id: int | None = None,
) -> dict[str, Any]:
    """Return newest position events with keyset pagination metadata."""

    limit = min(max(int(limit), 1), 500)
    fetch_limit = limit + 1
    with _connect(path) as conn:
        if before_id is None:
            rows = conn.execute(
                """
                SELECT id, ts, ticker, name, event_type, quantity_before,
                       quantity_after, delta_quantity, current_price, currency
                FROM position_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (fetch_limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, ts, ticker, name, event_type, quantity_before,
                       quantity_after, delta_quantity, current_price, currency
                FROM position_events
                WHERE id < ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(before_id), fetch_limit),
            ).fetchall()

    has_more = len(rows) > limit
    visible = rows[:limit]
    items = [dict(row) for row in visible]
    next_before_id = items[-1]["id"] if has_more and items else None
    return {
        "items": items,
        "has_more": has_more,
        "next_before_id": next_before_id,
        "limit": limit,
    }


def position_events_all(path: Path) -> list[dict[str, Any]]:
    """Return the complete local event log in chronological order."""

    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT id, ts, ticker, name, event_type, quantity_before,
                   quantity_after, delta_quantity, current_price, currency
            FROM position_events
            ORDER BY id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def position_event_count(path: Path) -> int:
    with _connect(path) as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM position_events").fetchone()
    return int(row["count"] if row is not None else 0)
