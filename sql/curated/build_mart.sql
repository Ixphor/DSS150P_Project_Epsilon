-- CURATED LAYER, step 2: consumption-ready data products built from the star schema.
-- Rerun strategy: full rebuild in ONE transaction (marts are small, derived, and cheap to recreate).
-- NOTE: build_curated.sql drops fact/dim tables with CASCADE, which also drops the view below,
--       so this file must run after every curated build (the DAG guarantees that order).

-- ---------------------------------------------------------------- 1. Denormalised, analysis-ready view
-- One row per complaint with every dimension attached. This is what gets exported to partitioned Parquet.
-- Numeric columns are cast to float8 so pandas/Parquet receive plain floats instead of Decimals.
CREATE OR REPLACE VIEW curated.v_complaints_enriched AS
SELECT
    f.complaint_id,
    f.date_received,
    f.received_year,
    f.received_month,
    f.date_sent_to_company,
    f.response_lag_days,
    c.company_name,
    p.product_name,
    p.sub_product_name,
    iss.issue_name,
    iss.sub_issue_name,
    f.state_fips,
    g.state_abbr,
    g.state_name,
    g.total_population::float8          AS state_population,
    g.median_household_income::float8   AS state_median_income,
    g.poverty_rate_pct::float8          AS state_poverty_rate_pct,
    f.institution_cert,
    inst.name                           AS institution_name,
    inst.asset_tier                     AS institution_asset_tier,
    inst.asset                          AS institution_asset_thousands_usd,
    f.zip_code,
    f.tags,
    f.submitted_via,
    f.company_public_response,
    f.company_response_to_consumer,
    f.timely_response,
    f.is_timely,
    f.batch_id
FROM curated.fact_complaints f
JOIN curated.dim_company  c   ON c.company_id  = f.company_id
JOIN curated.dim_product  p   ON p.product_id  = f.product_id
JOIN curated.dim_issue    iss ON iss.issue_id  = f.issue_id
LEFT JOIN curated.dim_geography   g    ON g.state_fips = f.state_fips
LEFT JOIN curated.dim_institution inst ON inst.cert    = f.institution_cert;

-- ---------------------------------------------------------------- 2. Monthly complaint mart
-- Grain: month x state x product x institution asset tier.
-- Answers: where, when and in which products are complaints rising, and how timely are responses,
-- for large vs. small banks vs. non-bank companies, next to state demographics.
DROP TABLE IF EXISTS curated.mart_complaints_monthly;
CREATE TABLE curated.mart_complaints_monthly AS
SELECT
    f.received_year,
    f.received_month,
    COALESCE(f.state_fips, 'NA')                                    AS state_fips,
    COALESCE(g.state_abbr, 'NA')                                    AS state_abbr,
    p.product_name,
    COALESCE(i.asset_tier, 'Not FDIC-matched')                      AS asset_tier,
    COUNT(*)                                                        AS complaints,
    COUNT(*) FILTER (WHERE f.is_timely)                             AS timely_complaints,
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.is_timely)
          / NULLIF(COUNT(*) FILTER (WHERE f.is_timely IS NOT NULL), 0), 2) AS timely_pct,
    ROUND(AVG(f.response_lag_days)::NUMERIC, 2)                     AS avg_response_lag_days,
    MAX(g.total_population)                                         AS state_population,
    MAX(g.median_household_income)                                  AS state_median_income,
    MAX(g.poverty_rate_pct)                                         AS state_poverty_rate_pct
FROM curated.fact_complaints f
JOIN curated.dim_product p ON p.product_id = f.product_id
LEFT JOIN curated.dim_geography   g ON g.state_fips = f.state_fips
LEFT JOIN curated.dim_institution i ON i.cert       = f.institution_cert
GROUP BY 1, 2, 3, 4, 5, 6;

ALTER TABLE curated.mart_complaints_monthly
    ADD PRIMARY KEY (received_year, received_month, state_fips, product_name, asset_tier);

-- ---------------------------------------------------------------- 3. Institution scorecard
-- Grain: FDIC institution x year (only complaints matched to an FDIC institution).
-- Answers: which banks draw the most complaints relative to their size, and how do they respond?
DROP TABLE IF EXISTS curated.mart_institution_scorecard;
CREATE TABLE curated.mart_institution_scorecard AS
SELECT
    f.institution_cert                                              AS cert,
    f.received_year,
    i.name                                                          AS institution_name,
    i.holding_company_name,
    i.asset_tier,
    i.state                                                         AS hq_state,
    i.asset                                                         AS asset_thousands_usd,
    i.roa,
    COUNT(*)                                                        AS complaints,
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.is_timely)
          / NULLIF(COUNT(*) FILTER (WHERE f.is_timely IS NOT NULL), 0), 2) AS timely_pct,
    ROUND(AVG(f.response_lag_days)::NUMERIC, 2)                     AS avg_response_lag_days,
    ROUND(COUNT(*) / NULLIF(i.asset / 1000000.0, 0), 3)             AS complaints_per_billion_assets
FROM curated.fact_complaints f
JOIN curated.dim_institution i ON i.cert = f.institution_cert
WHERE f.institution_cert IS NOT NULL
GROUP BY f.institution_cert, f.received_year, i.name, i.holding_company_name,
         i.asset_tier, i.state, i.asset, i.roa;

ALTER TABLE curated.mart_institution_scorecard ADD PRIMARY KEY (cert, received_year);

ANALYZE curated.mart_complaints_monthly;
ANALYZE curated.mart_institution_scorecard;