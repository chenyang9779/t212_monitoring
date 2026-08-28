from app.metrics import normalize_account, normalize_position


def test_normalize_position_calculates_local_pnl():
    result = normalize_position(
        {
            "averagePricePaid": 100.0,
            "currentPrice": 110.0,
            "quantity": 2.0,
            "quantityAvailableForTrading": 2.0,
            "quantityInPies": 0.0,
            "instrument": {
                "ticker": "TEST_US_EQ",
                "name": "Test Inc",
                "currency": "USD",
                "isin": "XX0000000000",
            },
            "walletImpact": {},
        }
    )
    assert result["cost_local"] == 200.0
    assert result["market_value_local"] == 220.0
    assert result["pnl_local"] == 20.0
    assert result["pnl_pct"] == 10.0


def test_normalize_account_calculates_unrealized_pct():
    result = normalize_account(
        {
            "id": 1,
            "currency": "GBP",
            "totalValue": 1050.0,
            "cash": {"availableToTrade": 50.0, "inPies": 0.0, "reservedForOrders": 0.0},
            "investments": {
                "currentValue": 1000.0,
                "totalCost": 900.0,
                "realizedProfitLoss": 25.0,
                "unrealizedProfitLoss": 100.0,
            },
        }
    )
    assert round(result["unrealized_pl_pct"], 6) == round(100.0 / 900.0 * 100.0, 6)
