import pandas as pd

df = pd.read_csv('swedish_funds_complete.csv')
print(f"Loaded {len(df):,} holdings from {df['fund_name'].nunique():,} funds")

print("\nTOP 10 HOLDINGS (by total weight):")
print(df.groupby(['isin', 'name'])['weight_pct'].sum().sort_values(ascending=False).head(10))

print("\nLARGEST FUNDS (SEK billions):")
print(df.groupby('fund_name')['market_value_sek'].sum() / 1e9 .sort_values(ascending=False).head(10))

print("\nTOP COMPANIES:")
print(df['fund_company'].value_counts().head(10))

print("\nTOP COUNTRIES (SEK billions):")
print(df.groupby('country')['market_value_sek'].sum() / 1e9 .sort_values(ascending=False).head(10))

print("\nAUM BY QUARTER (SEK trillions):")
print(df.groupby('quarter')['market_value_sek'].sum() / 1e12 .sort_index())

top_holdings = df.groupby(['isin', 'name'])['weight_pct'].sum().sort_values(ascending=False).head(10)
aum = df.groupby('fund_name')['market_value_sek'].sum() / 1e9
countries = df.groupby('country')['market_value_sek'].sum() / 1e9
quarter_aum = df.groupby('quarter')['market_value_sek'].sum() / 1e12

top_holdings.to_csv('top_100_holdings.csv')
aum.head(50).to_csv('top_50_funds.csv')
countries.to_csv('country_exposure.csv')
quarter_aum.to_csv('aum_growth.csv')

print("\nSAVED: top_100_holdings.csv | top_50_funds.csv | country_exposure.csv")
