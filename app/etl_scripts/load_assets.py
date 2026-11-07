import logging
import pandas as pd
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import yaml
from pathlib import Path
from app.database.models import Asset, Sector

logger = logging.getLogger(__name__)

def build_engine(config: dict):
    db_config = config['database']
    db_conn_str = (f"postgresql://CREDENTIAL_REMOVED_9bcf166e240683cd1b72a7f9d05b8274@"
                   f"{db_config['host']}:{db_config['port']}/{db_config['db_name']}")
    return create_engine(db_conn_str, pool_pre_ping=True)

def load_assets_from_csv(csv_path: str, config: dict) -> int:
    engine = build_engine(config)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    sector_map = {
        'US': 'Technology', 'SE': 'Industrials', 'GB': 'Financials',
        'JP': 'Consumer', 'CH': 'Healthcare', 'DE': 'Automotive'
    }
    
    logger.info(f"Reading assets from {csv_path}")
    
    try:
        df = pd.read_csv(csv_path)
        assets_df = df[['isin', 'name', 'country']].drop_duplicates(subset=['isin'])
        logger.info(f"Found {len(assets_df)} unique assets")
        
        loaded = 0
        for _, row in assets_df.iterrows():
            ticker = row['isin']
            if pd.isna(ticker) or str(ticker).strip() == '' or str(ticker).lower() == 'nan':
                continue
            
            ticker = str(ticker).strip()
            existing = session.query(Asset).filter(Asset.ticker == ticker).first()
            
            if not existing:
                sector_name = sector_map.get(row['country'], 'Other')
                sector = session.query(Sector).filter(Sector.sector_name == sector_name).first()
                
                if not sector:
                    sector = Sector(sector_name=sector_name)
                    session.add(sector)
                    session.flush()
                
                asset = Asset(ticker=ticker, name=row['name'], sector_id=sector.id)
                session.add(asset)
                loaded += 1
                
                if loaded % 1000 == 0:
                    session.flush()
        
        session.commit()
        logger.info(f"Loaded {loaded} new assets")
        return loaded
        
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to load assets: {e}", exc_info=True)
        raise
    finally:
        session.close()
        engine.dispose()

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load(open(project_root / 'config' / 'config.yaml'))
    load_assets_from_csv(project_root / 'swedish_funds_complete.csv', config)
