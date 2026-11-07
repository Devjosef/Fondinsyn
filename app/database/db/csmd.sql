-- Retrieve all source metadata entries
SELECT id, source_name, url, last_updated
FROM control.source_metadata;

-- Retrieve metadata for a specific source by name
SELECT id, source_name, url, last_updated
FROM control.source_metadata
WHERE source_name = :source_name;

-- Insert a new source metadata record
INSERT INTO control.source_metadata (source_name, url, last_updated)
VALUES (:source_name, :url, :last_updated)
RETURNING id;

-- Update a source metadata record by id
UPDATE control.source metadata
SET source_name = :source_name
    url = :url,
    last_updated = :last_updated
WHERE id = :id;

-- Delete a source metadata record by id
DELETE FROM control.source_metadata
WHERE id = :id;