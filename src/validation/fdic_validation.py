import json
from datetime import date
from pathlib import Path

import pandas as pd

from src.extract.fdic_extract import RAW_DIR

OUTPUT_DIR = Path("outputs/validation")
VALID_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC", "AS", "GU", "MP", "PR", "VI", "FM", "MH", "PW",
}


def load_latest_raw():
    files = sorted(RAW_DIR.glob("fdic_institutions_*.json"))
    if not files:
        raise FileNotFoundError("No raw FDIC file found. Run src/extract/fdic_extract.py first.")
    document = json.loads(files[-1].read_text(encoding="utf-8"))
    frame = pd.DataFrame(document["records"])
    return frame.replace(r"^\s*$", pd.NA, regex=True), files[-1]


def build_rules(df):
    assets = pd.to_numeric(df["ASSET"], errors="coerce")
    established = pd.to_datetime(df["ESTYMD"], format="%m/%d/%Y", errors="coerce")
    active = pd.to_numeric(df["ACTIVE"], errors="coerce")
    return {
        "1_null_core_keys": df[["CERT", "NAME", "STALP", "CITY"]].isna().any(axis=1),
        "2_invalid_state_code": df["STALP"].notna() & ~df["STALP"].isin(VALID_STATES),
        "3_null_asset": assets.isna(),
        "4_nonpositive_asset": assets <= 0,
        "5_invalid_zip_format": df["ZIP"].notna() & ~df["ZIP"].astype(str).str.match(r"^[0-9]{5}$"),
        "6_future_established_date": established > pd.Timestamp(date.today()),
        "7_unparseable_established_date": established.isna(),
        "8_not_active": active != 1,
    }


def run_validations():
    df, source_path = load_latest_raw()
    print(f"Validating {source_path}")
    print(f"Total raw records: {len(df):,}\n")

    print("--- VALIDATION TEST RESULTS ---")
    failure_stats = []
    flagged = []

    duplicate_certs = int(df.loc[df["CERT"].duplicated(keep=False), "CERT"].nunique())
    failure_stats.append({"Rule": "0_duplicate_cert", "Failed Rows": duplicate_certs})
    label = "FAILED" if duplicate_certs else "PASSED"
    print(f"{label} 0_duplicate_cert: {duplicate_certs:,} distinct CERT values have duplicates")

    for rule_name, failed in build_rules(df).items():
        failed_count = int(failed.sum())
        failure_stats.append({"Rule": rule_name, "Failed Rows": failed_count})
        label = "FAILED" if failed_count else "PASSED"
        print(f"{label} {rule_name}: {failed_count:,} rows")
        if failed_count:
            rows = df.loc[failed, ["CERT", "NAME"]].copy()
            rows["Rule"] = rule_name
            flagged.append(rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(failure_stats).to_csv(OUTPUT_DIR / "fdic_validation_report.csv", index=False)
    if flagged:
        pd.concat(flagged).to_csv(OUTPUT_DIR / "fdic_flagged_records.csv", index=False)

    unknown_states = sorted(df.loc[df["STALP"].notna() & ~df["STALP"].isin(VALID_STATES), "STALP"].unique())
    if unknown_states:
        print(f"\nState codes not in the valid list: {unknown_states}")

    flagged_certs = pd.concat(flagged)["CERT"].nunique() if flagged else 0
    print(f"\nTotal flagged institutions: {flagged_certs:,} of {len(df):,}")
    print(f"Reports saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    run_validations()