from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import load_settings
from .db import SnapshotStore
from .service import MonitorService

settings = load_settings()
store = SnapshotStore(settings.db_path)
monitor = MonitorService(settings, store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await monitor.start()
    yield
    await monitor.stop()


app = FastAPI(title="Trading 212 Position Monitor", version="1.2.0", lifespan=lifespan)
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


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


@app.get("/api/alerts")
def api_alerts(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, object]:
    return {"items": store.alerts(limit=limit)}
