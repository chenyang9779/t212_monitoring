from app.streaming import EventBroker, encode_sse


def test_event_broker_fans_out_without_blocking_slow_subscriber():
    broker = EventBroker(queue_size=4)
    first = broker.subscribe()
    second = broker.subscribe()

    event = broker.publish("portfolio", {"value": 1})

    assert first.get_nowait() == event
    assert second.get_nowait() == event
    assert broker.stats()["subscribers"] == 2
    assert broker.stats()["published"] == 1


def test_event_broker_drops_oldest_when_queue_is_full():
    broker = EventBroker(queue_size=4)
    queue = broker.subscribe()

    for value in range(6):
        broker.publish("portfolio", {"value": value})

    values = []
    while not queue.empty():
        values.append(queue.get_nowait().data["value"])

    assert values == [2, 3, 4, 5]
    assert broker.stats()["dropped"] == 2


def test_encode_sse_sets_event_id_name_and_json_payload():
    encoded = encode_sse("position_event", {"ticker": "AAPL_US_EQ", "delta": 1.5}, event_id=42)

    assert "id: 42\n" in encoded
    assert "event: position_event\n" in encoded
    assert 'data: {"ticker":"AAPL_US_EQ","delta":1.5}\n' in encoded
    assert encoded.endswith("\n\n")
