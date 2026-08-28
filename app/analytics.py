from __future__ import annotations

from typing import Any


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric == numeric and numeric not in (float("inf"), float("-inf")):
            return numeric
    return None


def calculate_segmented_drawdown(
    points: list[dict[str, Any]],
    reset_timestamps: list[str],
    value_key: str,
) -> dict[str, Any]:
    """Calculate drawdown on a percentage-return series, resetting at trade events.

    Each point's percentage is converted to a wealth index ``1 + pct / 100``.
    A position-size change changes cost basis and can mechanically move the reported
    return, so any supplied reset timestamp starts a new drawdown segment.
    """

    valid_points: list[tuple[str, float]] = []
    for point in points:
        ts = str(point.get("ts") or "")
        value = _finite_number(point.get(value_key))
        if ts and value is not None:
            valid_points.append((ts, value))

    if not valid_points:
        return {
            "current_drawdown_pct": None,
            "max_drawdown_pct": None,
            "peak_return_pct": None,
            "current_return_pct": None,
            "peak_ts": None,
            "trough_ts": None,
            "observations": 0,
            "segments": 0,
        }

    resets = sorted(ts for ts in reset_timestamps if ts)
    reset_index = 0
    segment_peak_wealth: float | None = None
    segment_peak_return: float | None = None
    segment_peak_ts: str | None = None
    current_peak_return: float | None = None
    current_peak_ts: str | None = None
    max_drawdown = 0.0
    max_drawdown_trough_ts: str | None = None
    segments = 1

    for ts, return_pct in valid_points:
        reset_here = False
        while reset_index < len(resets) and resets[reset_index] <= ts:
            reset_here = True
            reset_index += 1
        if reset_here:
            segment_peak_wealth = None
            segment_peak_return = None
            segment_peak_ts = None
            segments += 1

        wealth = max(1e-12, 1.0 + return_pct / 100.0)
        if segment_peak_wealth is None or wealth >= segment_peak_wealth:
            segment_peak_wealth = wealth
            segment_peak_return = return_pct
            segment_peak_ts = ts

        assert segment_peak_wealth is not None
        drawdown = (wealth / segment_peak_wealth - 1.0) * 100.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            max_drawdown_trough_ts = ts

        current_peak_return = segment_peak_return
        current_peak_ts = segment_peak_ts

    current_return = valid_points[-1][1]
    current_wealth = max(1e-12, 1.0 + current_return / 100.0)
    peak_wealth = max(1e-12, 1.0 + (current_peak_return or 0.0) / 100.0)
    current_drawdown = (current_wealth / peak_wealth - 1.0) * 100.0

    return {
        "current_drawdown_pct": current_drawdown,
        "max_drawdown_pct": max_drawdown,
        "peak_return_pct": current_peak_return,
        "current_return_pct": current_return,
        "peak_ts": current_peak_ts,
        "trough_ts": max_drawdown_trough_ts,
        "observations": len(valid_points),
        "segments": segments,
    }


def calculate_pnl_attribution(
    account: dict[str, Any] | None,
    positions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Attribute current unrealized P/L to open positions in account currency.

    Trading 212 exposes ``walletImpact.unrealizedProfitLoss`` per position in the
    account currency. Only positions with a finite account-currency wallet P/L are
    included; instrument-currency P/L is never mixed into this calculation.
    """

    if not account:
        return {
            "available": False,
            "reason": "account data unavailable",
            "currency": "",
            "account_unrealized_pl": None,
            "sum_position_unrealized_pl": None,
            "reconciliation_difference": None,
            "gross_gains": None,
            "gross_losses": None,
            "rows": [],
            "accounted_positions": 0,
            "total_positions": len(positions),
        }

    currency = str(account.get("currency") or "")
    account_unrealized = _finite_number(account.get("unrealized_pl"))
    rows: list[dict[str, Any]] = []

    for position in positions:
        pnl = _finite_number(position.get("wallet_unrealized_pl"))
        wallet_currency = str(position.get("wallet_currency") or "")
        if pnl is None:
            continue
        if currency and wallet_currency and wallet_currency != currency:
            continue
        rows.append(
            {
                "ticker": str(position.get("ticker") or "UNKNOWN"),
                "name": str(position.get("name") or "Unknown instrument"),
                "pnl": pnl,
                "fx_impact": _finite_number(position.get("wallet_fx_impact")),
            }
        )

    if not rows:
        return {
            "available": False,
            "reason": "account-currency position P/L is unavailable",
            "currency": currency,
            "account_unrealized_pl": account_unrealized,
            "sum_position_unrealized_pl": None,
            "reconciliation_difference": None,
            "gross_gains": None,
            "gross_losses": None,
            "rows": [],
            "accounted_positions": 0,
            "total_positions": len(positions),
        }

    summed = sum(row["pnl"] for row in rows)
    gross_gains = sum(max(row["pnl"], 0.0) for row in rows)
    gross_losses = sum(min(row["pnl"], 0.0) for row in rows)
    gross_abs = sum(abs(row["pnl"]) for row in rows)

    for row in rows:
        row["gross_share_pct"] = abs(row["pnl"]) / gross_abs * 100.0 if gross_abs > 0 else 0.0
        row["net_contribution_pct"] = (
            row["pnl"] / account_unrealized * 100.0
            if account_unrealized not in (None, 0.0)
            else None
        )

    rows.sort(key=lambda row: abs(row["pnl"]), reverse=True)
    difference = account_unrealized - summed if account_unrealized is not None else None

    return {
        "available": True,
        "reason": None,
        "currency": currency,
        "account_unrealized_pl": account_unrealized,
        "sum_position_unrealized_pl": summed,
        "reconciliation_difference": difference,
        "gross_gains": gross_gains,
        "gross_losses": gross_losses,
        "largest_contributor": max(rows, key=lambda row: row["pnl"]) if rows else None,
        "largest_detractor": min(rows, key=lambda row: row["pnl"]) if rows else None,
        "rows": rows,
        "accounted_positions": len(rows),
        "total_positions": len(positions),
    }
