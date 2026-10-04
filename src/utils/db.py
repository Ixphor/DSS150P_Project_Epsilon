"""
Shared PostgreSQL connection utility.
All load/validation/profiling scripts should import get_connection()
from here instead of re-declaring their own os.getenv() calls.
"""
import os
import logging
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_USER = os.getenv("POSTGRES_USER", "airflow")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
TARGET_DB = os.getenv("POSTGRES_DB", "cfpb_pipeline")

if not DB_PASS:
    raise EnvironmentError("POSTGRES_PASSWORD not set — check your .env file")


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
    """Creates TARGET_DB if it doesn't already exist. Connects to the default 'airflow' db to do so."""
    conn = psycopg2.connect(dbname="airflow", user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (TARGET_DB,))
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {TARGET_DB};")
        logger.info("Created database '%s'.", TARGET_DB)
    cur.close()
    conn.close()