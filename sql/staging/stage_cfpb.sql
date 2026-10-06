-- STAGING LAYER: CFPB complaints
-- Allowed here: clean, standardise, derive fields, quarantine invalid rows.
-- NOT allowed: joins to other sources (that is the curated layer).
-- Rerun strategy: controlled full rebuild inside ONE transaction (readers never see a half-built table).

CREATE SCHEMA IF NOT EXISTS staging;

DROP VIEW  IF EXISTS staging.v_cfpb_classified;
DROP TABLE IF EXISTS staging.complaints;
DROP TABLE IF EXISTS staging.complaints_rejected;

-- Single definition of "what makes a complaint invalid", used by both tables below.
CREATE VIEW staging.v_cfpb_classified AS
SELECT
    r.*,
    CASE
        WHEN r.date_received IS NULL OR r.product IS NULL OR r.company IS NULL
            THEN 'null_core_field'
        WHEN r.timely_response IS NOT NULL AND r.timely_response NOT IN ('Yes', 'No')
            THEN 'invalid_timely_enum'
        WHEN r.date_sent_to_company IS NULL OR r.date_sent_to_company < r.date_received
            THEN 'missing_or_negative_sla_lag'
        WHEN r.date_received > CURRENT_DATE
            THEN 'future_date_received'
    END AS reject_reason
FROM raw.raw_cfpb_complaints r;

-- Quarantine: nothing is silently dropped.
CREATE TABLE staging.complaints_rejected AS
SELECT complaint_id, date_received, date_sent_to_company, product, company,
       timely_response, reject_reason, source_system, batch_id, NOW() AS rejected_at
FROM staging.v_cfpb_classified
WHERE reject_reason IS NOT NULL;

-- Clean rows. Missing-value rules: sub_product / sub_issue / issue -> 'Not specified', tags -> 'No Tag',
-- invalid ZIP -> NULL (a bad ZIP does not invalidate the whole complaint).
CREATE TABLE staging.complaints AS
SELECT
    complaint_id,
    date_received,
    date_sent_to_company,
    (date_sent_to_company - date_received)                          AS response_lag_days,
    EXTRACT(YEAR  FROM date_received)::SMALLINT                     AS received_year,
    EXTRACT(MONTH FROM date_received)::SMALLINT                     AS received_month,
    TRIM(product)                                                   AS product,
    COALESCE(NULLIF(TRIM(sub_product), ''), 'Not specified')        AS sub_product,
    COALESCE(NULLIF(TRIM(issue), ''), 'Not specified')              AS issue,
    COALESCE(NULLIF(TRIM(sub_issue), ''), 'Not specified')          AS sub_issue,
    UPPER(TRIM(company))                                            AS company,
    NULLIF(UPPER(TRIM(state)), '')                                  AS state,
    CASE WHEN zip_code ~ '^[0-9X]{5}$' THEN zip_code END            AS zip_code,
    COALESCE(NULLIF(TRIM(tags), ''), 'No Tag')                      AS tags,
    submitted_via,
    company_public_response,
    company_response_to_consumer,
    timely_response,
    (timely_response = 'Yes')                                       AS is_timely,
    source_system,
    batch_id,
    ingested_at
FROM staging.v_cfpb_classified
WHERE reject_reason IS NULL;

ALTER TABLE staging.complaints ADD PRIMARY KEY (complaint_id);
CREATE INDEX idx_stg_complaints_company ON staging.complaints (company);
ANALYZE staging.complaints;
