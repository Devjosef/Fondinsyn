-- Lookup sector_id by sector_name
SELECT id
FROM raw.sectors
WHERE sector_name = :sector_name;