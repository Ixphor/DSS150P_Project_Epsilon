import os
from src.utils.db import get_connection

TRANSFORM_SQL = """
CREATE SCHEMA IF NOT EXISTS curated;

-- 1. Create Dimension: dim_company
DROP TABLE IF EXISTS curated.dim_company CASCADE;
CREATE TABLE curated.dim_company (
    company_id SERIAL PRIMARY KEY,
    company_name TEXT UNIQUE
);
INSERT INTO curated.dim_company (company_name)
SELECT DISTINCT company FROM staging.complaints WHERE company IS NOT NULL;

-- 2. Create Dimension: dim_product
DROP TABLE IF EXISTS curated.dim_product CASCADE;
CREATE TABLE curated.dim_product (
    product_id SERIAL PRIMARY KEY,
    product_name TEXT,
    sub_product_name TEXT,
    UNIQUE (product_name, sub_product_name)
);
INSERT INTO curated.dim_product (product_name, sub_product_name)
SELECT DISTINCT product, sub_product FROM staging.complaints WHERE product IS NOT NULL;

-- 3. Create Dimension: dim_issue
DROP TABLE IF EXISTS curated.dim_issue CASCADE;
CREATE TABLE curated.dim_issue (
    issue_id SERIAL PRIMARY KEY,
    issue_name TEXT,
    sub_issue TEXT,
    UNIQUE (issue_name, sub_issue)
);
INSERT INTO curated.dim_issue (issue_name, sub_issue)
SELECT DISTINCT issue, sub_issue FROM staging.complaints WHERE issue IS NOT NULL;

-- 4. Create Fact Table: fact_complaints
DROP TABLE IF EXISTS curated.fact_complaints CASCADE;
CREATE TABLE curated.fact_complaints (
    complaint_id TEXT PRIMARY KEY,
    company_id INT REFERENCES curated.dim_company(company_id),
    product_id INT REFERENCES curated.dim_product(product_id),
    issue_id INT REFERENCES curated.dim_issue(issue_id),
    date_received DATE,
    date_sent_to_company DATE,
    state TEXT,
    zip_code TEXT,
    tags TEXT,
    submitted_via TEXT,
    company_public_response TEXT,
    company_response_to_consumer TEXT,
    timely_response TEXT,
    ingested_at TIMESTAMP
);

INSERT INTO curated.fact_complaints (
    complaint_id, company_id, product_id, issue_id,
    date_received, date_sent_to_company, state, zip_code, tags,
    submitted_via, company_public_response, company_response_to_consumer,
    timely_response, ingested_at
)
SELECT
    s.complaint_id,
    c.company_id,
    p.product_id,
    i.issue_id,
    s.date_received::DATE,
    s.date_sent_to_company::DATE,
    s.state,
    s.zip_code,
    s.tags,
    s.submitted_via,
    s.company_public_response,
    s.company_response_to_consumer,
    s.timely_response,
    s.ingested_at::TIMESTAMP
FROM staging.complaints s
LEFT JOIN curated.dim_company c
    ON s.company = c.company_name
LEFT JOIN curated.dim_product p
    ON s.product = p.product_name AND s.sub_product IS NOT DISTINCT FROM p.sub_product_name
LEFT JOIN curated.dim_issue i
    ON s.issue = i.issue_name AND s.sub_issue IS NOT DISTINCT FROM i.sub_issue;
"""

def run_transformation():
    print("Connecting to database to build Star Schema...")
    conn = get_connection()
    cur = conn.cursor()

    print("Executing transformations in PostgreSQL (This may take 1-3 minutes for 18M rows)...")
    cur.execute(TRANSFORM_SQL)

    cur.execute("SELECT COUNT(*) FROM curated.fact_complaints;")
    fact_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM curated.dim_company;")
    company_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM curated.dim_product;")
    product_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM curated.dim_issue;")
    issue_count = cur.fetchone()[0]

    print("\nStar Schema built successfully in the 'curated' layer!")
    print(f"Fact Table (fact_complaints): {fact_count:,} rows")
    print(f"Dimension (dim_company): {company_count:,} unique companies")
    print(f"Dimension (dim_product): {product_count:,} unique product hierarchies")
    print(f"Dimension (dim_issue): {issue_count:,} unique issue hierarchies")

    print("\nExporting Star Schema to 'data/curated/'...")
    os.makedirs("data/curated", exist_ok=True)

    tables_to_export = ["dim_company", "dim_product", "dim_issue", "fact_complaints"]

    for table in tables_to_export:
        file_path = f"data/curated/{table}.csv"
        with open(file_path, "w") as f:
            cur.copy_expert(f"COPY curated.{table} TO STDOUT WITH CSV HEADER", f)
        print(f"Exported curated.{table} -> {file_path}")

    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    run_transformation()