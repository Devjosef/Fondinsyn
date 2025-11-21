-- Retrieve all fund sector allocations
SELECT id, fund_id, sector_id, allocation, date
FROM raw.fund_sector_allocation:

-- Retrieve allocations for a specific fund on a specific date
SELECT fsa.id, fsa.fund_id, s.sector_name, fsa.allocationm fsa.date
FROM raw.fund_sector_allocation fsa
JOIN raw.sectors s ON fsa.sector_id = s.id
WHERE fsa.fund_id = :fund_id
    AND fsa.date = :date;

-- Insert new allocation
INSERT INTO raw.fund_sector_allocation (fund_id, sector_id, allocation, date)
VALUES (:fund_id, :sector_id, :allocation, :date)
RETURNING id;

-- Update allocation by id
UPDATE raw.fund_sector_allocation
SET allocation = :allocation, date = :date
WHERE id = :id;

-- Delete allocation by id
DELETE FROM raw.fund_sector_allocation
WHERE id = :id;