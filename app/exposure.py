from __future__ import annotations

from collections import defaultdict
from typing import Any


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric == numeric and numeric not in (float("inf"), float("-inf")):
            return numeric
    return None


def normalize_instrument_metadata(item: dict[str, Any]) -> dict[str, Any] | None:
    ticker = item.get("ticker")
    if not ticker:
        return None
    return {
        "ticker": str(ticker),
        "isin": str(item.get("isin") or ""),
        "name": str(item.get("name") or ticker),
        "currency": str(item.get("currencyCode") or item.get("currency") or ""),
        "type": str(item.get("type") or ""),
        "working_schedule_id": item.get("workingScheduleId"),
        "added_on": item.get("addedOn"),
        "short_name": str(item.get("shortName") or ""),
        "raw": item,
    }


def build_exposure(
    account: dict[str, Any] | None,
    positions: list[dict[str, Any]],
    metadata: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build exposure views from account-currency position values and broker metadata.

    Currency exposure here means the instrument's quoted currency, not issuer domicile
    or economic revenue exposure. No sector/country classification is invented when
    the broker metadata does not provide it.
    """

    account_currency = str((account or {}).get("currency") or "")
    by_ticker = {str(item.get("ticker") or ""): item for item in metadata}

    rows: list[dict[str, Any]] = []
    currency_totals: dict[str, float] = defaultdict(float)
    type_totals: dict[str, float] = defaultdict(float)
    total_value = 0.0
    covered_value = 0.0

    for position in positions:
        value = _number(position.get("wallet_current_value"))
        if value is None:
            continue
        total_value += value
        meta = by_ticker.get(str(position.get("ticker") or "")) or {}
        instrument_currency = str(meta.get("currency") or position.get("currency") or "UNKNOWN")
        instrument_type = str(meta.get("type") or "UNKNOWN")
        currency_totals[instrument_currency] += value
        type_totals[instrument_type] += value
        if meta:
            covered_value += value
        rows.append(
            {
                "ticker": position.get("ticker"),
                "name": meta.get("name") or position.get("name"),
                "isin": meta.get("isin") or position.get("isin") or "",
                "instrument_currency": instrument_currency,
                "instrument_type": instrument_type,
                "account_currency": account_currency,
                "account_value": value,
                "weight_pct": None,
                "metadata_available": bool(meta),
            }
        )

    denominator = _number((account or {}).get("investments_current_value"))
    if denominator in (None, 0.0):
        denominator = total_value if total_value else None

    if denominator:
        for row in rows:
            row["weight_pct"] = row["account_value"] / denominator * 100.0

    def groups(values: dict[str, float]) -> list[dict[str, Any]]:
        result = [
            {
                "name": name,
                "account_value": value,
                "weight_pct": value / denominator * 100.0 if denominator else None,
            }
            for name, value in values.items()
        ]
        result.sort(key=lambda item: item["account_value"], reverse=True)
        return result

    rows.sort(key=lambda item: item["account_value"], reverse=True)
    return {
        "account_currency": account_currency,
        "invested_value": denominator,
        "positions_with_value": len(rows),
        "metadata_coverage_pct": (
            covered_value / total_value * 100.0 if total_value else None
        ),
        "currency_exposure": groups(currency_totals),
        "type_exposure": groups(type_totals),
        "positions": rows,
        "notes": {
            "currency": "Instrument quoted currency, not issuer domicile or economic exposure.",
            "sector_country": "Unavailable unless supplied by a future metadata provider.",
        },
    }
