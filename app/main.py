from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .analytics import calculate_pnl_attribution, calculate_segmented_drawdown
from .config import load_settings
from .db import SnapshotStore
from .event_queries import position_events_all, position_events_page
from .export_routes import build_export_router
from .exposure import build_exposure
from .history_queries import (
    account_history_all,
    account_snapshot_count,
    account_snapshot_timestamps,
    position_history_all,
    position_snapshot_count,
)
from .lifecycle import build_position_lifecycles
from .market_data import SUPPORTED_BAR_MINUTES, aggregate_quotes_to_bars
from .operations import (
    configure_app_logging,
    readiness_status,
    request_log_payload,
    reset_request_id,
    resolve_request_id,
    set_request_id,
    startup_checks,
)
from .quality import evaluate_data_quality
from .reconciliation import reconcile_position_events
from .service import MonitorService
from .storage import database_status
from .streaming import EventBroker, encode_sse

settings = load_settings()
store = SnapshotStore(settings.db_path)
event_broker = EventBroker()
monitor = MonitorService(settings, store, events=event_broker)
logger = configure_app_logging()
static_dir = Path(__file__).resolve().parent / "static"
startup_report = startup_checks(
    db_path=settings.db_path,
    static_dir=static_dir,
    api_key=settings.api_key,
    api_secret=settings.api_secret,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_starting", extra={"structured": {"event": "application_starting", "startup_ok": startup_report["ok"]}})
    await monitor.start()
    try:
        yield
    finally:
        logger.info("application_stopping", extra={"structured": {"event": "application_stopping"}})
        await monitor.stop()
        logger.info("application_stopped", extra={"structured": {"event": "application_stopped"}})


app = FastAPI(title="Trading 212 Position Monitor", version="2.4.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.include_router(build_export_router(store, monitor))


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = resolve_request_id(request.headers.get("X-Request-ID"))
    token = set_request_id(request_id)
    started = time.monotonic()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        logger.exception(
            "unhandled_request_exception",
            extra={"structured": {"event": "http_exception", "method": request.method, "path": request.url.path}},
        )
        raise
    finally:
        logger.info(
            "http_request",
            extra={
                "structured": request_log_payload(
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    started_monotonic=started,
                )
            },
        )
        reset_request_id(token)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    if "/static/live.js" not in html:
        html = html.replace(
            "</body>",
            '  <script src="/static/live.js" defer></script>\n</body>',
        )
    return HTMLResponse(html)


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {
        "ok": True,
        "startup_ok": startup_report["ok"],
        "startup_issues": startup_report["issues"],
    }


@app.get("/readyz")
def readyz() -> JSONResponse:
    payload = readiness_status(
        monitor_status=monitor.status(),
        db_path=settings.db_path,
        max_sync_age_seconds=max(settings.poll_seconds * 5.0, 30.0),
    )
    payload["startup_ok"] = startup_report["ok"]
    if not startup_report["ok"]:
        payload["ready"] = False
        payload["reasons"] = [*payload["reasons"], "startup_checks_failed"]
    return JSONResponse(payload, status_code=200 if payload["ready"] else 503)


@app.get("/api/status")
def api_status() -> dict[str, object]:
    return monitor.status()


@app.get("/api/operations")
def api_operations() -> dict[str, object]:
    readiness = readiness_status(
        monitor_status=monitor.status(),
        db_path=settings.db_path,
        max_sync_age_seconds=max(settings.poll_seconds * 5.0, 30.0),
    )
    if not startup_report["ok"]:
        readiness["ready"] = False
        readiness["reasons"] = [*readiness["reasons"], "startup_checks_failed"]
    return {
        "startup": startup_report,
        "readiness": readiness,
        "stream": event_broker.stats(),
    }


@app.get("/api/stream/status")
def api_stream_status() -> dict[str, object]:
    return {"available": True, **event_broker.stats()}


@app.get("/api/stream")
async def api_stream(request: Request) -> StreamingResponse:
    async def events():
        queue = event_broker.subscribe()
        try:
            initial = {
                "status": monitor.status(),
                "latest": monitor.latest(),
                "stream": event_broker.stats(),
            }
            yield encode_sse("ready", initial)

            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield encode_sse(item.event, item.data, event_id=item.id)
        finally:
            event_broker.unsubscribe(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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


@app.get("/api/instruments")
async def api_instruments(
    refresh: bool = Query(default=False),
) -> dict[str, object]:
    return await monitor.instruments_metadata(force=refresh)


@app.get("/api/exposure")
async def api_exposure(
    refresh_metadata: bool = Query(default=False),
) -> dict[str, object]:
    latest = monitor.latest()
    metadata = await monitor.instruments_metadata(force=refresh_metadata)
    exposure = build_exposure(
        latest.get("account"),
        latest.get("positions") or [],
        metadata.get("items") or [],
    )
    return {
        "available": latest.get("account") is not None,
        "metadata_available": bool(metadata.get("available")),
        "metadata_stale": bool(metadata.get("stale")),
        "metadata_refreshed_at": metadata.get("refreshed_at"),
        "metadata_error": metadata.get("error"),
        **exposure,
    }


@app.get("/api/history")
def api_history(hours: int = Query(default=24, ge=1, le=720)) -> dict[str, object]:
    items = store.history(hours=hours)
    total = account_snapshot_count(settings.db_path, hours=hours)
    return {
        "items": items,
        "total": total,
        "returned": len(items),
        "truncated": total > len(items),
    }


@app.get("/api/position-history")
def api_position_history(
    ticker: str = Query(..., min_length=1),
    hours: int = Query(default=24, ge=1, le=720),
) -> dict[str, object]:
    items = store.position_history(ticker=ticker, hours=hours)
    total = position_snapshot_count(settings.db_path, ticker=ticker, hours=hours)
    return {
        "items": items,
        "total": total,
        "returned": len(items),
        "truncated": total > len(items),
    }


@app.get("/api/position-events")
def api_position_events(
    limit: int = Query(default=100, ge=1, le=500),
    before_id: int | None = Query(default=None, ge=1),
) -> dict[str, object]:
    return position_events_page(settings.db_path, limit=limit, before_id=before_id)


@app.get("/api/position-lifecycles")
def api_position_lifecycles() -> dict[str, object]:
    latest = monitor.latest()
    events = position_events_all(settings.db_path)
    result = build_position_lifecycles(events, latest.get("positions") or [])
    return {
        **result,
        "source_events": len(events),
        "event_history_complete": True,
    }


@app.get("/api/data-quality")
def api_data_quality(
    hours: int = Query(default=24, ge=1, le=168),
) -> dict[str, object]:
    latest = monitor.latest()
    status = monitor.status()
    return evaluate_data_quality(
        account_history=account_snapshot_timestamps(settings.db_path, hours=hours),
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
        history = position_history_all(settings.db_path, ticker=ticker, hours=hours)
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

    history = account_history_all(settings.db_path, hours=hours)
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
