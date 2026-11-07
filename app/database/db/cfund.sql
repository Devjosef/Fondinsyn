--- Retrieve funds
SELECT id, name, provider
FROM raw.funds;

-- Retrieve funds with holdings & history counts
SELECT f.id, f.name, f.provider,
    COUNT(DISTINCT h.id) AS holdings_count,
    COUNT(DISTINCT fh.id) AS history_count
FROM raw.funds f
LEFT JOIN raw.fund_holdings h ON h.fund_id = f.id
LEFT JOIN raw.fund_history fh ON fh.fund_id = f.id
GROUP BY f.id, f.name, f.provider;

-- Get all funds with latest performance metrics for each fund
SELECT DISTINCT ON (f.id) f.id, f.name, fp.metric_name, fp.metric_value, fp.date
FROM raw.funds f
JOIN raw.fund_performance fp ON f.id = fp.fund_id
ORDER BY f.id, fp.date DESC;

--- Get fund holdings summarized, (by asset on specific date)
SELECT f.id AS fund_id, f.name AS fund_name,
    a.id AS asset_id, a.ticker, a.name AS asset_name,
    SUM(h.weight) AS total_weight
FROM raw.holdings h
JOIN raw.funds f ON h.fund_id = f.id
JOIN raw.assets a ON h.asset_id = a.id
WHERE h.date = :date
GROUP BY f.id, f.name, a.id, a.ticker, a.name;

--- Insert a new fund record, (returning it's id)
INSERT INTO raw.funds (name, provider)
VALUES (:name, :provider)
RETURNING id;

--- Update existing fund
UPDATE raw.funds
SET name = :name, provider = :provider
WHERE id = :fund_id;

--- Delete a fund by id
DELETE FROM raw.funds
WHERE id = :fund_id;