"""
CFPB bulk extract (BOOTSTRAP source).

Downloads the full CFPB complaint database (complaints.csv.zip) and unpacks it to
data/raw/complaints.csv, byte-for-byte as published. If the CSV is already there
(e.g. you placed it manually) nothing is downloaded, so reruns are cheap and safe.
Use --force to re-download.
"""
import argparse
import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone

from src.utils import config
from src.utils.http import build_session
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

META_PATH = config.CFPB_BULK_CSV.with_suffix(".csv.meta.json")


def download_zip(url: str, dest) -> int:
    """Streams the zip to `dest` (via a .part file so a failed download never looks complete)."""
    part = dest.with_suffix(dest.suffix + ".part")
    session = build_session()
    total = 0
    next_log = 100 * 1024 * 1024
    logger.info("Downloading %s", url)
    with session.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(part, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                fh.write(chunk)
                total += len(chunk)
                if total >= next_log:
                    logger.info("  ... %d MB downloaded", total // (1024 * 1024))
                    next_log += 100 * 1024 * 1024
    part.replace(dest)
    return total


def extract_csv(zip_path, target) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
        if not members:
            raise RuntimeError(f"No CSV found inside {zip_path}: {zf.namelist()}")
        logger.info("Unpacking %s -> %s", members[0], target)
        part = target.with_suffix(".csv.part")
        with zf.open(members[0]) as src, open(part, "wb") as dst:
            shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)
    part.replace(target)


def run(force: bool = False):
    target = config.CFPB_BULK_CSV
    if target.exists() and not force:
        logger.info("Bulk CSV already present at %s (%d bytes) - skipping download", target, target.stat().st_size)
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    zip_path = target.with_suffix(".csv.zip")
    try:
        size = download_zip(config.CFPB_BULK_URL, zip_path)
        extract_csv(zip_path, target)
    finally:
        zip_path.unlink(missing_ok=True)

    META_PATH.write_text(
        json.dumps(
            {
                "source": "CFPB Consumer Complaint Database (bulk CSV)",
                "source_url": config.CFPB_BULK_URL,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "zip_bytes": size,
                "csv_bytes": target.stat().st_size,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Bulk CSV ready: %s", target)
    return target


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download even if the CSV exists")
    run(force=parser.parse_args().force)
