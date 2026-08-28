# Trading 212 Position Monitor

A read-only Trading 212 portfolio monitor designed so a strategy/execution layer can be added later without rewriting the monitoring stack.

## What it does

- Polls `GET /api/v0/equity/account/summary` and `GET /api/v0/equity/positions`.
- Shows account value, cash, realized/unrealized P&L, and all open positions.
- Calculates per-position local-currency market value and return from quantity, average price, and current price.
- Stores account/position snapshots in SQLite.
- Shows a simple account-value history chart.
- Supports optional local alerts for per-position and whole-portfolio unrealized loss thresholds.
- Contains no order-placement code.

## Security model

Create a Trading 212 API key with read-only permissions for account/portfolio data. Keep the key and secret only in `.env`. Do not commit `.env`.

For live usage, consider restricting the API key to the host's fixed IP/CIDR in Trading 212 settings.

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

The poll interval must be at least five seconds because the account-summary endpoint is rate-limited to one request per five seconds. The positions endpoint permits one request per second.

## API routes exposed by this monitor

- `GET /healthz`
- `GET /api/status`
- `GET /api/latest`
- `GET /api/history?hours=24`
- `GET /api/alerts?limit=50`

## Data model note

Trading 212 reports account summary values in the primary account currency. Position `averagePricePaid` and `currentPrice` are instrument-currency values. Therefore, the monitor labels per-position derived value/P&L in the instrument currency and does not incorrectly sum those derived values across currencies.

## Later quant extension

Keep the current read-only monitor intact and add separate modules for:

1. market-data ingestion,
2. signal/strategy calculation,
3. risk checks and position sizing,
4. execution adapter,
5. order/fill reconciliation,
6. backtest/paper/live mode separation.

Do not give the monitoring key order permissions; use a separate credential for an execution service if/when live trading is added.
