--- Retrieve all fund history records
SELECT id, fund_id, change_description, date
FROM raw.fund_history;

-- Retrieve fund history filtered by fund and date
SELECT id, fund_id,change_description, date
FROM raw.fund_history
WHERE fund_id = :fund_id
    AND date = :date;

-- Insert new fund history record
INSERT INTO raw.fund_history (fund_id, change_description, date)
VALUES (:fund_id, :change_description, :date)
RETURNING id;

-- Update fund history record by id
UPDATE raw.fund_history
SET change_description = :change_description,
    date = :date
WHERE id = :id;

-- Delete fund history record by id
DELETE FROM raw.fund_history
WHERE id = :id;