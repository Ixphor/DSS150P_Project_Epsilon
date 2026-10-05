SELECT 'CREATE DATABASE cfpb_pipeline'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'cfpb_pipeline')\gexec

\c cfpb_pipeline

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS curated;

CREATE TABLE IF NOT EXISTS raw.raw_cfpb_complaints (
    date_received DATE,
    product TEXT,
    sub_product TEXT,
    issue TEXT,
    sub_issue TEXT,
    company_public_response TEXT,
    company TEXT,
    state TEXT,
    zip_code TEXT,
    tags TEXT,
    submitted_via TEXT,
    date_sent_to_company DATE,
    company_response_to_consumer TEXT,
    timely_response TEXT,
    complaint_id BIGINT PRIMARY KEY,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT DEFAULT 'cfpb_complaints_csv'
);

CREATE TABLE IF NOT EXISTS raw.raw_fdic_institutions (
    cert                BIGINT PRIMARY KEY,
    name                TEXT,
    name_hcr            TEXT,
    city                TEXT,
    state               TEXT,
    state_name          TEXT,
    zip                 TEXT,
    asset               BIGINT,
    deposits            BIGINT,
    net_income          BIGINT,
    roa                 NUMERIC(15,4),
    roe                 NUMERIC(15,4),
    offices             INTEGER,
    bank_class          TEXT,
    charter             TEXT,
    regulator           TEXT,
    active              INTEGER,
    inactive            INTEGER,
    established_date    DATE,
    date_updated        DATE,
    run_date            DATE,
    report_date         DATE,
    ingested_at         TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.raw_census_state (
    state_fips               TEXT PRIMARY KEY,
    name                     TEXT,
    total_population         NUMERIC,
    median_household_income  NUMERIC,
    poverty_population       NUMERIC,
    white_alone              NUMERIC,
    black_alone               NUMERIC,
    ingested_at              TIMESTAMP DEFAULT NOW()
);