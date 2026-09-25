from __future__ import annotations

import os
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str
    api_secret: str
    environment: str
    demo_mode: bool
    poll_seconds: float
    snapshot_seconds: float
    db_path: Path
    raw_retention_days: int | None
    position_loss_alert_pct: float | None
    total_loss_alert_pct: float | None

    @property
    def base_url(self) -> str:
        return f"https://{self.environment}.trading212.com/api/v0"


def _finite_float(name: str, raw: str) -> float:
    value = float(raw)
    if not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def _optional_float(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    value = _finite_float(name, raw)
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def _optional_positive_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    value = int(raw)
    if value < 1:
        raise ValueError(f"{name} must be >= 1 when configured")
    return value


def _read_env(name: str, default: str = "") -> str:
    """Read an environment variable after load_dotenv has run."""
    return os.getenv(name, default).strip()


def load_settings() -> Settings:
    # demo_mode must be checked BEFORE reading credentials, because
    # load_dotenv() (at module level) may have populated them from .env.
    demo_mode = _read_env("T212_DEMO", "").lower() == "true"

    if demo_mode:
        # Demo mode must never construct a Trading212Client, regardless of
        # what credentials are in .env or the environment.
        api_key = ""
        api_secret = ""
        environment = "demo"
        # Use a separate database so demo mode never overwrites live data
        db_path = Path(os.getenv("T212_DB_PATH", "data/demo-monitor.db"))
    else:
        api_key = _read_env("T212_API_KEY", "")
        api_secret = _read_env("T212_API_SECRET", "")
        environment = _read_env("T212_ENV", "demo")
        if environment not in {"demo", "live"}:
            raise ValueError("T212_ENV must be either 'demo' or 'live'")
        db_path = Path(os.getenv("T212_DB_PATH", "data/monitor.db"))

    poll_seconds = _finite_float(
        "T212_POLL_SECONDS",
        os.getenv("T212_POLL_SECONDS", "6"),
    )
    snapshot_seconds = _finite_float(
        "T212_SNAPSHOT_SECONDS",
        os.getenv("T212_SNAPSHOT_SECONDS", "30"),
    )
    if poll_seconds < 5:
        raise ValueError("T212_POLL_SECONDS must be >= 5 to respect the account-summary rate limit")
    if snapshot_seconds < poll_seconds:
        raise ValueError("T212_SNAPSHOT_SECONDS must be >= T212_POLL_SECONDS")

    return Settings(
        api_key=api_key,
        api_secret=api_secret,
        environment=environment,
        demo_mode=demo_mode,
        poll_seconds=poll_seconds,
        snapshot_seconds=snapshot_seconds,
        db_path=db_path,
        raw_retention_days=_optional_positive_int("T212_RAW_RETENTION_DAYS"),
        position_loss_alert_pct=_optional_float("T212_POSITION_LOSS_ALERT_PCT"),
        total_loss_alert_pct=_optional_float("T212_TOTAL_LOSS_ALERT_PCT"),
    )
