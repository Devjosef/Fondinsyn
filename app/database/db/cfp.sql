-- Retrieve all fund performance entries
SELECT id, fund_id, metric_name, metric_value, date
FROM raw.fund_performance;

-- Retrieve performance for a given fund, metric, and date
SELECT id, fund_id, metric_name, metric_value date
FROM raw.fund_performance
WHERE fund_id = :fund_id
    AND metric_name = :metric_name
    AND date = :date;

-- Insert new fund performance record
INSERT INTO raw.fund_performance (fund_id, metric_name, metric_value, date)
VALUES (:fund_id, :metric_name, :metric_value, :date)
RETURNING id;

-- Update fund performance record by id
UPDATE raw.fund_performance
SET metric_value = :metric_value, date = :date
WHERE id = :id;

--Delete fund performance record by id
DELETE FROM raw.fund_performance
WHERE id = :id;