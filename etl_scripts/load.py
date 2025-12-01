import logging
import pandas as pd
from sqlalchemy import create_engine
import yaml
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError, ProgrammingError 

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

def load_sector_allocations(transformed_chunk: pd.DataFrame, config: dict) -> None:
    engine = build_engine(config)
    load_config = config['etl']['load']
    chunksize = load_config['chunksize']  
    
    table_name = 'fund_sector_allocation' 
    
    logger.info(f"Loading {len(transformed_chunk)} rows → raw.{table_name}")
    
    df = transformed_chunk.copy()
    df = df.rename(columns={'total_weight_pct': 'allocation'})

    df['date'] = pd.to_datetime(df['quarter'] + '-01').dt.date
    
    load_df = df[['fund_name', 'sector', 'allocation', 'date']].copy()
    
    try:
        load_df.to_sql(
            name=table_name,
            schema='raw', 
            con=engine,
            if_exists='append', 
            chunksize=chunksize, 
            method='multi' 
        )
        logger.info(f"Loaded {len(load_df)} sector allocations to raw.{table_name}")
    except Exception as e:
        logger.error(f"Load failed: {e}", exc_info=True)
        raise
    finally:
        engine.dispose()

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5)
)

def log_etl_success(config: dict, rows_loaded: int):
    engine = build_engine(config)
    try:
        pd.DataFrame({
            'run_date': [pd.Timestamp.now().date()],
            'status': ['success'],
            'message': [f'Loaded {rows_loaded:,} FI sector allocations']
        }).to_sql('etl_log', schema='control', con=engine, if_exists='append', index=False)
    finally:
        engine.dispose()

if __name__ == "__main__":
    # Test
    config = yaml.safe_load(open('config/config.yaml'))
    from extract import extract_holdings
    from transform import transform_holdings
    
    total_loaded = 0
    for i, chunk in enumerate(extract_holdings()):
        if i == 0:  # Test the first chunk
            for transformed in transform_holdings(chunk):
                load_sector_allocations(transformed, config)
                total_loaded += len(transformed)
                break
    log_etl_success(config, total_loaded)
