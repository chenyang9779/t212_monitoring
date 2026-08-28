from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .db import SnapshotStore
from .export_events import position_events_all
from .export_history import account_history_all, position_history_all
from .exporting import export_response, flatten_record
from .market_data import SUPPORTED_BAR_MINUTES, aggregate_quotes_to_bars
from .service import MonitorService


def build_export_router(store: SnapshotStore, monitor: MonitorService) -> APIRouter:
    router = APIRouter(prefix="/api/export", tags=["export"])

    @router.get("/positions")
    def export_positions(
        format: str = Query(default="csv", pattern="^(csv|jsonl)$"),
    ):
        rows = monitor.latest().get("positions") or []
        export_rows = [
            {
                "ticker": row.get("ticker"),
                "name": row.get("name"),
                "isin": row.get("isin"),
                "currency": row.get("currency"),
                "quantity": row.get("quantity"),
                "average_price": row.get("average_price"),
                "current_price": row.get("current_price"),
                "cost_local": row.get("cost_local"),
                "market_value_local": row.get("market_value_local"),
                "pnl_local": row.get("pnl_local"),
                "pnl_pct": row.get("pnl_pct"),
                "wallet_currency": row.get("wallet_currency"),
                "wallet_total_cost": row.get("wallet_total_cost"),
                "wallet_current_value": row.get("wallet_current_value"),
                "wallet_unrealized_pl": row.get("wallet_unrealized_pl"),
                "wallet_fx_impact": row.get("wallet_fx_impact"),
                "opened_at": row.get("opened_at"),
            }
            for row in rows
        ]
        return export_response(export_rows, "positions", format)

    @router.get("/account-history")
    def export_account_history(
        hours: int = Query(default=24, ge=1, le=720),
        format: str = Query(default="csv", pattern="^(csv|jsonl)$"),
    ):
        return export_response(
            account_history_all(store.path, hours=hours),
            f"account_history_{hours}h",
            format,
        )

    @router.get("/position-history")
    def export_position_history(
        ticker: str = Query(..., min_length=1),
        hours: int = Query(default=24, ge=1, le=720),
        format: str = Query(default="csv", pattern="^(csv|jsonl)$"),
    ):
        return export_response(
            position_history_all(store.path, ticker=ticker, hours=hours),
            f"position_history_{ticker}_{hours}h",
            format,
        )

    @router.get("/position-events")
    def export_position_events(
        format: str = Query(default="csv", pattern="^(csv|jsonl)$"),
    ):
        return export_response(
            position_events_all(store.path),
            "position_events",
            format,
        )

    @router.get("/alerts")
    def export_alerts(
        limit: int = Query(default=500, ge=1, le=500),
        format: str = Query(default="csv", pattern="^(csv|jsonl)$"),
    ):
        rows = [flatten_record(row) for row in store.alerts(limit=limit)]
        return export_response(rows, "alerts", format)

    @router.get("/market-quotes")
    def export_market_quotes(
        ticker: str = Query(..., min_length=1),
        hours: int = Query(default=24, ge=1, le=720),
        source: str = Query(default="t212_position", min_length=1),
        limit: int = Query(default=10000, ge=1, le=100000),
        format: str = Query(default="csv", pattern="^(csv|jsonl)$"),
    ):
        rows = store.market_quotes(
            ticker=ticker,
            hours=hours,
            source=source,
            limit=limit,
        )
        return export_response(
            rows,
            f"market_quotes_{ticker}_{hours}h_{source}",
            format,
        )

    @router.get("/market-bars")
    def export_market_bars(
        ticker: str = Query(..., min_length=1),
        hours: int = Query(default=24, ge=1, le=720),
        minutes: int = Query(default=5),
        source: str = Query(default="t212_position", min_length=1),
        format: str = Query(default="csv", pattern="^(csv|jsonl)$"),
    ):
        if minutes not in SUPPORTED_BAR_MINUTES:
            supported = ", ".join(str(value) for value in sorted(SUPPORTED_BAR_MINUTES))
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported bar interval. Supported minutes: {supported}",
            )
        quotes = store.market_quotes(
            ticker=ticker,
            hours=hours,
            source=source,
            limit=100000,
        )
        rows = aggregate_quotes_to_bars(quotes, minutes)
        return export_response(
            rows,
            f"market_bars_{ticker}_{minutes}m_{hours}h_{source}",
            format,
        )

    @router.get("/orders/history")
    async def export_order_history(
        limit: int = Query(default=50, ge=1, le=50),
        ticker: str | None = Query(default=None, min_length=1),
        format: str = Query(default="csv", pattern="^(csv|jsonl)$"),
    ):
        payload = await monitor.historical_orders(limit=limit, ticker=ticker)
        if not payload.get("available"):
            raise HTTPException(
                status_code=int(payload.get("status_code") or 502),
                detail=payload.get("error") or "Historical orders are unavailable",
            )
        rows = [flatten_record(row) for row in payload.get("items") or [] if isinstance(row, dict)]
        suffix = f"_{ticker}" if ticker else ""
        response = export_response(rows, f"order_history{suffix}", format)
        response.headers["X-Export-Page-Complete"] = str(not bool(payload.get("next_page_path"))).lower()
        if payload.get("next_page_path"):
            response.headers["X-Export-Has-More"] = "true"
        return response

    @router.get("/transactions")
    async def export_transactions(
        limit: int = Query(default=50, ge=1, le=50),
        format: str = Query(default="csv", pattern="^(csv|jsonl)$"),
    ):
        payload = await monitor.transactions(limit=limit)
        if not payload.get("available"):
            raise HTTPException(
                status_code=int(payload.get("status_code") or 502),
                detail=payload.get("error") or "Transactions are unavailable",
            )
        rows = [flatten_record(row) for row in payload.get("items") or [] if isinstance(row, dict)]
        response = export_response(rows, "transactions", format)
        response.headers["X-Export-Page-Complete"] = str(not bool(payload.get("next_page_path"))).lower()
        if payload.get("next_page_path"):
            response.headers["X-Export-Has-More"] = "true"
        return response

    return router
