import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://api.fdic.gov/banks/institutions"
RAW_DIR = Path("data/raw/fdic")
PAGE_SIZE = 1000

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def fetch_institutions(filters="ACTIVE:1"):
    records = []
    offset = 0
    with requests.Session() as session:
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
            except requests.exceptions.Timeout:
                logger.error("FDIC API request timed out at offset %d", offset)
                raise
            except requests.exceptions.HTTPError as e:
                logger.error("FDIC API returned HTTP error at offset %d: %s", offset, e)
                raise
            except requests.exceptions.RequestException as e:
                logger.error("FDIC API request failed at offset %d: %s", offset, e)
                raise

            payload = response.json()
            rows = payload.get("data", [])
            if not rows:
                break

            records.extend(row["data"] for row in rows)
            logger.info("Fetched %d institutions so far (offset %d)", len(records), offset)
            offset += len(rows)

            # Stop once we get a short page back — more reliable than trusting
            # meta.total, which could be missing/0 and cause silent truncation.
            if len(rows) < PAGE_SIZE:
                break

    logger.info("Finished fetching FDIC institutions: %d total", len(records))
    return records


def save_raw(records):
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


def to_parquet(raw_path):
    document = json.loads(raw_path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(document["records"])
    out_path = raw_path.with_suffix(".parquet")
    frame.to_parquet(out_path, index=False)
    logger.info("Saved Parquet file to %s", out_path)
    return out_path


if __name__ == "__main__":
    records = fetch_institutions()
    raw_path = save_raw(records)
    parquet_path = to_parquet(raw_path)
    print(f"Fetched {len(records)} institutions")
    print(f"Raw JSON: {raw_path}")
    print(f"Parquet: {parquet_path}")