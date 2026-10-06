"""
Mart validation (runs after build_mart): the data products must reconcile with the fact table.
"""
import logging

from src.utils import config
from src.utils.db import get_connection, scalar
from src.utils.logging_config import setup_logging
from src.validation.common import CheckResult, enforce, write_report

logger = logging.getLogger(__name__)


def build_checks(cur) -> list:
    fact = scalar(cur, "SELECT COUNT(*) FROM curated.fact_complaints;")
    fact_matched = scalar(cur, "SELECT COUNT(*) FROM curated.fact_complaints WHERE institution_cert IS NOT NULL;")
    monthly_rows = scalar(cur, "SELECT COUNT(*) FROM curated.mart_complaints_monthly;")
    monthly_sum = int(scalar(cur, "SELECT COALESCE(SUM(complaints), 0) FROM curated.mart_complaints_monthly;"))
    score_rows = scalar(cur, "SELECT COUNT(*) FROM curated.mart_institution_scorecard;")
    score_sum = int(scalar(cur, "SELECT COALESCE(SUM(complaints), 0) FROM curated.mart_institution_scorecard;"))
    bad_pct = scalar(cur, "SELECT COUNT(*) FROM curated.mart_complaints_monthly WHERE timely_pct < 0 OR timely_pct > 100;")
    bad_counts = scalar(
        cur,
        "SELECT COUNT(*) FROM curated.mart_complaints_monthly WHERE complaints <= 0 OR timely_complaints > complaints;",
    )
    bad_ratio = scalar(cur, "SELECT COUNT(*) FROM curated.mart_institution_scorecard WHERE complaints_per_billion_assets < 0;")

    return [
        CheckResult("marts_not_empty", 0 if (monthly_rows > 0 and score_rows > 0) else 1, 1, detail=f"monthly={monthly_rows:,} scorecard={score_rows:,}"),
        CheckResult("monthly_mart_sums_to_fact", abs(monthly_sum - fact), max(fact, 1), detail=f"mart={monthly_sum:,} fact={fact:,}"),
        CheckResult("scorecard_sums_to_matched_complaints", abs(score_sum - fact_matched), max(fact_matched, 1), detail=f"mart={score_sum:,} fact_matched={fact_matched:,}"),
        CheckResult("timely_pct_between_0_and_100", bad_pct, max(monthly_rows, 1)),
        CheckResult("counts_internally_consistent", bad_counts, max(monthly_rows, 1)),
        CheckResult("complaints_per_billion_assets_non_negative", bad_ratio, max(score_rows, 1)),
    ]


def run_validations():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            results = build_checks(cur)
    finally:
        conn.close()
    write_report(results, config.VALIDATION_DIR / "mart_validation_report.csv")
    enforce(results, "Mart")
    return results


if __name__ == "__main__":
    setup_logging()
    run_validations()