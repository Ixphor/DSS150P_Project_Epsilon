"""
Repeat-run safety of the raw CFPB upsert. Needs the PostgreSQL container; skipped when no database is reachable
(start it with `docker compose up -d postgres`). Test rows use IDs far above real CFPB complaint numbers and are
removed afterwards.
"""
import pytest
from psycopg2.extras import execute_values

from src.load.cfpb_common import RAW_COLUMNS, ensure_table
from src.load.load_cfpb_api import UPSERT_SQL, normalize_record
from src.utils.db import get_connection

TEST_IDS = (9_000_000_001, 9_000_000_002)


def _rows(batch_id: str):
    records = [
        {"complaint_id": str(i), "date_received": "2026-09-27T12:00:00-05:00", "product": "Mortgage",
         "company": "TEST BANK", "state": "CA", "timely": "Yes"}
        for i in TEST_IDS
    ]
    return [normalize_record(r, batch_id) for r in records]


@pytest.fixture
def conn():
    try:
        connection = get_connection()
    except Exception as exc:
        pytest.skip(f"PostgreSQL not reachable: {exc}")
    ensure_table(connection)
    connection.commit()
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM raw.raw_cfpb_complaints WHERE complaint_id = ANY(%s);", (list(TEST_IDS),))
    connection.commit()
    connection.close()


def test_upserting_the_same_batch_twice_creates_no_duplicates(conn):
    with conn.cursor() as cur:
        first = execute_values(cur, UPSERT_SQL, _rows("run1"), fetch=True)
        second = execute_values(cur, UPSERT_SQL, _rows("run2"), fetch=True)
        cur.execute("SELECT COUNT(*) FROM raw.raw_cfpb_complaints WHERE complaint_id = ANY(%s);", (list(TEST_IDS),))
        count = cur.fetchone()[0]
    assert [ins for (ins,) in first] == [True, True]      # first run inserts
    assert [ins for (ins,) in second] == [False, False]   # second run only updates
    assert count == len(TEST_IDS)                         # still one row per complaint_id


def test_upsert_refreshes_the_existing_row(conn):
    with conn.cursor() as cur:
        execute_values(cur, UPSERT_SQL, _rows("old_batch"), fetch=True)
        execute_values(cur, UPSERT_SQL, _rows("new_batch"), fetch=True)
        cur.execute("SELECT DISTINCT batch_id FROM raw.raw_cfpb_complaints WHERE complaint_id = ANY(%s);", (list(TEST_IDS),))
        batches = [r[0] for r in cur.fetchall()]
    assert batches == ["new_batch"]