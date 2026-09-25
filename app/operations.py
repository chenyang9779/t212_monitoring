from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = _REQUEST_ID.get()
        if request_id:
            payload["request_id"] = request_id
        extra = getattr(record, "structured", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def configure_app_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("t212_monitor")
    logger.setLevel(level)
    logger.propagate = False
    if not any(getattr(handler, "_t212_json", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._t212_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    return logger


def resolve_request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    if candidate and _REQUEST_ID_RE.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def set_request_id(value: str):
    return _REQUEST_ID.set(value)


def reset_request_id(token: Any) -> None:
    _REQUEST_ID.reset(token)


def database_probe(path: Path) -> tuple[bool, str | None]:
    try:
        with sqlite3.connect(path, timeout=2) as conn:
            row = conn.execute("SELECT 1").fetchone()
        if not row or row[0] != 1:
            return False, "SQLite probe returned an unexpected result"
        return True, None
    except Exception as exc:
        return False, str(exc)


def startup_checks(
    *,
    db_path: Path,
    static_dir: Path,
    api_key: str,
    api_secret: str,
    demo_mode: bool = False,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []

    if not demo_mode and (not api_key or not api_secret):
        issues.append(
            {
                "severity": "critical",
                "code": "missing_credentials",
                "message": "T212_API_KEY and T212_API_SECRET must both be configured",
            }
        )

    if not static_dir.is_dir() or not (static_dir / "index.html").is_file():
        issues.append(
            {
                "severity": "critical",
                "code": "static_assets_missing",
                "message": "Dashboard static assets are missing",
            }
        )

    db_ok, db_error = database_probe(db_path)
    if not db_ok:
        issues.append(
            {
                "severity": "critical",
                "code": "database_unavailable",
                "message": db_error or "SQLite database is unavailable",
            }
        )

    return {
        "ok": not any(item["severity"] == "critical" for item in issues),
        "issues": issues,
        "database_ok": db_ok,
    }


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def readiness_status(
    *,
    monitor_status: dict[str, Any],
    db_path: Path,
    max_sync_age_seconds: float,
) -> dict[str, Any]:
    db_ok, db_error = database_probe(db_path)
    last_sync = _parse_utc(monitor_status.get("last_sync"))
    sync_age = (
        max(0.0, (datetime.now(timezone.utc) - last_sync).total_seconds())
        if last_sync
        else None
    )
    connected = bool(monitor_status.get("connected"))
    sync_fresh = sync_age is not None and sync_age <= max_sync_age_seconds

    reasons: list[str] = []
    if not db_ok:
        reasons.append("database_unavailable")
    if not connected:
        reasons.append("broker_not_connected")
    if not sync_fresh:
        reasons.append("broker_sync_stale")

    return {
        "ready": not reasons,
        "database_ok": db_ok,
        "database_error": db_error,
        "broker_connected": connected,
        "last_sync": monitor_status.get("last_sync"),
        "sync_age_seconds": sync_age,
        "max_sync_age_seconds": max_sync_age_seconds,
        "reasons": reasons,
    }


def request_log_payload(
    *,
    method: str,
    path: str,
    status_code: int,
    started_monotonic: float,
) -> dict[str, Any]:
    return {
        "event": "http_request",
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": round((time.monotonic() - started_monotonic) * 1000.0, 2),
    }
