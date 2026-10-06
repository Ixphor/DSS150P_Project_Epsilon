"""
Curated builder: staging -> curated star schema (CFPB facts + Census geography + FDIC institutions).

    python -m src.transform.build_curated

Runs sql/curated/build_curated.sql as ONE transaction, then reports row counts and how well the
three sources integrated (state match rate, FDIC institution match rate).
"""
import logging

from src.utils import config
from src.utils.db import get_connection, run_sql_file, scalar
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


def build() -> dict:
    conn = get_connection()
    try:
        # helper functions must exist (cheap and idempotent)
        run_sql_file(config.SQL_DIR / "staging" / "00_functions.sql", conn)
        logger.info("Building curated star schema (this takes a few minutes on the full 18M rows)...")
        run_sql_file(config.SQL_DIR / "curated" / "build_curated.sql", conn)
        conn.commit()

        stats = {}
        with conn.cursor() as cur:
            for table in ("fact_complaints", "dim_company", "dim_product", "dim_issue", "dim_geography", "dim_institution", "bridge_company_institution"):
                stats[table] = scalar(cur, f"SELECT COUNT(*) FROM curated.{table};")
            staged = scalar(cur, "SELECT COUNT(*) FROM staging.complaints;")
            with_state = scalar(cur, "SELECT COUNT(*) FROM curated.fact_complaints WHERE state_fips IS NOT NULL;")
            with_inst = scalar(cur, "SELECT COUNT(*) FROM curated.fact_complaints WHERE institution_cert IS NOT NULL;")
            matched_companies = stats["bridge_company_institution"]

        for table, n in stats.items():
            logger.info("curated.%s: %s rows", table, f"{n:,}")
        if stats["fact_complaints"] != staged:
            raise RuntimeError(f"Fact row count {stats['fact_complaints']} != staged complaints {staged}")
        total = stats["fact_complaints"] or 1
        logger.info("Integration - Census state match: %s / %s complaints (%.1f%%)", f"{with_state:,}", f"{total:,}", 100.0 * with_state / total)
        logger.info("Integration - FDIC institution match: %s / %s complaints (%.1f%%), %d of %d companies",
                    f"{with_inst:,}", f"{total:,}", 100.0 * with_inst / total, matched_companies, stats["dim_company"])
        return stats
    except Exception:
        conn.rollback()
        logger.exception("Curated build failed - transaction rolled back, previous curated tables untouched")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    setup_logging()
    build()
