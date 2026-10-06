-- CURATED LAYER: star schema integrating CFPB (facts), Census (geography) and FDIC (institutions).
-- Allowed here: joins across sources, surrogate keys, constraints, derived business fields.
-- Rerun strategy: full rebuild of all curated tables in ONE transaction (atomic swap of results).
--
--   dim_geography  (Census)  --+
--   dim_institution (FDIC)   --+--> fact_complaints (CFPB) <-- dim_company, dim_product, dim_issue
--   bridge_company_institution links a CFPB company to an FDIC institution via normalised names.

CREATE SCHEMA IF NOT EXISTS curated;

DROP TABLE IF EXISTS curated.fact_complaints CASCADE;
DROP TABLE IF EXISTS curated.bridge_company_institution CASCADE;
DROP TABLE IF EXISTS curated.dim_company CASCADE;
DROP TABLE IF EXISTS curated.dim_product CASCADE;
DROP TABLE IF EXISTS curated.dim_issue CASCADE;
DROP TABLE IF EXISTS curated.dim_geography CASCADE;
DROP TABLE IF EXISTS curated.dim_institution CASCADE;

-- ---------------------------------------------------------------- dim_geography (Census)
CREATE TABLE curated.dim_geography (
    state_fips               TEXT PRIMARY KEY,
    state_abbr               TEXT UNIQUE,
    state_name               TEXT NOT NULL,
    total_population         NUMERIC,
    median_household_income  NUMERIC,
    poverty_population       NUMERIC,
    poverty_rate_pct         NUMERIC(6,2),
    white_alone              NUMERIC,
    pct_white_alone          NUMERIC(6,2),
    black_alone              NUMERIC,
    pct_black_alone          NUMERIC(6,2)
);
INSERT INTO curated.dim_geography
SELECT state_fips, state_abbr, state_name, total_population, median_household_income,
       poverty_population, poverty_rate_pct, white_alone, pct_white_alone, black_alone, pct_black_alone
FROM staging.census_state;

-- ---------------------------------------------------------------- dim_institution (FDIC)
CREATE TABLE curated.dim_institution (
    cert                 BIGINT PRIMARY KEY,
    name                 TEXT NOT NULL,
    name_key             TEXT,
    holding_company_name TEXT,
    holding_company_key  TEXT,
    city                 TEXT,
    state                TEXT,
    zip5                 TEXT,
    asset                BIGINT,
    deposits             BIGINT,
    net_income           BIGINT,
    roa                  NUMERIC(15,4),
    roe                  NUMERIC(15,4),
    offices              INTEGER,
    bank_class           TEXT,
    charter              TEXT,
    regulator            TEXT,
    asset_tier           TEXT,
    established_date     DATE,
    report_date          DATE
);
INSERT INTO curated.dim_institution
SELECT cert, name, name_key, holding_company_name, holding_company_key, city, state, zip5,
       asset, deposits, net_income, roa, roe, offices, bank_class, charter, regulator,
       asset_tier, established_date, report_date
FROM staging.fdic_institutions;
CREATE INDEX idx_dim_institution_name_key ON curated.dim_institution (name_key);
CREATE INDEX idx_dim_institution_hc_key   ON curated.dim_institution (holding_company_key);

-- ---------------------------------------------------------------- CFPB dimensions
CREATE TABLE curated.dim_company (
    company_id   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_name TEXT NOT NULL UNIQUE,
    company_key  TEXT
);
INSERT INTO curated.dim_company (company_name, company_key)
SELECT DISTINCT company, staging.normalize_name(company)
FROM staging.complaints
ORDER BY company;

CREATE TABLE curated.dim_product (
    product_id       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_name     TEXT NOT NULL,
    sub_product_name TEXT NOT NULL,
    UNIQUE (product_name, sub_product_name)
);
INSERT INTO curated.dim_product (product_name, sub_product_name)
SELECT DISTINCT product, sub_product FROM staging.complaints ORDER BY 1, 2;

CREATE TABLE curated.dim_issue (
    issue_id       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issue_name     TEXT NOT NULL,
    sub_issue_name TEXT NOT NULL,
    UNIQUE (issue_name, sub_issue_name)
);
INSERT INTO curated.dim_issue (issue_name, sub_issue_name)
SELECT DISTINCT issue, sub_issue FROM staging.complaints ORDER BY 1, 2;

-- ---------------------------------------------------------------- bridge: CFPB company -> FDIC institution
-- Match 1 (preferred): company name == institution name.
-- Match 2: company name == the institution's holding-company name (e.g. "WELLS FARGO & COMPANY").
-- When a company maps to several institutions, the one with the largest assets is the primary.
CREATE TABLE curated.bridge_company_institution AS
WITH candidates AS (
    SELECT c.company_id, i.cert, 'institution_name'::TEXT AS match_type, i.asset
    FROM curated.dim_company c
    JOIN curated.dim_institution i ON i.name_key = c.company_key
    WHERE c.company_key IS NOT NULL
    UNION ALL
    SELECT c.company_id, i.cert, 'holding_company'::TEXT, i.asset
    FROM curated.dim_company c
    JOIN curated.dim_institution i ON i.holding_company_key = c.company_key
    WHERE c.company_key IS NOT NULL
),
ranked AS (
    SELECT company_id, cert, match_type,
           ROW_NUMBER() OVER (
               PARTITION BY company_id
               ORDER BY (match_type = 'institution_name') DESC, asset DESC NULLS LAST, cert
           ) AS rn
    FROM candidates
),
counts AS (
    SELECT company_id, COUNT(DISTINCT cert) AS candidate_institutions
    FROM candidates GROUP BY company_id
)
SELECT r.company_id, r.cert, r.match_type, k.candidate_institutions
FROM ranked r
JOIN counts k USING (company_id)
WHERE r.rn = 1;

ALTER TABLE curated.bridge_company_institution ADD PRIMARY KEY (company_id);
ALTER TABLE curated.bridge_company_institution
    ADD FOREIGN KEY (company_id) REFERENCES curated.dim_company (company_id),
    ADD FOREIGN KEY (cert)       REFERENCES curated.dim_institution (cert);

-- ---------------------------------------------------------------- fact_complaints
CREATE TABLE curated.fact_complaints (
    complaint_id                 BIGINT,
    company_id                   INT      NOT NULL,
    product_id                   INT      NOT NULL,
    issue_id                     INT      NOT NULL,
    state_fips                   TEXT,
    institution_cert             BIGINT,
    date_received                DATE     NOT NULL,
    date_sent_to_company         DATE,
    response_lag_days            INT,
    received_year                SMALLINT NOT NULL,
    received_month               SMALLINT NOT NULL,
    zip_code                     TEXT,
    tags                         TEXT,
    submitted_via                TEXT,
    company_public_response      TEXT,
    company_response_to_consumer TEXT,
    timely_response              TEXT,
    is_timely                    BOOLEAN,
    batch_id                     TEXT,
    ingested_at                  TIMESTAMP
);

INSERT INTO curated.fact_complaints
SELECT
    s.complaint_id,
    c.company_id,
    p.product_id,
    i.issue_id,
    g.state_fips,
    b.cert,
    s.date_received,
    s.date_sent_to_company,
    s.response_lag_days,
    s.received_year,
    s.received_month,
    s.zip_code,
    s.tags,
    s.submitted_via,
    s.company_public_response,
    s.company_response_to_consumer,
    s.timely_response,
    s.is_timely,
    s.batch_id,
    s.ingested_at
FROM staging.complaints s
JOIN curated.dim_company c ON c.company_name = s.company
JOIN curated.dim_product p ON p.product_name = s.product   AND p.sub_product_name = s.sub_product
JOIN curated.dim_issue   i ON i.issue_name   = s.issue     AND i.sub_issue_name   = s.sub_issue
LEFT JOIN curated.dim_geography g ON g.state_abbr = s.state
LEFT JOIN curated.bridge_company_institution b ON b.company_id = c.company_id;

ALTER TABLE curated.fact_complaints ADD PRIMARY KEY (complaint_id);
ALTER TABLE curated.fact_complaints
    ADD FOREIGN KEY (company_id)       REFERENCES curated.dim_company (company_id),
    ADD FOREIGN KEY (product_id)       REFERENCES curated.dim_product (product_id),
    ADD FOREIGN KEY (issue_id)         REFERENCES curated.dim_issue (issue_id),
    ADD FOREIGN KEY (state_fips)       REFERENCES curated.dim_geography (state_fips),
    ADD FOREIGN KEY (institution_cert) REFERENCES curated.dim_institution (cert);

CREATE INDEX idx_fact_date_received ON curated.fact_complaints (date_received);
CREATE INDEX idx_fact_year_month    ON curated.fact_complaints (received_year, received_month);
CREATE INDEX idx_fact_state         ON curated.fact_complaints (state_fips);
CREATE INDEX idx_fact_company       ON curated.fact_complaints (company_id);
CREATE INDEX idx_fact_institution   ON curated.fact_complaints (institution_cert) WHERE institution_cert IS NOT NULL;

ANALYZE curated.fact_complaints;
