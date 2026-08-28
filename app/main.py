from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .analytics import calculate_pnl_attribution, calculate_segmented_drawdown
from .config import load_settings
from .db import SnapshotStore
from .export_routes import build_export_router
from .lifecycle import build_position_lifecycles
from .market_data import SUPPORTED_BAR_MINUTES, aggregate_quotes_to_bars
from .quality import evaluate_data_quality
from .reconciliation import reconcile_position_events
from .service import MonitorService
from .storage import database_status

settings = load_settings()
store = SnapshotStore(settings.db_path)
monitor = MonitorService(settings, store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await monitor.start()
    yield
    await monitor.stop()


app = FastAPI(title="Trading 212 Position Monitor", version="2.1.0", lifespan=lifespan)
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.include_router(build_export_router(store, monitor))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/healthz")
def healthz() -> dict[str, object]:
    status = monitor.status()
    return {"ok": status["last_error"] is None, **status}


@app.get("/api/status")
def api_status() -> dict[str, object]:
    return monitor.status()


@app.get("/api/storage")
def api_storage() -> dict[str, object]:
    return {
        **database_status(settings.db_path, settings.raw_retention_days),
        "last_maintenance": monitor.state.last_maintenance,
        "maintenance_error": monitor.state.maintenance_error,
        "maintenance_deleted_total": monitor.state.maintenance_deleted_total,
    }


@app.get("/api/latest")
def api_latest() -> dict[str, object]:
    return monitor.latest()


@app.get("/api/history")
def api_history(hours: int = Query(default=24, ge=1, le=720)) -> dict[str, object]:
    return {"items": store.history(hours=hours)}


@app.get("/api/position-history")
def api_position_history(
    ticker: str = Query(..., min_length=1),
    hours: int = Query(default=24, ge=1, le=720),
) -> dict[str, object]:
    return {"items": store.position_history(ticker=ticker, hours=hours)}


@app.get("/api/position-events")
def api_position_events(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
    return {"items": store.position_events(limit=limit)}


@app.get("/api/position-lifecycles")
def api_position_lifecycles(
    event_limit: int = Query(default=500, ge=1, le=500),
) -> dict[str, object]:
    latest = monitor.latest()
    return build_position_lifecycles(
        store.position_events(limit=event_limit),
        latest.get("positions") or [],
    )


@app.get("/api/data-quality")
def api_data_quality(
    hours: int = Query(default=24, ge=1, le=168),
) -> dict[str, object]:
    latest = monitor.latest()
    status = monitor.status()
    return evaluate_data_quality(
        account_history=store.history(hours=hours),
        latest=latest,
        status=status,
        market_catalog=store.market_catalog(source="t212_position"),
        hours=hours,
        poll_seconds=settings.poll_seconds,
        snapshot_seconds=settings.snapshot_seconds,
    )


@app.get("/api/reconciliation")
async def api_reconciliation(
    event_limit: int = Query(default=50, ge=1, le=200),
    tolerance_seconds: int = Query(default=180, ge=30, le=900),
) -> dict[str, object]:
    events = store.position_events(limit=event_limit)
    history = await monitor.historical_orders(limit=50)
    if not history.get("available"):
        return {
            "available": False,
            "error": history.get("error") or "Historical orders are unavailable",
            "status_code": history.get("status_code"),
            "items": [],
        }

    result = reconcile_position_events(
        events,
        history.get("items") or [],
        tolerance_seconds=tolerance_seconds,
    )
    return {
        "available": True,
        "error": None,
        **result,
    }


@app.get("/api/drawdown")
def api_drawdown(
    hours: int = Query(default=24, ge=1, le=720),
    ticker: str | None = Query(default=None, min_length=1),
) -> dict[str, object]:
    if ticker:
        history = store.position_history(ticker=ticker, hours=hours)
        events = store.position_events_since(hours=hours, ticker=ticker)
        result = calculate_segmented_drawdown(
            history,
            [event["ts"] for event in events],
            "pnl_pct",
        )
        return {
            "scope": "position",
            "ticker": ticker,
            "hours": hours,
            **result,
        }

    history = store.history(hours=hours)
    events = store.position_events_since(hours=hours)
    result = calculate_segmented_drawdown(
        history,
        [event["ts"] for event in events],
        "unrealized_pl_pct",
    )
    return {
        "scope": "overall",
        "ticker": None,
        "hours": hours,
        **result,
    }


@app.get("/api/pnl-attribution")
def api_pnl_attribution() -> dict[str, object]:
    latest = monitor.latest()
    return calculate_pnl_attribution(
        latest.get("account"),
        latest.get("positions") or [],
    )


@app.get("/api/market/catalog")
def api_market_catalog(
    source: str = Query(default="t212_position", min_length=1),
) -> dict[str, object]:
    return {"source": source, "items": store.market_catalog(source=source)}


@app.get("/api/market/quotes")
def api_market_quotes(
    ticker: str = Query(..., min_length=1),
    hours: int = Query(default=24, ge=1, le=720),
    source: str = Query(default="t212_position", min_length=1),
    limit: int = Query(default=10000, ge=1, le=100000),
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "hours": hours,
        "source": source,
        "items": store.market_quotes(
            ticker=ticker,
            hours=hours,
            source=source,
            limit=limit,
        ),
    }


@app.get("/api/market/bars")
def api_market_bars(
    ticker: str = Query(..., min_length=1),
    hours: int = Query(default=24, ge=1, le=720),
    minutes: int = Query(default=5),
    source: str = Query(default="t212_position", min_length=1),
) -> dict[str, object]:
    if minutes not in SUPPORTED_BAR_MINUTES:
        supported = ", ".join(str(value) for value in sorted(SUPPORTED_BAR_MINUTES))
        return {
            "ticker": ticker,
            "hours": hours,
            "minutes": minutes,
            "source": source,
            "available": False,
            "error": f"Unsupported bar interval. Supported minutes: {supported}",
            "items": [],
        }

    quotes = store.market_quotes(
        ticker=ticker,
        hours=hours,
        source=source,
        limit=100000,
    )
    return {
        "ticker": ticker,
        "hours": hours,
        "minutes": minutes,
        "source": source,
        "available": True,
        "sampled": True,
        "items": aggregate_quotes_to_bars(quotes, minutes),
    }


@app.get("/api/orders/pending")
async def api_pending_orders() -> dict[str, object]:
    return await monitor.pending_orders()


@app.get("/api/orders/history")
async def api_order_history(
    limit: int = Query(default=50, ge=1, le=50),
    ticker: str | None = Query(default=None, min_length=1),
    next_page_path: str | None = Query(default=None, min_length=1),
) -> dict[str, object]:
    return await monitor.historical_orders(
        limit=limit,
        ticker=ticker,
        next_page_path=next_page_path,
    )


@app.get("/api/transactions")
async def api_transactions(
    limit: int = Query(default=50, ge=1, le=50),
    next_page_path: str | None = Query(default=None, min_length=1),
) -> dict[str, object]:
    return await monitor.transactions(limit=limit, next_page_path=next_page_path)


@app.get("/api/alerts")
def api_alerts(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, object]:
    return {"items": store.alerts(limit=limit)}
