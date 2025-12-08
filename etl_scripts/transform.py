import logging
import pandas as pd
from typing import Iterator

logger = logging.getLogger(__name__)

def transform_holdings(raw_holdings: pd.DataFrame) -> Iterator[pd.DataFrame]:
    logger.info(f"Transforming {len(raw_holdings)} FI holdings")

    if raw_holdings.empty:
        empty_df = pd.DataFrame(columns=['fund_name', 'country', 'market_cap_group', 'total_weight_pct', 'quarter'])
        yield empty_df
        return
    
    df = raw_holdings.copy()
    # Cleaning & parse dates
    required = ['fund_name', 'country', 'market_value_sek', 'weight_pct', 'quarter_end']
    df = df.dropna(subset=required)
    
    # Note: that weight pct is weight percentage.
    df['weight_pct'] = pd.to_numeric(df['weight_pct'], errors='coerce') / 10000
    df = df.dropna(subset=['weight_pct'])
    df = df[df['weight_pct'] >= 0]

    # Try to parse the quarters efficiently
    df['quarter'] = pd.to_datetime(df['quarter_end'], errors='coerce').dt.to_period('Q').astype(str)
    
    # Bucketing for market value
    df['market_cap_raw'] = pd.to_numeric(df['market_value_sek'], errors='coerce')
    market_cap_groups = pd.cut(
        df['market_cap_raw'].rank(pct=True, na_option='keep'), 
        bins=[0, 0.4, 0.8, 1.0], 
        labels=['Small', 'Mid', 'Large'],
        include_lowest=True
    )
    df['market_cap_group'] = market_cap_groups.astype(str).replace('nan', 'Other')
    
    # Maps countries to sectors
    sector_map = {
        'US': 'Technology', 'SE': 'Industrials', 'GB': 'Financials',
        'JP': 'Consumer', 'CH': 'Healthcare', 'DE': 'Automotive'
    }
    df['sector'] = df['country'].map(sector_map).fillna('Other')
    
    # MAIN AGGREGATION: ergo meaning assembled data points
    grouped = (df.groupby(['fund_name', 'sector', 'market_cap_group', 'quarter'], as_index=False)
              ['weight_pct'].sum()
              .rename(columns={'weight_pct': 'total_weight_pct'})
              .sort_values(['fund_name', 'quarter', 'sector', 'market_cap_group'])
              .reset_index(drop=True))
    
    logger.info(f"Aggregated to {len(grouped)} rows")
    yield grouped

if __name__ == "__main__":
    # Test with the FI extract format otherwise write a specific test with edge case
    from extract import extract_holdings
    for i, chunk in enumerate(extract_holdings()):
        if i == 0:  # Test the first chunk only: if it works great!
            for transformed in transform_holdings(chunk):
                print(f"Transformed shape: {transformed.shape}")
                print(transformed.head())
            break

transform_data = transform_holdings