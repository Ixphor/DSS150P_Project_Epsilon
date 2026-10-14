"""
CFPB validation against raw.raw_cfpb_complaints (bulk + API rows together).

One table scan computes every rule. Rules marked error fail the task when more than
MAX_REJECT_PCT of rows break them; rows that break the quarantine rules are excluded
from staging by src.transform.stage (and kept in staging.complaints_rejected).
"""
import logging

from src.utils import config
from src.utils.db import get_connection
from src.utils.logging_config import setup_logging
from src.validation.common import CheckResult, enforce, write_report
from src.validation.contracts import load_rules

logger = logging.getLogger(__name__)

TOL = config.MAX_REJECT_PCT

# name -> (severity, tolerated %, SQL condition that identifies a FAILING row)
RULES = load_rules("cfpb_complaints")


def build_checks(cur) -> list:
    selects = ",\n  ".join(f"COUNT(*) FILTER (WHERE {cond}) AS \"{name}\"" for name, (_, _, cond) in RULES.items())
    cur.execute(
        f"SELECT COUNT(*) AS total, COUNT(DISTINCT complaint_id) AS uniq, MAX(date_received) AS max_date,\n  {selects}\n"
        "FROM raw.raw_cfpb_complaints;"
    )
    cols = [d[0] for d in cur.description]
    row = dict(zip(cols, cur.fetchone()))
    total = row["total"]

    results = [
        CheckResult("table_not_empty", 1 if total == 0 else 0, 1, detail=f"rows={total:,}"),
        CheckResult("duplicate_complaint_ids", total - row["uniq"], total),
    ]
    for name, (severity, tol, _) in RULES.items():
        results.append(CheckResult(name, row[name], total, severity=severity, max_fail_pct=tol))

    cur.execute("SELECT (CURRENT_DATE - %s::date) > 14;", (row["max_date"],))
    stale = bool(cur.fetchone()[0]) if row["max_date"] else True
    results.append(CheckResult("freshness_within_14_days", int(stale), 1, severity="warn", detail=f"latest date_received={row['max_date']}"))
    return results


def run_validations():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            results = build_checks(cur)
    finally:
        conn.close()
    write_report(results, config.VALIDATION_DIR / "validation_report.csv")
    enforce(results, "CFPB")
    return results


if __name__ == "__main__":
    setup_logging()
    run_validations()
