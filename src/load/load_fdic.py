"""
FDIC Institution Loader
Loads FDIC BankFind data from the latest Parquet file into raw.raw_fdic_institutions.
Idempotent: UPSERT on CERT (FDIC's unique institution ID).
"""
import os
import glob
import sys
from datetime import datetime
import pandas as pd
from src.utils.db import get_connection, ensure_database_exists
import pandas as pd
from psycopg2.extras import execute_values
from src.utils.db import get_connection, ensure_database_exists

COLUMN_MAP = {
    "CERT": "cert",
    "NAME": "name",
    "NAMEHCR": "name_hcr",
    "CITY": "city",
    "STALP": "state",
    "STNAME": "state_name",
    "ZIP": "zip",
    "ASSET": "asset",
    "DEP": "deposits",
    "NETINC": "net_income",
    "ROA": "roa",
    "ROE": "roe",
    "OFFICES": "offices",
    "BKCLASS": "bank_class",
    "CHARTER": "charter",
    "REGAGNT": "regulator",
    "ACTIVE": "active",
    "INACTIVE": "inactive",
    "ESTYMD": "established_date",
    "DATEUPDT": "date_updated",
    "RUNDATE": "run_date",
    "REPDTE": "report_date",
}

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.raw_fdic_institutions (
    cert                BIGINT PRIMARY KEY,
    name                TEXT,
    name_hcr            TEXT,
    city                TEXT,
    state               TEXT,
    state_name          TEXT,
    zip                 TEXT,
    asset               BIGINT,
    deposits            BIGINT,
    net_income          BIGINT,
    roa                 NUMERIC(15,4),
    roe                 NUMERIC(15,4),
    offices             INTEGER,
    bank_class          TEXT,
    charter             TEXT,
    regulator           TEXT,
    active              INTEGER,
    inactive            INTEGER,
    established_date    DATE,
    date_updated        DATE,
    run_date            DATE,
    report_date         DATE,
    ingested_at         TIMESTAMP DEFAULT NOW()
);
"""

def get_latest_parquet() -> str:
    files = glob.glob("data/raw/fdic/fdic_institutions_*.parquet")
    if not files:
        raise FileNotFoundError("No FDIC Parquet files found in data/raw/fdic/")
    latest = sorted(files)[-1]
    print(f"Using latest file: {latest}")
    return latest

def parse_date(val):
    if val is None or pd.isna(val):
        return None
    if isinstance(val, str):
        val = val.strip()
        if val in ("", "9999-12-31", "12/31/9999"):
            return None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                continue
        return None
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None

def to_int(val):
    if val is None or pd.isna(val):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None

def load_fdic(parquet_path: str = None):
    if parquet_path is None:
        parquet_path = get_latest_parquet()

    df = pd.read_parquet(parquet_path)

    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        print(f"WARNING: missing expected columns: {missing}")
    present = [c for c in COLUMN_MAP if c in df.columns]
    df = df[present].rename(columns=COLUMN_MAP)

    before = len(df)
    df = df.dropna(subset=["cert"])
    if len(df) < before:
        print(f"Dropped {before - len(df)} rows with null cert")

    # FIX 1: Use pandas nullable Int64 so ints stay ints even with NULLs
    for col in ("cert", "asset", "deposits", "net_income", "offices", "active", "inactive"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    for col in ("roa", "roe"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ("established_date", "date_updated", "run_date", "report_date"):
        if col in df.columns:
            df[col] = df[col].apply(parse_date)

    df["cert"] = df["cert"].astype("Int64")
    df = df.dropna(subset=["cert"])  # in case coercion introduced nulls
    df["cert"] = df["cert"].astype("int64")

    cols = list(COLUMN_MAP.values())
    cols = [c for c in cols if c in df.columns]

    ensure_database_exists()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(CREATE_TABLE_SQL)
    conn.commit()

    # FIX 2: Explicitly convert numpy/pandas types to Python types
    values = []
    for row in df[cols].itertuples(index=False, name=None):
        clean_row = []
        for val in row:
            if val is None or (not isinstance(val, (list, dict)) and pd.isna(val)):
                clean_row.append(None)
            elif hasattr(val, "item"):  # numpy scalar → Python scalar
                clean_row.append(val.item())
            else:
                clean_row.append(val)
        values.append(tuple(clean_row))

    update_cols = [c for c in cols if c != "cert"]
    update_clause = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])

    insert_sql = f"""
        INSERT INTO raw.raw_fdic_institutions ({", ".join(cols)})
        VALUES %s
        ON CONFLICT (cert) DO UPDATE SET
            {update_clause},
            ingested_at = NOW();
    """

    execute_values(cur, insert_sql, values, page_size=1000)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM raw.raw_fdic_institutions;")
    total = cur.fetchone()[0]

    print(f"Loaded {len(values):,} institutions (upserted)")
    print(f"Total rows in raw.raw_fdic_institutions: {total:,}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    load_fdic(path)
