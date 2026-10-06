"""
Exports the curated layer to files (the "file side" of the medallion layers).

    python -m src.export.export_curated                 # everything
    python -m src.export.export_curated --since-year 2026   # refresh only recent fact partitions

Writes
  data/curated/fact_complaints/received_year=YYYY/received_month=M/part-0.parquet   (partitioned by year + month)
  data/curated/mart_complaints_monthly/received_year=YYYY/part-0.parquet            (partitioned by year)
  data/curated/mart_institution_scorecard.{parquet,csv,json}                       (small -> all three formats)
  data/staging/{fdic_institutions,census_state}.parquet                             (staging reference data)

Partition key: complaints are naturally time-series data and analysts filter by period first, so
(year, month) lets a query like "August 2026" open ~1 small file instead of scanning every complaint.

Rerun safety:
  * Fact partitions use REPLACE-PARTITION: each (year, month) is written to a hidden temp directory and
    swapped in, so a rerun overwrites that partition and never duplicates rows; a crash mid-write
    leaves the previous version intact. A full run also deletes partitions that no longer exist in the DB.
  * Marts are small and fully rebuilt (controlled truncate-and-load).
"""
import argparse
import logging
import shutil
from decimal import Decimal
from pathlib import Path

import pandas as pd

from src.utils import config
from src.utils.db import get_connection, scalar
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

FACT_ROOT = config.CURATED_DIR / "fact_complaints"
MONTHLY_ROOT = config.CURATED_DIR / "mart_complaints_monthly"
SCORECARD_STEM = config.CURATED_DIR / "mart_institution_scorecard"

FACT_SQL = "SELECT * FROM curated.v_complaints_enriched WHERE received_year = %s AND received_month = %s"


# ------------------------------------------------------------------ helpers
def decimals_to_float(df: pd.DataFrame) -> pd.DataFrame:
    """psycopg2 returns NUMERIC as Decimal objects; convert to float so Parquet/JSON stay simple."""
    for col in df.columns:
        if df[col].dtype == object:
            first = df[col].dropna().head(1)
            if len(first) and isinstance(first.iloc[0], Decimal):
                df[col] = df[col].astype(float)
    return df


def fetch_df(conn, sql: str, params=None) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [d[0] for d in cur.description]
        return decimals_to_float(pd.DataFrame(cur.fetchall(), columns=columns))


def write_partition(df: pd.DataFrame, root: Path, **keys) -> Path:
    """
    Replace-partition write. Partition keys become hive-style directories
    (root/received_year=2026/received_month=8/) and are dropped from the file itself.
    """
    part_dir = root.joinpath(*[f"{k}={v}" for k, v in keys.items()])
    tmp_dir = part_dir.parent / f".{part_dir.name}.tmp"   # leading '.' -> ignored by dataset readers
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True)
    out = df.drop(columns=list(keys))
    # An all-NULL object column would be written as Parquet type "null"; a month where that column is
    # entirely empty then clashes with months where it is a string (ArrowNotImplementedError on read).
    # Pin such columns to string so every partition file has the same schema.
    for col in out.columns[out.dtypes == object]:
        if out[col].isna().all():
            out[col] = out[col].astype("string")
    out.to_parquet(tmp_dir / "part-0.parquet", index=False, compression="snappy")
    if part_dir.exists():
        shutil.rmtree(part_dir)
    tmp_dir.rename(part_dir)
    return part_dir


def remove_stale_partitions(root: Path, keep: set) -> None:
    """Deletes (year, month) partition directories that are no longer present in the database."""
    for month_dir in root.glob("received_year=*/received_month=*"):
        year = int(month_dir.parent.name.split("=")[1])
        month = int(month_dir.name.split("=")[1])
        if (year, month) not in keep:
            logger.info("Removing stale partition %s", month_dir)
            shutil.rmtree(month_dir)
    for year_dir in root.glob("received_year=*"):
        if not any(year_dir.iterdir()):
            year_dir.rmdir()


# ------------------------------------------------------------------ exporters
def export_fact(conn, since_year=None) -> int:
    import pyarrow.dataset as ds

    sql = "SELECT DISTINCT received_year, received_month FROM curated.fact_complaints"
    params = None
    if since_year:
        sql += " WHERE received_year >= %s"
        params = (since_year,)
    with conn.cursor() as cur:
        cur.execute(sql + " ORDER BY 1, 2", params)
        partitions = [(int(y), int(m)) for y, m in cur.fetchall()]
    if not partitions:
        raise RuntimeError("No partitions found: curated.fact_complaints is empty or the view does not exist")

    logger.info("Exporting %d (year, month) partitions to %s", len(partitions), FACT_ROOT)
    exported = 0
    for year, month in partitions:
        df = fetch_df(conn, FACT_SQL, (year, month))
        df["institution_cert"] = df["institution_cert"].astype("Int64")   # nullable BIGINT, not float
        write_partition(df, FACT_ROOT, received_year=year, received_month=month)
        exported += len(df)
        logger.info("  received_year=%d/received_month=%d: %s rows", year, month, f"{len(df):,}")

    if since_year is None:
        remove_stale_partitions(FACT_ROOT, set(partitions))

    # Reconcile: rows in the Parquet dataset must equal rows in the database.
    with conn.cursor() as cur:
        if since_year:
            expected = scalar(cur, "SELECT COUNT(*) FROM curated.fact_complaints WHERE received_year >= %s;", (since_year,))
        else:
            expected = scalar(cur, "SELECT COUNT(*) FROM curated.fact_complaints;")
    dataset = ds.dataset(FACT_ROOT, format="parquet", partitioning="hive")
    flt = (ds.field("received_year") >= since_year) if since_year else None
    actual = dataset.count_rows(filter=flt)
    logger.info("Fact export reconciliation: database=%s parquet=%s", f"{expected:,}", f"{actual:,}")
    if expected != actual:
        raise RuntimeError(f"Export reconciliation failed: database has {expected} rows, Parquet has {actual}")
    return exported


def export_marts(conn) -> None:
    monthly = fetch_df(conn, "SELECT * FROM curated.mart_complaints_monthly")
    shutil.rmtree(MONTHLY_ROOT, ignore_errors=True)
    for year, group in monthly.groupby("received_year"):
        write_partition(group.reset_index(drop=True), MONTHLY_ROOT, received_year=int(year))
    logger.info("mart_complaints_monthly: %s rows in %d year partitions", f"{len(monthly):,}", monthly["received_year"].nunique())

    scorecard = fetch_df(conn, "SELECT * FROM curated.mart_institution_scorecard")
    config.CURATED_DIR.mkdir(parents=True, exist_ok=True)
    scorecard.to_parquet(SCORECARD_STEM.with_suffix(".parquet"), index=False)
    scorecard.to_csv(SCORECARD_STEM.with_suffix(".csv"), index=False)
    scorecard.to_json(SCORECARD_STEM.with_suffix(".json"), orient="records", indent=2)
    logger.info("mart_institution_scorecard: %s rows written as Parquet, CSV and JSON", f"{len(scorecard):,}")


def export_staging_reference(conn) -> None:
    config.STAGING_DIR.mkdir(parents=True, exist_ok=True)
    for name, table in (("fdic_institutions", "staging.fdic_institutions"), ("census_state", "staging.census_state")):
        df = fetch_df(conn, f"SELECT * FROM {table}")
        path = config.STAGING_DIR / f"{name}.parquet"
        df.to_parquet(path, index=False)
        logger.info("Staging export: %s (%s rows)", path, f"{len(df):,}")


def main(since_year=None) -> None:
    conn = get_connection()
    try:
        export_staging_reference(conn)
        export_fact(conn, since_year)
        export_marts(conn)
    except Exception:
        logger.exception("Export failed")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since-year", type=int, help="only rewrite fact partitions from this year onward")
    main(parser.parse_args().since_year)