import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv

# Force Python to read local environment variables (.env)
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("POSTGRES_USER", "airflow")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "airflow_pass")
TARGET_DB = os.getenv("TARGET_DB", "cfpb_pipeline")

VALIDATION_RULES = {
    "1_null_core_keys": "complaint_id IS NULL OR date_received IS NULL OR product IS NULL OR company IS NULL",
    "2_invalid_timely_enum": "timely_response NOT IN ('Yes', 'No') AND timely_response IS NOT NULL",
    "3_negative_sla_lag": "date_sent_to_company < date_received OR date_sent_to_company IS NULL",
    "4_invalid_zip_format": "zip_code !~ '^[0-9X]{5}$' AND zip_code IS NOT NULL AND zip_code != ''",
    "5_future_date_received": "date_received > CURRENT_DATE"
}

DUPLICATE_CHECK_SQL = """
SELECT COUNT(*) FROM (
    SELECT complaint_id
    FROM raw.raw_cfpb_complaints
    GROUP BY complaint_id
    HAVING COUNT(*) > 1
) AS duplicates;
"""

CREATE_SCHEMA_SQL = "CREATE SCHEMA IF NOT EXISTS staging;"

CREATE_STAGING_TABLE_SQL = """
DROP TABLE IF EXISTS staging.complaints;
CREATE TABLE staging.complaints AS
SELECT *
FROM raw.raw_cfpb_complaints
WHERE
    (complaint_id IS NOT NULL AND date_received IS NOT NULL AND product IS NOT NULL AND company IS NOT NULL)
    AND (timely_response IN ('Yes', 'No') OR timely_response IS NULL)
    AND (date_sent_to_company >= date_received)
    AND (zip_code ~ '^[0-9X]{5}$' OR zip_code IS NULL OR zip_code = '')
    AND (date_received <= CURRENT_DATE);

UPDATE staging.complaints
SET tags = 'No Tag'
WHERE tags IS NULL;
"""

def run_validations():
    print("Connecting to database to run validation checks...")
    conn = psycopg2.connect(dbname=TARGET_DB, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT)
    cur = conn.cursor()

    # Ensure staging schema exists before inserting tables
    cur.execute(CREATE_SCHEMA_SQL)

    cur.execute("SELECT COUNT(*) FROM raw.raw_cfpb_complaints;")
    total_raw = cur.fetchone()[0]
    print(f"Total raw records: {total_raw:,}\n")

    print("--- VALIDATION TEST RESULTS (DATA CLEANING SUMMARY) ---")
    failure_stats = []
    
    cur.execute(DUPLICATE_CHECK_SQL)
    duplicate_count = cur.fetchone()[0]
    failure_stats.append({"Rule": "0_duplicate_complaint_ids", "Failed Rows": duplicate_count})
    print(f"Failed 0_duplicate_complaint_ids: {duplicate_count:,} distinct IDs have duplicates")

    for rule_name, sql_condition in VALIDATION_RULES.items():
        query = f"SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE {sql_condition};"
        cur.execute(query)
        failed_count = cur.fetchone()[0]
        failure_stats.append({"Rule": rule_name, "Failed Rows": failed_count})
        print(f"Failed {rule_name}: {failed_count:,} rows filtered out")

    os.makedirs("outputs/validation", exist_ok=True)
    pd.DataFrame(failure_stats).to_csv("outputs/validation/validation_report.csv", index=False)
    print("\nValidation summary saved to 'outputs/validation/validation_report.csv'")
    
    print("\nApplying filters and creating staging.complaints table in Postgres...")
    cur.execute(CREATE_STAGING_TABLE_SQL)
    
    cur.execute("SELECT COUNT(*) FROM staging.complaints;")
    total_staged = cur.fetchone()[0]
    
    print(f"Successfully staged {total_staged:,} valid records.")
    print(f"Total quarantined (failed validation): {total_raw - total_staged:,} records.")
    
    # Export validated data to the data/staging folder
    print("\nExporting validated data to 'data/staging/staged_complaints.csv'...")
    os.makedirs("data/staging", exist_ok=True)
    
    # Use Postgres native COPY instead of pandas for massive datasets
    with open("data/staging/staged_complaints.csv", "w") as f:
        cur.copy_expert("COPY staging.complaints TO STDOUT WITH CSV HEADER", f)
        
    print("Clean data exported successfully!")

    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    run_validations()