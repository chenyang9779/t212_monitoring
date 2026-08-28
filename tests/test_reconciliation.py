from app.reconciliation import normalize_historical_order, reconcile_position_events


def test_normalize_sell_order_signs_quantity_negative():
    order = normalize_historical_order(
        {
            "id": "abc",
            "ticker": "MSFT_US_EQ",
            "side": "SELL",
            "filledQuantity": 2.0,
            "fillPrice": 501.25,
            "filledAt": "2026-08-28T12:00:00Z",
            "status": "FILLED",
        }
    )

    assert order is not None
    assert order["quantity"] == -2.0
    assert order["price"] == 501.25


def test_reconcile_combines_multiple_fills_for_one_poll_delta():
    events = [
        {
            "id": 1,
            "ts": "2026-08-28T12:02:00+00:00",
            "ticker": "MSFT_US_EQ",
            "name": "Microsoft",
            "event_type": "ADD",
            "delta_quantity": 1.5,
        }
    ]
    orders = [
        {
            "id": "a",
            "ticker": "MSFT_US_EQ",
            "side": "BUY",
            "filledQuantity": 1.0,
            "fillPrice": 500.0,
            "filledAt": "2026-08-28T12:00:30Z",
            "status": "FILLED",
        },
        {
            "id": "b",
            "ticker": "MSFT_US_EQ",
            "side": "BUY",
            "filledQuantity": 0.5,
            "fillPrice": 502.0,
            "filledAt": "2026-08-28T12:01:00Z",
            "status": "FILLED",
        },
    ]

    result = reconcile_position_events(events, orders, tolerance_seconds=180)

    assert result["matched"] == 1
    assert result["unmatched"] == 0
    assert result["items"][0]["broker_quantity"] == 1.5
    assert round(result["items"][0]["broker_price"], 6) == round((500.0 + 251.0) / 1.5, 6)
    assert result["items"][0]["broker_order_count"] == 2


def test_reconcile_does_not_match_wrong_quantity():
    events = [
        {
            "id": 2,
            "ts": "2026-08-28T12:02:00+00:00",
            "ticker": "MSFT_US_EQ",
            "name": "Microsoft",
            "event_type": "REDUCE",
            "delta_quantity": -1.0,
        }
    ]
    orders = [
        {
            "id": "c",
            "ticker": "MSFT_US_EQ",
            "side": "SELL",
            "filledQuantity": 0.25,
            "filledAt": "2026-08-28T12:01:30Z",
            "status": "FILLED",
        }
    ]

    result = reconcile_position_events(events, orders, tolerance_seconds=180)

    assert result["matched"] == 0
    assert result["unmatched"] == 1
    assert result["items"][0]["status"] == "unmatched"
