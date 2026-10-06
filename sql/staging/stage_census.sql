-- STAGING LAYER: Census ACS state-level estimates (jam/sentinel values already NULL from the loader)

DROP TABLE IF EXISTS staging.census_state;

CREATE TABLE staging.census_state AS
SELECT
    rc.state_fips,
    m.state_abbr,
    TRIM(rc.name)                                                                AS state_name,
    rc.total_population,
    rc.median_household_income,
    rc.poverty_population,
    ROUND(100.0 * rc.poverty_population / NULLIF(rc.total_population, 0), 2)    AS poverty_rate_pct,
    rc.white_alone,
    ROUND(100.0 * rc.white_alone / NULLIF(rc.total_population, 0), 2)           AS pct_white_alone,
    rc.black_alone,
    ROUND(100.0 * rc.black_alone / NULLIF(rc.total_population, 0), 2)           AS pct_black_alone,
    rc.ingested_at
FROM raw.raw_census_state rc
LEFT JOIN curated.state_abbr_fips_map m ON rc.state_fips = m.state_fips;

ALTER TABLE staging.census_state ADD PRIMARY KEY (state_fips);
ANALYZE staging.census_state;
