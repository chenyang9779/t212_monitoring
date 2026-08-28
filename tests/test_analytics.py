from app.analytics import calculate_segmented_drawdown


def test_drawdown_without_position_change_uses_running_peak():
    result = calculate_segmented_drawdown(
        [
            {"ts": "2026-08-28T10:00:00+00:00", "pnl_pct": 10.0},
            {"ts": "2026-08-28T10:01:00+00:00", "pnl_pct": 20.0},
            {"ts": "2026-08-28T10:02:00+00:00", "pnl_pct": 5.0},
        ],
        [],
        "pnl_pct",
    )

    assert round(result["current_drawdown_pct"], 6) == round((1.05 / 1.20 - 1.0) * 100.0, 6)
    assert round(result["max_drawdown_pct"], 6) == round((1.05 / 1.20 - 1.0) * 100.0, 6)
    assert result["peak_return_pct"] == 20.0
    assert result["segments"] == 1


def test_position_change_resets_drawdown_peak():
    result = calculate_segmented_drawdown(
        [
            {"ts": "2026-08-28T10:00:00+00:00", "pnl_pct": 25.0},
            {"ts": "2026-08-28T10:01:00+00:00", "pnl_pct": 20.0},
            {"ts": "2026-08-28T10:02:00+00:00", "pnl_pct": 2.0},
            {"ts": "2026-08-28T10:03:00+00:00", "pnl_pct": 4.0},
        ],
        ["2026-08-28T10:02:00+00:00"],
        "pnl_pct",
    )

    assert result["segments"] == 2
    assert result["peak_return_pct"] == 4.0
    assert result["current_drawdown_pct"] == 0.0
    assert round(result["max_drawdown_pct"], 6) == round((1.20 / 1.25 - 1.0) * 100.0, 6)
