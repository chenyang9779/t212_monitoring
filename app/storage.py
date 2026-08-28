from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

RAW_RETENTION_TABLES = ("account_snapshots", "position_snapshots", "market_quotes")
REPORT_TABLES = (
    "account_snapshots",
    "position_snapshots",
    "market_quotes",
    "position_events",
    "alerts",
)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def database_status(path: Path, retention_days: int | None = None) -> dict[str, Any]:
    """Return SQLite size, row counts and time coverage without modifying data."""

    tables: list[dict[str, Any]] = []
    with _connect(path) as conn:
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])

        for table in REPORT_TABLES:
            row = conn.execute(
                f"SELECT COUNT(*) AS rows, MIN(ts) AS oldest_ts, MAX(ts) AS newest_ts FROM {table}"
            ).fetchone()
            tables.append(
                {
                    "table": table,
                    "rows": int(row["rows"]),
                    "oldest_ts": row["oldest_ts"],
                    "newest_ts": row["newest_ts"],
                    "retention_managed": table in RAW_RETENTION_TABLES,
                }
            )

    wal_path = Path(f"{path}-wal")
    shm_path = Path(f"{path}-shm")
    allocated_bytes = page_count * page_size
    reclaimable_bytes = freelist_count * page_size
    return {
        "db_path": str(path),
        "db_bytes": _file_size(path),
        "wal_bytes": _file_size(wal_path),
        "shm_bytes": _file_size(shm_path),
        "total_files_bytes": _file_size(path) + _file_size(wal_path) + _file_size(shm_path),
        "allocated_bytes": allocated_bytes,
        "reclaimable_bytes": reclaimable_bytes,
        "page_count": page_count,
        "page_size": page_size,
        "freelist_pages": freelist_count,
        "retention_enabled": retention_days is not None,
        "retention_days": retention_days,
        "retention_tables": list(RAW_RETENTION_TABLES),
        "tables": tables,
    }


def prune_raw_data(path: Path, retention_days: int) -> dict[str, Any]:
    """Delete high-frequency raw records older than the configured retention window.

    Position events and alerts are intentionally excluded because they are low-volume
    audit records used for lifecycle reconstruction and reconciliation.
    """

    if retention_days < 1:
        raise ValueError("retention_days must be >= 1")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    deleted: dict[str, int] = {}
    with _connect(path) as conn:
        for table in RAW_RETENTION_TABLES:
            cursor = conn.execute(f"DELETE FROM {table} WHERE ts < ?", (cutoff,))
            deleted[table] = max(int(cursor.rowcount), 0)
        conn.execute("PRAGMA optimize")

    return {
        "cutoff": cutoff,
        "retention_days": retention_days,
        "deleted": deleted,
        "deleted_total": sum(deleted.values()),
    }
