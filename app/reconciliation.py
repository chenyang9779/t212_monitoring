from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
from typing import Any


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric == numeric and numeric not in (float("inf"), float("-inf")):
            return numeric
    return None


def _pick(item: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = item
        ok = True
        for key in path.split("."):
            if not isinstance(current, dict) or key not in current:
                ok = False
                break
            current = current[key]
        if ok and current not in (None, ""):
            return current
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000.0
        try:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return _parse_timestamp(int(text))
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_historical_order(item: dict[str, Any]) -> dict[str, Any] | None:
    ticker = _pick(
        item,
        "ticker",
        "instrument.ticker",
        "order.ticker",
        "order.instrument.ticker",
    )
    if not ticker:
        return None

    explicit_filled = _pick(
        item,
        "filledQuantity",
        "executedQuantity",
        "order.filledQuantity",
        "order.executedQuantity",
    )
    quantity_value = explicit_filled
    if _finite_number(quantity_value) in (None, 0.0):
        quantity_value = _pick(item, "quantity", "order.quantity")

    quantity = _finite_number(quantity_value)
    if quantity in (None, 0.0):
        return None

    status = str(_pick(item, "status", "order.status") or "").upper()
    if explicit_filled is None and status in {"CANCELLED", "CANCELED", "REJECTED"}:
        return None

    side = str(_pick(item, "side", "order.side") or "").upper()
    if side in {"SELL", "S"}:
        quantity = -abs(quantity)
    elif side in {"BUY", "B"}:
        quantity = abs(quantity)

    timestamp_value = _pick(
        item,
        "filledAt",
        "dateExecuted",
        "executedAt",
        "dateModified",
        "modifiedAt",
        "dateCreated",
        "createdAt",
        "order.filledAt",
        "order.dateExecuted",
        "order.executedAt",
        "order.dateModified",
        "order.modifiedAt",
        "order.dateCreated",
        "order.createdAt",
    )
    timestamp = _parse_timestamp(timestamp_value)
    if timestamp is None:
        return None

    price = _finite_number(
        _pick(
            item,
            "fillPrice",
            "averagePrice",
            "filledPrice",
            "executionPrice",
            "order.fillPrice",
            "order.averagePrice",
            "order.filledPrice",
            "order.executionPrice",
        )
    )
    order_id = _pick(item, "id", "order.id", "reference", "referenceId")

    return {
        "id": str(order_id) if order_id is not None else "",
        "ticker": str(ticker),
        "quantity": quantity,
        "price": price,
        "status": status,
        "ts": timestamp.isoformat(),
        "_dt": timestamp,
    }


def _same_sign(left: float, right: float) -> bool:
    return (left > 0 and right > 0) or (left < 0 and right < 0)


def _weighted_price(orders: list[dict[str, Any]]) -> float | None:
    priced: list[tuple[float, float]] = []
    for order in orders:
        price = _finite_number(order.get("price"))
        if price is not None:
            priced.append((abs(float(order["quantity"])), price))
    total_quantity = sum(quantity for quantity, _ in priced)
    if total_quantity <= 0:
        return None
    return sum(quantity * price for quantity, price in priced) / total_quantity


def reconcile_position_events(
    events: list[dict[str, Any]],
    historical_orders: list[dict[str, Any]],
    tolerance_seconds: int = 180,
) -> dict[str, Any]:
    """Match observed position deltas to nearby historical broker fills.

    One polling delta may contain several fills, so small combinations of nearby
    same-ticker/same-side orders are tested. Broker orders are not reused.
    """

    tolerance_seconds = min(max(int(tolerance_seconds), 30), 900)
    orders = [
        normalized
        for item in historical_orders
        if isinstance(item, dict)
        for normalized in [normalize_historical_order(item)]
        if normalized is not None
    ]

    parsed_events: list[tuple[dict[str, Any], datetime, float]] = []
    for event in events:
        event_ts = _parse_timestamp(event.get("ts"))
        delta = _finite_number(event.get("delta_quantity"))
        ticker = str(event.get("ticker") or "")
        if event_ts is not None and delta not in (None, 0.0) and ticker:
            parsed_events.append((event, event_ts, delta))
    parsed_events.sort(key=lambda entry: entry[1])

    used_orders: set[int] = set()
    results: list[dict[str, Any]] = []

    for event, event_dt, delta in parsed_events:
        candidate_indices = [
            index
            for index, order in enumerate(orders)
            if index not in used_orders
            and order["ticker"] == event["ticker"]
            and _same_sign(float(order["quantity"]), delta)
            and abs((event_dt - order["_dt"]).total_seconds()) <= tolerance_seconds
        ]
        candidate_indices.sort(
            key=lambda index: abs((event_dt - orders[index]["_dt"]).total_seconds())
        )
        candidate_indices = candidate_indices[:10]

        quantity_tolerance = max(1e-8, abs(delta) * 1e-6)
        best_combo: tuple[int, ...] | None = None
        best_score: tuple[float, float, int] | None = None

        for size in range(1, min(6, len(candidate_indices)) + 1):
            for combo in combinations(candidate_indices, size):
                broker_quantity = sum(float(orders[index]["quantity"]) for index in combo)
                if abs(broker_quantity - delta) > quantity_tolerance:
                    continue
                lags = [abs((event_dt - orders[index]["_dt"]).total_seconds()) for index in combo]
                score = (max(lags, default=0.0), sum(lags), size)
                if best_score is None or score < best_score:
                    best_score = score
                    best_combo = combo

        if best_combo is None:
            nearest = orders[candidate_indices[0]] if candidate_indices else None
            results.append(
                {
                    "event_id": event.get("id"),
                    "event_ts": event.get("ts"),
                    "ticker": event.get("ticker"),
                    "name": event.get("name"),
                    "event_type": event.get("event_type"),
                    "observed_quantity": delta,
                    "status": "unmatched",
                    "broker_quantity": None,
                    "broker_price": None,
                    "broker_order_ids": [],
                    "broker_order_count": 0,
                    "broker_last_ts": nearest["ts"] if nearest else None,
                    "lag_seconds": (event_dt - nearest["_dt"]).total_seconds() if nearest else None,
                    "candidate_order_count": len(candidate_indices),
                }
            )
            continue

        matched_orders = [orders[index] for index in best_combo]
        used_orders.update(best_combo)
        broker_last = max(matched_orders, key=lambda order: order["_dt"])
        results.append(
            {
                "event_id": event.get("id"),
                "event_ts": event.get("ts"),
                "ticker": event.get("ticker"),
                "name": event.get("name"),
                "event_type": event.get("event_type"),
                "observed_quantity": delta,
                "status": "matched",
                "broker_quantity": sum(float(order["quantity"]) for order in matched_orders),
                "broker_price": _weighted_price(matched_orders),
                "broker_order_ids": [order["id"] for order in matched_orders if order["id"]],
                "broker_order_count": len(matched_orders),
                "broker_last_ts": broker_last["ts"],
                "lag_seconds": (event_dt - broker_last["_dt"]).total_seconds(),
                "candidate_order_count": len(candidate_indices),
            }
        )

    matched = sum(1 for item in results if item["status"] == "matched")
    total = len(results)
    return {
        "events_considered": total,
        "matched": matched,
        "unmatched": total - matched,
        "match_rate_pct": matched / total * 100.0 if total else None,
        "broker_orders_normalized": len(orders),
        "broker_orders_used": len(used_orders),
        "tolerance_seconds": tolerance_seconds,
        "items": list(reversed(results)),
    }
