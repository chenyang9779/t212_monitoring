# Trading 212 Position Monitor

A read-only Trading 212 portfolio monitor designed so a strategy/execution layer can be added later without rewriting the monitoring stack.

## What it does

- Polls Trading 212 account summary and open positions.
- Shows account value, cash, realized/unrealized P&L, and all open positions.
- Stores account and position snapshots in SQLite.
- Detects position OPEN / ADD / REDUCE / CLOSE events while the monitor is running.
- Provides allocation, drawdown, normalized position comparison, P/L attribution, and instrument exposure views.
- Exposes read-only pending orders, historical orders, and transactions when the API key has those permissions.
- Caches Trading 212 instrument metadata for quoted-currency and instrument-type exposure.
- Stores sampled position marks in a separate market-data table for downstream analytics.
- Exposes CSV and JSONL download endpoints for downstream notebooks and services.
- Exposes an SSE live stream for browsers and other read-only consumers.
- Provides liveness/readiness probes, request IDs, startup diagnostics, and structured application logs.
- Contains no order-placement code.

## Security model

Create a Trading 212 API key with read-only permissions for account/portfolio data. Keep the key and secret only in `.env`. Do not commit `.env`.

For live usage, consider restricting the API key to the host's fixed IP/CIDR in Trading 212 settings.

If a separate quant/execution service is added later, give any order-capable credentials to that service only. Do not add execution permissions to the monitoring key.

## Setup

Python 3.11+ is recommended.

```bash
cd trading212-position-monitor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` locally and set `T212_API_KEY` and `T212_API_SECRET`. Keep `T212_ENV=demo` while validating the integration. Switch to `T212_ENV=live` only when you want to read the real account.

Run:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

## Configuration

```dotenv
T212_API_KEY=
T212_API_SECRET=
T212_ENV=demo
T212_POLL_SECONDS=6
T212_SNAPSHOT_SECONDS=30
T212_DB_PATH=data/monitor.db
T212_RAW_RETENTION_DAYS=
T212_POSITION_LOSS_ALERT_PCT=
T212_TOTAL_LOSS_ALERT_PCT=
```

Alert thresholds are disabled when blank. Example: a value of `8` means an alert is recorded when unrealized return is `<= -8%`.

`T212_RAW_RETENTION_DAYS` is also disabled when blank. When configured, the monitor periodically removes older account snapshots, position snapshots, and sampled market quotes while keeping low-volume audit data such as position events and alerts.

The poll interval must be at least five seconds because the account-summary endpoint is rate-limited more strictly than the positions endpoint.

## API routes exposed by this monitor

Core monitoring:

- `GET /healthz`
- `GET /readyz`
- `GET /api/operations`
- `GET /api/status`
- `GET /api/storage`
- `GET /api/latest`
- `GET /api/instruments[?refresh=true]`
- `GET /api/exposure[?refresh_metadata=true]`
- `GET /api/history?hours=24`
- `GET /api/position-history?ticker=...&hours=24`
- `GET /api/position-events?limit=100`
- `GET /api/position-lifecycles?event_limit=500`
- `GET /api/data-quality?hours=24`
- `GET /api/reconciliation?event_limit=50&tolerance_seconds=180`
- `GET /api/drawdown?hours=24[&ticker=...]`
- `GET /api/pnl-attribution`
- `GET /api/alerts?limit=50`

Live stream:

- `GET /api/stream`
- `GET /api/stream/status`

Broker history:

- `GET /api/orders/pending`
- `GET /api/orders/history?limit=50`
- `GET /api/transactions?limit=50`

Stored market-data interface:

- `GET /api/market/catalog`
- `GET /api/market/quotes?ticker=...&hours=24`
- `GET /api/market/bars?ticker=...&hours=24&minutes=5`

Supported sampled-bar intervals are `1, 5, 15, 30, 60, 240, 1440` minutes.

## Operational hardening

`GET /healthz` is a lightweight liveness endpoint. It answers while the process is running and also exposes whether startup checks found configuration or local-resource problems.

`GET /readyz` is stricter. It returns HTTP `200` only when startup checks succeeded, SQLite is queryable, the broker monitor is connected, and the last successful Trading 212 sync is fresh. Otherwise it returns HTTP `503` with machine-readable reasons such as `broker_not_connected`, `broker_sync_stale`, `database_unavailable`, or `startup_checks_failed`.

`GET /api/operations` exposes the startup report, current readiness calculation, and SSE stream counters for local/operator diagnostics.

Every HTTP request receives an `X-Request-ID` response header. A caller-supplied `X-Request-ID` is preserved only when it matches a conservative safe-character policy; otherwise the server generates a new ID. Application request logs are emitted as one-line JSON with UTC timestamps, log level, request ID, method, path, status code, and duration. Unhandled exceptions are logged with the same request ID.

The FastAPI lifespan logs explicit startup/stopping/stopped events and always awaits `monitor.stop()` during shutdown, so the polling task and HTTP client are closed before process exit.

Example probes:

```bash
curl -i http://127.0.0.1:8000/healthz
curl -i http://127.0.0.1:8000/readyz
curl -s http://127.0.0.1:8000/api/operations | python -m json.tool
```

For a service manager or container orchestrator, use `/healthz` as the liveness probe and `/readyz` as the readiness probe.

## Instrument metadata and exposure

`GET /api/instruments` fetches Trading 212's read-only instrument metadata and caches it in memory for six hours. `?refresh=true` forces a refresh. Metadata failures do not mark the core portfolio monitor disconnected; if a previous metadata response exists, the endpoint can continue serving it as stale cache.

`GET /api/exposure` joins current open positions to that metadata and aggregates **account-currency position values** by:

- instrument quoted currency, and
- Trading 212 instrument type.

The exposure code deliberately does not invent sector or country classifications. Quoted currency is also not treated as issuer domicile or economic/revenue exposure. A future provider can add sector/country metadata under a separate source without changing that distinction.

## SSE live stream

`GET /api/stream` is a read-only Server-Sent Events feed. A new connection first receives a `ready` event containing current monitor status and the latest portfolio state. Subsequent events are emitted from the existing monitor polling loop; opening the stream does not create extra Trading 212 polling requests.

Current event names:

- `ready` — current monitor status and latest portfolio on connection.
- `portfolio` — normalized account and open-position state after a successful Trading 212 poll.
- `snapshot` — emitted after a local SQLite snapshot is saved.
- `position_event` — an observed OPEN / ADD / REDUCE / CLOSE quantity change.
- `alert` — a newly activated monitor alert.
- `monitor_error` — a Trading 212 monitoring error.
- `maintenance` / `maintenance_error` — optional retention-maintenance status.

The server sends comment heartbeats every 15 seconds when no event is available. Each subscriber has a bounded in-memory queue; a slow consumer drops its oldest pending event rather than blocking the broker polling loop. This stream is therefore intended for live state notification, not as an authoritative durable event log. Durable consumers should use SQLite/export/history endpoints to recover state after disconnects.

The browser dashboard opens the SSE stream automatically. Existing periodic refreshes remain as a fallback while the dashboard is progressively migrated toward event-driven updates.

You can inspect the feed directly:

```bash
curl -N http://127.0.0.1:8000/api/stream
```

And inspect stream counters:

```bash
curl -s http://127.0.0.1:8000/api/stream/status | python -m json.tool
```

## Export API

All export endpoints are read-only and accept `format=csv` or `format=jsonl`. CSV is the default. Responses include `Content-Disposition` and an `X-Export-Rows` header.

Local datasets:

- `GET /api/export/positions?format=csv`
- `GET /api/export/account-history?hours=24&format=csv`
- `GET /api/export/position-history?ticker=...&hours=24&format=csv`
- `GET /api/export/position-events?limit=500&format=csv`
- `GET /api/export/alerts?limit=500&format=jsonl`
- `GET /api/export/market-quotes?ticker=...&hours=24&format=csv`
- `GET /api/export/market-bars?ticker=...&hours=24&minutes=5&format=csv`

Broker-backed datasets:

- `GET /api/export/orders/history?limit=50&format=csv`
- `GET /api/export/transactions?limit=50&format=csv`

Broker-backed exports intentionally fetch at most one Trading 212 history page per request. If more broker pages exist, the response includes `X-Export-Has-More: true`. This prevents a single download request from recursively consuming the broker history rate limit.

Nested broker payloads are flattened into dotted CSV columns such as `order.ticker`. JSONL retains one JSON object per line. CSV string values that begin with spreadsheet formula prefixes are escaped to reduce formula-injection risk when files are opened in Excel or similar software.

Examples:

```bash
curl -OJ "http://127.0.0.1:8000/api/export/positions"
curl -OJ "http://127.0.0.1:8000/api/export/account-history?hours=168&format=csv"
curl -OJ "http://127.0.0.1:8000/api/export/market-bars?ticker=AAPL_US_EQ&hours=168&minutes=5&format=jsonl"
```

## Market-data model

The monitor now has a separate `market_quotes` domain. Every saved portfolio snapshot copies the Trading 212 `currentPrice` for each open position into `market_quotes` with source `t212_position`.

On first startup after this schema is introduced, existing `position_snapshots.current_price` values are backfilled once into `market_quotes`.

Important: these are **sampled broker position marks**, not exchange tick data and not authoritative exchange OHLC bars. The `/api/market/bars` endpoint aggregates the observed samples into OHLC-style buckets for research convenience. For production-grade quant research, add a dedicated external market-data provider and store that feed under a separate source.

## Data model note

Trading 212 reports account summary values in the primary account currency. Position `averagePricePaid` and `currentPrice` are instrument-currency values. Cross-position portfolio analytics therefore use account-currency wallet-impact fields when available and avoid summing incompatible instrument currencies.

## Quant architecture

The quant component should be a separate service or repository. The monitor should remain the read-only broker-state and data-capture service.

Recommended boundary:

```text
Trading 212
    │
    ▼
t212_monitoring
    ├── account snapshots
    ├── position snapshots
    ├── position events
    ├── broker orders / transactions
    └── sampled market quotes
            │
            │ read-only data contract
            ▼
quant_service
    ├── feature generation
    ├── signals
    ├── portfolio construction
    ├── risk
    ├── backtest / paper mode
    └── optional execution adapter
```

For a local prototype, the quant service can open `data/monitor.db` in SQLite read-only mode. For a cleaner long-term boundary, prefer consuming the monitor's HTTP API, export endpoints, or SSE notifications so the quant service does not depend on this repository's SQLite schema.

The monitor must never depend on the quant service to keep collecting broker state. The dependency should be one-way: quant reads monitoring data; monitoring does not import strategy code.
