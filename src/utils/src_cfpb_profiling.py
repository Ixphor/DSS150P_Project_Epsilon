import os
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("POSTGRES_USER", "airflow")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
if not DB_PASS:
    raise EnvironmentError("POSTGRES_PASSWORD not set - check your .env file")
TARGET_DB = os.getenv("POSTGRES_DB", "airflow")

OUTPUT_DIR = "outputs/cfpb_profiling"

OVERVIEW_SQL = """
SELECT
    COUNT(*) AS total_records,
    COUNT(DISTINCT complaint_id) AS unique_complaint_ids,
    COUNT(DISTINCT product) AS distinct_products,
    COUNT(DISTINCT sub_product) AS distinct_sub_products,
    COUNT(DISTINCT company) AS distinct_companies,
    COUNT(DISTINCT state) AS distinct_states,
    COUNT(DISTINCT submitted_via) AS distinct_submitted_via,
    MIN(date_received) AS min_date_received,
    MAX(date_received) AS max_date_received,
    COUNT(*) FILTER (WHERE date_sent_to_company < date_received) AS negative_sla_lag_anomalies
FROM raw.raw_cfpb_complaints;
"""

COLUMN_PROFILE_SQL = """
WITH totals AS (
    SELECT COUNT(*):: numeric AS n FROM raw.raw_cfpb_complaints
)
SELECT
    col_name,
    null_count,
    ROUND(100.0 * null_count / t.n, 2) AS null_pct,
    distinct_count
FROM totals t
CROSS JOIN LATERAL (
    VALUES
        ('date_received', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE date_received IS NULL), 
            (SELECT COUNT(DISTINCT date_received) FROM raw.raw_cfpb_complaints)),
        ('product', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE product IS NULL), 
            (SELECT COUNT(DISTINCT product) FROM raw.raw_cfpb_complaints)),
        ('sub_product', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE sub_product IS NULL), 
            (SELECT COUNT(DISTINCT sub_product) FROM raw.raw_cfpb_complaints)),
        ('issue', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE issue IS NULL), 
            (SELECT COUNT(DISTINCT issue) FROM raw.raw_cfpb_complaints)),
        ('sub_issue', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE sub_issue IS NULL), 
            (SELECT COUNT(DISTINCT sub_issue) FROM raw.raw_cfpb_complaints)),
        ('company_public_response', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE company_public_response IS NULL), 
            (SELECT COUNT(DISTINCT company_public_response) FROM raw.raw_cfpb_complaints)),
        ('company', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE company IS NULL), 
            (SELECT COUNT(DISTINCT company) FROM raw.raw_cfpb_complaints)),
        ('state', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE state IS NULL), 
            (SELECT COUNT(DISTINCT state) FROM raw.raw_cfpb_complaints)),
        ('zip_code', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE zip_code IS NULL), 
            (SELECT COUNT(DISTINCT zip_code) FROM raw.raw_cfpb_complaints)),
        ('tags', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE tags IS NULL), 
            (SELECT COUNT(DISTINCT tags) FROM raw.raw_cfpb_complaints)),
        ('submitted_via', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE submitted_via IS NULL), 
            (SELECT COUNT(DISTINCT submitted_via) FROM raw.raw_cfpb_complaints)),
        ('date_sent_to_company', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE date_sent_to_company IS NULL), 
            (SELECT COUNT(DISTINCT date_sent_to_company) FROM raw.raw_cfpb_complaints)),
        ('company_response_to_consumer', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE company_response_to_consumer IS NULL), 
            (SELECT COUNT(DISTINCT company_response_to_consumer) FROM raw.raw_cfpb_complaints)),
        ('timely_response', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE timely_response IS NULL), 
            (SELECT COUNT(DISTINCT timely_response) FROM raw.raw_cfpb_complaints)),
        ('complaint_id', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE complaint_id IS NULL), 
            (SELECT COUNT(DISTINCT complaint_id) FROM raw.raw_cfpb_complaints)),
        ('ingested_at', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE ingested_at IS NULL), 
            (SELECT COUNT(DISTINCT ingested_at) FROM raw.raw_cfpb_complaints)),
        ('source_system', 
            (SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE source_system IS NULL), 
            (SELECT COUNT(DISTINCT source_system) FROM raw.raw_cfpb_complaints))
) AS cols(col_name, null_count, distinct_count);
"""

# Queries to find the most common text values/phrases for the specified columns
# para macheck ano ba yung mga common issues that persist also what are the common responses from the company 
# chinecheck then what common tags are used to categorize the complaints
TOP_TEXT_SQL = {
    "issue": "SELECT issue, COUNT(*) as frequency FROM raw.raw_cfpb_complaints WHERE issue IS NOT NULL GROUP BY issue ORDER BY frequency DESC LIMIT 5;",
    "sub_issue": "SELECT sub_issue, COUNT(*) as frequency FROM raw.raw_cfpb_complaints WHERE sub_issue IS NOT NULL GROUP BY sub_issue ORDER BY frequency DESC LIMIT 5;",
    "company_public_response": "SELECT company_public_response, COUNT(*) as frequency FROM raw.raw_cfpb_complaints WHERE company_public_response IS NOT NULL GROUP BY company_public_response ORDER BY frequency DESC LIMIT 5;",
    "tags": "SELECT tags, COUNT(*) as frequency FROM raw.raw_cfpb_complaints WHERE tags IS NOT NULL GROUP BY tags ORDER BY frequency DESC LIMIT 5;"
}

def run_profiling():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    conn = psycopg2.connect(dbname=TARGET_DB, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT)

    print("Running dataset overview...")
    df_overview = pd.read_sql_query(OVERVIEW_SQL, conn)
    df_overview.to_csv(f"{OUTPUT_DIR}/01_dataset_overview.csv", index=False)
    print(df_overview.T)

    print("\nRunning column completeness...")
    df_cols = pd.read_sql_query(COLUMN_PROFILE_SQL, conn)
    df_cols.to_csv(f"{OUTPUT_DIR}/02_column_completeness.csv", index=False)
    print(df_cols.to_string(index=False))

    print("\nRunning common phrases for text columns...")
    for col_name, sql in TOP_TEXT_SQL.items():
        df_text = pd.read_sql_query(sql, conn)
        df_text.to_csv(f"{OUTPUT_DIR}/03_top_{col_name}.csv", index=False)
        print(f"\nTop 5 for {col_name}:")
        print(df_text.to_string(index=False))

    conn.close()
    print(f"\nAll reports saved to {OUTPUT_DIR}/")

if __name__ == "__main__":
    run_profiling()