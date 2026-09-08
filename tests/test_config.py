from __future__ import annotations

import pytest

from app.config import load_settings


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("T212_POLL_SECONDS", "nan"),
        ("T212_POLL_SECONDS", "inf"),
        ("T212_SNAPSHOT_SECONDS", "-inf"),
        ("T212_POSITION_LOSS_ALERT_PCT", "nan"),
        ("T212_TOTAL_LOSS_ALERT_PCT", "inf"),
    ],
)
def test_load_settings_rejects_non_finite_numbers(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv("T212_POLL_SECONDS", "6")
    monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
    monkeypatch.delenv("T212_POSITION_LOSS_ALERT_PCT", raising=False)
    monkeypatch.delenv("T212_TOTAL_LOSS_ALERT_PCT", raising=False)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=rf"^{name} must be a finite number$"):
        load_settings()


def test_load_settings_accepts_finite_numeric_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("T212_POLL_SECONDS", "5.5")
    monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "12")
    monkeypatch.setenv("T212_POSITION_LOSS_ALERT_PCT", "8.25")
    monkeypatch.setenv("T212_TOTAL_LOSS_ALERT_PCT", "10")

    settings = load_settings()

    assert settings.poll_seconds == 5.5
    assert settings.snapshot_seconds == 12.0
    assert settings.position_loss_alert_pct == 8.25
    assert settings.total_loss_alert_pct == 10.0
