CREATE OR REPLACE VIEW analytics.v_fondinsyn_quarter_summary AS
SELECT
    quarter_end,
    SUM(market_value_sek) AS market_value_sek,
    COUNT(DISTINCT fund_name)::integer AS fund_count,
    COUNT(DISTINCT isin)::integer AS instrument_count
FROM analytics.mv_holdings_by_quarter
GROUP BY quarter_end;

CREATE OR REPLACE VIEW analytics.v_fondinsyn_latest_fund_values AS
SELECT
    holdings.quarter_end,
    holdings.fund_name,
    SUM(holdings.market_value_sek) AS market_value_sek
FROM analytics.mv_holdings_by_quarter AS holdings
WHERE holdings.quarter_end = (
    SELECT MAX(quarter_end)
    FROM analytics.mv_holdings_by_quarter
)
GROUP BY holdings.quarter_end, holdings.fund_name;

CREATE OR REPLACE VIEW analytics.v_fondinsyn_latest_security_values AS
SELECT
    holdings.quarter_end,
    COALESCE(NULLIF(BTRIM(holdings.security_name), ''), holdings.isin) AS security_name,
    holdings.isin,
    SUM(holdings.market_value_sek) AS market_value_sek
FROM analytics.mv_holdings_by_quarter AS holdings
WHERE holdings.quarter_end = (
    SELECT MAX(quarter_end)
    FROM analytics.mv_holdings_by_quarter
)
GROUP BY
    holdings.quarter_end,
    COALESCE(NULLIF(BTRIM(holdings.security_name), ''), holdings.isin),
    holdings.isin;
