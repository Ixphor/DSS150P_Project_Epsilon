"""
CFPB API loader (incremental).

Reads the newest data/raw/cfpb_api/cfpb_api_*.json, maps API field names to the raw
table's columns and UPSERTs on complaint_id. Idempotent: running it twice on the same
file inserts nothing new; overlap with already-loaded complaints just refreshes them.
"""
import argparse
import glob
import logging
from datetime import date
from pathlib import Path
from typing import Optional

import ijson
from psycopg2.extras import execute_values

from src.load.cfpb_common import RAW_COLUMNS, ensure_table
from src.utils import config
from src.utils.db import ensure_database_exists, get_connection, scalar
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

UPSERT_SQL = f"""
INSERT INTO raw.raw_cfpb_complaints ({', '.join(RAW_COLUMNS)})
VALUES %s
ON CONFLICT (complaint_id) DO UPDATE SET
    {', '.join(f'{c} = EXCLUDED.{c}' for c in RAW_COLUMNS if c != 'complaint_id')},
    ingested_at = NOW()
RETURNING (xmax = 0) AS inserted;
"""


def latest_raw_file() -> Path:
    files = sorted(glob.glob(str(config.CFPB_API_RAW_DIR / "cfpb_api_*.json")))
    if not files:
        raise FileNotFoundError(f"No CFPB API raw files in {config.CFPB_API_RAW_DIR}. Run extract_cfpb_api first.")
    logger.info("Using latest raw file: %s", files[-1])
    return Path(files[-1])


def _text(value) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _date(value) -> Optional[date]:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])  # API dates look like 2026-09-27T12:00:00-05:00
    except ValueError:
        return None


def normalize_record(rec: dict, batch_id: str) -> Optional[tuple]:
    """Maps one API record to a raw-table row (order = RAW_COLUMNS). None if it has no usable ID."""
    try:
        complaint_id = int(rec["complaint_id"])
    except (KeyError, TypeError, ValueError):
        return None
    return (
        _date(rec.get("date_received")),
        _text(rec.get("product")),
        _text(rec.get("sub_product")),
        _text(rec.get("issue")),
        _text(rec.get("sub_issue")),
        _text(rec.get("company_public_response")),
        _text(rec.get("company")),
        _text(rec.get("state")),
        _text(rec.get("zip_code")),
        _text(rec.get("tags")),
        _text(rec.get("submitted_via")),
        _date(rec.get("date_sent_to_company")),
        _text(rec.get("company_response")),   # API name for "Company response to consumer"
        _text(rec.get("timely")),             # API name for "Timely response?"
        complaint_id,
        "cfpb_api",
        batch_id,
    )


def load_api(raw_path: Path = None) -> dict:
    raw_path = raw_path or latest_raw_file()
    
    # Extract batch_id safely from the filename rather than loading the whole JSON envelope
    batch_id = raw_path.stem.replace("cfpb_api_", "")
    
    stats = {"read": 0, "skipped": 0, "inserted": 0, "updated": 0}

    ensure_database_exists()
    conn = get_connection()
    try:
        ensure_table(conn)
        cur = conn.cursor()
        before = scalar(cur, "SELECT COUNT(*) FROM raw.raw_cfpb_complaints;")
        
        # Stream the JSON file byte-by-byte
        with open(raw_path, "rb") as f:
            rows = {}
            
            # ijson streams only the objects inside the "records" array
            for rec in ijson.items(f, 'records.item'):
                stats["read"] += 1
                row = normalize_record(rec, batch_id)
                
                if row is None:
                    stats["skipped"] += 1
                else:
                    # Deduplicate within the batch using a dictionary
                    complaint_id = row[RAW_COLUMNS.index("complaint_id")]
                    rows[complaint_id] = row
                
                # Execute upsert when batch reaches 5000
                if len(rows) >= 5000:
                    results = execute_values(cur, UPSERT_SQL, list(rows.values()), fetch=True)
                    inserted_this_batch = sum(1 for (ins,) in results if ins)
                    stats["inserted"] += inserted_this_batch
                    stats["updated"] += len(results) - inserted_this_batch
                    
                    conn.commit()
                    rows.clear()
                    logger.info("Processed %d records...", stats["read"])

            # Process the final partial batch
            if rows:
                results = execute_values(cur, UPSERT_SQL, list(rows.values()), fetch=True)
                inserted_this_batch = sum(1 for (ins,) in results if ins)
                stats["inserted"] += inserted_this_batch
                stats["updated"] += len(results) - inserted_this_batch
                conn.commit()

        if stats["skipped"]:
            logger.warning("Skipped %d records without a valid complaint_id", stats["skipped"])

        after = scalar(cur, "SELECT COUNT(*) FROM raw.raw_cfpb_complaints;")
        logger.info("Upsert complete: %d inserted (new), %d updated (already present). Table rows %s -> %s",
                    stats["inserted"], stats["updated"], f"{before:,}", f"{after:,}")
    except Exception:
        conn.rollback()
        logger.exception("API load failed - transaction rolled back")
        raise
    finally:
        conn.close()
        
    return stats


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", help="raw JSON file (default: newest in data/raw/cfpb_api/)")
    args = parser.parse_args()
    load_api(Path(args.file) if args.file else None)