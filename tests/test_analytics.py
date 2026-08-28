from app.analytics import calculate_pnl_attribution, calculate_segmented_drawdown


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


def test_pnl_attribution_uses_account_currency_wallet_values():
    result = calculate_pnl_attribution(
        {"currency": "GBP", "unrealized_pl": -50.0},
        [
            {
                "ticker": "GAIN_US_EQ",
                "name": "Gain Inc",
                "wallet_currency": "GBP",
                "wallet_unrealized_pl": 25.0,
                "wallet_fx_impact": 1.5,
            },
            {
                "ticker": "LOSS_US_EQ",
                "name": "Loss Inc",
                "wallet_currency": "GBP",
                "wallet_unrealized_pl": -75.0,
                "wallet_fx_impact": -2.0,
            },
        ],
    )

    assert result["available"] is True
    assert result["currency"] == "GBP"
    assert result["sum_position_unrealized_pl"] == -50.0
    assert result["reconciliation_difference"] == 0.0
    assert result["gross_gains"] == 25.0
    assert result["gross_losses"] == -75.0
    assert result["largest_contributor"]["ticker"] == "GAIN_US_EQ"
    assert result["largest_detractor"]["ticker"] == "LOSS_US_EQ"
    assert result["rows"][0]["ticker"] == "LOSS_US_EQ"
    assert round(result["rows"][0]["gross_share_pct"], 6) == 75.0
    assert round(result["rows"][0]["net_contribution_pct"], 6) == 150.0


def test_pnl_attribution_rejects_instrument_currency_fallbacks():
    result = calculate_pnl_attribution(
        {"currency": "GBP", "unrealized_pl": -10.0},
        [
            {
                "ticker": "USD_ONLY",
                "name": "USD only",
                "currency": "USD",
                "pnl_local": -12.0,
                "wallet_currency": "",
                "wallet_unrealized_pl": None,
            }
        ],
    )

    assert result["available"] is False
    assert result["rows"] == []
