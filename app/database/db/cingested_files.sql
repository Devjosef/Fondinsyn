CREATE TABLE IF NOT EXISTS control.ingested_files (
    id SERIAL PRIMARY KEY,
    quarter_id VARCHAR(10) NOT NULL UNIQUE,
    file_url VARCHAR(512) NOT NULL,
    local_path VARCHAR(255),
    
    lifecycle_state VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    files_downloaded INTEGER DEFAULT 0,
    holdings_extracted INTEGER DEFAULT 0,
    xml_parse_errors INTEGER DEFAULT 0,
    
    error_message TEXT,
    error_traceback TEXT,
    retry_count INTEGER DEFAULT 0,
    
    UNIQUE(quarter_id),
    INDEX idx_ingested_files_quarter_id (quarter_id),
    INDEX idx_ingested_files_lifecycle_state (lifecycle_state),
    INDEX idx_ingested_files_created_at (created_at),
    INDEX idx_ingested_files_state_retry (lifecycle_state, retry_count)
);

CREATE OR REPLACE VIEW control.v_missing_quarters AS
SELECT 
    'Q1' AS quarter_num, 
    EXTRACT(YEAR FROM CURRENT_DATE) AS year,
    EXTRACT(YEAR FROM CURRENT_DATE)::text || 'Q1' AS quarter_id
UNION ALL
SELECT 'Q2', EXTRACT(YEAR FROM CURRENT_DATE), EXTRACT(YEAR FROM CURRENT_DATE)::text || 'Q2'
UNION ALL
SELECT 'Q3', EXTRACT(YEAR FROM CURRENT_DATE), EXTRACT(YEAR FROM CURRENT_DATE)::text || 'Q3'
UNION ALL
SELECT 'Q4', EXTRACT(YEAR FROM CURRENT_DATE), EXTRACT(YEAR FROM CURRENT_DATE)::text || 'Q4'
WHERE NOT EXISTS (
    SELECT 1 FROM control.ingested_files 
    WHERE lifecycle_state IN ('COMPLETED', 'IN_PROGRESS')
);

CREATE OR REPLACE FUNCTION control.sp_upsert_ingestion_state(
    p_quarter_id VARCHAR(10),
    p_file_url VARCHAR(512),
    p_new_state VARCHAR(50),
    p_error_msg TEXT DEFAULT NULL,
    p_error_trace TEXT DEFAULT NULL
)
RETURNS TABLE (
    id INTEGER,
    lifecycle_state VARCHAR(50),
    created_at TIMESTAMP,
    completed_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    WITH upsert AS (
        INSERT INTO control.ingested_files 
            (quarter_id, file_url, lifecycle_state, created_at)
        VALUES 
            (p_quarter_id, p_file_url, COALESCE(p_new_state, 'PENDING'), CURRENT_TIMESTAMP)
        ON CONFLICT (quarter_id) DO UPDATE
        SET 
            lifecycle_state = CASE
                WHEN excluded.lifecycle_state = 'COMPLETED' THEN 'COMPLETED'
                WHEN p_new_state = 'FAILED' THEN 'FAILED'
                ELSE COALESCE(p_new_state, lifecycle_state)
            END,
            started_at = CASE WHEN p_new_state = 'IN_PROGRESS' THEN CURRENT_TIMESTAMP ELSE started_at END,
            completed_at = CASE WHEN p_new_state = 'COMPLETED' THEN CURRENT_TIMESTAMP ELSE completed_at END,
            error_message = COALESCE(p_error_msg, error_message),
            error_traceback = COALESCE(p_error_trace, error_traceback),
            retry_count = CASE WHEN p_new_state = 'FAILED' THEN retry_count + 1 ELSE retry_count END
        RETURNING 
            ingested_files.id,
            ingested_files.lifecycle_state,
            ingested_files.created_at,
            ingested_files.completed_at
    )
    SELECT * FROM upsert;
END;
$$ LANGUAGE plpgsql;

GRANT SELECT ON control.ingested_files TO dvjosef;
GRANT EXECUTE ON FUNCTION control.sp_upsert_ingestion_state TO dvjosef;