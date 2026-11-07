-- This table is used to bulk load holdings data before inserting into raw.holdings

CREATE TEMP TABLE IF NOT EXISTS holdings_staging (
    fund_id INTEGER,
    asset_id INTEGER,
    weight_pct NUMERIC,
    quarter_end DATE
);

-- Ensure unique constraint exists on raw.holdings
-- (This constraint is used for ON CONFLICT DO NOTHING in UPSERT)
CREATE INDEX IF NOT EXISTS idx_holdings_fk ON raw.holdings(fund_id, asset_id, date);


