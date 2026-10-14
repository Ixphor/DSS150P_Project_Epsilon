-- Row counts and duplicate checks for the whole pipeline.
-- Run before and after a repeat DAG run: the numbers must not grow when the source has nothing new.
--   docker compose exec -T postgres psql -U airflow -d cfpb_pipeline < sql/queries/row_counts.sql

SELECT layer, table_name, row_count, distinct_keys,
       CASE WHEN distinct_keys IS NULL THEN 'n/a'
            WHEN row_count = distinct_keys THEN 'OK (no duplicates)'
            ELSE 'DUPLICATES' END AS duplicate_check
FROM (
    SELECT 1 AS ord, 'raw' AS layer, 'raw_cfpb_complaints' AS table_name,
           COUNT(*) AS row_count, COUNT(DISTINCT complaint_id) AS distinct_keys FROM raw.raw_cfpb_complaints
    UNION ALL SELECT 2, 'raw', 'raw_fdic_institutions',  COUNT(*), COUNT(DISTINCT cert)       FROM raw.raw_fdic_institutions
    UNION ALL SELECT 3, 'raw', 'raw_census_state',       COUNT(*), COUNT(DISTINCT state_fips) FROM raw.raw_census_state
    UNION ALL SELECT 4, 'staging', 'complaints',          COUNT(*), COUNT(DISTINCT complaint_id) FROM staging.complaints
    UNION ALL SELECT 5, 'staging', 'complaints_rejected', COUNT(*), COUNT(DISTINCT complaint_id) FROM staging.complaints_rejected
    UNION ALL SELECT 6, 'staging', 'fdic_institutions',   COUNT(*), COUNT(DISTINCT cert)         FROM staging.fdic_institutions
    UNION ALL SELECT 7, 'staging', 'census_state',        COUNT(*), COUNT(DISTINCT state_fips)   FROM staging.census_state
    UNION ALL SELECT 8, 'curated', 'dim_company',         COUNT(*), COUNT(DISTINCT company_id)   FROM curated.dim_company
    UNION ALL SELECT 9, 'curated', 'dim_product',         COUNT(*), COUNT(DISTINCT product_id)   FROM curated.dim_product
    UNION ALL SELECT 10, 'curated', 'dim_issue',          COUNT(*), COUNT(DISTINCT issue_id)     FROM curated.dim_issue
    UNION ALL SELECT 11, 'curated', 'dim_geography',      COUNT(*), COUNT(DISTINCT state_fips)   FROM curated.dim_geography
    UNION ALL SELECT 12, 'curated', 'dim_institution',    COUNT(*), COUNT(DISTINCT cert)         FROM curated.dim_institution
    UNION ALL SELECT 13, 'curated', 'bridge_company_institution', COUNT(*), COUNT(DISTINCT company_id) FROM curated.bridge_company_institution
    UNION ALL SELECT 14, 'curated', 'fact_complaints',    COUNT(*), COUNT(DISTINCT complaint_id) FROM curated.fact_complaints
    UNION ALL SELECT 15, 'curated', 'mart_complaints_monthly',     COUNT(*), NULL FROM curated.mart_complaints_monthly
    UNION ALL SELECT 16, 'curated', 'mart_institution_scorecard',  COUNT(*), NULL FROM curated.mart_institution_scorecard
) t
ORDER BY ord;

-- Reconciliation: every raw complaint is either staged or quarantined, and every staged complaint is in the fact table.
SELECT
    (SELECT COUNT(*) FROM raw.raw_cfpb_complaints)                                         AS raw_rows,
    (SELECT COUNT(*) FROM staging.complaints) + (SELECT COUNT(*) FROM staging.complaints_rejected) AS staged_plus_rejected,
    (SELECT COUNT(*) FROM staging.complaints)                                              AS staged_rows,
    (SELECT COUNT(*) FROM curated.fact_complaints)                                         AS fact_rows;

-- Quarantine breakdown
SELECT reject_reason, COUNT(*) AS rows_quarantined
FROM staging.complaints_rejected
GROUP BY 1
ORDER BY 2 DESC;