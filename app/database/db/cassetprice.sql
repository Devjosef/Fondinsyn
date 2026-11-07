-- Retrieve all asset prices
SELECT id, asset_id, price, date
FROM raw.asset_price;


-- Retreive price history for a specific asset and date range, 
-- ordered latest by first
SELECT id, asset_id, price, date
FROM raw.asset_price
WHERE asset_id = :asset_id
    AND date BETWEEN :start_date AND :end_date
ORDER BY date DESC;

-- Insert new asset price record
INSERT INTO raw.asset_price (asset_id, price, date)
VALUES (:asset_id, :price, :date)
RETURNING id;

-- Update an existing asset price by id
UPDATE raw.asset_price
SET price = :price, date = :date
WHERE id = :id;

-- Delete an asset record by id
DELETE FROM raw.asset_price
WHERE id = :id;
