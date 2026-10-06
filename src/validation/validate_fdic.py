"""
FDIC validation: checks the newest raw JSON file (source-faithful) before it is staged.
Hard rules (error) stop the pipeline; softer data-quality rules (warn) are reported and the
offending rows are listed in outputs/validation/fdic_flagged_records.csv.
"""
import json
import logging
from datetime import date

import pandas as pd

from src.extract.extract_fdic import RAW_DIR
from src.utils import config
from src.utils.logging_config import setup_logging
from src.validation.common import CheckResult, enforce, write_report

logger = logging.getLogger(__name__)

MIN_EXPECTED_INSTITUTIONS = 1000  # ~4,200 active institutions today; far fewer means a truncated extract
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
        raise FileNotFoundError(f"No raw FDIC file in {RAW_DIR}. Run src.extract.extract_fdic first.")
    document = json.loads(files[-1].read_text(encoding="utf-8"))
    frame = pd.DataFrame(document["records"]).replace(r"^\s*$", pd.NA, regex=True)
    return document, frame, files[-1]


def build_checks(document: dict, df: pd.DataFrame):
    n = len(df)
    assets = pd.to_numeric(df["ASSET"], errors="coerce")
    established = pd.to_datetime(df["ESTYMD"], format="%m/%d/%Y", errors="coerce")
    active = pd.to_numeric(df["ACTIVE"], errors="coerce")

    # (name, boolean series of failing rows, severity)
    row_rules = [
        ("null_core_keys", df[["CERT", "NAME", "STALP", "CITY"]].isna().any(axis=1), "error"),
        ("invalid_state_code", df["STALP"].notna() & ~df["STALP"].isin(VALID_STATES), "error"),
        ("nonpositive_asset", assets <= 0, "error"),
        ("not_active", active != 1, "error"),
        ("null_asset", assets.isna(), "warn"),
        ("invalid_zip_format", df["ZIP"].notna() & ~df["ZIP"].astype(str).str.match(r"^[0-9]{5}"), "warn"),
        ("future_established_date", established > pd.Timestamp(date.today()), "warn"),
        ("unparseable_established_date", established.isna(), "warn"),
    ]

    dup_certs = int(df["CERT"].duplicated(keep=False).sum())
    results = [
        CheckResult("duplicate_cert", dup_certs, n),
        CheckResult("row_count_floor", 0 if n >= MIN_EXPECTED_INSTITUTIONS else n, MIN_EXPECTED_INSTITUTIONS, detail=f"rows={n}"),
        CheckResult(
            "metadata_count_matches",
            abs(int(document.get("record_count", -1)) - n),
            n,
            detail=f"metadata={document.get('record_count')} actual={n}",
        ),
    ]
    flagged = []
    for name, failed, severity in row_rules:
        failed = failed.fillna(False)
        results.append(CheckResult(name, int(failed.sum()), n, severity=severity))
        if failed.any():
            rows = df.loc[failed, ["CERT", "NAME"]].copy()
            rows["Rule"] = name
            flagged.append(rows)
    return results, (pd.concat(flagged) if flagged else None)


def run_validations():
    document, df, source = load_latest_raw()
    logger.info("Validating %s (%d records)", source.name, len(df))
    results, flagged = build_checks(document, df)

    write_report(results, config.VALIDATION_DIR / "fdic_validation_report.csv")
    if flagged is not None:
        flagged.to_csv(config.VALIDATION_DIR / "fdic_flagged_records.csv", index=False)
        logger.info("Flagged %d institutions (see fdic_flagged_records.csv)", flagged["CERT"].nunique())
    enforce(results, "FDIC")
    return results


if __name__ == "__main__":
    setup_logging()
    run_validations()
