"""
Census Loader
Loads the latest Census ACS raw JSON into raw.raw_census_state.
Idempotent: UPSERT on state_fips.
"""
import json
import glob
import logging
from pathlib import Path

from psycopg2.extras import execute_values
from src.utils.db import get_connection, ensure_database_exists

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw/census")

JAM_VALUES = {-666666666, -888888888, -999999999, -555555555, -222222222}

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.raw_census_state (
    state_fips               TEXT PRIMARY KEY,
    name                     TEXT,
    total_population         NUMERIC,
    median_household_income  NUMERIC,
    poverty_population       NUMERIC,
    white_alone              NUMERIC,
    black_alone              NUMERIC,
    ingested_at              TIMESTAMP DEFAULT NOW()
);
"""


def latest_raw_file() -> str:
    files = sorted(glob.glob(str(RAW_DIR / "census_state_*.json")))
    if not files:
        raise FileNotFoundError(f"No raw Census files found in {RAW_DIR}")
    latest = files[-1]
    logger.info("Using latest file: %s", latest)
    return latest


def clean_value(v):
    """Casts to float, treating Census jam/sentinel codes as NULL rather than real data."""
    try:
        num = float(v)
        return None if num in JAM_VALUES else num
    except (TypeError, ValueError):
        return None


def load_census(raw_path: str = None):
    if raw_path is None:
        raw_path = latest_raw_file()

    with open(raw_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    header, rows = payload["data"][0], payload["data"][1:]
    col_idx = {col: i for i, col in enumerate(header)}

    values = []
    for row in rows:
        values.append((
            row[col_idx["state"]],
            row[col_idx["NAME"]],
            clean_value(row[col_idx["B01003_001E"]]),
            clean_value(row[col_idx["B19013_001E"]]),
            clean_value(row[col_idx["B17001_002E"]]),
            clean_value(row[col_idx["B02001_002E"]]),
            clean_value(row[col_idx["B02001_003E"]]),
        ))

    ensure_database_exists()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(CREATE_TABLE_SQL)
    conn.commit()

    insert_sql = """
        INSERT INTO raw.raw_census_state
        (state_fips, name, total_population, median_household_income, poverty_population, white_alone, black_alone)
        VALUES %s
        ON CONFLICT (state_fips) DO UPDATE SET
            name = EXCLUDED.name,
            total_population = EXCLUDED.total_population,
            median_household_income = EXCLUDED.median_household_income,
            poverty_population = EXCLUDED.poverty_population,
            white_alone = EXCLUDED.white_alone,
            black_alone = EXCLUDED.black_alone,
            ingested_at = NOW();
    """
    execute_values(cur, insert_sql, values, page_size=100)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM raw.raw_census_state;")
    total = cur.fetchone()[0]

    logger.info("Loaded %d Census state rows (upserted)", len(values))
    logger.info("Total rows in raw.raw_census_state: %d", total)

    cur.close()
    conn.close()


if __name__ == "__main__":
    load_census()