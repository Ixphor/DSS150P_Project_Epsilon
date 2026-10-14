"""
Pipeline row-count snapshot, used to prove that a repeat run creates no duplicates.

    python -m src.validation.pipeline_summary --label before_second_run
    # ... trigger the DAG again ...
    python -m src.validation.pipeline_summary --label after_second_run

Each call prints a table, appends the snapshot to outputs/validation/pipeline_summary_history.csv,
and shows the change versus the previous snapshot. Exit code 1 if any table has duplicate keys.
"""
import argparse
import logging
import sys
from datetime import datetime, timezone

import pandas as pd

from src.utils import config
from src.utils.db import get_connection
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

HISTORY_FILE = config.VALIDATION_DIR / "pipeline_summary_history.csv"

# (layer, table, key column or None). A key column also gives a duplicate check.
TABLES = [
    ("raw", "raw.raw_cfpb_complaints", "complaint_id"),
    ("raw", "raw.raw_fdic_institutions", "cert"),
    ("raw", "raw.raw_census_state", "state_fips"),
    ("staging", "staging.complaints", "complaint_id"),
    ("staging", "staging.complaints_rejected", "complaint_id"),
    ("staging", "staging.fdic_institutions", "cert"),
    ("staging", "staging.census_state", "state_fips"),
    ("curated", "curated.dim_company", "company_id"),
    ("curated", "curated.dim_product", "product_id"),
    ("curated", "curated.dim_issue", "issue_id"),
    ("curated", "curated.dim_geography", "state_fips"),
    ("curated", "curated.dim_institution", "cert"),
    ("curated", "curated.bridge_company_institution", "company_id"),
    ("curated", "curated.fact_complaints", "complaint_id"),
    ("curated", "curated.mart_complaints_monthly", None),
    ("curated", "curated.mart_institution_scorecard", None),
]


def snapshot(label: str) -> pd.DataFrame:
    """Counts rows (and distinct keys) for every table. A missing table is reported, not fatal."""
    taken_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    conn = get_connection()
    try:
        for layer, table, key in TABLES:
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) FROM {table};")
                    total = cur.fetchone()[0]
                    distinct = None
                    if key:
                        cur.execute(f"SELECT COUNT(DISTINCT {key}) FROM {table};")
                        distinct = cur.fetchone()[0]
            except Exception as exc:  # table not built yet
                conn.rollback()
                logger.warning("Could not read %s: %s", table, str(exc).splitlines()[0])
                total, distinct = None, None
            rows.append(
                {
                    "label": label,
                    "taken_at_utc": taken_at,
                    "layer": layer,
                    "table": table,
                    "row_count": total,
                    "distinct_keys": distinct,
                    "has_duplicates": (distinct is not None and total is not None and total != distinct),
                }
            )
    finally:
        conn.close()
    return pd.DataFrame(rows)


def with_delta(current: pd.DataFrame) -> pd.DataFrame:
    """Adds the row-count change versus the most recent earlier snapshot, if there is one."""
    current = current.copy()
    current["change_vs_previous"] = pd.NA
    if HISTORY_FILE.exists():
        history = pd.read_csv(HISTORY_FILE)
        if not history.empty:
            last = history[history["taken_at_utc"] == history["taken_at_utc"].max()].set_index("table")["row_count"]
            current["change_vs_previous"] = current["table"].map(lambda t: current.set_index("table").at[t, "row_count"] - last.get(t, float("nan")))
    return current


def main(label: str) -> int:
    current = with_delta(snapshot(label))
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    current.drop(columns=["change_vs_previous"]).to_csv(HISTORY_FILE, mode="a", header=not HISTORY_FILE.exists(), index=False)
    print(current[["layer", "table", "row_count", "distinct_keys", "has_duplicates", "change_vs_previous"]].to_string(index=False))
    print(f"\nSnapshot '{label}' appended to {HISTORY_FILE}")
    duplicated = current[current["has_duplicates"]]
    if not duplicated.empty:
        print("DUPLICATE KEYS FOUND in: " + ", ".join(duplicated["table"]))
        return 1
    print("No duplicate keys in any table.")
    return 0


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Row-count snapshot for before/after repeat-run evidence.")
    parser.add_argument("--label", default="snapshot", help="Name for this snapshot, e.g. before_second_run")
    sys.exit(main(parser.parse_args().label))