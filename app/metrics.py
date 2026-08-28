from __future__ import annotations

from typing import Any


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def normalize_position(position: dict[str, Any]) -> dict[str, Any]:
    instrument = position.get("instrument") or {}
    wallet_impact = position.get("walletImpact") or {}
    quantity = _number(position.get("quantity")) or 0.0
    average_price = _number(position.get("averagePricePaid"))
    current_price = _number(position.get("currentPrice"))

    cost_local = average_price * quantity if average_price is not None else None
    market_value_local = current_price * quantity if current_price is not None else None
    pnl_local = (
        market_value_local - cost_local
        if market_value_local is not None and cost_local is not None
        else None
    )
    pnl_pct = (
        (pnl_local / abs(cost_local)) * 100.0
        if pnl_local is not None and cost_local not in (None, 0)
        else None
    )

    wallet_total_cost = _number(wallet_impact.get("totalCost"))
    wallet_current_value = _number(wallet_impact.get("currentValue"))
    wallet_unrealized_pl = _number(wallet_impact.get("unrealizedProfitLoss"))
    wallet_pnl_pct = (
        (wallet_unrealized_pl / abs(wallet_total_cost)) * 100.0
        if wallet_unrealized_pl is not None and wallet_total_cost not in (None, 0)
        else None
    )

    return {
        "ticker": instrument.get("ticker") or position.get("ticker") or "UNKNOWN",
        "name": instrument.get("name") or instrument.get("ticker") or "Unknown instrument",
        "currency": instrument.get("currency") or "",
        "isin": instrument.get("isin") or "",
        "quantity": quantity,
        "quantity_available": _number(position.get("quantityAvailableForTrading")),
        "quantity_in_pies": _number(position.get("quantityInPies")),
        "average_price": average_price,
        "current_price": current_price,
        "cost_local": cost_local,
        "market_value_local": market_value_local,
        "pnl_local": pnl_local,
        "pnl_pct": pnl_pct,
        "wallet_currency": wallet_impact.get("currency") or "",
        "wallet_total_cost": wallet_total_cost,
        "wallet_current_value": wallet_current_value,
        "wallet_unrealized_pl": wallet_unrealized_pl,
        "wallet_fx_impact": _number(wallet_impact.get("fxImpact")),
        "wallet_pnl_pct": wallet_pnl_pct,
        "opened_at": position.get("createdAt"),
        "wallet_impact": wallet_impact,
        "raw": position,
    }


def normalize_account(summary: dict[str, Any]) -> dict[str, Any]:
    cash = summary.get("cash") or {}
    investments = summary.get("investments") or {}
    total_cost = _number(investments.get("totalCost"))
    unrealized = _number(investments.get("unrealizedProfitLoss"))
    unrealized_pct = (
        (unrealized / abs(total_cost)) * 100.0
        if unrealized is not None and total_cost not in (None, 0)
        else None
    )
    return {
        "id": summary.get("id"),
        "currency": summary.get("currency") or "",
        "total_value": _number(summary.get("totalValue")),
        "available_to_trade": _number(cash.get("availableToTrade")),
        "cash_in_pies": _number(cash.get("inPies")),
        "reserved_for_orders": _number(cash.get("reservedForOrders")),
        "investments_current_value": _number(investments.get("currentValue")),
        "investments_total_cost": total_cost,
        "realized_pl": _number(investments.get("realizedProfitLoss")),
        "unrealized_pl": unrealized,
        "unrealized_pl_pct": unrealized_pct,
        "raw": summary,
    }
