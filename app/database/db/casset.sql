--- Retrieve all assets
SELECT id, ticker, name, sector_id, market_cap
FROM raw.assets;

-- Retrieve assets joined with sector info
SELECT a.id AS asset_id, a.ticker, a.name AS asset_name,  a.market_cap,
       s.id AS sector_id, s.sector_name
FROM raw.assets a
LEFT JOIN raw.sectors s ON a.sector_id = s.id;

-- Insert a new asset
INSERT INTO raw.assets (ticker, name, sector_id, market_cap)
VALUES (:ticker, :name, :sector_id, :market_cap)
RETURNING id;

-- Update existing asset
UPDATE raw.assets
SET ticker = :ticker,
    name = :name,
    sector_id = :sector_id,
    market_cap = :market_cap
WHERE id = :asset_id;

-- Delete asset by id
DELETE FROM raw.assets
WHERE id = :asset_id;

-- Retrieve holdings of a specific asset (fund info)
SELECT h.id, h.fund_id, f.name AS fund_name, h.weight, h.date
FROM raw.holdings h
JOIN raw.funds f ON h.fund_id = f.id
WHERE h.asset_id = :asset_id;

-- Retrieve price history for an asset
SELECT id, price, date
FROM raw.asset_price
WHERE asset_id = :asset_id
ORDER BY date DESC;