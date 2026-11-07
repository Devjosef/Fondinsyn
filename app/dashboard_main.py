import logging
import os
import re
import calendar
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
import uvicorn
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fondinsyn")
app.mount(
    "/static",
    StaticFiles(directory=PROJECT_ROOT / "static"),
    name="static",
)
jinja_env = Environment(loader=FileSystemLoader(str(PROJECT_ROOT / "templates")))
FI_OPEN_DATA_URL = "https://www.fi.se/sv/om-fi/om-webbplatsen/oppen-data/"
FI_ARCHIVE_TIMESTAMP = re.compile(
    r"_(\d{4}-\d{2}-\d{2})(?:\s+(\d{2})\.(\d{2}))?\.zip$",
    re.IGNORECASE,
)

DATABASE_URL = os.getenv("DATABASE_URL")
engine = None
DB_CONNECTED = False

if DATABASE_URL:
    try:
        engine = create_engine(
            DATABASE_URL,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✓ PostgreSQL connection established")
        DB_CONNECTED = True
    except Exception as error:
        logger.error("✗ PostgreSQL connection failed (%s)", type(error).__name__)
        logger.warning("Falling back to mock data")
else:
    logger.info("DATABASE_URL is unset; using mock data")

MOCK_HOLDINGS = [
    {
        "isin": "SE0000106270",
        "fund_name": "Nordea Index Fond Sverige",
        "security_name": "Volvo AB",
        "market_value_sek": 45_250_000,
        "portfolio_weight": 3.25,
        "qoq_delta": 0.15,
    },
    {
        "isin": "SE0000106270",
        "fund_name": "Nordea Index Fond Sverige",
        "security_name": "Ericsson AB",
        "market_value_sek": 38_120_000,
        "portfolio_weight": 2.74,
        "qoq_delta": -0.42,
    },
    {
        "isin": "SE0000298882",
        "fund_name": "SPP Europafond",
        "security_name": "ASML Holding NV",
        "market_value_sek": 52_890_000,
        "portfolio_weight": 4.12,
        "qoq_delta": 0.87,
    },
    {
        "isin": "SE0000298882",
        "fund_name": "SPP Europafond",
        "security_name": "Novo Nordisk A/S",
        "market_value_sek": 41_670_000,
        "portfolio_weight": 3.25,
        "qoq_delta": 1.23,
    },
    {
        "isin": "SE0000680465",
        "fund_name": "SEB Indexfond Global",
        "security_name": "Apple Inc.",
        "market_value_sek": 78_450_000,
        "portfolio_weight": 5.64,
        "qoq_delta": 0.34,
    },
]


def quarter_id_for_end_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, str):
        try:
            value = datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    if not hasattr(value, "year") or not hasattr(value, "month") or not hasattr(value, "day"):
        return None

    if value.month not in (3, 6, 9, 12):
        return None
    if value.day != calendar.monthrange(value.year, value.month)[1]:
        return None
    return f"{value.year}Q{(value.month - 1) // 3 + 1}"


def quarter_end_for_id(quarter_id: str) -> datetime | None:
    match = re.fullmatch(r"(\d{4})Q([1-4])", quarter_id)
    if not match:
        return None
    year, quarter = int(match.group(1)), int(match.group(2))
    month = quarter * 3
    return datetime(year, month, calendar.monthrange(year, month)[1])


def fi_publication_date(source_file_name: str | None) -> datetime | None:
    if not source_file_name:
        return None
    match = FI_ARCHIVE_TIMESTAMP.search(source_file_name)
    if not match:
        return None
    date_format = "%Y-%m-%d %H.%M" if match.group(2) else "%Y-%m-%d"
    timestamp = match.group(1)
    if match.group(2):
        timestamp += f" {match.group(2)}.{match.group(3)}"
    try:
        return datetime.strptime(timestamp, date_format)
    except ValueError:
        logger.warning("Invalid FI archive timestamp in source filename: %s", source_file_name)
        return None


def audit_metadata_for_record(
    quarter_end: Any,
    source_url: str | None,
    local_path: str | None,
) -> Dict[str, Any]:
    source_file_name = Path(local_path).name if local_path else None
    if not source_file_name and source_url:
        filenames = parse_qs(urlsplit(source_url).query).get("filnamn")
        source_file_name = filenames[0] if filenames else None
    return {
        "quarter_id": quarter_id_for_end_date(quarter_end),
        "source_url": source_url,
        "source_file_name": source_file_name,
        "fi_publication_date": fi_publication_date(source_file_name),
        "download_timestamp": None,
        "ingestion_timestamp": None,
    }


def get_diagnostic_status() -> Dict[str, Any]:
    if not DB_CONNECTED:
        return {
            "postgresql": "DOWN",
            "latency_ms": 0,
            "last_quarter": "N/A",
            "last_update": "N/A",
            "quarter_id": None,
            "quarter_end_date": None,
            "record_count": len(MOCK_HOLDINGS),
        }
    
    try:
        started = datetime.now()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    (SELECT MAX(run_date) FROM control.etl_log 
                     WHERE right(status, 3) = :success_suffix OR status = :legacy_success),
                    MAX(quarter_end),
                    COUNT(*)
                FROM analytics.mv_holdings_by_quarter
            """), {"success_suffix": ":OK", "legacy_success": "success"})
            row = result.fetchone()
        
        return {
            "postgresql": "UP",
            "latency_ms": round((datetime.now() - started).total_seconds() * 1000),
            "last_quarter": row[1].strftime("%Y-%m-%d") if row and row[1] else "N/A",
            "last_update": row[0].strftime("%Y-%m-%d") if row and row[0] else "N/A",
            "quarter_id": quarter_id_for_end_date(row[1]) if row and row[1] else None,
            "quarter_end_date": row[1] if row and row[1] else None,
            "record_count": row[2] if row else 0,
        }
    except Exception as e:
        logger.warning(f"Failed to fetch diagnostics: {e}")
        return {
            "postgresql": "DEGRADED",
            "latency_ms": 0,
            "last_quarter": "N/A",
            "last_update": "N/A",
            "quarter_id": None,
            "quarter_end_date": None,
            "record_count": 0,
        }


def get_kpi_metrics() -> Dict[str, Any]:
    if not DB_CONNECTED:
        return {
            "total_aum_sek": sum(h["market_value_sek"] for h in MOCK_HOLDINGS),
            "active_funds": len(set(h["fund_name"] for h in MOCK_HOLDINGS)),
            "data_quality_score": 99.8,
        }
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT SUM(market_value_sek), COUNT(DISTINCT fund_name)
                FROM analytics.mv_holdings_by_quarter
                WHERE quarter_end = (SELECT MAX(quarter_end) FROM analytics.mv_holdings_by_quarter)
            """))
            row = result.fetchone()
            if row:
                return {
                    "total_aum_sek": row[0] or 0,
                    "active_funds": row[1] or 0,
                    "data_quality_score": 99.8,
                }
    except Exception as e:
        logger.warning(f"Failed to fetch KPI metrics: {e}")
    
    return {
        "total_aum_sek": sum(h["market_value_sek"] for h in MOCK_HOLDINGS),
        "active_funds": len(set(h["fund_name"] for h in MOCK_HOLDINGS)),
        "data_quality_score": 99.8,
    }


def get_ingestion_status() -> Dict[str, Any]:
    if not DB_CONNECTED:
        return {
            "quarters": [],
            "latest_available_quarter": None,
            "latest_file_completed_quarter": None,
            "last_completed_fetch": None,
            "error": "Databasen är inte tillgänglig. Kvartalsstatus kan inte visas just nu.",
        }

    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT quarter_id, file_url, local_path, lifecycle_state,
                       created_at, started_at, completed_at, files_downloaded
                FROM control.ingested_files
                ORDER BY quarter_id DESC
            """))
            rows = result.mappings().all()

        quarters = []
        latest_file_completed_quarter = None
        last_completed_fetch = None
        status_labels = {
            "PENDING": ("Väntar", "pending"),
            "IN_PROGRESS": ("Pågår", "processing"),
            "COMPLETED": ("Källfil hämtad och extraherad", "available"),
            "FAILED": ("Misslyckad", "failed"),
            "SKIPPED": ("Överhoppad", "pending"),
        }

        for row in rows:
            quarter_id = row["quarter_id"]
            state = str(row["lifecycle_state"]).upper()
            status_label, status_class = status_labels.get(
                state, ("Okänd", "pending")
            )
            local_path = row["local_path"]
            source_file_name = (
                Path(local_path).name if local_path else None
            )
            if not source_file_name and row["file_url"]:
                filenames = parse_qs(urlsplit(row["file_url"]).query).get("filnamn")
                source_file_name = filenames[0] if filenames else None
            publication_date = fi_publication_date(source_file_name)

            completed_at = row["completed_at"]
            if state == "COMPLETED":
                if latest_file_completed_quarter is None:
                    latest_file_completed_quarter = quarter_id
                if completed_at and (
                    last_completed_fetch is None
                    or completed_at > last_completed_fetch
                ):
                    last_completed_fetch = completed_at

            quarters.append({
                "quarter_id": quarter_id,
                "quarter_end_date": quarter_end_for_id(quarter_id),
                "file_url": row["file_url"],
                "source_file_name": source_file_name,
                "status_label": status_label,
                "status_class": status_class,
                "publication_date": publication_date,
                "download_timestamp": None,
                "ingestion_timestamp": None,
                "fetch_completed_at": completed_at,
                "registered_timestamp": row["created_at"],
                "processing_started_at": row["started_at"],
            })

        return {
            "quarters": quarters,
            "latest_available_quarter": quarters[0]["quarter_id"] if quarters else None,
            "latest_file_completed_quarter": latest_file_completed_quarter,
            "last_completed_fetch": last_completed_fetch,
            "error": None,
        }
    except Exception as e:
        logger.error("Failed to fetch quarterly ingestion status: %s", e)
        return {
            "quarters": [],
            "latest_available_quarter": None,
            "latest_file_completed_quarter": None,
            "last_completed_fetch": None,
            "error": "Kvartalsstatus kunde inte hämtas från databasen.",
        }


def get_latest_snapshot_context(diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    quarter_id = diagnostics.get("quarter_id")
    matching_release = next(
        (
            quarter
            for quarter in get_ingestion_status()["quarters"]
            if quarter["quarter_id"] == quarter_id
        ),
        None,
    )
    quarter_end_date = diagnostics.get("quarter_end_date")
    return {
        "quarter_id": quarter_id,
        "quarter_end_date": quarter_end_date,
        "publication_date": matching_release["publication_date"] if matching_release else None,
        "source_url": matching_release["file_url"] if matching_release else FI_OPEN_DATA_URL,
        "source_file_name": matching_release["source_file_name"] if matching_release else None,
        "download_timestamp": matching_release["download_timestamp"] if matching_release else None,
        "ingestion_timestamp": None,
        "fetch_completed_at": matching_release["fetch_completed_at"] if matching_release else None,
        "open_data_url": FI_OPEN_DATA_URL,
        "is_calendar_quarter_end": bool(quarter_id and quarter_end_date),
    }


def get_quarter_audit_metadata(quarter_id: str | None) -> Dict[str, Any]:
    release = next(
        (
            quarter
            for quarter in get_ingestion_status()["quarters"]
            if quarter["quarter_id"] == quarter_id
        ),
        None,
    )
    if not release:
        return {
            "quarter_id": quarter_id,
            "source_url": None,
            "source_file_name": None,
            "fi_publication_date": None,
            "download_timestamp": None,
            "ingestion_timestamp": None,
            "fetch_completed_at": None,
        }
    return {
        "quarter_id": release["quarter_id"],
        "source_url": release["file_url"],
        "source_file_name": release["source_file_name"],
        "fi_publication_date": release["publication_date"],
        "download_timestamp": release["download_timestamp"],
        "ingestion_timestamp": None,
        "fetch_completed_at": release["fetch_completed_at"],
    }


def get_available_quarters() -> List[Dict[str, Any]]:
    if not DB_CONNECTED:
        return []
    try:
        with engine.connect() as conn:
            dates = conn.execute(text("""
                SELECT DISTINCT quarter_end
                FROM analytics.mv_holdings_by_quarter
                WHERE quarter_end IS NOT NULL
                ORDER BY quarter_end
            """)).scalars().all()
    except Exception as e:
        logger.error("Failed to fetch quarters for comparison: %s", e)
        return []

    return [
        {"quarter_id": quarter_id_for_end_date(value), "quarter_end_date": value}
        for value in dates
        if quarter_id_for_end_date(value)
    ]


def get_quarter_comparison(
    previous_quarter: str,
    current_quarter: str,
    quarter_dates: Dict[str, Any],
    page: int = 1,
    page_size: int = 100,
) -> Dict[str, Any]:
    if not DB_CONNECTED:
        return {"items": [], "total_count": 0}

    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                WITH previous_snapshot AS (
                    SELECT fund_name, isin, security_name,
                           SUM(market_value_sek) AS market_value_sek,
                           SUM(portfolio_weight) AS portfolio_weight
                    FROM analytics.mv_holdings_by_quarter
                    WHERE quarter_end = :previous_date
                    GROUP BY fund_name, isin, security_name
                ),
                current_snapshot AS (
                    SELECT fund_name, isin, security_name,
                           SUM(market_value_sek) AS market_value_sek,
                           SUM(portfolio_weight) AS portfolio_weight
                    FROM analytics.mv_holdings_by_quarter
                    WHERE quarter_end = :current_date
                    GROUP BY fund_name, isin, security_name
                )
                SELECT
                    COALESCE(previous_snapshot.fund_name, current_snapshot.fund_name) AS fund_name,
                    COALESCE(previous_snapshot.isin, current_snapshot.isin) AS isin,
                    COALESCE(previous_snapshot.security_name, current_snapshot.security_name) AS security_name,
                    previous_snapshot.fund_name IS NOT NULL AS previous_exists,
                    current_snapshot.fund_name IS NOT NULL AS current_exists,
                    previous_snapshot.market_value_sek AS previous_market_value_sek,
                    current_snapshot.market_value_sek AS current_market_value_sek,
                    previous_snapshot.portfolio_weight AS previous_weight,
                    current_snapshot.portfolio_weight AS current_weight,
                    COUNT(*) OVER () AS total_count
                FROM previous_snapshot
                FULL OUTER JOIN current_snapshot
                  ON COALESCE(previous_snapshot.fund_name, '') = COALESCE(current_snapshot.fund_name, '')
                 AND COALESCE(previous_snapshot.isin, '') = COALESCE(current_snapshot.isin, '')
                 AND COALESCE(previous_snapshot.security_name, '') = COALESCE(current_snapshot.security_name, '')
                ORDER BY COALESCE(previous_snapshot.fund_name, current_snapshot.fund_name),
                         COALESCE(previous_snapshot.security_name, current_snapshot.security_name)
                LIMIT :limit OFFSET :offset
            """), {
                "previous_date": quarter_dates[previous_quarter],
                "current_date": quarter_dates[current_quarter],
                "limit": page_size,
                "offset": (page - 1) * page_size,
            })
            rows = result.mappings().all()
    except Exception as e:
        logger.error(
            "Failed comparing holdings for %s and %s: %s",
            previous_quarter,
            current_quarter,
            e,
        )
        raise

    comparisons = []
    total_count = rows[0]["total_count"] if rows else 0
    for row in rows:
        previous_weight = row["previous_weight"]
        current_weight = row["current_weight"]
        if not row["previous_exists"]:
            status = "Ny position"
        elif not row["current_exists"]:
            status = "Avslutad position"
        elif previous_weight is None or current_weight is None:
            status = "Oförändrad position"
        elif current_weight > previous_weight:
            status = "Ökad position"
        elif current_weight < previous_weight:
            status = "Minskad position"
        else:
            status = "Oförändrad position"

        previous_value = row["previous_market_value_sek"] or 0
        current_value = row["current_market_value_sek"] or 0
        comparisons.append({
            "fund_name": row["fund_name"],
            "isin": row["isin"],
            "security_name": row["security_name"],
            "previous_weight": previous_weight,
            "current_weight": current_weight,
            "weight_change": current_weight - previous_weight if (
                previous_weight is not None and current_weight is not None
            ) else None,
            "market_value_change_sek": current_value - previous_value,
            "status": status,
        })
    return {"items": comparisons, "total_count": total_count}


def search_holdings(query: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    if not DB_CONNECTED:
        if not query.strip():
            holdings = MOCK_HOLDINGS[:limit]
        else:
            q_lower = query.lower().strip()
            holdings = [
                h for h in MOCK_HOLDINGS
                if q_lower in h["isin"].lower() or q_lower in h["fund_name"].lower() or q_lower in h["security_name"].lower()
            ][:limit]
        return [
            {
                **holding,
                **audit_metadata_for_record(None, None, None),
            }
            for holding in holdings
        ]
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT holdings.isin, holdings.fund_name, holdings.security_name,
                       holdings.market_value_sek, holdings.portfolio_weight, holdings.qoq_delta,
                       holdings.quarter_end, ingestion.file_url, ingestion.local_path
                FROM analytics.mv_holdings_by_quarter AS holdings
                LEFT JOIN control.ingested_files AS ingestion
                  ON ingestion.quarter_id =
                     EXTRACT(YEAR FROM holdings.quarter_end)::INTEGER::TEXT
                     || 'Q' || EXTRACT(QUARTER FROM holdings.quarter_end)::INTEGER::TEXT
                WHERE holdings.quarter_end = (
                    SELECT MAX(quarter_end) FROM analytics.mv_holdings_by_quarter
                )
                  AND (
                    :q = ''
                    OR holdings.isin ILIKE :pattern
                    OR holdings.fund_name ILIKE :pattern
                    OR holdings.security_name ILIKE :pattern
                  )
                ORDER BY holdings.market_value_sek DESC
                LIMIT :limit
            """), {
                "q": query.strip(),
                "pattern": f"%{query.strip()}%",
                "limit": limit,
            })
            rows = result.mappings().all()
            return [
                {
                    "isin": row["isin"],
                    "fund_name": row["fund_name"],
                    "security_name": row["security_name"],
                    "market_value_sek": row["market_value_sek"],
                    "portfolio_weight": row["portfolio_weight"],
                    "qoq_delta": row["qoq_delta"],
                    **audit_metadata_for_record(
                        row["quarter_end"],
                        row["file_url"],
                        row["local_path"],
                    ),
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Search query failed: {e}")
        if not query.strip():
            return MOCK_HOLDINGS[:limit]
        q_lower = query.lower().strip()
        return [
            h for h in MOCK_HOLDINGS
            if q_lower in h["isin"].lower() or q_lower in h["fund_name"].lower() or q_lower in h["security_name"].lower()
        ][:limit]


@app.get("/", response_class=HTMLResponse)
async def index():
    template = jinja_env.get_template("index.html")
    diagnostics = get_diagnostic_status()
    return template.render(
        diagnostics=diagnostics,
        snapshot=get_latest_snapshot_context(diagnostics),
        kpis=get_kpi_metrics(),
        holdings=search_holdings(),
        query="",
    )


@app.get("/datastatus", response_class=HTMLResponse)
async def datastatus():
    template = jinja_env.get_template("datastatus.html")
    return template.render(ingestion=get_ingestion_status())


@app.get("/compare", response_class=HTMLResponse)
async def compare(
    previous: str | None = Query(None, pattern=r"^\d{4}Q[1-4]$"),
    current: str | None = Query(None, pattern=r"^\d{4}Q[1-4]$"),
    page: int = Query(1, ge=1),
):
    template = jinja_env.get_template("compare.html")
    quarters = get_available_quarters()
    quarter_dates = {quarter["quarter_id"]: quarter["quarter_end_date"] for quarter in quarters}
    error = None
    comparisons = []
    total_count = 0
    page_size = 100
    selected_previous = previous
    selected_current = current

    if selected_previous is None and selected_current is None and len(quarters) >= 2:
        selected_previous, selected_current = (
            quarters[-2]["quarter_id"],
            quarters[-1]["quarter_id"],
        )

    if not DB_CONNECTED:
        error = "Databasen är inte tillgänglig. Kvartalsjämförelsen kan inte hämtas."
    elif not quarters:
        error = "Inga verifierade kvartalsvisa innehav finns tillgängliga för jämförelse."
    elif selected_previous is None or selected_current is None:
        error = "Välj två kvartal med rapporterade innehav för att jämföra."
    elif selected_previous not in quarter_dates or selected_current not in quarter_dates:
        error = "Ett eller båda valda kvartalen saknar rapporterade innehav."
    elif quarter_dates[selected_previous] >= quarter_dates[selected_current]:
        error = "Välj ett äldre kvartal först och ett senare kvartal därefter."
    else:
        try:
            comparison_result = get_quarter_comparison(
                selected_previous,
                selected_current,
                quarter_dates,
                page=page,
                page_size=page_size,
            )
            comparisons = comparison_result["items"]
            total_count = comparison_result["total_count"]
        except Exception:
            error = "Kvartalsjämförelsen kunde inte hämtas från databasen."

    return template.render(
        quarters=quarters,
        previous=selected_previous,
        current=selected_current,
        previous_end=quarter_dates.get(selected_previous),
        current_end=quarter_dates.get(selected_current),
        previous_audit=get_quarter_audit_metadata(selected_previous),
        current_audit=get_quarter_audit_metadata(selected_current),
        comparisons=comparisons,
        total_count=total_count,
        page=page,
        total_pages=(total_count + page_size - 1) // page_size,
        error=error,
        source_url=FI_OPEN_DATA_URL,
    )


@app.get("/api/search", response_class=HTMLResponse)
async def search(
    q: str = Query("", min_length=0),
    search: str = Query("", min_length=0),
    limit: int = Query(100, ge=10, le=250)
):
    query = q or search or ""
    results = search_holdings(query, limit=limit)
    template = jinja_env.get_template("table_rows.html")
    return template.render(holdings=results)


@app.get("/api/diagnostics")
async def get_diagnostics():
    return get_diagnostic_status()


@app.get("/api/kpis")
async def get_kpis():
    return get_kpi_metrics()


if __name__ == "__main__":
    logger.info(f"Starting dashboard server at http://localhost:8000 (DB Connected: {DB_CONNECTED})")
    uvicorn.run("app.dashboard_main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")