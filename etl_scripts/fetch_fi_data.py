import logging
import os
import re
import shutil
import sys
import traceback
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
import yaml
from lxml import html as lxml_html
from sqlalchemy import create_engine, text
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError, IntegrityError

logger = logging.getLogger(__name__)

FI_BASE_URL = "https://www.fi.se/sv/vara-register/fondinnehav-per-kvartal/"
DATA_RAW_DIR = os.getenv("FI_DATA_PATH", "data/raw")

# FI serves the download links from the bare host "fi.se", while the page's
# canonical URL is on "www.fi.se". Accept both.
FI_HOSTS = {"fi.se", "www.fi.se"}

# The real filnamn value looks like "Fondinnehav_2026Q2_2026-10-14 08.12.zip".
# The anchor text uses spaces instead of underscores, so tolerate both.
QUARTERLY_ARCHIVE_REGEX = r"Fondinnehav[_ ](\d{4}Q[1-4])[_ ].*\.zip$"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; fi-holdings-fetcher/1.0)"}

Path(DATA_RAW_DIR).mkdir(parents=True, exist_ok=True)


def discover_fi_archives() -> Dict[str, str]:
    """Find official quarterly ZIP URLs on FI's public fund holdings page."""
    response = requests.get(FI_BASE_URL, timeout=30, headers=HEADERS)
    response.raise_for_status()
    document = lxml_html.fromstring(response.content)
    anchors = document.xpath("//a[@href]")
    logger.info(
        f"FI page fetched: status={response.status_code} url={response.url} "
        f"anchors={len(anchors)}"
    )
    archives = {}

    for anchor in anchors:
        archive_url = urljoin(response.url, anchor.get("href"))
        parsed_url = urlsplit(archive_url)
        if parsed_url.scheme != "https" or parsed_url.hostname not in FI_HOSTS:
            continue

        query = parse_qs(parsed_url.query)
        filename = query.get("filnamn", [anchor.text_content().strip()])[0]
        match = re.search(QUARTERLY_ARCHIVE_REGEX, filename, re.IGNORECASE)
        if match:
            archives[match.group(1).upper()] = archive_url

    if not archives:
        raise RuntimeError(
            f"No FI quarterly ZIP archives found at {FI_BASE_URL} "
            f"(final url {response.url}, {len(anchors)} anchors)"
        )
    return archives


def archive_filename(file_url: str) -> Optional[str]:
    """Return FI's filename (with publication timestamp) from a download URL."""
    values = parse_qs(urlsplit(file_url).query).get("filnamn")
    return values[0] if values else None


def build_engine(config: dict):
    db_config = config['database']
    db_conn_str = (
        f"postgresql://CREDENTIAL_REMOVED_9bcf166e240683cd1b72a7f9d05b8274@"
        f"{db_config['host']}:{db_config['port']}/{db_config['db_name']}"
    )
    return create_engine(db_conn_str, pool_pre_ping=True, echo=False)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type((OperationalError, IntegrityError))
)
def update_ingestion_state(
    config: dict,
    quarter_id: str,
    file_url: str,
    new_state: str,
    error_msg: Optional[str] = None,
    error_traceback: Optional[str] = None,
    metrics: Optional[Dict] = None
) -> Dict:
    engine = build_engine(config)
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id, lifecycle_state, created_at, completed_at
                FROM control.sp_upsert_ingestion_state(
                    :quarter_id,
                    :file_url,
                    :new_state,
                    :error_msg,
                    :error_trace
                )
            """), {
                'quarter_id': quarter_id,
                'file_url': file_url,
                'new_state': new_state,
                'error_msg': error_msg,
                'error_trace': error_traceback
            })
            row = result.fetchone()

            if metrics and row:
                conn.execute(text("""
                    UPDATE control.ingested_files
                    SET files_downloaded = :files_downloaded,
                        holdings_extracted = :holdings_extracted,
                        xml_parse_errors = :xml_parse_errors
                    WHERE id = :id
                """), {
                    'id': row[0],
                    'files_downloaded': metrics.get('files_downloaded', 0),
                    'holdings_extracted': metrics.get('holdings_extracted', 0),
                    'xml_parse_errors': metrics.get('xml_parse_errors', 0)
                })

            conn.commit()
            return {
                'id': row[0],
                'lifecycle_state': row[1],
                'created_at': row[2],
                'completed_at': row[3]
            }
    except Exception as e:
        logger.error(f"State transition failed for {quarter_id}: {e}")
        raise
    finally:
        engine.dispose()


def get_pending_quarters(config: dict) -> List[str]:
    engine = build_engine(config)
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT quarter_id
                FROM control.ingested_files
                WHERE lifecycle_state IN ('PENDING', 'FAILED')
                  AND retry_count < 3
                ORDER BY created_at ASC
            """))
            return [row[0] for row in result.fetchall()]
    except Exception as e:
        logger.error(f"Failed to query pending quarters: {e}")
        return []
    finally:
        engine.dispose()


def get_completed_quarters(config: dict) -> set:
    engine = build_engine(config)
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT quarter_id
                FROM control.ingested_files
                WHERE lifecycle_state = 'COMPLETED'
            """))
            return {row[0] for row in result.fetchall()}
    except Exception as e:
        logger.error(f"Failed to query completed quarters: {e}")
        return set()
    finally:
        engine.dispose()


def get_loaded_quarters(config: dict) -> set:
    """Return quarters already represented in raw.holdings."""
    engine = build_engine(config)
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT DISTINCT
                    EXTRACT(YEAR FROM date)::INTEGER,
                    EXTRACT(QUARTER FROM date)::INTEGER
                FROM raw.holdings
                WHERE date IS NOT NULL
            """))
            return {f"{year}Q{quarter}" for year, quarter in result.fetchall()}
    finally:
        engine.dispose()


def register_missing_archives(
    config: dict,
    archives: Dict[str, str],
    loaded_quarters: set,
) -> int:
    """Register incremental quarters; opt into historical backfill explicitly."""
    latest_loaded = max(loaded_quarters) if loaded_quarters else None
    backfill_all = os.getenv("FI_BACKFILL_ALL_HISTORY", "").lower() in {
        "1", "true", "yes"
    }
    candidates = [
        (quarter_id, file_url)
        for quarter_id, file_url in archives.items()
        if quarter_id not in loaded_quarters
        and (backfill_all or latest_loaded is None or quarter_id > latest_loaded)
    ]
    if not candidates:
        return 0

    engine = build_engine(config)
    try:
        with engine.begin() as conn:
            for quarter_id, file_url in candidates:
                # FI embeds a publication timestamp in the URL and changes it on
                # republish, so refresh the stored URL for anything not yet done.
                conn.execute(text("""
                    INSERT INTO control.ingested_files
                        (quarter_id, file_url, lifecycle_state)
                    VALUES (:quarter_id, :file_url, 'PENDING')
                    ON CONFLICT (quarter_id) DO UPDATE
                    SET file_url = EXCLUDED.file_url
                    WHERE control.ingested_files.lifecycle_state <> 'COMPLETED'
                """), {"quarter_id": quarter_id, "file_url": file_url})
    finally:
        engine.dispose()
    return len(candidates)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=30),
    retry=retry_if_exception_type((requests.RequestException,))
)
def download_fi_archive(quarter_id: str, file_url: str) -> Optional[Path]:
    # Cache by FI's timestamped filename so a republished archive is
    # re-downloaded instead of silently reusing a stale zip.
    fi_name = archive_filename(file_url)
    cache_name = (
        re.sub(r"[^A-Za-z0-9._-]+", "_", fi_name) if fi_name else f"{quarter_id}.zip"
    )
    output_path = Path(DATA_RAW_DIR) / cache_name

    if output_path.exists():
        logger.info(f"Archive already downloaded: {output_path}")
        return output_path

    try:
        logger.info(f"Downloading FI archive: {file_url} → {output_path}")
        if fi_name:
            # Let requests encode the space in the filename itself.
            parts = urlsplit(file_url)
            base = f"{parts.scheme}://{parts.netloc}{parts.path}"
            response = requests.get(
                base, params={"filnamn": fi_name}, timeout=60, headers=HEADERS
            )
        else:
            response = requests.get(file_url, timeout=60, headers=HEADERS)
        response.raise_for_status()

        # Write to a temp file, then rename, so a partial write never looks cached.
        tmp_path = output_path.with_suffix(output_path.suffix + ".part")
        with open(tmp_path, 'wb') as f:
            f.write(response.content)
        tmp_path.replace(output_path)

        logger.info(f"Downloaded {output_path.stat().st_size:,} bytes")
        return output_path
    except Exception as e:
        logger.error(f"Download failed for {quarter_id}: {e}")
        raise


def extract_archive(quarter_id: str, zip_path: Path) -> Tuple[int, int]:
    extract_dir = Path(DATA_RAW_DIR) / quarter_id
    # Clear any XML left over from an earlier version of this quarter.
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    files_extracted = 0
    parse_errors = 0

    try:
        logger.info(f"Extracting {zip_path} → {extract_dir}")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
            files_extracted = len([f for f in extract_dir.rglob('*.xml')])

        logger.info(f"Extracted {files_extracted} XML files to {extract_dir}")
        return files_extracted, parse_errors

    except zipfile.BadZipFile as e:
        parse_errors += 1
        logger.error(f"Bad ZIP file {zip_path}: {e}")
        # Remove the corrupt zip so the next retry downloads it again.
        zip_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        logger.error(f"Extraction failed for {quarter_id}: {e}")
        raise


def fetch_and_ingest_quarter(
    config: dict,
    quarter_id: str,
    file_url: str
) -> bool:
    try:
        logger.info(f"[{quarter_id}] Starting ingestion")
        update_ingestion_state(config, quarter_id, file_url, 'IN_PROGRESS')

        zip_path = download_fi_archive(quarter_id, file_url)
        if not zip_path:
            raise RuntimeError(f"Failed to download archive for {quarter_id}")

        files_extracted, parse_errors = extract_archive(quarter_id, zip_path)

        metrics = {
            'files_downloaded': 1,
            'holdings_extracted': files_extracted,
            'xml_parse_errors': parse_errors
        }
        update_ingestion_state(
            config, quarter_id, file_url, 'COMPLETED',
            metrics=metrics
        )

        logger.info(f"[{quarter_id}] ✓ Ingestion completed: {files_extracted} XML files")
        return True

    except Exception as e:
        error_msg = str(e)
        error_trace = traceback.format_exc()

        logger.error(f"[{quarter_id}] ✗ Ingestion failed: {error_msg}")
        logger.debug(error_trace)

        try:
            update_ingestion_state(
                config, quarter_id, file_url, 'FAILED',
                error_msg=error_msg,
                error_traceback=error_trace
            )
        except Exception as update_err:
            logger.error(f"Failed to record error state for {quarter_id}: {update_err}")

        return False


def run_fetch_pipeline(config: dict) -> Dict:
    logger.info("=" * 80)
    logger.info("FI DATA FETCH PIPELINE STARTING")
    logger.info("=" * 80)

    try:
        archives = discover_fi_archives()
        loaded_quarters = get_loaded_quarters(config)
        registered = register_missing_archives(config, archives, loaded_quarters)
        logger.info(
            f"FI discovery: {len(archives)} archives found, "
            f"{registered} new quarters registered"
        )

        pending_quarters = get_pending_quarters(config)
        completed_quarters = get_completed_quarters(config)

        logger.info(f"Gap-detection: {len(pending_quarters)} pending, "
                    f"{len(completed_quarters)} completed")

        stats = {
            'total_quarters': len(pending_quarters),
            'completed': 0,
            'failed': 0,
            'skipped': 0
        }

        for quarter_id in pending_quarters:
            if quarter_id in completed_quarters:
                logger.info(f"Skipping {quarter_id} (already COMPLETED)")
                stats['skipped'] += 1
                continue

            file_url = archives.get(quarter_id)
            if not file_url:
                logger.error(f"No current FI archive URL found for {quarter_id}")
                stats['failed'] += 1
                continue

            success = fetch_and_ingest_quarter(config, quarter_id, file_url)
            if success:
                stats['completed'] += 1
            else:
                stats['failed'] += 1

        logger.info("=" * 80)
        logger.info(f"PIPELINE SUMMARY: {stats['completed']} completed, "
                    f"{stats['failed']} failed, {stats['skipped']} skipped")
        logger.info("=" * 80)

        return stats

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    try:
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)
        stats = run_fetch_pipeline(config)

        exit_code = 0 if stats['failed'] == 0 else 1
        sys.exit(exit_code)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(2)


if __name__ == '__main__':
    main()