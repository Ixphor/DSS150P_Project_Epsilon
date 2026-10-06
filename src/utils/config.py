"""
Central configuration. Everything environment-specific comes from environment
variables (.env locally, docker-compose in containers); nothing is hard-coded to
a machine path.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Project root: PIPELINE_HOME in Docker (/opt/airflow), repo root when run locally.
PROJECT_ROOT = Path(os.getenv("PIPELINE_HOME") or Path(__file__).resolve().parents[2])

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"
CURATED_DIR = DATA_DIR / "curated"
SQL_DIR = PROJECT_ROOT / "sql"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
VALIDATION_DIR = OUTPUT_DIR / "validation"

# ---- CFPB ----
CFPB_BULK_CSV = RAW_DIR / "complaints.csv"
CFPB_BULK_URL = os.getenv("CFPB_BULK_URL", "https://files.consumerfinance.gov/ccdb/complaints.csv.zip")
CFPB_API_BASE_URL = os.getenv(
    "CFPB_API_BASE_URL",
    "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/",
)
CFPB_API_RAW_DIR = RAW_DIR / "cfpb_api"


def env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


def env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    return float(value) if value else default


CFPB_API_PAGE_SIZE = env_int("CFPB_API_PAGE_SIZE", 500)
CFPB_API_WINDOW_CAP = env_int("CFPB_API_WINDOW_CAP", 9500)
CFPB_API_LOOKBACK_DAYS = env_int("CFPB_API_LOOKBACK_DAYS", 14)
CFPB_API_MIN_INTERVAL = env_float("CFPB_API_MIN_INTERVAL", 1.0)  # seconds between API calls
CFPB_BULK_MIN_DATE = os.getenv("CFPB_BULK_MIN_DATE", "").strip() or None

# ---- FDIC ----
FDIC_API_BASE_URL = os.getenv("FDIC_API_BASE_URL", "https://api.fdic.gov/banks").rstrip("/")

# ---- Validation ----
MAX_REJECT_PCT = env_float("MAX_REJECT_PCT", 1.0)