"""
Demonstrates partition pruning: reading ONE (year, month) partition instead of scanning everything.

    python -m src.export.read_partition_demo                       # newest partition
    python -m src.export.read_partition_demo --year 2026 --month 8

Compares three reads of data/curated/fact_complaints:
  1. whole dataset, 2 columns          (no partition pruning)
  2. one partition, 2 columns          (partition pruning)
  3. one partition, all columns        (pruning of partitions, but every column read)
Results: outputs/format_comparison/partition_demo.csv
"""
import argparse
import logging
import time

import pandas as pd

from src.export.export_curated import FACT_ROOT
from src.utils import config
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

OUT_DIR = config.OUTPUT_DIR / "format_comparison"
COLUMNS = ["is_timely", "response_lag_days"]


def latest_partition(root=FACT_ROOT):
    found = []
    for month_dir in root.glob("received_year=*/received_month=*"):
        found.append((int(month_dir.parent.name.split("=")[1]), int(month_dir.name.split("=")[1])))
    if not found:
        raise FileNotFoundError(f"No partitions under {root}. Run src.export.export_curated first.")
    return max(found)


def run(year=None, month=None) -> pd.DataFrame:
    import pyarrow.dataset as ds

    if year is None or month is None:
        year, month = latest_partition()
    dataset = ds.dataset(FACT_ROOT, format="parquet", partitioning="hive")
    selected = (ds.field("received_year") == year) & (ds.field("received_month") == month)

    total_files = len(list(dataset.get_fragments()))
    files_in_partition = len(list(dataset.get_fragments(filter=selected)))
    logger.info("Dataset has %d partition files; the filter touches %d", total_files, files_in_partition)

    scenarios = [
        ("1. whole dataset, 2 columns", dict(columns=COLUMNS), total_files),
        (f"2. partition {year}-{month:02d}, 2 columns", dict(columns=COLUMNS, filter=selected), files_in_partition),
        (f"3. partition {year}-{month:02d}, all columns", dict(filter=selected), files_in_partition),
    ]
    rows = []
    for label, kwargs, files in scenarios:
        start = time.perf_counter()
        table = dataset.to_table(**kwargs)
        elapsed = time.perf_counter() - start
        timely_pct = None
        if "is_timely" in table.column_names:
            timely_pct = round(100.0 * table.column("is_timely").to_pandas().astype("float").mean(), 2)
        rows.append({
            "scenario": label,
            "files_scanned": files,
            "rows_read": table.num_rows,
            "columns_read": table.num_columns,
            "seconds": round(elapsed, 3),
            "timely_pct": timely_pct,
        })
        logger.info("%s", rows[-1])

    result = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT_DIR / "partition_demo.csv", index=False)
    print(result.to_string(index=False))
    return result


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int)
    args = parser.parse_args()
    run(args.year, args.month)