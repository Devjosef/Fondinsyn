import logging
import pandas as pd
from sqlalchemy.orm import sessionmaker, Session
import yaml
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError, ProgrammingError
from app.database.connection import create_database_engine
from app.database.models import Fund, Sector, FundSectorAllocation, ETLLog

logger = logging.getLogger(__name__)

def build_engine(config: dict):
    return create_database_engine(pool_pre_ping=True)

def get_or_create_fund(session: Session, fund_name: str) -> int:
    fund = session.query(Fund).filter(Fund.name == fund_name).first()
    if not fund:
        fund = Fund(name=fund_name, provider='FI')
        session.add(fund)
        session.flush()
    return fund.id

def get_or_create_sector(session: Session, sector_name: str) -> int:
    sector = session.query(Sector).filter(Sector.sector_name == sector_name).first()
    if not sector:
        sector = Sector(sector_name=sector_name)
        session.add(sector)
        session.flush()
    return sector.id

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((OperationalError, ProgrammingError))
)
def load_sector_allocations(transformed_chunk: pd.DataFrame, config: dict, session: Session = None) -> None:
    engine = build_engine(config)
    
    if not session:
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
    
    chunk_size = config['etl']['load'].get('chunksize', 5000)
    logger.info(f"Loading {len(transformed_chunk)} rows → FundSectorAllocation")
    
    try:
        unique_records_map = {}
        df = transformed_chunk.copy()
        df['date'] = df['quarter'].apply(lambda x: pd.Period(x, freq='Q').end_time.date() if pd.notna(x) else None)
        
        for _, row in df.iterrows():
            fund_id = get_or_create_fund(session, row['fund_name'])
            sector_id = get_or_create_sector(session, row['sector'])
            date = row['date']
            
            key = (fund_id, sector_id, date)
            unique_records_map[key] = {
                'fund_id': fund_id,
                'sector_id': sector_id,
                'allocation': float(row['total_weight_pct']),
                'date': date
            }
        
        records_to_insert = []
        for record in unique_records_map.values():
            existing = session.query(FundSectorAllocation).filter(
                FundSectorAllocation.fund_id == record['fund_id'],
                FundSectorAllocation.sector_id == record['sector_id'],
                FundSectorAllocation.date == record['date']
            ).first()
            
            if not existing:
                records_to_insert.append(record)
        
        if records_to_insert:
            logger.info(f"Bulk inserting {len(records_to_insert)} new records (dedup: {len(unique_records_map)} → {len(records_to_insert)})")
            for i in range(0, len(records_to_insert), chunk_size):
                chunk = records_to_insert[i:i+chunk_size]
                session.bulk_insert_mappings(FundSectorAllocation, chunk)
                session.flush()
            
            session.commit()
            logger.info(f"Loaded {len(records_to_insert)} new sector allocations")
        else:
            logger.info(f"No new records (all {len(unique_records_map)} already in database)")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Load failed: {e}", exc_info=True)
        raise
    finally:
        session.close()
        engine.dispose()

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5)
)
def log_etl_success(config: dict, rows_loaded: int):
    engine = build_engine(config)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        log_entry = ETLLog(
            run_date=pd.Timestamp.now().date(),
            status='success',
            message=f'Loaded {rows_loaded:,} FI sector allocations'
        )
        session.add(log_entry)
        session.commit()
        logger.info(f"ETL logged successfully: {rows_loaded:,} rows")
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to log ETL: {e}")
        raise
    finally:
        session.close()
        engine.dispose()

def load_data(transformed_data):
    project_root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load(open(project_root / 'config' / 'config.yaml'))
    
    engine = build_engine(config)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    total_loaded = 0
    try:
        for chunk_idx, chunk in enumerate(transformed_data):
            logger.info(f"Processing chunk {chunk_idx + 1}: {len(chunk)} records")
            load_sector_allocations(chunk, config, session)
            total_loaded += len(chunk)
        
        session.close()
        log_etl_success(config, total_loaded)
        logger.info(f"ETL complete: {total_loaded:,} total rows loaded")
        
    except Exception as e:
        session.rollback()
        logger.error(f"ETL failed: {e}")
        raise
    finally:
        session.close()
        engine.dispose()

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load(open(project_root / 'config' / 'config.yaml'))
    from extract import extract_holdings
    from transform import transform_holdings
    
    total_loaded = 0
    for i, chunk in enumerate(extract_holdings()):
        if i == 0:
            for transformed in transform_holdings(chunk):
                load_sector_allocations(transformed, config)
                total_loaded += len(transformed)
                break
    log_etl_success(config, total_loaded)
