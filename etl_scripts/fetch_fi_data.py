import logging
import os
import sys
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
import pandas as pd
import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError, IntegrityError

logger = logging.getLogger(__name__)

FI_BASE_URL = "https://www.fi.se/sv/vara-register/vardepappersfond/upplysningsskyldig/arkiv/"
FI_API_PATTERN = "https://www.fi.se/api/vardepappersfond/archive/{quarter_id}/"
DATA_RAW_DIR = os.getenv("FI_DATA_PATH", "data/raw")
QUARTERLY_ARCHIVE_REGEX = r'Q\d-\d{4}'

Path(DATA_RAW_DIR).mkdir(parents=True, exist_ok=True)


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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=30),
    retry=retry_if_exception_type((requests.RequestException,))
)
def download_fi_archive(quarter_id: str, file_url: str) -> Optional[Path]:
    output_path = Path(DATA_RAW_DIR) / f"{quarter_id}.zip"
    
    if output_path.exists():
        logger.info(f"Archive already downloaded: {output_path}")
        return output_path
    
    try:
        logger.info(f"Downloading FI archive: {file_url} → {output_path}")
        response = requests.get(file_url, timeout=60)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"Downloaded {output_path.stat().st_size:,} bytes")
        return output_path
    except Exception as e:
        logger.error(f"Download failed for {quarter_id}: {e}")
        raise


def extract_archive(quarter_id: str, zip_path: Path) -> Tuple[int, int]:
    extract_dir = Path(DATA_RAW_DIR) / quarter_id
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
    logger.info("="*80)
    logger.info("FI DATA FETCH PIPELINE STARTING")
    logger.info("="*80)
    
    try:
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
            
            file_url = FI_API_PATTERN.format(quarter_id=quarter_id)
            
            success = fetch_and_ingest_quarter(config, quarter_id, file_url)
            if success:
                stats['completed'] += 1
            else:
                stats['failed'] += 1
        
        logger.info("="*80)
        logger.info(f"PIPELINE SUMMARY: {stats['completed']} completed, "
                    f"{stats['failed']} failed, {stats['skipped']} skipped")
        logger.info("="*80)
        
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
        config = yaml.safe_load(open('config/config.yaml'))
        stats = run_fetch_pipeline(config)
        
        exit_code = 0 if stats['failed'] == 0 else 1
        sys.exit(exit_code)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(2)


if __name__ == '__main__':
    main()