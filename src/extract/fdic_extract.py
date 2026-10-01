import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://api.fdic.gov/banks/institutions"
RAW_DIR = Path("data/raw/fdic")
PAGE_SIZE = 1000


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
            response = session.get(BASE_URL, params=params, timeout=60)
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("data", [])
            if not rows:
                break
            records.extend(row["data"] for row in rows)
            offset += len(rows)
            if offset >= payload.get("meta", {}).get("total", 0):
                break
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
    return path


def to_parquet(raw_path):
    document = json.loads(raw_path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(document["records"])
    out_path = raw_path.with_suffix(".parquet")
    frame.to_parquet(out_path, index=False)
    return out_path


if __name__ == "__main__":
    records = fetch_institutions()
    raw_path = save_raw(records)
    parquet_path = to_parquet(raw_path)
    print(f"Fetched {len(records)} institutions")
    print(f"Raw JSON: {raw_path}")
    print(f"Parquet: {parquet_path}")