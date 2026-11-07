-- Lookup for fund_id by fund_name
SELECT id
FROM raw.funds
WHERE name = :fund_name;