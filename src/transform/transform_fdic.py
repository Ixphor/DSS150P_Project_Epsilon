import logging
from src.utils.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

ENRICH_FDIC_SQL = """
-- 1. Ensure curated schema exists
CREATE SCHEMA IF NOT EXISTS curated;

-- 2. Create dim_fdic_institution table
CREATE TABLE IF NOT EXISTS curated.dim_fdic_institution (
    cert INT PRIMARY KEY,
    institution_name TEXT,
    clean_name TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    total_assets_k_usd BIGINT,
    asset_tier TEXT,
    charter_type TEXT,
    is_active BOOLEAN
);

-- 3. Upsert dim_fdic_institution without dropping or truncating linked tables
INSERT INTO curated.dim_fdic_institution (
    cert, institution_name, clean_name, city, state, zip_code,
    total_assets_k_usd, asset_tier, charter_type, is_active
)
SELECT
    cert,
    name,
    UPPER(REGEXP_REPLACE(name, '[^a-zA-Z0-9 ]', '', 'g')) AS clean_name,
    city,
    state,
    zip AS zip_code,
    asset AS total_assets_k_usd,
    CASE
        WHEN asset >= 250000000 THEN 'Mega Bank ($250B+)'
        WHEN asset >= 10000000 THEN 'Large Regional ($10B-$250B)'
        WHEN asset >= 1000000 THEN 'Regional ($1B-$10B)'
        ELSE 'Community Bank (<$1B)'
    END AS asset_tier,
    charter AS charter_type,
    (active = 1) AS is_active
FROM raw.raw_fdic_institutions
ON CONFLICT (cert) DO UPDATE SET
    institution_name = EXCLUDED.institution_name,
    clean_name = EXCLUDED.clean_name,
    city = EXCLUDED.city,
    state = EXCLUDED.state,
    zip_code = EXCLUDED.zip_code,
    total_assets_k_usd = EXCLUDED.total_assets_k_usd,
    asset_tier = EXCLUDED.asset_tier,
    charter_type = EXCLUDED.charter_type,
    is_active = EXCLUDED.is_active;

-- 4. Add fdic_cert Foreign Key and asset_tier to dim_company
ALTER TABLE curated.dim_company
    ADD COLUMN IF NOT EXISTS fdic_cert INT REFERENCES curated.dim_fdic_institution(cert),
    ADD COLUMN IF NOT EXISTS asset_tier TEXT;

-- 5. Link dim_company to dim_fdic_institution using cleaned name matching
UPDATE curated.dim_company dc
SET 
    fdic_cert = dfi.cert,
    asset_tier = dfi.asset_tier
FROM curated.dim_fdic_institution dfi
WHERE UPPER(REGEXP_REPLACE(dc.company_name, '[^a-zA-Z0-9 ]', '', 'g')) = dfi.clean_name
  AND dc.fdic_cert IS NULL;
"""

def transform_fdic_data():
    logging.info("Building curated.dim_fdic_institution and linking to curated.dim_company...")
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(ENRICH_FDIC_SQL)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM curated.dim_fdic_institution;")
    fdic_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM curated.dim_company WHERE fdic_cert IS NOT NULL;")
    matched_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM curated.dim_company;")
    total_companies = cur.fetchone()[0]

    logging.info(f"dim_fdic_institution rows: {fdic_count:,}")
    logging.info(f"Matched {matched_count:,} / {total_companies:,} companies in dim_company to FDIC records.")

    cur.close()
    conn.close()

if __name__ == "__main__":
    transform_fdic_data()