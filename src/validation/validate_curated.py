"""
Curated-layer validation (runs after build_curated). Gates the end of the pipeline.

Checks: row reconciliation with staging, no negative response lag, date range sanity, geography
dimension size, state match rate, and that the FDIC crosswalk matched at least some institutions.
(Referential integrity is additionally enforced by FOREIGN KEY constraints in the database.)
"""
import logging

from src.utils import config
from src.utils.db import get_connection, scalar
from src.utils.logging_config import setup_logging
from src.validation.common import CheckResult, enforce, write_report

logger = logging.getLogger(__name__)

MIN_STATE_MATCH_PCT = 95.0


def build_checks(cur) -> list:
    fact = scalar(cur, "SELECT COUNT(*) FROM curated.fact_complaints;")
    staged = scalar(cur, "SELECT COUNT(*) FROM staging.complaints;")
    neg_lag = scalar(cur, "SELECT COUNT(*) FROM curated.fact_complaints WHERE response_lag_days < 0;")
    bad_dates = scalar(
        cur,
        "SELECT COUNT(*) FROM curated.fact_complaints WHERE date_received < DATE '2011-12-01' OR date_received > CURRENT_DATE;",
    )
    geo = scalar(cur, "SELECT COUNT(*) FROM curated.dim_geography;")
    no_state = scalar(cur, "SELECT COUNT(*) FROM curated.fact_complaints WHERE state_fips IS NULL;")
    matched = scalar(cur, "SELECT COUNT(*) FROM curated.fact_complaints WHERE institution_cert IS NOT NULL;")
    orphans = scalar(
        cur,
        "SELECT COUNT(*) FROM curated.fact_complaints f LEFT JOIN curated.dim_company c USING (company_id) WHERE c.company_id IS NULL;",
    )
    dup_ids = fact - scalar(cur, "SELECT COUNT(DISTINCT complaint_id) FROM curated.fact_complaints;")

    return [
        CheckResult("fact_matches_staging_rowcount", abs(fact - staged), max(staged, 1), detail=f"fact={fact:,} staged={staged:,}"),
        CheckResult("unique_complaint_id", dup_ids, fact),
        CheckResult("no_orphan_company_keys", orphans, fact),
        CheckResult("response_lag_non_negative", neg_lag, fact),
        CheckResult("date_received_in_valid_range", bad_dates, fact),
        CheckResult("dim_geography_has_52_states", 0 if geo == 52 else 1, 1, detail=f"rows={geo}"),
        CheckResult(
            "state_match_rate", no_state, fact, severity="error", max_fail_pct=100.0 - MIN_STATE_MATCH_PCT,
            detail=f"unmatched states tolerated up to {100.0 - MIN_STATE_MATCH_PCT:.0f}%",
        ),
        CheckResult("fdic_crosswalk_matched_some", 0 if matched > 0 else 1, 1, detail=f"matched_complaints={matched:,}"),
    ]


def run_validations():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            results = build_checks(cur)
    finally:
        conn.close()
    write_report(results, config.VALIDATION_DIR / "curated_validation_report.csv")
    enforce(results, "Curated")
    return results


if __name__ == "__main__":
    setup_logging()
    run_validations()
