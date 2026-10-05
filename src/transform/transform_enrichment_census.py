from src.utils.db import get_connection

CREATE_DIM_SQL = """
CREATE SCHEMA IF NOT EXISTS curated;

DROP TABLE IF EXISTS curated.dim_geography CASCADE;
CREATE TABLE curated.dim_geography (
    state_fips               TEXT PRIMARY KEY,
    state_abbr                TEXT,
    name                       TEXT,
    total_population          NUMERIC,
    median_household_income   NUMERIC,
    poverty_population        NUMERIC,
    white_alone                NUMERIC,
    black_alone                 NUMERIC
);

INSERT INTO curated.dim_geography
    (state_fips, state_abbr, name, total_population, median_household_income,
     poverty_population, white_alone, black_alone)
SELECT
    rc.state_fips,
    sm.state_abbr,
    rc.name,
    rc.total_population,
    rc.median_household_income,
    rc.poverty_population,
    rc.white_alone,
    rc.black_alone
FROM raw.raw_census_state rc
LEFT JOIN curated.state_abbr_fips_map sm
    ON rc.state_fips = sm.state_fips;
"""

ADD_FK_SQL = """
ALTER TABLE curated.fact_complaints
    ADD COLUMN IF NOT EXISTS state_fips TEXT REFERENCES curated.dim_geography(state_fips);
"""

BACKFILL_SQL = """
UPDATE curated.fact_complaints fc
SET state_fips = sm.state_fips
FROM curated.state_abbr_fips_map sm
WHERE fc.state = sm.state_abbr
  AND fc.state_fips IS NULL;
"""


def run_transformation():
    conn = get_connection()
    cur = conn.cursor()

    print("Building curated.dim_geography...")
    cur.execute(CREATE_DIM_SQL)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM curated.dim_geography;")
    geo_count = cur.fetchone()[0]
    print(f"dim_geography built: {geo_count} rows")

    print("Adding state_fips FK column to fact_complaints (if missing)...")
    cur.execute(ADD_FK_SQL)
    conn.commit()

    print("Backfilling fact_complaints.state_fips via abbreviation match...")
    cur.execute(BACKFILL_SQL)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM curated.fact_complaints WHERE state_fips IS NOT NULL;")
    matched = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM curated.fact_complaints;")
    total = cur.fetchone()[0]
    print(f"Matched {matched:,} / {total:,} fact_complaints rows to a state ({matched/total:.1%})")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run_transformation()