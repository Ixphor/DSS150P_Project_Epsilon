"""
Staging runner: raw -> staging for one source.

    python -m src.transform.stage cfpb|fdic|census

Each source's SQL lives in sql/staging/stage_<source>.sql and runs as one transaction.
After the build, row counts are logged and reconciled against the raw layer.
"""
import argparse
import logging

from src.utils import config
from src.utils.db import get_connection, run_sql_file, scalar
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

STAGING_SQL = config.SQL_DIR / "staging"
REFERENCE_SQL = config.SQL_DIR / "reference" / "state_fips_seed.sql"


def prepare(conn) -> None:
    """Shared prerequisites (idempotent): helper functions and the state/FIPS reference table."""
    run_sql_file(STAGING_SQL / "00_functions.sql", conn)
    run_sql_file(REFERENCE_SQL, conn)
    conn.commit()


def stage_cfpb(conn) -> None:
    run_sql_file(STAGING_SQL / "stage_cfpb.sql", conn)
    conn.commit()
    with conn.cursor() as cur:
        raw = scalar(cur, "SELECT COUNT(*) FROM raw.raw_cfpb_complaints;")
        staged = scalar(cur, "SELECT COUNT(*) FROM staging.complaints;")
        rejected = scalar(cur, "SELECT COUNT(*) FROM staging.complaints_rejected;")
        cur.execute("SELECT reject_reason, COUNT(*) FROM staging.complaints_rejected GROUP BY 1 ORDER BY 2 DESC;")
        reasons = cur.fetchall()
    logger.info("CFPB staging: raw=%s staged=%s quarantined=%s", f"{raw:,}", f"{staged:,}", f"{rejected:,}")
    for reason, n in reasons:
        logger.info("  quarantined %s: %s", reason, f"{n:,}")
    if staged + rejected != raw:  # reconciliation: every raw row must land in exactly one place
        raise RuntimeError(f"Row reconciliation failed: staged({staged}) + rejected({rejected}) != raw({raw})")


def stage_fdic(conn) -> None:
    run_sql_file(STAGING_SQL / "stage_fdic.sql", conn)
    conn.commit()
    with conn.cursor() as cur:
        raw = scalar(cur, "SELECT COUNT(*) FROM raw.raw_fdic_institutions WHERE active = 1;")
        staged = scalar(cur, "SELECT COUNT(*) FROM staging.fdic_institutions;")
        missing_asset = scalar(cur, "SELECT COUNT(*) FROM staging.fdic_institutions WHERE asset_missing;")
    logger.info("FDIC staging: raw active=%s staged=%s (asset unknown: %s)", f"{raw:,}", f"{staged:,}", missing_asset)
    if staged != raw:
        raise RuntimeError(f"Row reconciliation failed: staged({staged}) != raw active({raw})")


def stage_census(conn) -> None:
    run_sql_file(STAGING_SQL / "stage_census.sql", conn)
    conn.commit()
    with conn.cursor() as cur:
        raw = scalar(cur, "SELECT COUNT(*) FROM raw.raw_census_state;")
        staged = scalar(cur, "SELECT COUNT(*) FROM staging.census_state;")
        no_abbr = scalar(cur, "SELECT COUNT(*) FROM staging.census_state WHERE state_abbr IS NULL;")
    logger.info("Census staging: raw=%d staged=%d (without state abbreviation: %d)", raw, staged, no_abbr)
    if staged != raw:
        raise RuntimeError(f"Row reconciliation failed: staged({staged}) != raw({raw})")


STAGERS = {"cfpb": stage_cfpb, "fdic": stage_fdic, "census": stage_census}


def main(source: str) -> None:
    conn = get_connection()
    try:
        prepare(conn)
        STAGERS[source](conn)
    except Exception:
        conn.rollback()
        logger.exception("Staging %s failed", source)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=sorted(STAGERS))
    main(parser.parse_args().source)
