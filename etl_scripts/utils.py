import logging
import pandas as pd
from pathlib import Path
from typing import Dict, Any
from typing import Iterator
import yaml


logger = logging.getLogger(__name__)

def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)
    
def safe_numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, error='coerce').fillna(default)

def parse_quarter(file_path: str) -> str:
    return Path(file_path).parent.parent.name

def validate_holdings(df: pd.DataFrame) -> pd.DataFrame:
    required = ['fund_name', 'weight_pct', 'market_value_sek', 'quarter']
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    return df.dropna(subset=required)

def chunk_dataframe(df: pd.DataFrame, chunksize: int = 100_000) -> Iterator [pd.DataFrame]:
    for i in range(0, len(df), chunksize):
        yield df.iloc[i:i+chunksize]

def map_country_to_sector(country: str) -> str:
    sector_map = {
        'US': 'Technology', 'SE': 'Industrials', 'GB': 'Financials',
        'JP': 'Consumer', 'CH': 'Healthcare', 'DE': 'Automotive'
    }
    return sector_map.get(country, 'Other')