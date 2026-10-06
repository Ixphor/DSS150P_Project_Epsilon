"""
FDIC extract: active institutions from the BankFind API, paginated.
Raw JSON is saved untouched with ingestion metadata, plus a Parquet copy for the loader.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.utils import config
from src.utils.http import build_session
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

BASE_URL = f"{config.FDIC_API_BASE_URL}/institutions"
RAW_DIR = config.RAW_DIR / "fdic"
PAGE_SIZE = 1000


def fetch_institutions(filters: str = "ACTIVE:1") -> list[dict]:
    records, offset = [], 0
    session = build_session()
    while True:
        params = {
            "filters": filters,
            "limit": PAGE_SIZE,
            "offset": offset,
            "sort_by": "CERT",
            "sort_order": "ASC",
            "format": "json",
        }
        try:
            response = session.get(BASE_URL, params=params, timeout=60)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            logger.exception("FDIC API request failed at offset %d (%s)", offset, BASE_URL)
            raise

        rows = payload.get("data", [])
        if not rows:
            break
        records.extend(row["data"] for row in rows)
        logger.info("Fetched %d institutions so far (offset %d)", len(records), offset)
        offset += len(rows)
        if len(rows) < PAGE_SIZE:  # short page = last page (more reliable than meta.total)
            break

    if not records:
        raise RuntimeError("FDIC API returned 0 institutions - refusing to write an empty raw file")
    logger.info("Finished fetching FDIC institutions: %d total", len(records))
    return records


def save_raw(records: list[dict]) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RAW_DIR / f"fdic_institutions_{stamp}.json"
    document = {
        "ingested_at": stamp,
        "source": BASE_URL,
        "record_count": len(records),
        "records": records,
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    logger.info("Saved raw FDIC data to %s", path)
    return path


def to_parquet(raw_path: Path) -> Path:
    document = json.loads(raw_path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(document["records"])
    out_path = raw_path.with_suffix(".parquet")
    frame.to_parquet(out_path, index=False)
    logger.info("Saved Parquet file to %s", out_path)
    return out_path


def run() -> Path:
    records = fetch_institutions()
    raw_path = save_raw(records)
    return to_parquet(raw_path)


if __name__ == "__main__":
    setup_logging()
    run()
