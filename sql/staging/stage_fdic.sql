-- STAGING LAYER: FDIC institutions
-- FDIC dollar amounts (asset, deposits, net_income) are reported in THOUSANDS of USD.

DROP TABLE IF EXISTS staging.fdic_institutions;

CREATE TABLE staging.fdic_institutions AS
SELECT
    cert,
    TRIM(name)                                       AS name,
    staging.normalize_name(name)                     AS name_key,
    NULLIF(TRIM(name_hcr), '')                       AS holding_company_name,
    staging.normalize_name(name_hcr)                 AS holding_company_key,
    NULLIF(TRIM(city), '')                           AS city,
    NULLIF(UPPER(TRIM(state)), '')                   AS state,
    NULLIF(TRIM(state_name), '')                     AS state_name,
    CASE WHEN zip ~ '^[0-9]{5}' THEN LEFT(zip, 5) END AS zip5,
    asset,
    deposits,
    net_income,
    roa,
    roe,
    offices,
    bank_class,
    charter,
    regulator,
    CASE
        WHEN asset IS NULL OR asset <= 0 THEN 'Unknown'
        WHEN asset >= 250000000 THEN 'Over $250B'
        WHEN asset >= 10000000  THEN '$10B - $250B'
        WHEN asset >= 1000000   THEN '$1B - $10B'
        ELSE 'Under $1B'
    END                                              AS asset_tier,
    (asset IS NULL OR asset <= 0)                    AS asset_missing,
    established_date,
    report_date,
    ingested_at
FROM raw.raw_fdic_institutions
WHERE cert IS NOT NULL
  AND active = 1;

ALTER TABLE staging.fdic_institutions ADD PRIMARY KEY (cert);
CREATE INDEX idx_stg_fdic_name_key ON staging.fdic_institutions (name_key);
CREATE INDEX idx_stg_fdic_hc_key   ON staging.fdic_institutions (holding_company_key);
ANALYZE staging.fdic_institutions;
