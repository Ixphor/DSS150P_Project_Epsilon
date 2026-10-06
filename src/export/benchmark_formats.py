"""
CSV vs JSON vs Parquet benchmark on a real sample of the curated data.

    python -m src.export.benchmark_formats --rows 200000

Measures, per format: file size, write time, full-read time, and read time when only 3 columns are
needed (best of 3 reads), plus how many columns come back with the same data type they went in with.
Results: outputs/format_comparison/format_benchmark.csv and .md
"""
import argparse
import logging
import shutil
import time

import pandas as pd

from src.export.export_curated import fetch_df
from src.utils import config
from src.utils.db import get_connection
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

OUT_DIR = config.OUTPUT_DIR / "format_comparison"
WORK_DIR = config.CURATED_DIR / "_benchmark"   # leading '_' keeps dataset readers away from it
SUBSET = ["received_year", "is_timely", "response_lag_days"]


def _read_json_subset(path):
    return pd.read_json(path, lines=True)[SUBSET]


FORMATS = {
    # name: (extension, writer, full reader, subset reader)
    "csv": (
        ".csv",
        lambda df, p: df.to_csv(p, index=False),
        lambda p: pd.read_csv(p),
        lambda p: pd.read_csv(p, usecols=SUBSET),
    ),
    "json_lines": (
        ".jsonl",
        lambda df, p: df.to_json(p, orient="records", lines=True, date_format="iso"),
        lambda p: pd.read_json(p, lines=True),
        _read_json_subset,
    ),
    "parquet_snappy": (
        ".parquet",
        lambda df, p: df.to_parquet(p, index=False, compression="snappy"),
        lambda p: pd.read_parquet(p),
        lambda p: pd.read_parquet(p, columns=SUBSET),
    ),
    "parquet_zstd": (
        ".parquet",
        lambda df, p: df.to_parquet(p, index=False, compression="zstd"),
        lambda p: pd.read_parquet(p),
        lambda p: pd.read_parquet(p, columns=SUBSET),
    ),
}


def normalize_types(df: pd.DataFrame) -> pd.DataFrame:
    """Give the sample proper types so we can see which formats preserve them."""
    for col in ("date_received", "date_sent_to_company"):
        df[col] = pd.to_datetime(df[col])
    df["is_timely"] = df["is_timely"].astype("boolean")
    df["institution_cert"] = df["institution_cert"].astype("Int64")
    return df


def schema_preserved_pct(original: pd.DataFrame, roundtrip: pd.DataFrame) -> float:
    """% of columns that come back with the same kind of dtype (datetime, bool, int, float, text)."""
    same = sum(
        1 for c in original.columns
        if c in roundtrip.columns and original[c].dtype.kind == roundtrip[c].dtype.kind
    )
    return round(100.0 * same / len(original.columns), 1)


def best_of(fn, repeats=1):
    best, result = None, None
    for _ in range(repeats):
        start = time.perf_counter()
        result = fn()
        elapsed = time.perf_counter() - start
        best = elapsed if best is None else min(best, elapsed)
    return best, result


def benchmark(df: pd.DataFrame, work_dir=WORK_DIR, read_repeats: int = 3) -> pd.DataFrame:
    work_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    try:
        for name, (ext, writer, read_full, read_subset) in FORMATS.items():
            path = work_dir / f"sample_{name}{ext}"
            write_s, _ = best_of(lambda: writer(df, path))
            read_s, roundtrip = best_of(lambda: read_full(path), read_repeats)
            subset_s, _ = best_of(lambda: read_subset(path), read_repeats)
            rows.append({
                "format": name,
                "size_mb": round(path.stat().st_size / 1024 / 1024, 2),
                "write_s": round(write_s, 2),
                "read_all_columns_s": round(read_s, 2),
                "read_3_columns_s": round(subset_s, 2),
                "schema_preserved_pct": schema_preserved_pct(df, roundtrip),
            })
            logger.info("%s: %s", name, rows[-1])
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    result = pd.DataFrame(rows)
    csv_size = result.loc[result["format"] == "csv", "size_mb"].iloc[0]
    result["size_vs_csv_pct"] = (100.0 * result["size_mb"] / csv_size).round(1)
    return result


def to_markdown(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def run(rows: int = 200_000) -> pd.DataFrame:
    conn = get_connection()
    try:
        logger.info("Loading a sample of the %s most recent complaints", f"{rows:,}")
        sample = normalize_types(
            fetch_df(conn, "SELECT * FROM curated.v_complaints_enriched ORDER BY date_received DESC LIMIT %s", (rows,))
        )
    finally:
        conn.close()

    result = benchmark(sample)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT_DIR / "format_benchmark.csv", index=False)
    (OUT_DIR / "format_benchmark.md").write_text(
        f"Benchmark sample: {len(sample):,} rows x {sample.shape[1]} columns "
        f"(most recent complaints from curated.v_complaints_enriched)\n\n" + to_markdown(result) + "\n",
        encoding="utf-8",
    )
    logger.info("Benchmark written to %s", OUT_DIR)
    print(to_markdown(result))
    return result


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=200_000)
    run(parser.parse_args().rows)