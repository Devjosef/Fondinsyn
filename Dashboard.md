# Financial Terminal Dashboard

A lightweight FastAPI + HTMX dashboard for viewing Swedish index fund holdings. It pulls real-time data from PostgreSQL (`analytics.mv_holdings_by_quarter`) with an automatic mock fallback if the database is offline.

---

## Quick Start

```bash
pip install fastapi uvicorn jinja2 sqlalchemy
python dashboard_main.py
```

Open [http://localhost:8000](http://localhost:8000).

## Core Architecture

**Tech Stack:** FastAPI, HTMX, Tailwind CSS (via CDN), and Jinja2. Zero heavy frontend frameworks.

**Real-Time Search:** HTMX swaps table rows dynamically on `keyup` (debounced 200 ms) based on ISIN, fund name, or security name.

**Performance & Safety:** Uses SQLAlchemy connection pooling, parameterized `ILIKE` queries to prevent injection, and a default limit of 100 rows to prevent DOM bloat.

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | `GET` | Main dashboard interface (Jinja2 rendered) |
| `/api/search` | `GET` | HTMX table-row fragment (`?q=<term>&limit=<n>`) |
| `/api/diagnostics` | `GET` | System health, query latency, and record count (JSON) |
| `/api/kpis` | `GET` | Total AUM (SEK) and active fund counts (JSON) |

## ETL Pipeline Integration

The dashboard runs alongside the ETL pipeline and queries the analytics layer directly:

```text
ETL Pipeline → PostgreSQL (analytics.mv_holdings_by_quarter) → FastAPI → HTMX Browser
```

**Data behavior:**

- If PostgreSQL is up, the dashboard queries live data sorted by market value.
- If PostgreSQL is down, it automatically falls back to built-in mock holdings so the UI remains testable.