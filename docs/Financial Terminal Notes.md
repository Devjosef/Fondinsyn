---
title: Financial Terminal Notes
subtitle: How dashboard_main.py serves real-time HTMX queries
date: 2026-08-14
status: Refactor Notes
---

## Why I Built It This Way

Instead of introducing heavy client-side JavaScript frameworks (like React or Vue), the dashboard relies on server-driven UI using **FastAPI, HTMX, Tailwind CSS, and Jinja2**.

The design goal is simple: **Deliver sub-10ms search responses, prevent DOM bloat, and degrade gracefully if the database goes down.**

---

## How Search Queries Work

Rather than sending full-page reloads, HTMX handles targeted table swaps directly:

[ User Types in Search Box ] ──► [ 200ms Debounce ]
                                       │
                                       ▼
[ HTMX Replaces <tbody> ] ◄── [ Server Returns Partial HTML ]
                                       │
                                       ▼
                         [ Parameterized SQL (LIMIT 100) ]

1. **Debounce Inputs:** The search field waits 200ms after keyup to prevent hammering the database.
2. **Fetch Partial HTML:** HTMX queries `GET /api/search?q=<query>` and expects only table rows (`<tbody>`).
3. **Execute Safe Queries:** The server runs parameterized `ILIKE` searches against `analytics.mv_holdings_by_quarter`.
4. **Swap Table Body:** The client swaps out `#table-body` cleanly without losing scroll position or triggering a redraw of the page frame.

---

## Handling Database Failures

* **If PostgreSQL is Down (Graceful Degradation):**  
  The dashboard catches the failure during startup/query execution, logs a warning (`✗ PostgreSQL connection failed`), and falls back to mock data so the UI remains interactive for local testing.

* **If the Connection Drops Mid-Session:**  
  SQLAlchemy connection pooling (`pool_pre_ping=True`) verifies connections before query execution and re-establishes broken links automatically.

* **If the DB is Healthy:**  
  Live metrics (AUM, active fund count, record counts) pull directly from the latest materialized view refresh (`quarter_end = MAX(quarter_end)`).

---

## API Summary

* `GET /`: Renders main dashboard shell (`index.html`).
* `GET /api/search?q=<term>&limit=100`: Returns HTMX table row fragment (`table_rows.html`).
* `GET /api/diagnostics`: Returns DB connection status and latency JSON.
* `GET /api/kpis`: Returns aggregate total AUM and fund counts.

---

## Quick Testing

```bash
# Start the financial terminal
python dashboard_main.py

# Open in browser
open http://localhost:8000