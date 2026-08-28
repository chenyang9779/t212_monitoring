# Trading 212 Position Monitor

A read-only Trading 212 portfolio monitor designed so a strategy/execution layer can be added later without rewriting the monitoring stack.

## What it does

- Polls Trading 212 account summary and open positions.
- Shows account value, cash, realized/unrealized P&L, and all open positions.
- Stores account and position snapshots in SQLite.
- Detects position OPEN / ADD / REDUCE / CLOSE events while the monitor is running.
- Provides allocation, drawdown, normalized position comparison, and P/L attribution views.
- Exposes read-only pending orders, historical orders, and transactions when the API key has those permissions.
- Stores sampled position marks in a separate market-data table for downstream analytics.
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
T212_POSITION_LOSS_ALERT_PCT=
T212_TOTAL_LOSS_ALERT_PCT=
```

Alert thresholds are disabled when blank. Example: a value of `8` means an alert is recorded when unrealized return is `<= -8%`.

The poll interval must be at least five seconds because the account-summary endpoint is rate-limited more strictly than the positions endpoint.

## API routes exposed by this monitor

Core monitoring:

- `GET /healthz`
- `GET /api/status`
- `GET /api/latest`
- `GET /api/history?hours=24`
- `GET /api/position-history?ticker=...&hours=24`
- `GET /api/position-events?limit=100`
- `GET /api/drawdown?hours=24[&ticker=...]`
- `GET /api/pnl-attribution`
- `GET /api/alerts?limit=50`

Broker history:

- `GET /api/orders/pending`
- `GET /api/orders/history?limit=50`
- `GET /api/transactions?limit=50`

Stored market-data interface:

- `GET /api/market/catalog`
- `GET /api/market/quotes?ticker=...&hours=24`
- `GET /api/market/bars?ticker=...&hours=24&minutes=5`

Supported sampled-bar intervals are `1, 5, 15, 30, 60, 240, 1440` minutes.

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

For a local prototype, the quant service can open `data/monitor.db` in SQLite read-only mode. For a cleaner long-term boundary, prefer consuming the monitor's HTTP API (or exporting data to a dedicated analytical store) so the quant service does not depend on this repository's SQLite schema.

The monitor must never depend on the quant service to keep collecting broker state. The dependency should be one-way: quant reads monitoring data; monitoring does not import strategy code.
