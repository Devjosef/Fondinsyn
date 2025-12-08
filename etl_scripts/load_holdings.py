import logging
import pandas as pd
import psycopg2
from sqlalchemy import create_engine
import yaml
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError, ProgrammingError
import os

logger = logging.getLogger(__name__)

def build_engine(config: dict):
    db_config = config['database']
    db_conn_str = (f"postgresql://CREDENTIAL_REMOVED_9bcf166e240683cd1b72a7f9d05b8274@"
                   f"{db_config['host']}:{db_config['port']}/{db_config['db_name']}")
    return create_engine(db_conn_str, pool_pre_ping=True)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((OperationalError, ProgrammingError))
)
def load_holdings_from_csv(csv_path: str, config: dict) -> int:
    
    db_config = config['database']
    
    logger.info("Loading fund/asset mappings...")
    
    with psycopg2.connect(
        host=db_config['host'],
        port=db_config['port'],
        database=db_config['db_name'],
        user=db_config['user'],
        password=db_config['password']
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM raw.funds")
            fund_map = {row[1]: row[0] for row in cur.fetchall()}
            
            cur.execute("SELECT id, ticker FROM raw.assets")
            asset_map = {row[1]: row[0] for row in cur.fetchall()}
    
    logger.info(f"Loaded {len(fund_map)} funds, {len(asset_map)} assets")
    
    try:
        logger.info(f"Reading holdings from {csv_path}")
        df = pd.read_csv(csv_path)
        logger.info(f"Total records: {len(df)}")
        
        df['quarter_end'] = pd.to_datetime(df['quarter_end']).dt.date
        df = df.dropna(subset=['isin'])
        logger.info(f"After removing NaN ISINs: {len(df)} records")
        
        df['fund_id'] = df['fund_name'].map(fund_map)
        df['asset_id'] = df['isin'].map(asset_map)
        
        missing_funds = df['fund_id'].isna().sum()
        missing_assets = df['asset_id'].isna().sum()
        logger.info(f"Mismatches - missing funds: {missing_funds}, missing assets: {missing_assets}")
        
        df = df.dropna(subset=['fund_id', 'asset_id']).drop_duplicates()
        logger.info(f"After dedup: {len(df)} records ready for insert")
        
        staging_file = 'holdings_staging.csv'
        df[['fund_id', 'asset_id', 'weight_pct', 'quarter_end']].to_csv(
            staging_file, index=False, header=False
        )
        logger.info(f"  Wrote staging file: {staging_file}")
        
        try:
            logger.info("Starting COPY + UPSERT...")
            
            with psycopg2.connect(
                host=db_config['host'],
                port=db_config['port'],
                database=db_config['db_name'],
                user=db_config['user'],
                password=db_config['password']
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TEMP TABLE IF NOT EXISTS holdings_staging (
                            fund_id INTEGER,
                            asset_id INTEGER,
                            weight_pct NUMERIC,
                            quarter_end DATE
                        )
                    """)
                    
                    logger.info("Executing COPY...")
                    with open(staging_file, 'r') as f:
                        cur.copy_expert(
                            "COPY holdings_staging (fund_id, asset_id, weight_pct, quarter_end) FROM STDIN WITH CSV",
                            f
                        )
                    logger.info(f"COPY completed: {cur.rowcount} rows")
                    
                    logger.info("Executing UPSERT...")
                    cur.execute("""
                        INSERT INTO raw.holdings (fund_id, asset_id, weight, date)
                        SELECT fund_id, asset_id, weight_pct::numeric(10,6), quarter_end 
                        FROM holdings_staging
                        ON CONFLICT (fund_id, asset_id, date) DO NOTHING
                    """)
                    logger.info(f"UPSERT completed: {cur.rowcount} rows inserted")
                    
                    conn.commit()
            
            logger.info(f"Loaded {len(df)} holdings to raw.holdings")
            return len(df)
        
        finally:
            if os.path.exists(staging_file):
                os.unlink(staging_file)
        
    except Exception as e:
        logger.error(f"Failed to load holdings: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    config = yaml.safe_load(open('config/config.yaml'))
    load_holdings_from_csv('swedish_funds_complete.csv', config)
