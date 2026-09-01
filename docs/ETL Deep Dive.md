---
title: ETL Deep Dive
subtitle: How I reliably process FI data in run_pipeline.py
date: 2026-08-14
status: Refactor Notes
---

## Why I Refactored

Previously, the pipeline assumed Finansinspektionen (FI) data was complete, database schema operations wouldn't clash, and long-running queries wouldn't lock the UI. If a network call dropped or a row constraint failed, the script would fail silently, leave staging tables behind, or lock Superset dashboards.

I updated the ETL pipeline to follow a simple rule: **Track every boundary, validate data quality early, and use savepoints so failures recover cleanly.**

---

## The Steps Before Writing Data

Instead of dumping files straight into the database, data flows through five plain checks:

[ 1. What's Missing? ] ──► [ 2. Download & Extract ]
│
[ 4. Upsert with Savepoints ] ◄── [ 3. Validate & Stage ]
│
▼
[ 5. Non-Blocking Views ]

1. **Check Gap State:** We query `control.ingested_files` to find missing quarters and mark them `IN_PROGRESS`.
2. **Download & Extract:** We pull zip files with automatic retries and parse the raw XML.
3. **Validate & Stage:** We drop bad ISINs or weights early, record row loss metrics, and write clean records to a temporary staging table.
4. **Savepoint Upsert:** We write to production tables using `SAVEPOINT`. If an error occurs, we roll back *only* that batch without crashing the entire transaction.
5. **Refresh Dashboards:** Materialized views update concurrently using unique indexes so users can keep querying Superset while data reloads.

---

## What Happens When Things Fail

* **If the database is down (Fatal Error / Exit Code 2):**  
  The orchestrator stops immediately. It won't attempt network downloads or run transforms without a state store.

* **If a single quarter or network call fails (Warning / Exit Code 1):**  
  The error message and full traceback are recorded in `control.ingested_files` under `FAILED`. The pipeline logs a warning and moves to the next quarter without stopping the batch.

* **If everything passes (Success / Exit Code 0):**  
  All states mark `COMPLETED`, metrics append to logs, and analytics views refresh cleanly.

---

## What We Track

Every run persists audit data across the system:

* `control.ingested_files`: Tracks quarter states (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`), error tracebacks, and retry counts.
* Data Quality Metrics: Logs original row counts versus dropped rows (missing ISINs, invalid weights, duplicates).
* Phase Metrics: Times each phase and exports status to `control.etl_log`.

---

## Quick Testing

```bash
# Run the complete pipeline
python run_pipeline.py

# Check the exit status
echo $?
```
