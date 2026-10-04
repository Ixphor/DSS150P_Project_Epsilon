import io
import os
import sys
import time
import pandas as pd
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("POSTGRES_USER", "airflow")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
if not DB_PASS:
    raise EnvironmentError("POSTGRES_PASSWORD not set - check your .env file")
TARGET_DB = os.getenv("POSTGRES_DB", "airflow")

EXPECTED_COLS = [
    "Date received", "Product", "Sub-product", "Issue", "Sub-issue",
    "Company public response", "Company", "State", "ZIP code", "Tags",
    "Submitted via", "Date sent to company", "Company response to consumer",
    "Timely response?", "Complaint ID"
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
    source_system TEXT DEFAULT 'cfpb_bulk_csv'
);

CREATE INDEX IF NOT EXISTS idx_cfpb_date_received ON raw.raw_cfpb_complaints (date_received);
CREATE INDEX IF NOT EXISTS idx_cfpb_product ON raw.raw_cfpb_complaints (product);
"""


def ensure_database_and_table():
    conn = psycopg2.connect(dbname="airflow", user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (TARGET_DB,))
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {TARGET_DB};")
        print(f"Created database '{TARGET_DB}'.")
    cur.close()
    conn.close()

    conn = psycopg2.connect(dbname=TARGET_DB, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT)
    cur = conn.cursor()
    cur.execute(CREATE_TABLE_SQL)
    conn.commit()
    cur.close()
    conn.close()


def ingest_in_batches(csv_path: str, batch_size: int = 100_000, truncate_first: bool = True):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Cannot find file at: {csv_path}")

    ensure_database_and_table()

    conn = psycopg2.connect(dbname=TARGET_DB, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT)
    cur = conn.cursor()

    if truncate_first:
        cur.execute("TRUNCATE TABLE raw.raw_cfpb_complaints;")
        conn.commit()
        print("Cleared existing rows in raw.raw_cfpb_complaints.")

    copy_sql = "COPY raw.raw_cfpb_complaints (date_received, product, sub_product, issue, sub_issue, company_public_response, company, state, zip_code, tags, submitted_via, date_sent_to_company, company_response_to_consumer, timely_response, complaint_id) FROM STDIN WITH (FORMAT csv, NULL '')"
    total_rows = 0
    start_time = time.time()

    chunks = pd.read_csv(csv_path, chunksize=batch_size, dtype=str, usecols=EXPECTED_COLS)

    for batch_num, chunk in enumerate(chunks, start=1):
        batch_start = time.time()

        chunk = chunk[EXPECTED_COLS].dropna(subset=["Complaint ID"])

        buffer = io.StringIO()
        chunk.to_csv(buffer, index=False, header=False)
        buffer.seek(0)

        cur.copy_expert(copy_sql, buffer)
        conn.commit()

        total_rows += len(chunk)
        elapsed = time.time() - batch_start
        print(f"[Batch {batch_num:03d}] Ingested {len(chunk):,} rows ({elapsed:.2f}s) | Total: {total_rows:,}")

    total_time = time.time() - start_time
    print(f"\nFinished! Ingested {total_rows:,} total rows from {csv_path} in {total_time:.2f}s.")

    cur.execute("ANALYZE raw.raw_cfpb_complaints;")
    conn.commit()

    cur.close()
    conn.close()


if __name__ == "__main__":
    default_path = "data/raw/complaints.csv"
    file_to_ingest = sys.argv[1] if len(sys.argv) > 1 else default_path
    ingest_in_batches(file_to_ingest, batch_size=100_000, truncate_first=True)