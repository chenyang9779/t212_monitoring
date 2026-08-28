from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric == numeric and numeric not in (float("inf"), float("-inf")):
            return numeric
    return None


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def evaluate_data_quality(
    account_history: list[dict[str, Any]],
    latest: dict[str, Any],
    status: dict[str, Any],
    market_catalog: list[dict[str, Any]],
    hours: int,
    poll_seconds: float,
    snapshot_seconds: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate monitoring freshness, snapshot continuity and valuation integrity."""

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    hours = min(max(int(hours), 1), 168)
    poll_seconds = max(float(poll_seconds), 1.0)
    snapshot_seconds = max(float(snapshot_seconds), poll_seconds)
    issues: list[dict[str, Any]] = []

    def add_issue(code: str, severity: str, message: str, **detail: Any) -> None:
        issues.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "detail": detail,
            }
        )

    history_points = [
        (parsed, row)
        for row in account_history
        for parsed in [_parse_ts(row.get("ts"))]
        if parsed is not None
    ]
    history_points.sort(key=lambda item: item[0])

    gap_threshold = snapshot_seconds * 2.5
    gap_seconds: list[float] = []
    for (left_ts, _), (right_ts, _) in zip(history_points, history_points[1:]):
        gap = (right_ts - left_ts).total_seconds()
        if gap > gap_threshold:
            gap_seconds.append(gap)

    if not history_points:
        add_issue(
            "no_account_snapshots",
            "warning",
            f"No account snapshots are stored in the last {hours}h.",
        )
    elif gap_seconds:
        max_gap = max(gap_seconds)
        severity = "critical" if max_gap > snapshot_seconds * 20 else "warning"
        add_issue(
            "snapshot_gaps",
            severity,
            f"Detected {len(gap_seconds)} account snapshot gap(s); largest gap is {max_gap:.0f}s.",
            gap_count=len(gap_seconds),
            max_gap_seconds=max_gap,
            expected_snapshot_seconds=snapshot_seconds,
        )

    actual_span_seconds = (
        (history_points[-1][0] - history_points[0][0]).total_seconds()
        if len(history_points) >= 2
        else 0.0
    )
    expected_over_span = (
        max(1, int(actual_span_seconds / snapshot_seconds) + 1)
        if history_points
        else 0
    )
    continuity_pct = (
        min(100.0, len(history_points) / expected_over_span * 100.0)
        if expected_over_span
        else None
    )
    requested_window_seconds = hours * 3600.0
    observed_window_pct = (
        min(100.0, actual_span_seconds / requested_window_seconds * 100.0)
        if history_points
        else 0.0
    )

    last_sync = _parse_ts(latest.get("last_sync") or status.get("last_sync"))
    sync_age_seconds = (now - last_sync).total_seconds() if last_sync else None
    sync_warning_after = max(30.0, poll_seconds * 3.0)
    sync_critical_after = max(120.0, poll_seconds * 10.0)
    if last_sync is None:
        add_issue("never_synced", "critical", "The monitor has not completed a successful Trading 212 sync.")
    elif sync_age_seconds is not None and sync_age_seconds > sync_warning_after:
        severity = "critical" if sync_age_seconds >= sync_critical_after else "warning"
        add_issue(
            "stale_sync",
            severity,
            f"Last successful Trading 212 sync is {sync_age_seconds:.0f}s old.",
            age_seconds=sync_age_seconds,
            warning_after_seconds=sync_warning_after,
        )

    last_snapshot = history_points[-1][0] if history_points else None
    snapshot_age_seconds = (now - last_snapshot).total_seconds() if last_snapshot else None
    snapshot_warning_after = max(60.0, snapshot_seconds * 3.0)
    if snapshot_age_seconds is not None and snapshot_age_seconds > snapshot_warning_after:
        severity = "critical" if snapshot_age_seconds > max(300.0, snapshot_seconds * 10.0) else "warning"
        add_issue(
            "stale_snapshot",
            severity,
            f"Latest stored account snapshot is {snapshot_age_seconds:.0f}s old.",
            age_seconds=snapshot_age_seconds,
            warning_after_seconds=snapshot_warning_after,
        )

    if status.get("last_error"):
        add_issue(
            "monitor_error",
            "critical",
            f"Monitor currently reports an error: {status['last_error']}",
        )

    account = latest.get("account") if isinstance(latest.get("account"), dict) else None
    positions = latest.get("positions") if isinstance(latest.get("positions"), list) else []
    account_currency = str(account.get("currency") or "") if account else ""

    tickers = [str(position.get("ticker") or "") for position in positions]
    duplicate_tickers = sorted({ticker for ticker in tickers if ticker and tickers.count(ticker) > 1})
    if duplicate_tickers:
        add_issue(
            "duplicate_positions",
            "critical",
            f"Duplicate open-position ticker(s) detected: {', '.join(duplicate_tickers)}.",
            tickers=duplicate_tickers,
        )

    missing_prices = [
        str(position.get("ticker") or "UNKNOWN")
        for position in positions
        if _finite_number(position.get("current_price")) is None
    ]
    nonpositive_prices = [
        str(position.get("ticker") or "UNKNOWN")
        for position in positions
        if (_finite_number(position.get("current_price")) or 0.0) <= 0.0
        and _finite_number(position.get("current_price")) is not None
    ]
    if missing_prices:
        add_issue(
            "missing_current_prices",
            "warning",
            f"{len(missing_prices)} open position(s) have no current price.",
            tickers=missing_prices,
        )
    if nonpositive_prices:
        add_issue(
            "nonpositive_prices",
            "critical",
            f"{len(nonpositive_prices)} open position(s) have a non-positive current price.",
            tickers=nonpositive_prices,
        )

    wallet_valid: list[float] = []
    wallet_missing: list[str] = []
    wallet_currency_mismatch: list[str] = []
    for position in positions:
        ticker = str(position.get("ticker") or "UNKNOWN")
        wallet_value = _finite_number(position.get("wallet_current_value"))
        wallet_currency = str(position.get("wallet_currency") or "")
        if account_currency and wallet_currency and wallet_currency != account_currency:
            wallet_currency_mismatch.append(ticker)
            continue
        if wallet_value is None:
            wallet_missing.append(ticker)
            continue
        wallet_valid.append(wallet_value)

    if wallet_currency_mismatch:
        add_issue(
            "wallet_currency_mismatch",
            "warning",
            f"{len(wallet_currency_mismatch)} position wallet value(s) do not match the account currency.",
            tickers=wallet_currency_mismatch,
            account_currency=account_currency,
        )
    if positions and wallet_missing:
        add_issue(
            "wallet_values_incomplete",
            "warning",
            f"Account-currency wallet values are missing for {len(wallet_missing)} open position(s).",
            tickers=wallet_missing,
        )

    invested_value = _finite_number(account.get("investments_current_value")) if account else None
    wallet_sum = sum(wallet_valid) if wallet_valid else None
    valuation_difference = (
        invested_value - wallet_sum
        if invested_value is not None and wallet_sum is not None and not wallet_missing and not wallet_currency_mismatch
        else None
    )
    valuation_difference_pct = (
        abs(valuation_difference) / abs(invested_value) * 100.0
        if valuation_difference is not None and invested_value not in (None, 0.0)
        else None
    )
    if valuation_difference_pct is not None and valuation_difference_pct > 1.0:
        severity = "critical" if valuation_difference_pct > 5.0 else "warning"
        add_issue(
            "valuation_mismatch",
            severity,
            f"Broker invested value differs from summed position wallet values by {valuation_difference_pct:.2f}%.",
            account_invested_value=invested_value,
            position_wallet_sum=wallet_sum,
            difference=valuation_difference,
            difference_pct=valuation_difference_pct,
            currency=account_currency,
        )

    catalog_by_ticker = {
        str(item.get("ticker") or ""): item
        for item in market_catalog
        if str(item.get("source") or "t212_position") == "t212_position"
    }
    stale_quote_tickers: list[str] = []
    missing_quote_tickers: list[str] = []
    quote_warning_after = max(60.0, snapshot_seconds * 3.0)
    for position in positions:
        ticker = str(position.get("ticker") or "")
        if not ticker:
            continue
        catalog_item = catalog_by_ticker.get(ticker)
        if catalog_item is None:
            missing_quote_tickers.append(ticker)
            continue
        quote_ts = _parse_ts(catalog_item.get("last_ts"))
        if quote_ts is None:
            missing_quote_tickers.append(ticker)
            continue
        if (now - quote_ts).total_seconds() > quote_warning_after:
            stale_quote_tickers.append(ticker)

    if missing_quote_tickers:
        add_issue(
            "missing_market_quotes",
            "warning",
            f"No stored market quote series exists for {len(missing_quote_tickers)} open position(s).",
            tickers=missing_quote_tickers,
        )
    if stale_quote_tickers:
        add_issue(
            "stale_market_quotes",
            "warning",
            f"Stored market quotes are stale for {len(stale_quote_tickers)} open position(s).",
            tickers=stale_quote_tickers,
            warning_after_seconds=quote_warning_after,
        )

    severity_rank = {"healthy": 0, "warning": 1, "critical": 2}
    overall = "healthy"
    for issue in issues:
        if severity_rank[issue["severity"]] > severity_rank[overall]:
            overall = issue["severity"]

    return {
        "status": overall,
        "hours": hours,
        "issues": issues,
        "critical": sum(1 for issue in issues if issue["severity"] == "critical"),
        "warnings": sum(1 for issue in issues if issue["severity"] == "warning"),
        "account_snapshots": len(history_points),
        "snapshot_gap_count": len(gap_seconds),
        "max_snapshot_gap_seconds": max(gap_seconds) if gap_seconds else 0.0,
        "snapshot_continuity_pct": continuity_pct,
        "observed_window_pct": observed_window_pct,
        "last_sync": last_sync.isoformat() if last_sync else None,
        "sync_age_seconds": sync_age_seconds,
        "last_snapshot": last_snapshot.isoformat() if last_snapshot else None,
        "snapshot_age_seconds": snapshot_age_seconds,
        "open_positions": len(positions),
        "positions_with_wallet_values": len(wallet_valid),
        "stale_quote_count": len(stale_quote_tickers),
        "missing_quote_count": len(missing_quote_tickers),
        "valuation_currency": account_currency,
        "valuation_account_invested": invested_value,
        "valuation_position_sum": wallet_sum,
        "valuation_difference": valuation_difference,
        "valuation_difference_pct": valuation_difference_pct,
    }
