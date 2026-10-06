"""Offline tests for the export helpers (no database needed)."""
from decimal import Decimal

import pandas as pd

from src.export.benchmark_formats import normalize_types, schema_preserved_pct, to_markdown
from src.export.export_curated import decimals_to_float, remove_stale_partitions, write_partition


def sample_frame(n=3):
    return pd.DataFrame({"received_year": [2026] * n, "received_month": [8] * n, "x": range(n)})


def test_write_partition_uses_hive_layout_and_drops_key_columns(tmp_path):
    write_partition(sample_frame(), tmp_path, received_year=2026, received_month=8)
    files = list(tmp_path.glob("received_year=2026/received_month=8/*.parquet"))
    assert len(files) == 1
    assert list(pd.read_parquet(files[0]).columns) == ["x"]


def test_write_partition_replaces_instead_of_appending(tmp_path):
    write_partition(sample_frame(3), tmp_path, received_year=2026, received_month=8)
    write_partition(sample_frame(1), tmp_path, received_year=2026, received_month=8)  # rerun with different data
    files = list(tmp_path.glob("received_year=2026/received_month=8/*.parquet"))
    assert len(files) == 1 and len(pd.read_parquet(files[0])) == 1
    assert not list(tmp_path.glob("received_year=2026/.*")), "temp directory must not be left behind"


def test_remove_stale_partitions_keeps_only_listed(tmp_path):
    for month in (7, 8):
        write_partition(sample_frame(), tmp_path, received_year=2026, received_month=month)
    write_partition(sample_frame(), tmp_path, received_year=2025, received_month=1)
    remove_stale_partitions(tmp_path, keep={(2026, 8)})
    remaining = sorted(p.name for p in tmp_path.glob("received_year=*/received_month=*"))
    assert remaining == ["received_month=8"]
    assert not (tmp_path / "received_year=2025").exists()


def test_decimals_become_floats():
    df = pd.DataFrame({"a": [Decimal("1.50"), None], "b": ["x", "y"]})
    out = decimals_to_float(df)
    assert out["a"].dtype == float and out["a"].isna().tolist() == [False, True]
    assert out["b"].tolist() == ["x", "y"]   # text columns untouched


def test_schema_preserved_pct_detects_lost_types():
    df = normalize_types(pd.DataFrame({
        "date_received": ["2026-08-01"], "date_sent_to_company": ["2026-08-02"],
        "is_timely": [True], "institution_cert": [123],
    }))
    as_csv_text = df.astype(str)   # what a text format gives back: everything is strings
    assert schema_preserved_pct(df, df) == 100.0
    assert schema_preserved_pct(df, as_csv_text) < 100.0


def test_markdown_table():
    md = to_markdown(pd.DataFrame({"format": ["csv"], "size_mb": [1.0]}))
    assert md.splitlines()[0] == "| format | size_mb |" and "| csv | 1.0 |" in md