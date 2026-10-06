"""
Source profiling for the Census ACS extract.
Run after extract_census.py has produced at least one raw file.
Outputs a profiling summary to outputs/census_profiling/census_profile.md
"""

import os
import json
import glob
import pandas as pd

RAW_DIR = os.path.join("data", "raw", "census")
OUTPUT_PATH = os.path.join("outputs", "census_profiling", "census_profile.md")

# Census "jam values" — sentinel codes meaning the estimate couldn't be
# computed (insufficient sample), NOT genuinely zero or missing-at-random.
# See: census.gov/data/developers/data-sets/acs-1year/notes-on-acs-estimate-and-annotation-values.html
JAM_VALUES = {-666666666, -888888888, -999999999, -555555555, -222222222}


def load_latest_raw():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "census_state_*.json")))
    if not files:
        raise FileNotFoundError(f"No raw Census files found in {RAW_DIR}")
    latest = files[-1]
    with open(latest, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return latest, payload


def to_dataframe(payload):
    rows = payload["data"]
    header, records = rows[0], rows[1:]
    df = pd.DataFrame(records, columns=header)
    return df


def profile(df: pd.DataFrame, payload: dict, source_file: str) -> str:
    lines = []
    lines.append(f"# Census ACS Source Profile\n")
    lines.append(f"- Source file: `{source_file}`")
    lines.append(f"- Retrieved at: {payload.get('retrieved_at')}")
    lines.append(f"- Source URL: {payload.get('source_url')}")
    lines.append(f"- ACS year: {payload.get('acs_year')}\n")

    lines.append("## Row / Column Counts")
    lines.append(f"- Rows: {len(df)}")
    lines.append(f"- Columns: {len(df.columns)}\n")

    lines.append("## Fields and Raw Dtypes")
    lines.append("All fields arrive as strings from the Census API, regardless of logical type — this must be handled in staging.\n")
    for col in df.columns:
        lines.append(f"- `{col}`: dtype={df[col].dtype}")
    lines.append("")

    lines.append("## Missingness (true nulls/blank strings)")
    for col in df.columns:
        n_null = df[col].isna().sum() + (df[col] == "").sum()
        lines.append(f"- `{col}`: {n_null} missing ({n_null / len(df):.1%})")
    lines.append("")

    lines.append("## Duplicate Check")
    if "state" in df.columns:
        dupes = df["state"].duplicated().sum()
        lines.append(f"- Duplicate `state` FIPS codes: {dupes}")
    lines.append(f"- Fully duplicate rows: {df.duplicated().sum()}\n")

    lines.append("## Jam Value Check (Census-specific data quality issue)")
    lines.append("Census returns sentinel codes like -666666666 when an estimate can't be computed due to insufficient sample size — these are NOT valid numeric values and must be treated as nulls in staging, not averaged/summed.\n")
    numeric_cols = [c for c in df.columns if c not in ("NAME", "state")]
    for col in numeric_cols:
        numeric_series = pd.to_numeric(df[col], errors="coerce")
        jam_count = numeric_series.isin(JAM_VALUES).sum()
        lines.append(f"- `{col}`: {jam_count} jam-value rows")
    lines.append("")

    lines.append("## Descriptive Statistics (numeric fields, jam values excluded)")
    for col in numeric_cols:
        numeric_series = pd.to_numeric(df[col], errors="coerce")
        clean = numeric_series[~numeric_series.isin(JAM_VALUES)]
        if clean.notna().any():
            lines.append(
                f"- `{col}`: min={clean.min():.0f}, max={clean.max():.0f}, "
                f"mean={clean.mean():.1f}, median={clean.median():.0f}"
            )
    lines.append("")

    lines.append("## Known Limitations")
    lines.append("- Geography is state-level only (52 rows: 50 states + DC + Puerto Rico) — CFPB complaints only expose ZIP-3, so state is the safest reliable join key; ZCTA-level Census data was considered but rejected for join reliability.")
    lines.append("- ACS 5-year estimates are rolling averages, not single-year snapshots — a documented trade-off vs. ACS 1-year data, which has more volatility but fewer small-sample suppressions.")
    lines.append("- As of May 2026 the Census API requires a registered key; this is an external dependency documented in `.env.example`.")

    return "\n".join(lines)


def run():
    source_file, payload = load_latest_raw()
    df = to_dataframe(payload)
    report = profile(df, payload, source_file)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Profile written to {OUTPUT_PATH}")
    print(df.head())


if __name__ == "__main__":
    run()