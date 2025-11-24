import pandas as pd

def transform_holdings(raw_holdings: list) -> pd.DataFrame:
    if not raw_holdings:
        return pd.DataFrame(columns=['fund_id', 'sector', 'market_cap_group', 'total_weight', 'date'])
    
    df = pd.DataFrame(raw_holdings)

    required = ['fund_id', 'sector', 'market_cap', 'weight', 'date']
    df = df.dropna(subset=required)

    df['weight'] = pd.to_numeric(df['weight'], errors='coerce')
    df = df.dropna(subset=['weight'])
    df = df[df['weight'] >= 0]

    market_cap_map = {
        'large': 'Large', 'mega': 'Large', 'large cap': 'Large', 'large-cap': 'Large',
        'mid': 'Mid', 'mid cap': 'Mid', 'mid-cap': 'Mid',
        'small': 'Small', 'small cap': 'Small', 'small-cap': 'Small',
    }
    df['market_cap_group'] = df['market_cap'].astype(str).str.lower().map(market_cap_map).fillna('Other')

    grouped = df.groupby(['fund_id', 'sector', 'market_cap_group', 'date'], as_index=False)['weight'].sum().rename(columns={'weight': 'total_weight'})

    grouped = grouped.sort_values(['fund_id', 'date', 'sector', 'market_cap_group']).reset_index(drop=True)
    return grouped

if __name__ == "__main__":
    sample_data = [
        {"fund_id": "fund_1", "sector": "Technology", "market_cap": "Large", "weight": 0.15, "date": "2025-11-24"},
        {"fund_id": "fund_1", "sector": "Technology", "market_cap": "large", "weight": 0.10, "date": "2025-11-24"},
        {"fund_id": "fund_1", "sector": "Finance", "market_cap": "Mid Cap", "weight": 0.20, "date": "2025-11-24"},
        {"fund_id": "fund_2", "sector": "Healthcare", "market_cap": "small", "weight": 0.30, "date": "2025-11-24"},
    ]

    result = transform_holdings(sample_data)
    print(result)

