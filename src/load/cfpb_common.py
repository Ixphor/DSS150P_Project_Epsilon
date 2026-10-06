"""Shared definition of the raw CFPB table, used by both the bulk and the API loader."""

RAW_COLUMNS = [
    "date_received", "product", "sub_product", "issue", "sub_issue",
    "company_public_response", "company", "state", "zip_code", "tags",
    "submitted_via", "date_sent_to_company", "company_response_to_consumer",
    "timely_response", "complaint_id", "source_system", "batch_id",
]

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS raw;

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
    source_system TEXT,
    batch_id TEXT
);

-- Older databases created before batch tracking existed
ALTER TABLE raw.raw_cfpb_complaints ADD COLUMN IF NOT EXISTS batch_id TEXT;
ALTER TABLE raw.raw_cfpb_complaints ADD COLUMN IF NOT EXISTS source_system TEXT;

CREATE INDEX IF NOT EXISTS idx_cfpb_date_received ON raw.raw_cfpb_complaints (date_received);
CREATE INDEX IF NOT EXISTS idx_cfpb_product ON raw.raw_cfpb_complaints (product);
"""


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
    conn.commit()
