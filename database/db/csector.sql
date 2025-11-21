--- Retrieve all sectors
SELECT id, sector_name
FROM raw.sectors;

--- Get assets by sector
SELECT s.id AS sector_id, s.sector_name, a.id AS asset_id, a.ticker, a.sector_name
FROM raw.sectors s
JOIN raw.assets a ON a.sector_id = s.id;

--- Get sector allocations for funds on a specific date
SELECT fsa.fund_id, s.sector_name, fsa.allocation, fsa.date
FROM raw.fund_sector_allocation fsa
JOIN raw.sectors s ON fsa.sector_id = s.id
WHERE fsa.date = :date;

--- Insert a new sector
INSERT INTO raw.sectors (sector_name)
VALUES(:sector_name)
RETURNING id;

--- Update sector
UPDATE raw.sectors
SET sector_name = :sector_name
WHERE id = :sector_id;

-- Delete sector
DELETE FROM raw.sectors
WHERE id = :sector_id;