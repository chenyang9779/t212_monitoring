from datetime import datetime, timedelta, timezone

from app.quality import evaluate_data_quality


def _base_latest(now: datetime):
    return {
        "last_sync": now.isoformat(),
        "account": {
            "currency": "GBP",
            "investments_current_value": 150.0,
        },
        "positions": [
            {
                "ticker": "AAA",
                "current_price": 10.0,
                "wallet_current_value": 100.0,
                "wallet_currency": "GBP",
            },
            {
                "ticker": "BBB",
                "current_price": 20.0,
                "wallet_current_value": 50.0,
                "wallet_currency": "GBP",
            },
        ],
    }


def test_data_quality_healthy_snapshot_series():
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    history = [
        {"ts": (now - timedelta(seconds=90)).isoformat()},
        {"ts": (now - timedelta(seconds=60)).isoformat()},
        {"ts": (now - timedelta(seconds=30)).isoformat()},
        {"ts": now.isoformat()},
    ]
    catalog = [
        {"ticker": "AAA", "source": "t212_position", "last_ts": now.isoformat()},
        {"ticker": "BBB", "source": "t212_position", "last_ts": now.isoformat()},
    ]

    result = evaluate_data_quality(
        history,
        _base_latest(now),
        {"last_sync": now.isoformat(), "last_error": None},
        catalog,
        hours=1,
        poll_seconds=6,
        snapshot_seconds=30,
        now=now,
    )

    assert result["status"] == "healthy"
    assert result["snapshot_gap_count"] == 0
    assert result["valuation_difference"] == 0.0
    assert result["critical"] == 0
    assert result["warnings"] == 0


def test_data_quality_detects_snapshot_gap_and_stale_sync():
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    history = [
        {"ts": (now - timedelta(minutes=10)).isoformat()},
        {"ts": (now - timedelta(minutes=9, seconds=30)).isoformat()},
        {"ts": (now - timedelta(minutes=2)).isoformat()},
    ]
    latest = _base_latest(now - timedelta(minutes=2))

    result = evaluate_data_quality(
        history,
        latest,
        {"last_sync": latest["last_sync"], "last_error": None},
        [],
        hours=1,
        poll_seconds=6,
        snapshot_seconds=30,
        now=now,
    )

    codes = {issue["code"] for issue in result["issues"]}
    assert result["status"] == "critical"
    assert "snapshot_gaps" in codes
    assert "stale_sync" in codes
    assert "stale_snapshot" in codes
    assert "missing_market_quotes" in codes


def test_data_quality_detects_valuation_and_currency_problems():
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    history = [{"ts": now.isoformat()}]
    latest = _base_latest(now)
    latest["positions"][0]["wallet_current_value"] = 80.0
    latest["positions"][1]["wallet_currency"] = "USD"
    catalog = [
        {"ticker": "AAA", "source": "t212_position", "last_ts": now.isoformat()},
        {"ticker": "BBB", "source": "t212_position", "last_ts": now.isoformat()},
    ]

    result = evaluate_data_quality(
        history,
        latest,
        {"last_sync": now.isoformat(), "last_error": None},
        catalog,
        hours=1,
        poll_seconds=6,
        snapshot_seconds=30,
        now=now,
    )

    codes = {issue["code"] for issue in result["issues"]}
    assert result["status"] == "warning"
    assert "wallet_currency_mismatch" in codes
    assert result["valuation_difference"] is None


def test_data_quality_detects_duplicate_and_missing_price():
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    latest = _base_latest(now)
    latest["positions"] = [
        {
            "ticker": "AAA",
            "current_price": None,
            "wallet_current_value": 75.0,
            "wallet_currency": "GBP",
        },
        {
            "ticker": "AAA",
            "current_price": 10.0,
            "wallet_current_value": 75.0,
            "wallet_currency": "GBP",
        },
    ]
    catalog = [{"ticker": "AAA", "source": "t212_position", "last_ts": now.isoformat()}]

    result = evaluate_data_quality(
        [{"ts": now.isoformat()}],
        latest,
        {"last_sync": now.isoformat(), "last_error": None},
        catalog,
        hours=1,
        poll_seconds=6,
        snapshot_seconds=30,
        now=now,
    )

    codes = {issue["code"] for issue in result["issues"]}
    assert result["status"] == "critical"
    assert "duplicate_positions" in codes
    assert "missing_current_prices" in codes
