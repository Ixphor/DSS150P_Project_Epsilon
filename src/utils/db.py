"""
Shared PostgreSQL helpers.
All load / validation / transform scripts import from here instead of re-declaring
their own os.getenv() calls.
"""
import logging
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

load_dotenv()

logger = logging.getLogger(__name__)

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_USER = os.getenv("POSTGRES_USER", "airflow")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
TARGET_DB = os.getenv("POSTGRES_DB", "cfpb_pipeline")

if not DB_PASS:
    raise EnvironmentError("POSTGRES_PASSWORD not set - check your .env file")


def get_connection(dbname: str = None):
    """Returns a psycopg2 connection to the target pipeline database (or a specified db)."""
    return psycopg2.connect(
        dbname=dbname or TARGET_DB,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
    )


def ensure_database_exists():
    """Creates TARGET_DB if it doesn't already exist (connects to the bootstrap 'airflow' db)."""
    conn = psycopg2.connect(dbname="airflow", user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (TARGET_DB,))
    if not cur.fetchone():
        cur.execute(f'CREATE DATABASE "{TARGET_DB}";')
        logger.info("Created database '%s'.", TARGET_DB)
    cur.close()
    conn.close()


def run_sql_file(path, conn=None) -> None:
    """
    Executes a .sql file as ONE transaction: either every statement applies or none do.
    Pass an open connection to share a transaction with other work; otherwise a
    connection is opened, committed and closed here.
    """
    sql = Path(path).read_text(encoding="utf-8")
    own_conn = conn is None
    conn = conn or get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)  # no params: '%' and backslashes in the SQL are left untouched
        if own_conn:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()


def scalar(cur, sql: str, params=None):
    """Runs a query and returns the first column of the first row."""
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None
