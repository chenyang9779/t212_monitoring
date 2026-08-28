from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _duration_seconds(opened_at: str | None, closed_at: str | None) -> float | None:
    opened = _parse_ts(opened_at)
    if opened is None:
        return None
    closed = _parse_ts(closed_at) if closed_at else datetime.now(timezone.utc)
    if closed is None:
        return None
    return max(0.0, (closed - opened).total_seconds())


def build_position_lifecycles(
    events: list[dict[str, Any]],
    current_positions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate observed position events into open/closed position lifecycles.

    Existing holdings present before monitoring started have an unknown open time.
    Those lifecycles are returned with ``complete=False`` rather than inventing an
    opening event or holding period.
    """

    ordered = sorted(events, key=lambda event: (str(event.get("ts") or ""), int(event.get("id") or 0)))
    current_by_ticker = {str(position.get("ticker") or ""): position for position in current_positions}
    active: dict[str, dict[str, Any]] = {}
    completed: list[dict[str, Any]] = []
    sequence: dict[str, int] = {}

    def start_lifecycle(event: dict[str, Any], complete: bool) -> dict[str, Any]:
        ticker = str(event.get("ticker") or "UNKNOWN")
        sequence[ticker] = sequence.get(ticker, 0) + 1
        opened_at = str(event.get("ts")) if complete and event.get("event_type") == "OPEN" else None
        quantity_before = float(event.get("quantity_before") or 0.0)
        quantity_after = float(event.get("quantity_after") or 0.0)
        baseline_quantity = max(quantity_before, 0.0) if not complete else 0.0
        return {
            "lifecycle_id": f"{ticker}:{sequence[ticker]}",
            "ticker": ticker,
            "name": str(event.get("name") or ticker),
            "currency": str(event.get("currency") or ""),
            "status": "open",
            "complete": complete,
            "opened_at": opened_at,
            "first_observed_at": str(event.get("ts") or ""),
            "last_event_at": str(event.get("ts") or ""),
            "closed_at": None,
            "initial_observed_quantity": baseline_quantity,
            "current_quantity": quantity_after,
            "peak_quantity": max(baseline_quantity, quantity_after),
            "total_added_quantity": 0.0,
            "total_reduced_quantity": 0.0,
            "event_count": 0,
            "open_price": event.get("current_price") if opened_at else None,
            "close_price": None,
            "realized_pl": None,
            "realized_pl_available": False,
        }

    for event in ordered:
        ticker = str(event.get("ticker") or "")
        if not ticker:
            continue
        event_type = str(event.get("event_type") or "").upper()
        delta = float(event.get("delta_quantity") or 0.0)
        lifecycle = active.get(ticker)

        if event_type == "OPEN":
            if lifecycle is not None:
                lifecycle["status"] = "closed"
                lifecycle["closed_at"] = str(event.get("ts") or "")
                lifecycle["close_price"] = event.get("current_price")
                lifecycle["current_quantity"] = 0.0
                completed.append(lifecycle)
            lifecycle = start_lifecycle(event, complete=True)
            active[ticker] = lifecycle
        elif lifecycle is None:
            lifecycle = start_lifecycle(event, complete=False)
            active[ticker] = lifecycle

        lifecycle["event_count"] += 1
        lifecycle["last_event_at"] = str(event.get("ts") or "")
        lifecycle["current_quantity"] = float(event.get("quantity_after") or 0.0)
        lifecycle["peak_quantity"] = max(
            float(lifecycle["peak_quantity"]),
            float(event.get("quantity_before") or 0.0),
            float(event.get("quantity_after") or 0.0),
        )

        if delta > 0:
            lifecycle["total_added_quantity"] += delta
        elif delta < 0:
            lifecycle["total_reduced_quantity"] += abs(delta)

        if event_type == "CLOSE":
            lifecycle["status"] = "closed"
            lifecycle["closed_at"] = str(event.get("ts") or "")
            lifecycle["close_price"] = event.get("current_price")
            lifecycle["current_quantity"] = 0.0
            completed.append(lifecycle)
            active.pop(ticker, None)

    # Holdings that predate the monitor may have no recorded quantity event at all.
    for ticker, position in current_by_ticker.items():
        if not ticker or ticker in active:
            continue
        quantity = float(position.get("quantity") or 0.0)
        if quantity <= 0:
            continue
        sequence[ticker] = sequence.get(ticker, 0) + 1
        active[ticker] = {
            "lifecycle_id": f"{ticker}:{sequence[ticker]}",
            "ticker": ticker,
            "name": str(position.get("name") or ticker),
            "currency": str(position.get("currency") or ""),
            "status": "open",
            "complete": False,
            "opened_at": None,
            "first_observed_at": None,
            "last_event_at": None,
            "closed_at": None,
            "initial_observed_quantity": quantity,
            "current_quantity": quantity,
            "peak_quantity": quantity,
            "total_added_quantity": 0.0,
            "total_reduced_quantity": 0.0,
            "event_count": 0,
            "open_price": None,
            "close_price": None,
            "realized_pl": None,
            "realized_pl_available": False,
        }

    items = completed + list(active.values())
    for item in items:
        item["holding_seconds"] = _duration_seconds(item["opened_at"], item["closed_at"])

    items.sort(
        key=lambda item: item.get("closed_at") or item.get("last_event_at") or item.get("opened_at") or "",
        reverse=True,
    )
    open_count = sum(1 for item in items if item["status"] == "open")
    closed_count = len(items) - open_count
    incomplete_count = sum(1 for item in items if not item["complete"])

    return {
        "items": items,
        "open": open_count,
        "closed": closed_count,
        "incomplete": incomplete_count,
        "total": len(items),
        "realized_pl_available": False,
    }
