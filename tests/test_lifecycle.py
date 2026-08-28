from app.lifecycle import build_position_lifecycles


def test_complete_open_add_reduce_close_lifecycle():
    events = [
        {
            "id": 1,
            "ts": "2026-08-28T10:00:00+00:00",
            "ticker": "MSFT_US_EQ",
            "name": "Microsoft",
            "currency": "USD",
            "event_type": "OPEN",
            "quantity_before": 0.0,
            "quantity_after": 1.0,
            "delta_quantity": 1.0,
            "current_price": 500.0,
        },
        {
            "id": 2,
            "ts": "2026-08-28T11:00:00+00:00",
            "ticker": "MSFT_US_EQ",
            "name": "Microsoft",
            "currency": "USD",
            "event_type": "ADD",
            "quantity_before": 1.0,
            "quantity_after": 1.5,
            "delta_quantity": 0.5,
            "current_price": 505.0,
        },
        {
            "id": 3,
            "ts": "2026-08-28T12:00:00+00:00",
            "ticker": "MSFT_US_EQ",
            "name": "Microsoft",
            "currency": "USD",
            "event_type": "REDUCE",
            "quantity_before": 1.5,
            "quantity_after": 0.5,
            "delta_quantity": -1.0,
            "current_price": 510.0,
        },
        {
            "id": 4,
            "ts": "2026-08-28T13:00:00+00:00",
            "ticker": "MSFT_US_EQ",
            "name": "Microsoft",
            "currency": "USD",
            "event_type": "CLOSE",
            "quantity_before": 0.5,
            "quantity_after": 0.0,
            "delta_quantity": -0.5,
            "current_price": 515.0,
        },
    ]

    result = build_position_lifecycles(events, [])
    lifecycle = result["items"][0]

    assert result["open"] == 0
    assert result["closed"] == 1
    assert result["incomplete"] == 0
    assert lifecycle["complete"] is True
    assert lifecycle["status"] == "closed"
    assert lifecycle["total_added_quantity"] == 1.5
    assert lifecycle["total_reduced_quantity"] == 1.5
    assert lifecycle["peak_quantity"] == 1.5
    assert lifecycle["current_quantity"] == 0.0
    assert lifecycle["holding_seconds"] == 3 * 60 * 60


def test_preexisting_position_is_marked_incomplete():
    result = build_position_lifecycles(
        [],
        [
            {
                "ticker": "NVDA_US_EQ",
                "name": "NVIDIA",
                "currency": "USD",
                "quantity": 2.0,
            }
        ],
    )

    lifecycle = result["items"][0]
    assert result["open"] == 1
    assert result["closed"] == 0
    assert result["incomplete"] == 1
    assert lifecycle["complete"] is False
    assert lifecycle["opened_at"] is None
    assert lifecycle["holding_seconds"] is None
    assert lifecycle["initial_observed_quantity"] == 2.0


def test_preexisting_position_with_reduce_keeps_unknown_open_time():
    events = [
        {
            "id": 1,
            "ts": "2026-08-28T10:00:00+00:00",
            "ticker": "AAPL_US_EQ",
            "name": "Apple",
            "currency": "USD",
            "event_type": "REDUCE",
            "quantity_before": 3.0,
            "quantity_after": 2.0,
            "delta_quantity": -1.0,
            "current_price": 220.0,
        }
    ]

    result = build_position_lifecycles(
        events,
        [{"ticker": "AAPL_US_EQ", "name": "Apple", "currency": "USD", "quantity": 2.0}],
    )
    lifecycle = result["items"][0]

    assert lifecycle["complete"] is False
    assert lifecycle["opened_at"] is None
    assert lifecycle["initial_observed_quantity"] == 3.0
    assert lifecycle["current_quantity"] == 2.0
    assert lifecycle["total_reduced_quantity"] == 1.0
