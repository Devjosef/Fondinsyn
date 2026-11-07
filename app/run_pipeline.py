import logging
import os
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from sqlalchemy import create_engine, text

from app.docker_manager import DockerOrchestrator
from app.etl_scripts.extract import extract_data
from app.etl_scripts.fetch_fi_data import run_fetch_pipeline
from app.etl_scripts.load_assets import load_assets_from_csv
from app.etl_scripts.load_holdings import load_holdings_from_csv
from app.etl_scripts.transform import transform_data

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def resolve_holdings_csv() -> Path:
    for path in (
        PROJECT_ROOT / 'swedish_funds_complete.csv',
        PROJECT_ROOT / 'CSV' / 'swedish_funds_complete.csv',
    ):
        if path.is_file():
            return path
    raise FileNotFoundError('swedish_funds_complete.csv not found in project root or CSV/')


class PipelineMetrics:
    def __init__(self):
        self.start_time = utcnow()
        self.phases: Dict[str, Dict] = {}
        self.errors: List[Tuple[str, str, str]] = []

    def record_phase_start(self, phase_name: str) -> None:
        self.phases[phase_name] = {
            'status': 'IN_PROGRESS',
            'start': utcnow(),
            'end': None,
            'duration_sec': None,
            'metrics': {},
        }
        logger.info(f"[PHASE: {phase_name}] STARTED")

    def _close_phase(self, phase_name: str, status: str, metrics: Optional[Dict]) -> None:
        phase = self.phases[phase_name]
        phase['end'] = utcnow()
        phase['status'] = status
        phase['duration_sec'] = (phase['end'] - phase['start']).total_seconds()
        if metrics:
            phase['metrics'] = metrics

    def record_phase_success(self, phase_name: str, metrics: Optional[Dict] = None) -> None:
        self._close_phase(phase_name, 'COMPLETED', metrics)
        logger.info(
            f"[PHASE: {phase_name}] ✓ COMPLETED ({self.phases[phase_name]['duration_sec']:.2f}s)"
        )

    def record_phase_failure(
        self,
        phase_name: str,
        error_msg: str,
        error_trace: str,
        metrics: Optional[Dict] = None,
    ) -> None:
        self._close_phase(phase_name, 'FAILED', metrics)
        self.errors.append((phase_name, error_msg, error_trace))
        logger.error(f"[PHASE: {phase_name}] ✗ FAILED: {error_msg}")

    def get_summary(self) -> Dict:
        statuses = [p['status'] for p in self.phases.values()]
        return {
            'total_phases': len(self.phases),
            'completed': statuses.count('COMPLETED'),
            'failed': statuses.count('FAILED'),
            'total_duration_sec': (utcnow() - self.start_time).total_seconds(),
            'phases': self.phases,
            'errors': [(e[0], e[1]) for e in self.errors],
        }


@contextmanager
def db_engine(config: dict):
    db = config['database']
    engine = create_engine(
        f"postgresql://CREDENTIAL_REMOVED_9bcf166e240683cd1b72a7f9d05b8274@{db['host']}:{db['port']}/{db['db_name']}",
        pool_pre_ping=True,
        echo=False,
    )
    try:
        yield engine
    finally:
        engine.dispose()


def log_pipeline_run(config: dict, phase: str, status: str, message: str) -> None:
    try:
        with db_engine(config) as engine, engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO control.etl_log (run_date, status, message)
                VALUES (CURRENT_DATE, :status, :message)
            """), {'status': f"{phase}:{status}", 'message': message})
    except Exception as e:
        logger.warning(f"Failed to log pipeline event: {e}")


def check_database_connectivity(config: dict) -> bool:
    try:
        with db_engine(config) as engine, engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✓ Database connectivity verified")
        return True
    except Exception as e:
        logger.error(f"✗ Database connectivity check failed: {e}")
        return False


def sync_superset_dashboard() -> bool:
    orchestrator = DockerOrchestrator()
    if not orchestrator.initialize():
        raise RuntimeError("Could not initialize Superset for dashboard synchronization")
    orchestrator.provision_superset_dashboard()
    logger.info("Clearing Superset cache...")
    return orchestrator.clear_superset_cache()


def phase_pre_check(config: dict, metrics: PipelineMetrics) -> bool:
    metrics.record_phase_start('PRE_CHECK')
    try:
        if not check_database_connectivity(config):
            raise RuntimeError("Database unreachable")

        try:
            with db_engine(config) as engine, engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM control.etl_log LIMIT 1"))
                conn.execute(text("SELECT 1 FROM control.ingested_files LIMIT 1"))
            logger.info("✓ Control tables verified")
        except Exception as table_err:
            logger.warning(f"Control tables not found (schema may not be initialized): {table_err}")

        log_pipeline_run(config, 'PRE_CHECK', 'OK', 'Database ready')
        metrics.record_phase_success('PRE_CHECK')
        return True
    except Exception as e:
        metrics.record_phase_failure('PRE_CHECK', str(e), traceback.format_exc())
        return False


def phase_docker_verify(config: dict, metrics: PipelineMetrics) -> bool:
    metrics.record_phase_start('DOCKER_VERIFY')
    try:
        orchestrator = DockerOrchestrator()
        if not orchestrator.initialize():
            raise RuntimeError("Container discovery failed - fatal containers missing")

        exit_code = orchestrator.verify_all_containers()
        if exit_code == 2:
            raise RuntimeError("Critical container failure - cannot proceed")
        if exit_code == 1:
            logger.warning("Some containers unhealthy - proceeding with caution")
        else:
            logger.info("✓ All containers healthy")

        orchestrator.export_diagnostics()

        log_pipeline_run(config, 'DOCKER_VERIFY', 'OK', f'Containers verified (exit_code={exit_code})')
        metrics.record_phase_success('DOCKER_VERIFY', metrics={'docker_exit_code': exit_code})
        return True
    except Exception as e:
        metrics.record_phase_failure('DOCKER_VERIFY', str(e), traceback.format_exc())
        return False


def phase_fetch(config: dict, metrics: PipelineMetrics) -> bool:
    metrics.record_phase_start('FETCH')
    try:
        stats = run_fetch_pipeline(config)
        log_pipeline_run(
            config, 'FETCH', 'OK',
            f"Fetched {stats['completed']} quarters, "
            f"failed: {stats['failed']}, skipped: {stats['skipped']}",
        )

        if stats['failed']:
            metrics.record_phase_failure(
                'FETCH', f"{stats['failed']} quarter(s) failed", '', metrics=stats
            )
            return False

        metrics.record_phase_success('FETCH', metrics=stats)
        return True
    except Exception as e:
        metrics.record_phase_failure('FETCH', str(e), traceback.format_exc())
        return False


def newest_xml_mtime(xml_root: Path) -> Optional[float]:
    mtimes = [p.stat().st_mtime for p in xml_root.rglob('*.xml')]
    return max(mtimes) if mtimes else None


def phase_extract_transform(config: dict, metrics: PipelineMetrics) -> bool:
    metrics.record_phase_start('EXTRACT_TRANSFORM')
    try:
        xml_root = Path(os.getenv('FI_DATA_PATH', 'data/raw'))
        if not xml_root.is_absolute():
            xml_root = PROJECT_ROOT / xml_root
        xml_mtime = newest_xml_mtime(xml_root)

        try:
            csv_path: Optional[Path] = resolve_holdings_csv()
        except FileNotFoundError:
            csv_path = None

        if xml_mtime is None or (csv_path and csv_path.stat().st_mtime >= xml_mtime):
            if csv_path is None:
                raise FileNotFoundError("No FI XML on disk and no existing holdings CSV")
            logger.info(f"No new FI XML since last export; reusing {csv_path}")
            metrics.record_phase_success(
                'EXTRACT_TRANSFORM',
                metrics={'extracted': 0, 'transformed': 0, 'source_csv': str(csv_path)},
            )
            return True

        total_extracted = 0
        total_transformed = 0
        for chunk_idx, chunk in enumerate(extract_data(), start=1):
            if chunk.empty:
                logger.warning(f"Empty chunk {chunk_idx} from extract_data()")
                continue
            total_extracted += len(chunk)
            for transformed_chunk in transform_data(chunk):
                total_transformed += len(transformed_chunk)

        try:
            if resolve_holdings_csv().stat().st_mtime < xml_mtime:
                logger.warning(
                    "Holdings CSV was not updated by transform_data; LOAD will use the previous export"
                )
        except FileNotFoundError:
            logger.warning("Holdings CSV still missing after transform; LOAD will fail")

        stats = {'extracted': total_extracted, 'transformed': total_transformed}
        if total_extracted == 0:
            metrics.record_phase_failure(
                'EXTRACT_TRANSFORM', "XML present but no records extracted", '', metrics=stats
            )
            return False

        log_pipeline_run(
            config, 'EXTRACT_TRANSFORM', 'OK',
            f"Extracted {total_extracted}, transformed {total_transformed} records",
        )
        metrics.record_phase_success('EXTRACT_TRANSFORM', metrics=stats)
        return True
    except Exception as e:
        metrics.record_phase_failure('EXTRACT_TRANSFORM', str(e), traceback.format_exc())
        return False


def phase_load(config: dict, metrics: PipelineMetrics) -> bool:
    metrics.record_phase_start('LOAD')
    try:
        csv_path = str(resolve_holdings_csv())

        assets_loaded = load_assets_from_csv(csv_path, config)
        holdings_loaded = load_holdings_from_csv(csv_path, config)
        logger.info(f"Loaded {assets_loaded} assets, {holdings_loaded} holdings")

        log_pipeline_run(config, 'LOAD', 'OK', f"Loaded {assets_loaded} assets, {holdings_loaded} holdings")
        metrics.record_phase_success(
            'LOAD', metrics={'assets_loaded': assets_loaded, 'holdings_loaded': holdings_loaded}
        )
        return True
    except Exception as e:
        metrics.record_phase_failure('LOAD', str(e), traceback.format_exc())
        return False


def phase_refresh_analytics(config: dict, metrics: PipelineMetrics) -> bool:
    metrics.record_phase_start('REFRESH_ANALYTICS')
    try:
        load_phase = metrics.phases.get('LOAD', {})
        load_metrics = load_phase.get('metrics', {})
        skip_refresh = load_phase.get('status') == 'COMPLETED' and not (
            load_metrics.get('assets_loaded', 0) or load_metrics.get('holdings_loaded', 0)
        )
        if skip_refresh:
            logger.info("Skipping analytics refresh: the idempotent load added no rows")

        views_refreshed = 0
        views = []
        if not skip_refresh:
            with db_engine(config) as engine:
                with engine.connect() as conn:
                    views = conn.execute(text("""
                        SELECT schemaname, matviewname
                        FROM pg_matviews
                        WHERE schemaname = 'analytics'
                        ORDER BY matviewname
                    """)).fetchall()

                for schema_name, view_name in views:
                    qualified_name = '.'.join(
                        '"' + identifier.replace('"', '""') + '"'
                        for identifier in (schema_name, view_name)
                    )
                    try:
                        logger.info(f"Refreshing {qualified_name}...")
                        with engine.begin() as conn:
                            conn.execute(text(f"REFRESH MATERIALIZED VIEW {qualified_name}"))
                        views_refreshed += 1
                    except Exception as view_err:
                        logger.error(f"Failed to refresh {qualified_name}: {view_err}")

        if views_refreshed < len(views):
            stats = {'views_refreshed': views_refreshed, 'views_total': len(views)}
            metrics.record_phase_failure(
                'REFRESH_ANALYTICS',
                f"{len(views) - views_refreshed} view(s) failed to refresh",
                '',
                metrics=stats,
            )
            return False

        cache_cleared = sync_superset_dashboard()
        stats = {
            'views_refreshed': views_refreshed,
            'views_total': len(views),
            'skipped': skip_refresh,
            'superset_dashboard_synced': True,
            'superset_cache_cleared': cache_cleared,
        }
        if not cache_cleared:
            logger.warning(
                "Superset dashboard was synchronized, but its cache could not be cleared"
            )
        log_pipeline_run(
            config,
            'REFRESH_ANALYTICS',
            'OK',
            f"Refreshed {views_refreshed}/{len(views)} materialized views; "
            "synchronized Fondinsyn Superset dashboard",
        )
        metrics.record_phase_success('REFRESH_ANALYTICS', metrics=stats)
        return True
    except Exception as e:
        metrics.record_phase_failure('REFRESH_ANALYTICS', str(e), traceback.format_exc())
        return False


def phase_post_check(config: dict, metrics: PipelineMetrics) -> bool:
    metrics.record_phase_start('POST_CHECK')
    try:
        summary = metrics.get_summary()
        log_pipeline_run(
            config, 'POST_CHECK', 'OK',
            f"Pipeline complete: {summary['completed']}/{summary['total_phases']} phases OK, "
            f"duration: {summary['total_duration_sec']:.1f}s",
        )
        metrics.record_phase_success('POST_CHECK')
        return True
    except Exception as e:
        metrics.record_phase_failure('POST_CHECK', str(e), traceback.format_exc())
        return False


def run_pipeline(config: dict) -> int:
    logger.info("=" * 80)
    logger.info("MASTER ETL PIPELINE STARTING")
    logger.info("=" * 80)

    metrics = PipelineMetrics()

    phases = [
        ('PRE_CHECK', phase_pre_check, True),
        ('DOCKER_VERIFY', phase_docker_verify, True),
        ('FETCH', phase_fetch, False),
        ('EXTRACT_TRANSFORM', phase_extract_transform, False),
        ('LOAD', phase_load, False),
        ('REFRESH_ANALYTICS', phase_refresh_analytics, False),
        ('POST_CHECK', phase_post_check, False),
    ]

    for phase_name, phase_func, blocking in phases:
        try:
            success = phase_func(config, metrics)
        except Exception as e:
            logger.error(f"Unexpected exception in {phase_name}: {e}", exc_info=True)
            success = False
            if phase_name not in metrics.phases:
                metrics.record_phase_start(phase_name)
            metrics.record_phase_failure(phase_name, str(e), traceback.format_exc())

        if not success and blocking:
            logger.error(f"✗ Blocking phase {phase_name} failed - aborting pipeline")
            logger.info(f"PIPELINE SUMMARY:\n{yaml.safe_dump(metrics.get_summary())}")
            return 2

    summary = metrics.get_summary()
    logger.info("=" * 80)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 80)
    logger.info(f"SUMMARY:\n{yaml.safe_dump(summary)}")

    return 0 if summary['failed'] == 0 else 1


def main():
    Path('logs').mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler('logs/pipeline.log'),
            logging.StreamHandler(sys.stdout),
        ],
    )

    try:
        with open(PROJECT_ROOT / 'config' / 'config.yaml') as f:
            config = yaml.safe_load(f)
        sys.exit(run_pipeline(config))
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(2)


if __name__ == '__main__':
    main()