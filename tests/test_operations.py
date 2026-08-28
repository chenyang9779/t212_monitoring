from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.operations import readiness_status, resolve_request_id, startup_checks


def test_request_id_accepts_safe_client_value() -> None:
    assert resolve_request_id("trace-123") == "trace-123"


def test_request_id_replaces_unsafe_value() -> None:
    value = resolve_request_id("bad request id with spaces")
    assert value != "bad request id with spaces"
    assert len(value) == 32


def test_startup_checks_report_missing_credentials(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("ok", encoding="utf-8")
    db_path = tmp_path / "monitor.db"
    db_path.touch()

    result = startup_checks(
        db_path=db_path,
        static_dir=static_dir,
        api_key="",
        api_secret="",
    )

    assert result["ok"] is False
    assert any(item["code"] == "missing_credentials" for item in result["issues"])


def test_readiness_requires_fresh_connected_sync(tmp_path: Path) -> None:
    db_path = tmp_path / "monitor.db"
    db_path.touch()
    now = datetime.now(timezone.utc)

    ready = readiness_status(
        monitor_status={
            "connected": True,
            "last_sync": (now - timedelta(seconds=5)).isoformat(),
        },
        db_path=db_path,
        max_sync_age_seconds=30,
    )
    assert ready["ready"] is True

    stale = readiness_status(
        monitor_status={
            "connected": True,
            "last_sync": (now - timedelta(minutes=5)).isoformat(),
        },
        db_path=db_path,
        max_sync_age_seconds=30,
    )
    assert stale["ready"] is False
    assert "broker_sync_stale" in stale["reasons"]
