# Financial Terminal & Swedish Index Funds ETL Pipeline

**Project Overview**
This project delivers a production-ready, automated ETL pipeline and an interactive financial terminal dashboard for Swedish index fund holdings. It processes quarterly regulatory reports from Finansinspektionen (FI), consolidating millions of raw asset records into structured analytical views (sector exposure, market cap distribution, QoQ deltas, and fund performance metrics).

**Purpose**
Eliminates manual gathering of fund holdings data by automatically parsing FI's published reports. The system normalizes raw financial reporting into standard market metrics, enabling fast comparative analysis, trend tracking, and risk assessment across Swedish investment funds.

---

## Key Capabilities & Tech Stack

- **Automated Pipeline:** Quarterly extraction of zipped XML files from Finansinspektionen, fully cleaned and transformed into analytical schemas.
- **Real-time Terminal Dashboard:** Built with **FastAPI**, **HTMX**, and **Jinja2** for instant, sub-10ms server-side filtering of holdings across millions of records without heavy client-side JavaScript.
- **Storage & Performance:** **PostgreSQL** with optimized materialized views (`analytics.mv_holdings_by_quarter`), B-tree indexing on ISINs and fund names, and SQLAlchemy connection pooling.
- **Infrastructure:** Fully containerized via **Docker** and **Docker Compose**.

### Tech Stack
- **Backend Framework:** FastAPI, Uvicorn
- **Frontend / UI:** HTMX, HTML5, Jinja2 Templates, CSS
- **Database & ORM:** PostgreSQL 15+, SQLAlchemy
- **Data Processing:** Python 3.11+, Pandas, LXML (XML parsing), PyYAML (config)
- **DevOps:** Docker, Docker Compose

---

## System Architecture & Schema Scale

- **Record Volume:** ~1.79 million historical and active holdings records.
- **Fund Coverage:** 941 active and historical Swedish index funds.
- **Database Schema:** 12 structured relational tables and analytical views (including sector allocation, market cap breakdowns, fund performance, QoQ deltas, country exposure, asset pricing, and diagnostic logs).

---

## Automated Quarterly Execution (FI Reports)

The pipeline is designed around FI's quarterly reporting cycle and handles new releases automatically.

1. **Detection & Extraction:** Checks Finansinspektionen's public register for newly published quarterly zipped XML reports (e.g., `Fondinnehav 2024Q4 ... .zip`)
2. **Ingestion & Validation:** Parses XML payloads, standardizes currencies, verifies asset identifiers (ISINs), and updates `control.etl_log` with run metadata and checksums.
3. **Materialized View Refresh:** Automatically refreshes `analytics.mv_holdings_by_quarter` to reflect the latest quarter end (`quarter_end = MAX(quarter_end)`).
4. **Dashboard Auto-Update:** The FastAPI dashboard immediately serves the newly published quarter data on next page refresh or search query.

### Manual vs. Automated Clarification

- **Automatic:** A background/scheduled task (e.g., cron, systemd timer, or Docker healthcheck + scheduler) polls FI's register for new quarterly files and triggers the ETL when a new quarter is detected.
- **Manual Trigger:** You can still run the pipeline manually for testing or reprocessing:
  ```bash
  python3 etl/run_pipeline.py --quarter latest
  ```

---

## Quickstart & Usage

### 1. Launch with Docker & FastAPI

```bash
# Start PostgreSQL Database Container
docker-compose up -d

# Start Financial Terminal Dashboard Server
python3 dashboard_main.py
```

Access the dashboard at **http://localhost:8000**.

### 2. Trigger Quarterly ETL Update

To manually trigger or test the ETL pipeline for a new FI report cycle:

```bash
python3 etl/run_pipeline.py --quarter latest
```

Optional flags (example):

```bash
python3 etl/run_pipeline.py --quarter 2024Q4 --reprocess
```

---

## Data Sources & Compliance Notes

- **Source:** Finansinspektionen (FI) quarterly fund holdings, published as zipped XML files.
- **Reporting Cadence:** Fund managers report quarterly; FI publishes with a ~2-month delay.
- **Data Format:** XML per FI schemas for UCITS and special funds.
- **Auditability:** All runs are logged in `control.etl_log` with quarter, file hash, record counts, and status for traceability.

---

## Project Status

- **Current Status:** Complete & Production Ready.
- The system is fully operational for the current quarter and configured to seamlessly process and serve new quarterly reports as soon as they are published by Finansinspektionen.

---

## Expected Outcomes

Investors, analysts, and portfolio managers get an up-to-date, clear view of how Swedish index funds are composed each quarter. This makes comparing funds easier by aiding understanding of sector & market risks better. The setup cuts down on manual work and gives timely, standardized insights to back investment decisions.

---

## Final Conclusion

A production-ready ETL pipeline that processes Swedish index fund holdings from Finansinspektionen's quarterly reports. Turned into a 12-table schema (holdings, fund_sector_allocation, market_cap_breakdown, fund_performance, aum_growth, sector time series + 6 more analytical tables) containing 1.79 million holdings records across 941 funds. Delivers comprehensive sector/market cap analysis, country exposure, asset pricing, and a fully built Apache Superset–compatible data model plus a FastAPI/HTMX financial terminal. Manual quarterly updates are no longer required; the system automatically ingests new FI rapport data each quarter. The project is complete and operational for this quarter.
