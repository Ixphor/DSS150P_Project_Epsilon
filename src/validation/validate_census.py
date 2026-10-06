"""
Census validation (runs after load_census). Five automated checks:
  1 schema, 2 row count, 3 uniqueness, 4 accepted values, 5 range sanity.
Raises ValidationError on failure so the Airflow task (and everything downstream) stops.
"""
import logging

from src.utils import config
from src.utils.db import get_connection, scalar
from src.utils.logging_config import setup_logging
from src.validation.common import CheckResult, enforce, write_report

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = {
    "state_fips", "name", "total_population", "median_household_income",
    "poverty_population", "white_alone", "black_alone", "ingested_at",
}
EXPECTED_ROW_COUNT = 52  # 50 states + DC + Puerto Rico


def build_checks(cur) -> list:
    total = scalar(cur, "SELECT COUNT(*) FROM raw.raw_census_state;")

    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND table_name = 'raw_census_state';"
    )
    missing = EXPECTED_COLUMNS - {r[0] for r in cur.fetchall()}

    dupes = scalar(cur, "SELECT COUNT(*) FROM (SELECT state_fips FROM raw.raw_census_state GROUP BY 1 HAVING COUNT(*) > 1) d;")
    bad_codes = scalar(cur, "SELECT COUNT(*) FROM raw.raw_census_state WHERE state_fips !~ '^[0-9]{2}$';")
    bad_ranges = scalar(
        cur,
        "SELECT COUNT(*) FROM raw.raw_census_state WHERE total_population IS NULL OR median_household_income IS NULL "
        "OR total_population <= 0 OR median_household_income <= 0;",
    )

    return [
        CheckResult("schema_columns_present", len(missing), len(EXPECTED_COLUMNS), detail=f"missing={sorted(missing)}" if missing else ""),
        CheckResult("row_count_is_52", 0 if total == EXPECTED_ROW_COUNT else 1, 1, detail=f"actual={total}"),
        CheckResult("unique_state_fips", dupes, total),
        CheckResult("valid_fips_format", bad_codes, total),
        CheckResult("population_income_positive", bad_ranges, total),
    ]


def run_validations():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            results = build_checks(cur)
    finally:
        conn.close()
    write_report(results, config.VALIDATION_DIR / "census_validation_report.csv")
    enforce(results, "Census")
    return results


if __name__ == "__main__":
    setup_logging()
    run_validations()
