-- Handles duplicates via the Unique constraint fsa(fund sector allocation)
INSERT INTO raw.fund_sector_allocation (fund_id, sector_id, allocation, date)
VALUES (:fund_id, :sector_id, :allocation, :date)
ON CONFLICT (fund_id, sector_id, date)
DO UPDATE SET
    allocation = EXCLUDED.allocation
RETURNING id;