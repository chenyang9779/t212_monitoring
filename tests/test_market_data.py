from app.market_data import aggregate_quotes_to_bars


def test_aggregate_quotes_to_five_minute_bars():
    quotes = [
        {"ts": "2026-08-28T10:00:10+00:00", "ticker": "TEST", "price": 100.0, "currency": "USD", "source": "t212_position"},
        {"ts": "2026-08-28T10:02:10+00:00", "ticker": "TEST", "price": 103.0, "currency": "USD", "source": "t212_position"},
        {"ts": "2026-08-28T10:04:10+00:00", "ticker": "TEST", "price": 99.0, "currency": "USD", "source": "t212_position"},
        {"ts": "2026-08-28T10:05:10+00:00", "ticker": "TEST", "price": 101.0, "currency": "USD", "source": "t212_position"},
    ]

    bars = aggregate_quotes_to_bars(quotes, 5)

    assert len(bars) == 2
    assert bars[0]["open"] == 100.0
    assert bars[0]["high"] == 103.0
    assert bars[0]["low"] == 99.0
    assert bars[0]["close"] == 99.0
    assert bars[0]["observations"] == 3
    assert bars[1]["open"] == 101.0
    assert bars[1]["close"] == 101.0


def test_daily_bar_uses_utc_day_boundary():
    quotes = [
        {"ts": "2026-08-28T23:59:00+00:00", "ticker": "TEST", "price": 10.0},
        {"ts": "2026-08-29T00:01:00+00:00", "ticker": "TEST", "price": 11.0},
    ]

    bars = aggregate_quotes_to_bars(quotes, 1440)

    assert [bar["ts"] for bar in bars] == [
        "2026-08-28T00:00:00+00:00",
        "2026-08-29T00:00:00+00:00",
    ]
