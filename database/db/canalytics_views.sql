CREATE SCHEMA IF NOT EXISTS analytics;

DROP MATERIALIZED VIEW IF EXISTS analytics.mv_fund_sector_allocation_summary CASCADE;

CREATE MATERIALIZED VIEW analytics.mv_fund_sector_allocation_summary AS
SELECT 
    f.id AS fund_id,
    f.name AS fund_name,
    s.id AS sector_id,
    s.sector_name AS sector,
    fsa.allocation AS allocation_pct,
    fsa.date AS quarter_end,
    COUNT(DISTINCT h.id) AS holding_count,
    SUM(a.market_cap) AS sector_market_cap,
    MIN(fsa.date) AS first_seen,
    MAX(fsa.date) AS last_seen,
    CURRENT_TIMESTAMP AS view_refreshed_at
FROM raw.fund_sector_allocation fsa
INNER JOIN raw.funds f ON fsa.fund_id = f.id
INNER JOIN raw.sectors s ON fsa.sector_id = s.id
LEFT JOIN raw.holdings h ON f.id = h.fund_id AND fsa.date = h.date
LEFT JOIN raw.assets a ON h.asset_id = a.id AND s.id = a.sector_id
GROUP BY 
    f.id, f.name, s.id, s.sector_name, fsa.allocation, fsa.date
WITH DATA;

CREATE UNIQUE INDEX idx_mv_fsa_unique_key ON analytics.mv_fund_sector_allocation_summary
    (fund_id, sector_id, quarter_end);

CREATE INDEX idx_mv_fsa_fund_id ON analytics.mv_fund_sector_allocation_summary (fund_id);
CREATE INDEX idx_mv_fsa_sector_id ON analytics.mv_fund_sector_allocation_summary (sector_id);
CREATE INDEX idx_mv_fsa_date ON analytics.mv_fund_sector_allocation_summary (quarter_end);

GRANT SELECT ON analytics.mv_fund_sector_allocation_summary TO dvjosef;

DROP MATERIALIZED VIEW IF EXISTS analytics.mv_holdings_by_quarter CASCADE;

CREATE MATERIALIZED VIEW analytics.mv_holdings_by_quarter AS
SELECT 
    h.id AS holding_id,
    f.id AS fund_id,
    f.name AS fund_name,
    a.id AS asset_id,
    a.ticker AS ticker,
    a.name AS asset_name,
    s.sector_name AS sector,
    a.market_cap AS asset_market_cap,
    h.weight AS holding_weight_pct,
    h.date AS quarter_end,
    LAG(h.weight) OVER (
        PARTITION BY f.id, a.id 
        ORDER BY h.date
    ) AS prev_quarter_weight,
    h.weight - LAG(h.weight) OVER (
        PARTITION BY f.id, a.id 
        ORDER BY h.date
    ) AS weight_change_pct,
    ROW_NUMBER() OVER (
        PARTITION BY f.id, a.id 
        ORDER BY h.date DESC
    ) AS quarter_recency_rank,
    CURRENT_TIMESTAMP AS view_refreshed_at
FROM raw.holdings h
INNER JOIN raw.funds f ON h.fund_id = f.id
INNER JOIN raw.assets a ON h.asset_id = a.id
LEFT JOIN raw.sectors s ON a.sector_id = s.id
WITH DATA;

CREATE UNIQUE INDEX idx_mv_holdings_unique_key ON analytics.mv_holdings_by_quarter
    (holding_id, fund_id, asset_id, quarter_end);

CREATE INDEX idx_mv_holdings_fund_id ON analytics.mv_holdings_by_quarter (fund_id);
CREATE INDEX idx_mv_holdings_asset_id ON analytics.mv_holdings_by_quarter (asset_id);
CREATE INDEX idx_mv_holdings_date ON analytics.mv_holdings_by_quarter (quarter_end);
CREATE INDEX idx_mv_holdings_sector ON analytics.mv_holdings_by_quarter (sector);

GRANT SELECT ON analytics.mv_holdings_by_quarter TO dvjosef;

DROP MATERIALIZED VIEW IF EXISTS analytics.mv_fund_performance_trends CASCADE;

CREATE MATERIALIZED VIEW analytics.mv_fund_performance_trends AS
SELECT 
    f.id AS fund_id,
    f.name AS fund_name,
    fp.metric_name AS metric,
    fp.metric_value AS metric_value,
    fp.date AS quarter_end,
    LAG(fp.metric_value) OVER (
        PARTITION BY f.id, fp.metric_name 
        ORDER BY fp.date
    ) AS prev_quarter_value,
    fp.metric_value - LAG(fp.metric_value) OVER (
        PARTITION BY f.id, fp.metric_name 
        ORDER BY fp.date
    ) AS metric_change,
    AVG(fp.metric_value) OVER (
        PARTITION BY f.id, fp.metric_name 
        ORDER BY fp.date 
        ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
    ) AS moving_avg_4q,
    ROW_NUMBER() OVER (
        PARTITION BY f.id, fp.metric_name 
        ORDER BY fp.date DESC
    ) AS recency_rank,
    CURRENT_TIMESTAMP AS view_refreshed_at
FROM raw.fund_performance fp
INNER JOIN raw.funds f ON fp.fund_id = f.id
WITH DATA;

CREATE UNIQUE INDEX idx_mv_perf_unique_key ON analytics.mv_fund_performance_trends
    (fund_id, metric, quarter_end);

CREATE INDEX idx_mv_perf_fund_id ON analytics.mv_fund_performance_trends (fund_id);
CREATE INDEX idx_mv_perf_metric ON analytics.mv_fund_performance_trends (metric);
CREATE INDEX idx_mv_perf_date ON analytics.mv_fund_performance_trends (quarter_end);

GRANT SELECT ON analytics.mv_fund_performance_trends TO dvjosef;

CREATE OR REPLACE VIEW analytics.v_view_refresh_status AS
SELECT 
    'mv_fund_sector_allocation_summary' AS view_name,
    (SELECT COALESCE(MAX(view_refreshed_at), '1900-01-01'::timestamp) 
     FROM analytics.mv_fund_sector_allocation_summary) AS last_refreshed,
    CURRENT_TIMESTAMP - (SELECT COALESCE(MAX(view_refreshed_at), '1900-01-01'::timestamp) 
     FROM analytics.mv_fund_sector_allocation_summary) AS age
UNION ALL
SELECT 
    'mv_holdings_by_quarter' AS view_name,
    (SELECT COALESCE(MAX(view_refreshed_at), '1900-01-01'::timestamp) 
     FROM analytics.mv_holdings_by_quarter) AS last_refreshed,
    CURRENT_TIMESTAMP - (SELECT COALESCE(MAX(view_refreshed_at), '1900-01-01'::timestamp) 
     FROM analytics.mv_holdings_by_quarter) AS age
UNION ALL
SELECT 
    'mv_fund_performance_trends' AS view_name,
    (SELECT COALESCE(MAX(view_refreshed_at), '1900-01-01'::timestamp) 
     FROM analytics.mv_fund_performance_trends) AS last_refreshed,
    CURRENT_TIMESTAMP - (SELECT COALESCE(MAX(view_refreshed_at), '1900-01-01'::timestamp) 
     FROM analytics.mv_fund_performance_trends) AS age;

GRANT USAGE ON SCHEMA analytics TO dvjosef;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO dvjosef;
GRANT SELECT ON ALL VIEWS IN SCHEMA analytics TO dvjosef;