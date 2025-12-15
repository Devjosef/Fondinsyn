import pandas as pd

df = pd.read_csv('swedish_funds_complete.csv')
print(f"Loaded {len(df):,} holdings from {df['fund_name'].nunique():,} funds")

print("\nTOP 10 HOLDINGS (by total weight):")
print(df.groupby(['isin', 'name'])['weight_pct'].sum().sort_values(ascending=False).head(10))

print("\nLARGEST FUNDS (SEK billions):")
largest_funds = (df.groupby('fund_name')['market_value_sek'].sum() / 1e9).sort_values(ascending=False).head(10)
print(largest_funds)

print("\nTOP COMPANIES:")
if 'fund_company' in df.columns:
    print(df['fund_company'].value_counts().head(10))
else:
    print('No fund_company column available')

print("\nTOP COUNTRIES (SEK billions):")
countries = (df.groupby('country')['market_value_sek'].sum() / 1e9).sort_values(ascending=False).head(10)
print(countries)

print("\nAUM BY QUARTER (SEK trillions):")
quarter_aum = (df.groupby('quarter')['market_value_sek'].sum() / 1e12).sort_index()
print(quarter_aum)

# Prepare outputs
top_holdings = df.groupby(['isin', 'name'])['weight_pct'].sum().sort_values(ascending=False).head(100)
aum = (df.groupby('fund_name')['market_value_sek'].sum() / 1e9).sort_values(ascending=False)

# Save CSVs
top_holdings.to_csv('top_100_holdings.csv')
aum.head(50).to_csv('top_50_funds.csv')
# Save full country exposure and quarter AUM
df.groupby('country')['market_value_sek'].sum().to_csv('country_exposure.csv')
quarter_aum.to_csv('aum_growth.csv')

print("\nSAVED: top_100_holdings.csv | top_50_funds.csv | country_exposure.csv")
