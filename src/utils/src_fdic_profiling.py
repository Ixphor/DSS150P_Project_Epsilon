import json
from pathlib import Path

import pandas as pd

from src.extract.fdic_extract import RAW_DIR, fetch_institutions, save_raw

OUTPUT_DIR = Path("outputs/fdic_profiling")
TOP_N = 5
TOP_COLUMNS = {
    "state": "STALP",
    "charter_class": "BKCLASS",
    "holding_company": "NAMEHCR",
    "specialization": "SPECGRPN",
}


def load_latest_raw():
    files = sorted(RAW_DIR.glob("fdic_institutions_*.json"))
    path = files[-1] if files else save_raw(fetch_institutions())
    document = json.loads(path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(document["records"])
    return frame.replace(r"^\s*$", pd.NA, regex=True), path


def dataset_overview(df):
    established = pd.to_datetime(df["ESTYMD"], format="%m/%d/%Y", errors="coerce")
    assets = pd.to_numeric(df["ASSET"], errors="coerce")
    active = pd.to_numeric(df["ACTIVE"], errors="coerce")
    name_counts = df["NAME"].str.upper().str.strip().value_counts()
    return pd.DataFrame([{
        "total_records": len(df),
        "unique_cert": df["CERT"].nunique(),
        "distinct_names": df["NAME"].nunique(),
        "names_shared_by_multiple_records": int((name_counts > 1).sum()),
        "distinct_states": df["STALP"].nunique(),
        "distinct_charter_classes": df["BKCLASS"].nunique(),
        "active_institutions": int((active == 1).sum()),
        "min_established": established.min().date(),
        "max_established": established.max().date(),
        "min_asset": assets.min(),
        "max_asset": assets.max(),
        "missing_or_nonpositive_asset": int((assets.isna() | (assets <= 0)).sum()),
    }])


def column_completeness(df):
    total = len(df)
    nulls = df.isna().sum()
    result = pd.DataFrame({
        "col_name": df.columns,
        "null_count": nulls.values,
        "null_pct": (100 * nulls / total).round(2).values,
        "distinct_count": df.nunique().values,
    })
    return result.sort_values("null_pct", ascending=False)


def top_values(df, column):
    counts = df[column].value_counts().head(TOP_N)
    return counts.rename_axis(column).reset_index(name="frequency")


def run_profiling():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df, source_path = load_latest_raw()
    print(f"Profiling {source_path}")

    print("\nRunning dataset overview...")
    overview = dataset_overview(df)
    overview.to_csv(OUTPUT_DIR / "01_dataset_overview.csv", index=False)
    print(overview.T)

    print("\nRunning column completeness...")
    completeness = column_completeness(df)
    completeness.to_csv(OUTPUT_DIR / "02_column_completeness.csv", index=False)
    print(completeness.head(20).to_string(index=False))

    print("\nRunning top values...")
    for label, column in TOP_COLUMNS.items():
        top = top_values(df, column)
        top.to_csv(OUTPUT_DIR / f"03_top_{label}.csv", index=False)
        print(f"\nTop {TOP_N} for {label}:")
        print(top.to_string(index=False))

    print(f"\nAll reports saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    run_profiling()