import logging
import pandas as pd
import psycopg2
from sqlalchemy import create_engine
import yaml
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError, ProgrammingError
from typing import Tuple, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


def build_engine(config: dict):
    db_config = config['database']
    db_conn_str = (f"postgresql://CREDENTIAL_REMOVED_9bcf166e240683cd1b72a7f9d05b8274@"
                   f"{db_config['host']}:{db_config['port']}/{db_config['db_name']}")
    return create_engine(db_conn_str, pool_pre_ping=True)


def create_staging_table(cur, schema_ddl: str) -> None:
    try:
        cur.execute(schema_ddl)
        logger.debug("Staging table created successfully")
    except psycopg2.Error as e:
        if "already exists" in str(e).lower():
            logger.debug("Staging table already exists (idempotent)")
        else:
            logger.error(f"DDL error: {e}")
            raise


def load_and_validate_csv(csv_path: str) -> Tuple[pd.DataFrame, Dict]:
    if not Path(csv_path).exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    
    logger.info(f"Loading CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    original_count = len(df)
    
    required_cols = ['fund_name', 'isin', 'weight_pct', 'quarter_end']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")
    
    logger.info(f"Total records from CSV: {original_count}")
    
    df['quarter_end'] = pd.to_datetime(df['quarter_end'], errors='coerce').dt.date
    
    df = df.dropna(subset=['isin'])
    after_isin_drop = len(df)
    logger.info(f"After removing NaN ISINs: {after_isin_drop} records "
                f"(dropped {original_count - after_isin_drop})")
    
    df['weight_pct'] = pd.to_numeric(df['weight_pct'], errors='coerce')
    df = df.dropna(subset=['weight_pct'])
    after_weight_drop = len(df)
    logger.info(f"After removing NaN weight_pct: {after_weight_drop} records")
    
    df = df.drop_duplicates(subset=['fund_name', 'isin', 'quarter_end'])
    after_dedup = len(df)
    logger.info(f"After dedup: {after_dedup} records")
    
    metrics = {
        'original': original_count,
        'after_isin_drop': after_isin_drop,
        'after_weight_drop': after_weight_drop,
        'after_dedup': after_dedup,
        'dropped': original_count - after_dedup
    }
    
    return df, metrics


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((OperationalError, ProgrammingError, psycopg2.OperationalError))
)
def load_holdings_from_csv(csv_path: str, config: dict) -> int:
    db_config = config['database']
    
    try:
        df, quality_metrics = load_and_validate_csv(csv_path)
        logger.info(f"Data quality: {quality_metrics}")
    except Exception as e:
        logger.error(f"CSV validation failed: {e}")
        raise
    
    logger.info("Loading fund/asset mappings from database...")
    fund_map = {}
    asset_map = {}
    
    try:
        with psycopg2.connect(
            host=db_config['host'],
            port=db_config['port'],
            database=db_config['db_name'],
            user=db_config['user'],
            password=db_config['password'],
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name FROM raw.funds")
                fund_map = {row[1]: row[0] for row in cur.fetchall()}
                
                cur.execute("SELECT id, ticker FROM raw.assets")
                asset_map = {row[1]: row[0] for row in cur.fetchall()}
    except psycopg2.Error as e:
        logger.error(f"Failed to load mappings: {e}")
        raise
    
    logger.info(f"Loaded {len(fund_map)} funds, {len(asset_map)} assets from database")
    
    df['fund_id'] = df['fund_name'].map(fund_map)
    df['asset_id'] = df['isin'].map(asset_map)
    
    missing_funds = df['fund_id'].isna().sum()
    missing_assets = df['asset_id'].isna().sum()
    logger.warning(f"Data mismatches - missing funds: {missing_funds}, missing assets: {missing_assets}")
    
    before_mapping = len(df)
    df = df.dropna(subset=['fund_id', 'asset_id'])
    after_mapping = len(df)
    logger.info(f"After mapping validation: {after_mapping} records "
                f"(dropped {before_mapping - after_mapping} unmapped)")
    
    if df.empty:
        logger.warning("No valid records after mapping - aborting load")
        return 0
    
    staging_file = 'holdings_staging.csv'
    df['fund_id'] = df['fund_id'].astype(int)
    df['asset_id'] = df['asset_id'].astype(int)
    try:
        df[['fund_id', 'asset_id', 'weight_pct', 'quarter_end']].to_csv(
            staging_file, index=False, header=False
        )
        logger.info(f"Wrote staging CSV: {staging_file}")
    except IOError as e:
        logger.error(f"Failed to write staging file: {e}")
        raise
    
    rows_loaded = 0
    staging_ddl = """
        CREATE TEMP TABLE IF NOT EXISTS holdings_staging (
            fund_id INTEGER NOT NULL,
            asset_id INTEGER NOT NULL,
            weight_pct NUMERIC(10, 6) NOT NULL,
            quarter_end DATE NOT NULL
        )
    """
    
    try:
        with psycopg2.connect(
            host=db_config['host'],
            port=db_config['port'],
            database=db_config['db_name'],
            user=db_config['user'],
            password=db_config['password'],
        ) as conn:
            with conn.cursor() as cur:
                create_staging_table(cur, staging_ddl)
                
                cur.execute("SAVEPOINT sp_holdings_load")
                
                try:
                    logger.info(f"Executing COPY from {staging_file}...")
                    with open(staging_file, 'r') as f:
                        cur.copy_expert(
                            "COPY holdings_staging (fund_id, asset_id, weight_pct, quarter_end) FROM STDIN WITH CSV",
                            f
                        )
                    rows_copied = cur.rowcount
                    logger.info(f"COPY completed: {rows_copied} rows into staging table")
                    
                    logger.info("Executing UPSERT...")
                    upsert_sql = """
                        INSERT INTO raw.holdings (fund_id, asset_id, weight, date)
                        SELECT fund_id, asset_id, weight_pct, quarter_end 
                        FROM holdings_staging
                        ON CONFLICT (fund_id, asset_id, date) DO NOTHING
                    """
                    cur.execute(upsert_sql)
                    rows_loaded = cur.rowcount
                    logger.info(f"UPSERT completed: {rows_loaded} rows inserted "
                                f"({rows_copied - rows_loaded} duplicates skipped)")
                    
                    cur.execute("RELEASE SAVEPOINT sp_holdings_load")
                    conn.commit()
                
                except psycopg2.IntegrityError as e:
                    logger.error(f"Constraint violation: {e}")
                    cur.execute("ROLLBACK TO SAVEPOINT sp_holdings_load")
                    logger.info("Rolled back to savepoint (partial UPSERT recovered)")
                    raise
                
                except Exception as e:
                    logger.error(f"Error during load: {e}")
                    cur.execute("ROLLBACK TO SAVEPOINT sp_holdings_load")
                    logger.info("Rolled back to savepoint")
                    raise
        
        logger.info(f"Successfully loaded {rows_loaded} holdings to raw.holdings")
        return rows_loaded
    
    except psycopg2.Error as e:
        logger.error(f"Database error during load: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error during load: {e}", exc_info=True)
        raise
    finally:
        try:
            if Path(staging_file).exists():
                Path(staging_file).unlink()
                logger.debug(f"Cleaned up staging file: {staging_file}")
        except Exception as e:
            logger.warning(f"Failed to clean up staging file: {e}")


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load(open(project_root / 'config' / 'config.yaml'))
    load_holdings_from_csv(project_root / 'swedish_funds_complete.csv', config)