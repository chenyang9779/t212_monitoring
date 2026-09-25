"""Synthetic demo data generator for screenshot and documentation purposes.

This module generates entirely fictional portfolio data and seeds it into a
SQLite database using the normal SnapshotStore API.  It never contacts any
external service, never uses real credentials, and can be toggled on or off
with a single environment variable.

Usage (development / screenshot only):

    T212_DEMO=true python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

The generated data is stored in the database configured by ``T212_DB_PATH``
(default ``data/demo-monitor.db``).  This file is git-ignored by default
and must never be committed to version control.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Synthetic portfolio definition
# ---------------------------------------------------------------------------
# All values below are fictional and designed to produce visually interesting
# dashboards (varied allocation, mixed P/L, multiple lifecycle events).

_CURRENCY = "GBP"
_ACCOUNT_CURRENCY = "GBP"

_POSITIONS: list[dict[str, Any]] = [
    {
        "ticker": "VUSA_US",
        "name": "Vanguard FTSE All-World UCITS ETF",
        "isin": "IE00B8CQ0768",
        "currency": "USD",
        "quantity": 200,
        "average_price": 29.80,
        "current_price": 30.85,
        "instrument_type": "ETF",
        "opened_at": "2023-06-15T09:00:00Z",
    },
    {
        "ticker": "AAPL_US",
        "name": "Apple Inc",
        "isin": "US0378331005",
        "currency": "USD",
        "quantity": 30,
        "average_price": 178.50,
        "current_price": 192.30,
        "instrument_type": "Stock",
        "opened_at": "2023-09-01T10:30:00Z",
    },
    {
        "ticker": "MSFT_US",
        "name": "Microsoft Corporation",
        "isin": "US5949181045",
        "currency": "USD",
        "quantity": 7,
        "average_price": 350.00,
        "current_price": 368.20,
        "instrument_type": "Stock",
        "opened_at": "2024-01-10T11:00:00Z",
    },
    {
        "ticker": "NVDA_US",
        "name": "NVIDIA Corporation",
        "isin": "US67066G1040",
        "currency": "USD",
        "quantity": 8,
        "average_price": 420.00,
        "current_price": 456.40,
        "instrument_type": "Stock",
        "opened_at": "2024-02-01T09:15:00Z",
    },
    {
        "ticker": "GOOGL_US",
        "name": "Alphabet Inc Class A",
        "isin": "US02079K3059",
        "currency": "USD",
        "quantity": 15,
        "average_price": 142.00,
        "current_price": 139.50,
        "instrument_type": "Stock",
        "opened_at": "2024-01-20T14:00:00Z",
    },
    {
        "ticker": "TSLA_US",
        "name": "Tesla Inc",
        "isin": "US88160R1014",
        "currency": "USD",
        "quantity": 0,
        "average_price": 245.00,
        "current_price": None,
        "instrument_type": "Stock",
        "opened_at": "2023-03-01T10:00:00Z",
        "closed_at": "2024-03-10T16:00:00Z",
    },
]

# Timeline configuration for the synthetic history
_HISTORY_HOURS = 24  # 24 hours of simulated history
_POSITION_SNAPSHOT_INTERVAL = 1800  # every 30 minutes in simulated time (28 ticks)
_ACCOUNT_SNAPSHOT_INTERVAL = 600  # every 10 minutes (10 per position tick)

# Seed for reproducibility (so screenshots are stable across runs)
_RANDOM_SEED = 42


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rnd(seed: int, lo: float, hi: float) -> float:
    """Deterministic perturbation around *lo* for reproducibility."""
    rng = random.Random(seed)
    return round(rng.uniform(lo, hi), 2)


def _make_position_raw(pos: dict[str, Any]) -> dict[str, Any]:
    """Build a fake Trading 212 position object matching the broker schema."""
    return {
        "ticker": pos["ticker"],
        "instrument": {
            "ticker": pos["ticker"],
            "name": pos["name"],
            "isin": pos["isin"],
            "currency": pos["currency"],
            "type": pos["instrument_type"],
        },
        "quantity": pos["quantity"],
        "averagePricePaid": pos["average_price"],
        "currentPrice": pos["current_price"],
        "walletImpact": {
            "totalCost": pos["average_price"] * pos["quantity"],
            "currentValue": (
                pos["current_price"] * pos["quantity"]
                if pos["current_price"]
                else None
            ),
            "unrealizedProfitLoss": None,
            "fxImpact": None,
            "currency": _ACCOUNT_CURRENCY,
        },
        "createdAt": pos["opened_at"],
    }


# ---------------------------------------------------------------------------
# Seeding logic
# ---------------------------------------------------------------------------

def seed_demo_data(db_path: Path, hours: int = _HISTORY_HOURS) -> None:
    """Populate a fresh (or existing) database with synthetic portfolio data.

    This walks forward in simulated time, creating:
      - account snapshots  (every _ACCOUNT_SNAPSHOT_INTERVAL steps)
      - position snapshots  (every _POSITION_SNAPSHOT_INTERVAL step)
      - position events     (lifecycle changes)
      - alerts              (some synthetic alerts)
      - market_quotes       (via SnapshotStore.save_snapshot)

    Parameters
    ----------
    db_path:
        SQLite database file to seed (e.g. ``data/demo-monitor.db``).
    hours:
        Simulated time span in the past to back-fill (default 48 h).
    """
    from .db import SnapshotStore

    store = SnapshotStore(db_path)
    now = datetime.now(timezone.utc)
    start_ts = now - timedelta(hours=hours)

    # Seed the deterministic generator
    random.seed(_RANDOM_SEED)

    # ---- build simulated lifecycle ----
    # Explicit lifecycle events at specific simulated timestamps.
    # All 4 event types (OPEN, ADD, REDUCE, CLOSE) are present.
    lifecycle_events: list[dict[str, Any]] = [
        # AAPL: OPEN at 0s, ADD at 3600s
        {"ts_offset_s": 0, "ticker": "AAPL_US", "event": "OPEN", "qty_after": 15},
        {"ts_offset_s": 3600, "ticker": "AAPL_US", "event": "ADD", "qty_after": 30},
        # NVDA: OPEN at 3600s, ADD at 7200s
        {"ts_offset_s": 3600, "ticker": "NVDA_US", "event": "OPEN", "qty_after": 5},
        {"ts_offset_s": 7200, "ticker": "NVDA_US", "event": "ADD", "qty_after": 8},
        # MSFT: OPEN at 3600s, REDUCE at 14400s
        {"ts_offset_s": 3600, "ticker": "MSFT_US", "event": "OPEN", "qty_after": 10},
        {"ts_offset_s": 14400, "ticker": "MSFT_US", "event": "REDUCE", "qty_after": 7},
        # VUSA: OPEN at 0s, ADD at 10800s
        {"ts_offset_s": 0, "ticker": "VUSA_US", "event": "OPEN", "qty_after": 150},
        {"ts_offset_s": 10800, "ticker": "VUSA_US", "event": "ADD", "qty_after": 200},
        # GOOGL: OPEN at 7200s, ADD at 14400s
        {"ts_offset_s": 7200, "ticker": "GOOGL_US", "event": "OPEN", "qty_after": 10},
        {"ts_offset_s": 14400, "ticker": "GOOGL_US", "event": "ADD", "qty_after": 15},
        # TSLA: OPEN at 0s, REDUCE at 3600s, CLOSE at 7200s
        {"ts_offset_s": 0, "ticker": "TSLA_US", "event": "OPEN", "qty_after": 10},
        {"ts_offset_s": 3600, "ticker": "TSLA_US", "event": "REDUCE", "qty_after": 5},
        {"ts_offset_s": 7200, "ticker": "TSLA_US", "event": "CLOSE", "qty_after": 0},
    ]

    max_ts = hours * 3600  # seconds from start

    # Accumulator: current quantity per ticker across the simulated timeline
    qty_state: dict[str, float] = {}

    # Current simulated price perturbation base per ticker
    price_base: dict[str, float] = {}
    for pos in _POSITIONS:
        price_base[pos["ticker"]] = pos["current_price"] or pos["average_price"]

    # Pre-build lookup of lifecycle events by simulated timestamp
    # (keys are integer seconds from start_ts)
    lifecycle_by_offset: dict[int, list[dict[str, Any]]] = {}
    for ev in lifecycle_events:
        key = min(ev["ts_offset_s"], max_ts)
        lifecycle_by_offset.setdefault(key, []).append(ev)

    # ---- walk simulated timeline ----
    # We iterate at every _POSITION_SNAPSHOT_INTERVAL seconds.
    # For each tick we:
    #   1. Apply lifecycle events at this timestamp
    #   2. Generate a position snapshot for every active ticker
    #   3. Generate an account snapshot every _ACCOUNT_SNAPSHOT_INTERVAL ticks

    tick = 0
    for offset_s in range(0, max_ts + 10, _POSITION_SNAPSHOT_INTERVAL):
        offset_s = min(offset_s, max_ts)
        ts_iso = (start_ts + timedelta(seconds=offset_s)).isoformat()

        # Apply lifecycle events at this timestamp
        for ev in lifecycle_by_offset.get(offset_s, []):
            ticker = ev["ticker"]
            old_qty = qty_state.get(ticker, 0.0)
            new_qty = ev["qty_after"]
            delta = new_qty - old_qty

            pos_cfg = next(
                (p for p in _POSITIONS if p["ticker"] == ticker), None
            )
            if pos_cfg is None:
                continue

            current_price = pos_cfg["current_price"] or pos_cfg["average_price"]
            name = pos_cfg["name"]
            currency = pos_cfg["currency"]

            store.add_position_event(
                ts=ts_iso,
                ticker=ticker,
                name=name,
                event_type=ev["event"],
                quantity_before=old_qty,
                quantity_after=new_qty,
                delta_quantity=delta,
                current_price=current_price,
                currency=currency,
            )

            qty_state[ticker] = new_qty

        # Collect position snapshots for ALL positions (including closed ones)
        # at this tick so that the latest position state is always available
        pos_rows: list[dict[str, Any]] = []
        total_invested_tick = 0.0
        total_value_tick = 0.0
        total_pnl_tick = 0.0

        for pos_cfg in _POSITIONS:
            ticker = pos_cfg["ticker"]
            qty = qty_state.get(ticker, 0.0)

            current_price = pos_cfg["current_price"] or price_base[ticker]
            drift = _rnd(offset_s + hash(ticker), -2.0, 2.0)
            sim_price = round(max(0.01, current_price + drift), 2)

            cost_local = round(pos_cfg["average_price"] * qty, 2) if qty else 0.0
            market_value_local = round(sim_price * qty, 2) if qty else 0.0
            pnl_local = round(market_value_local - cost_local, 2) if qty else 0.0
            pnl_pct = (
                round(pnl_local / abs(cost_local) * 100, 2) if cost_local else 0.0
            )

            # Only include in portfolio totals if position is active
            if qty > 0:
                total_invested_tick += cost_local
                total_value_tick += market_value_local
                total_pnl_tick += pnl_local

            position_raw = _make_position_raw(pos_cfg)
            position_raw["quantity"] = qty
            position_raw["averagePricePaid"] = pos_cfg["average_price"]
            position_raw["currentPrice"] = sim_price
            position_raw["walletImpact"]["currentValue"] = market_value_local
            position_raw["walletImpact"]["unrealizedProfitLoss"] = pnl_local

            pos_rows.append(
                {
                    "ticker": ticker,
                    "name": pos_cfg["name"],
                    "currency": pos_cfg["currency"],
                    "isin": pos_cfg["isin"],
                    "quantity": qty,
                    "average_price": pos_cfg["average_price"],
                    "current_price": sim_price,
                    "cost_local": cost_local,
                    "market_value_local": market_value_local,
                    "pnl_local": pnl_local,
                    "pnl_pct": pnl_pct,
                    "wallet_currency": _ACCOUNT_CURRENCY,
                    "wallet_total_cost": cost_local,
                    "wallet_current_value": market_value_local,
                    "wallet_unrealized_pl": pnl_local,
                    "wallet_fx_impact": None,
                    "opened_at": pos_cfg["opened_at"],
                    "raw": position_raw,
                }
            )

        # Save all positions in a single call
        if pos_rows:
            store.save_snapshot(
                ts_iso,
                {
                    "currency": _ACCOUNT_CURRENCY,
                    "total_value": round(total_value_tick, 2),
                    "available_to_trade": 3420.18,
                    "investments_current_value": round(total_value_tick, 2),
                    "investments_total_cost": round(total_invested_tick, 2),
                    "realized_pl": 200.0,
                    "unrealized_pl": round(total_pnl_tick, 2),
                    "unrealized_pl_pct": round(
                        total_pnl_tick / total_invested_tick * 100, 2
                    )
                    if total_invested_tick
                    else None,
                    "raw": {},
                },
                pos_rows,
            )

        tick += 1

        # ---- account snapshot every 6 position ticks ----
        if tick % 6 == 0:
            total_value_acc = round(total_value_tick + 3420.18, 2)
            store.save_snapshot(
                ts_iso,
                {
                    "currency": _ACCOUNT_CURRENCY,
                    "total_value": total_value_acc,
                    "available_to_trade": 3420.18,
                    "investments_current_value": round(total_value_tick, 2),
                    "investments_total_cost": round(total_invested_tick, 2),
                    "realized_pl": 200.0,
                    "unrealized_pl": round(total_pnl_tick, 2),
                    "unrealized_pl_pct": round(
                        total_pnl_tick / total_invested_tick * 100, 2
                    )
                    if total_invested_tick
                    else None,
                    "raw": {"id": "DEMO-ACCOUNT"},
                },
                [],  # positions already saved above
            )

    # ---- final synthetic "live" state ----
    # Build the current latest positions for the dashboard to render
    final_positions: list[dict[str, Any]] = []
    total_invested = 0.0
    total_value = 0.0

    for pos_cfg in _POSITIONS:
        qty = qty_state.get(pos_cfg["ticker"], 0.0)
        if qty == 0:
            continue  # closed positions excluded from current list
        current_price = pos_cfg["current_price"] or pos_cfg["average_price"]
        cost = round(pos_cfg["average_price"] * qty, 2)
        value = round(current_price * qty, 2)
        pnl = round(value - cost, 2)
        total_invested += cost
        total_value += value

        final_positions.append(
            {
                "ticker": pos_cfg["ticker"],
                "name": pos_cfg["name"],
                "currency": pos_cfg["currency"],
                "isin": pos_cfg["isin"],
                "quantity": qty,
                "average_price": pos_cfg["average_price"],
                "current_price": current_price,
                "cost_local": cost,
                "market_value_local": value,
                "pnl_local": pnl,
                "pnl_pct": round(pnl / cost * 100, 2) if cost else 0.0,
                "wallet_currency": _ACCOUNT_CURRENCY,
                "wallet_total_cost": cost,
                "wallet_current_value": value,
                "wallet_unrealized_pl": pnl,
                "wallet_fx_impact": None,
                "opened_at": pos_cfg["opened_at"],
                "raw": _make_position_raw(pos_cfg),
            }
        )

    total_pl = round(total_value - total_invested, 2)
    account_final = {
        "currency": _ACCOUNT_CURRENCY,
        "total_value": round(total_value + 3420.18, 2),  # add cash
        "available_to_trade": 3420.18,
        "investments_current_value": round(total_value, 2),
        "investments_total_cost": round(total_invested, 2),
        "realized_pl": round(200.0, 2),
        "unrealized_pl": total_pl,
        "unrealized_pl_pct": round(
            total_pl / total_invested * 100, 2
        )
        if total_invested
        else None,
        "raw": {"id": "DEMO-ACCOUNT"},
    }

    # Save the final snapshot so /api/latest and /api/status work
    store.save_snapshot(
        datetime.now(timezone.utc).isoformat(),
        account_final,
        final_positions,
    )

    # ---- synthetic alerts ----
    now_iso = datetime.now(timezone.utc).isoformat()
    for ticker in ["GOOGL_US"]:
        store.add_alert(
            ts=now_iso,
            severity="warning",
            rule="position_loss",
            message=f"{ticker} unrealized return is -1.76%",
            ticker=ticker,
            payload={"pnl_pct": -1.76, "threshold": 8.0},
        )


