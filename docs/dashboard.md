# Fondinsyn

**A Swedish-language quarterly fund-holdings explorer built on public data from Finansinspektionen.**

Fondinsyn presents quarterly Swedish fund holdings from PostgreSQL (`analytics.mv_holdings_by_quarter`) in a searchable FastAPI + HTMX interface. Holdings are reported per quarter and reflect FI data after reporting and processing. A small mock dataset is used when PostgreSQL is unavailable so the interface can be tested locally.

## Quick Start

```bash
pip install fastapi uvicorn jinja2 sqlalchemy
python -m app.dashboard_main
```

Open [http://localhost:8000](http://localhost:8000).
Open [http://localhost:8000/datastatus](http://localhost:8000/datastatus) for quarterly ingestion status.

## Core Architecture

**Tech stack:** FastAPI, HTMX, Tailwind CSS (via CDN), and Jinja2.

**Search:** HTMX updates matching table rows when searching by ISIN, fund name, or security name. Search results cover holdings in the latest reported quarter.

**Performance and safety:** Uses SQLAlchemy connection pooling, parameterized `ILIKE` queries, and a default limit of 100 rows.

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | `GET` | Main dashboard interface |
| `/datastatus` | `GET` | Available quarterly releases, ingestion state, FI source links, and recorded timestamps |
| `/api/search` | `GET` | Search results for quarterly holdings (`?q=<term>&limit=<n>`) |
| `/api/diagnostics` | `GET` | Database status, latest quarter, and record count (JSON) |
| `/api/kpis` | `GET` | Reported holdings market value (SEK) and fund count for the latest quarter (JSON) |

## Data flow

```text
Quarterly FI data → PostgreSQL (analytics.mv_holdings_by_quarter) → Fondinsyn
```

- When PostgreSQL is available, the dashboard queries records for the latest reported quarter.
- When PostgreSQL is unavailable, the dashboard uses built-in mock holdings for local testing.
- Datastatus reuses `control.ingested_files`. Publication dates and distinct download timestamps are not stored in the current schema and are shown as unregistered.

## Optional Superset analytics

Superset is an optional analyst-facing view; Fondinsyn remains the canonical application. After analytics materialized views refresh, the ETL provisions three Superset datasets and updates the published Fondinsyn dashboard from the current quarterly holdings view. Its charts show reported market value by quarter, fund, and security, and the dashboard refreshes every 15 minutes. The ETL also clears Superset's cache after synchronization.
