from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str
    api_secret: str
    environment: str
    poll_seconds: float
    snapshot_seconds: float
    db_path: Path
    position_loss_alert_pct: float | None
    total_loss_alert_pct: float | None

    @property
    def base_url(self) -> str:
        return f"https://{self.environment}.trading212.com/api/v0"


def _optional_float(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    value = float(raw)
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def load_settings() -> Settings:
    api_key = os.getenv("T212_API_KEY", "").strip()
    api_secret = os.getenv("T212_API_SECRET", "").strip()
    environment = os.getenv("T212_ENV", "demo").strip().lower()
    if environment not in {"demo", "live"}:
        raise ValueError("T212_ENV must be either 'demo' or 'live'")

    poll_seconds = float(os.getenv("T212_POLL_SECONDS", "6"))
    snapshot_seconds = float(os.getenv("T212_SNAPSHOT_SECONDS", "30"))
    if poll_seconds < 5:
        raise ValueError("T212_POLL_SECONDS must be >= 5 to respect the account-summary rate limit")
    if snapshot_seconds < poll_seconds:
        raise ValueError("T212_SNAPSHOT_SECONDS must be >= T212_POLL_SECONDS")

    db_path = Path(os.getenv("T212_DB_PATH", "data/monitor.db"))

    return Settings(
        api_key=api_key,
        api_secret=api_secret,
        environment=environment,
        poll_seconds=poll_seconds,
        snapshot_seconds=snapshot_seconds,
        db_path=db_path,
        position_loss_alert_pct=_optional_float("T212_POSITION_LOSS_ALERT_PCT"),
        total_loss_alert_pct=_optional_float("T212_TOTAL_LOSS_ALERT_PCT"),
    )
