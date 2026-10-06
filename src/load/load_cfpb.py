"""
CFPB BULK loader (bootstrap).

Loads data/raw/complaints.csv into raw.raw_cfpb_complaints with chunked COPY.

Rerun safety:
  * If the table already has rows, this step is SKIPPED (the incremental API loader
    owns the table from then on), so a daily DAG run never wipes API-loaded data.
  * The whole load is ONE transaction: a crash halfway leaves the table empty
    (rolled back), never half-loaded, so the next run simply retries the bootstrap.
  * --force truncates and reloads from the CSV.
"""
import argparse
import io
import logging
import time
from datetime import datetime, timezone

import pandas as pd

from src.load.cfpb_common import RAW_COLUMNS, ensure_table
from src.utils import config
from src.utils.db import ensure_database_exists, get_connection, scalar
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

# CSV header -> raw column
CSV_TO_RAW = {
    "Date received": "date_received",
    "Product": "product",
    "Sub-product": "sub_product",
    "Issue": "issue",
    "Sub-issue": "sub_issue",
    "Company public response": "company_public_response",
    "Company": "company",
    "State": "state",
    "ZIP code": "zip_code",
    "Tags": "tags",
    "Submitted via": "submitted_via",
    "Date sent to company": "date_sent_to_company",
    "Company response to consumer": "company_response_to_consumer",
    "Timely response?": "timely_response",
    "Complaint ID": "complaint_id",
}

COPY_SQL = (
    f"COPY raw.raw_cfpb_complaints ({', '.join(RAW_COLUMNS)}) "
    "FROM STDIN WITH (FORMAT csv, NULL '')"
)


def load_bulk(csv_path=None, force: bool = False, min_date: str = None, batch_size: int = 100_000) -> int:
    csv_path = csv_path or config.CFPB_BULK_CSV
    min_date = min_date or config.CFPB_BULK_MIN_DATE
    if not csv_path.exists():
        raise FileNotFoundError(f"Bulk CSV not found at {csv_path} - run extract_cfpb_bulk first")

    ensure_database_exists()
    conn = get_connection()
    try:
        ensure_table(conn)
        cur = conn.cursor()

        existing = scalar(cur, "SELECT COUNT(*) FROM raw.raw_cfpb_complaints;")
        if existing and not force:
            logger.info("raw.raw_cfpb_complaints already has %s rows - skipping bulk bootstrap (use --force to reload)", f"{existing:,}")
            return 0
        if force and existing:
            logger.warning("--force: truncating %s existing rows", f"{existing:,}")
            cur.execute("TRUNCATE TABLE raw.raw_cfpb_complaints;")

        batch_id = "bulk_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        min_ts = pd.to_datetime(min_date) if min_date else None
        if min_ts is not None:
            logger.info("Demo slice: only loading complaints received on/after %s", min_date)

        total_rows, start = 0, time.time()
        usecols = list(CSV_TO_RAW.keys())
        for n, chunk in enumerate(pd.read_csv(csv_path, chunksize=batch_size, dtype=str, usecols=usecols), start=1):
            chunk = chunk.rename(columns=CSV_TO_RAW).dropna(subset=["complaint_id"])
            if min_ts is not None:
                chunk = chunk[pd.to_datetime(chunk["date_received"], errors="coerce") >= min_ts]
            if chunk.empty:
                continue
            chunk["source_system"] = "cfpb_bulk_csv"
            chunk["batch_id"] = batch_id

            buffer = io.StringIO()
            chunk[RAW_COLUMNS].to_csv(buffer, index=False, header=False)
            buffer.seek(0)
            cur.copy_expert(COPY_SQL, buffer)

            total_rows += len(chunk)
            logger.info("[chunk %03d] +%s rows | total %s | %.0fs elapsed", n, f"{len(chunk):,}", f"{total_rows:,}", time.time() - start)

        conn.commit()  # single commit: all-or-nothing bootstrap
        cur.execute("ANALYZE raw.raw_cfpb_complaints;")
        conn.commit()
        logger.info("Bulk load finished: %s rows in %.0fs (batch %s)", f"{total_rows:,}", time.time() - start, batch_id)
        return total_rows
    except Exception:
        conn.rollback()
        logger.exception("Bulk load failed - transaction rolled back, table left unchanged")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="?", help="path to complaints.csv (default: data/raw/complaints.csv)")
    parser.add_argument("--force", action="store_true", help="truncate and reload from the CSV")
    parser.add_argument("--min-date", help="only load complaints on/after YYYY-MM-DD (demo slice)")
    args = parser.parse_args()
    from pathlib import Path
    load_bulk(Path(args.csv) if args.csv else None, force=args.force, min_date=args.min_date)
