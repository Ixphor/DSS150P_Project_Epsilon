"""
Census validation — runs after load_census.py.
Implements 5 automated data-quality checks:
  1. Schema/column presence
  2. Row count (expect 52: 50 states + DC + PR)
  3. Uniqueness (no duplicate state_fips)
  4. Accepted values (state_fips must be a valid 2-digit code, zero-padded)
  5. Range sanity (population/income must be positive, non-jam values)
"""
import logging
from src.utils.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = {
    "state_fips", "name", "total_population", "median_household_income",
    "poverty_population", "white_alone", "black_alone", "ingested_at",
}

EXPECTED_ROW_COUNT = 52  # 50 states + DC + Puerto Rico


def check_schema(cur) -> bool:
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'raw' AND table_name = 'raw_census_state';
    """)
    actual_cols = {row[0] for row in cur.fetchall()}
    missing = EXPECTED_COLUMNS - actual_cols
    if missing:
        logger.error("FAILED schema check — missing columns: %s", missing)
        return False
    logger.info("PASSED schema check — all expected columns present")
    return True


def check_row_count(cur) -> bool:
    cur.execute("SELECT COUNT(*) FROM raw.raw_census_state;")
    count = cur.fetchone()[0]
    if count != EXPECTED_ROW_COUNT:
        logger.warning("Row count is %d, expected %d — possible partial load", count, EXPECTED_ROW_COUNT)
        return False
    logger.info("PASSED row count check — %d rows", count)
    return True


def check_uniqueness(cur) -> bool:
    cur.execute("""
        SELECT state_fips, COUNT(*) FROM raw.raw_census_state
        GROUP BY state_fips HAVING COUNT(*) > 1;
    """)
    dupes = cur.fetchall()
    if dupes:
        logger.error("FAILED uniqueness check — duplicate state_fips: %s", dupes)
        return False
    logger.info("PASSED uniqueness check — no duplicate state_fips")
    return True


def check_accepted_values(cur) -> bool:
    cur.execute("""
        SELECT state_fips FROM raw.raw_census_state
        WHERE state_fips !~ '^[0-9]{2}$';
    """)
    bad = cur.fetchall()
    if bad:
        logger.error("FAILED accepted-values check — invalid state_fips codes: %s", bad)
        return False
    logger.info("PASSED accepted-values check — all state_fips are valid 2-digit codes")
    return True


def check_ranges(cur) -> bool:
    cur.execute("""
        SELECT state_fips, total_population, median_household_income
        FROM raw.raw_census_state
        WHERE total_population < 0 OR median_household_income < 0
           OR total_population IS NULL OR median_household_income IS NULL;
    """)
    bad = cur.fetchall()
    if bad:
        logger.warning("Range check found %d rows with null/negative population or income: %s", len(bad), bad)
        return False
    logger.info("PASSED range check — population and income are non-null and non-negative")
    return True


def run_validations():
    conn = get_connection()
    cur = conn.cursor()

    results = {
        "schema": check_schema(cur),
        "row_count": check_row_count(cur),
        "uniqueness": check_uniqueness(cur),
        "accepted_values": check_accepted_values(cur),
        "ranges": check_ranges(cur),
    }

    cur.close()
    conn.close()

    passed = sum(results.values())
    logger.info("Census validation summary: %d/%d checks passed", passed, len(results))

    if passed < len(results):
        logger.warning("One or more Census validation checks failed — review log above")

    return results


if __name__ == "__main__":
    run_validations()