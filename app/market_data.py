from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SUPPORTED_BAR_MINUTES = {1, 5, 15, 30, 60, 240, 1440}


def _parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _bucket_start(dt: datetime, minutes: int) -> datetime:
    if minutes == 1440:
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    total_minutes = dt.hour * 60 + dt.minute
    bucket_minutes = total_minutes - (total_minutes % minutes)
    return dt.replace(
        hour=bucket_minutes // 60,
        minute=bucket_minutes % 60,
        second=0,
        microsecond=0,
    )


def aggregate_quotes_to_bars(
    quotes: list[dict[str, Any]],
    minutes: int,
) -> list[dict[str, Any]]:
    """Aggregate sampled quote marks into OHLC-style bars.

    These bars are derived from monitor samples, not exchange trade bars. ``open``,
    ``high``, ``low`` and ``close`` therefore describe observed sampled marks only.
    """

    if minutes not in SUPPORTED_BAR_MINUTES:
        raise ValueError(f"Unsupported bar interval: {minutes} minutes")

    buckets: dict[str, dict[str, Any]] = {}
    for quote in quotes:
        ts = str(quote.get("ts") or "")
        price = quote.get("price")
        if not ts or isinstance(price, bool) or not isinstance(price, (int, float)):
            continue
        numeric = float(price)
        if not (numeric == numeric) or numeric in (float("inf"), float("-inf")):
            continue

        dt = _parse_ts(ts)
        bucket_ts = _bucket_start(dt, minutes).isoformat()
        bar = buckets.get(bucket_ts)
        if bar is None:
            bar = {
                "ts": bucket_ts,
                "ticker": quote.get("ticker") or "",
                "isin": quote.get("isin") or "",
                "name": quote.get("name") or "",
                "currency": quote.get("currency") or "",
                "source": quote.get("source") or "",
                "open": numeric,
                "high": numeric,
                "low": numeric,
                "close": numeric,
                "observations": 1,
                "first_observation_ts": ts,
                "last_observation_ts": ts,
            }
            buckets[bucket_ts] = bar
            continue

        bar["high"] = max(float(bar["high"]), numeric)
        bar["low"] = min(float(bar["low"]), numeric)
        bar["close"] = numeric
        bar["observations"] = int(bar["observations"]) + 1
        bar["last_observation_ts"] = ts

    return [buckets[key] for key in sorted(buckets)]
