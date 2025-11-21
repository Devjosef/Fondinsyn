-- Retrieve ETL logs
SELECT id, run_date, status, message
FROM control.etl_log

-- Insert a new ETL log
INSERT INTO control.etl_log (run_date, status, message)
VALUES (:run_date, :status, :message)
RETURNING :id;

-- Update ETL log by id
UPDATE control.etl_log
SET status = :status
    message = :message
WHERE id = :id;

-- Delete ETL log by id
DELETE FROM control.etl_log
WHERE id = :id;