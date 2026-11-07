-- Retrieve holdings
SELECT id, fund_id, asset_id, weight, date
FROM raw.holdings;

-- Retrieve holdings for a specific fund. by date
SELECT h.id, h.fund_id, h.asset_id, h.weight, h.date
FROM raw.holdings h
WHERE h.fund_id = :fund_id
    AND h.date = :date;

-- Holdings for a specific asset, with associated fund info
SELECT h.id, h.fund_id, f.name AS fund_name, h.weight, h.date
FROM raw.holdings h
JOIN raw.funds f ON h.fund_id = f.id
WHERE h.asset_id = :asset_id;

-- Insert a new holding
INSERT INTO raw.holdings (fund_id, asset_id, weight, date)
VALUES (:fund_id, :asset_id, :weight, :date)
RETURNING id;

-- Update an existing holding
UPDATE raw.holdings
SET weight = :weight, date = :date
WHERE id = :holding_id;

-- Delete a holding by id
DELETE FROM raw.holdings
WHERE id = :holding_id;