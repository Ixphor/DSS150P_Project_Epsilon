"""
Extracts American Community Survey (ACS) 5-year estimates from the
Census Bureau API at the state level, for enrichment of complaint data.
"""

import os
import json
import logging
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CENSUS_BASE_URL = os.getenv("CENSUS_API_BASE_URL", "https://api.census.gov/data")
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", "")
ACS_YEAR = "2022"
ACS_DATASET = "acs/acs5"

VARIABLES = [
    "NAME",
    "B01003_001E",  # total population
    "B19013_001E",  # median household income
    "B17001_002E",  # population below poverty line
    "B02001_002E",  # white alone
    "B02001_003E",  # Black/African American alone
]

RAW_OUTPUT_DIR = os.path.join("data", "raw", "census")


def build_request_url() -> tuple[str, dict]:
    """Builds the ACS request URL and query params for state-level geography."""
    url = f"{CENSUS_BASE_URL}/{ACS_YEAR}/{ACS_DATASET}"
    params = {
        "get": ",".join(VARIABLES),
        "for": "state:*",
    }
    if CENSUS_API_KEY:
        params["key"] = CENSUS_API_KEY
    return url, params


def fetch_census_data() -> list[list[str]]:
    """Calls the Census API and returns the raw JSON (list-of-lists) response."""
    url, params = build_request_url()
    logger.info("Requesting Census ACS data: %s", url)

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        logger.error("Census API request timed out")
        raise
    except requests.exceptions.HTTPError as e:
        # 429/403 commonly means you've hit the unauthenticated rate limit
        logger.error("Census API returned HTTP error: %s", e)
        raise
    except requests.exceptions.RequestException as e:
        logger.error("Census API request failed: %s", e)
        raise
    
    data = response.json()
    if not data or len(data) < 2:
        logger.warning("Census API returned no data rows")
    return data


def save_raw(data: list[list[str]]) -> str:
    """Persists the raw response with ingestion metadata, source-faithful."""
    os.makedirs(RAW_OUTPUT_DIR, exist_ok=True)

    retrieved_at = datetime.now(timezone.utc).isoformat()
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    payload = {
        "source": "U.S. Census Bureau ACS 5-Year Estimates",
        "source_url": build_request_url()[0],
        "acs_year": ACS_YEAR,
        "retrieved_at": retrieved_at,
        "batch_id": batch_id,
        "record_count": max(len(data) - 1, 0),  # minus header row
        "data": data,
    }

    out_path = os.path.join(RAW_OUTPUT_DIR, f"census_state_{batch_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    logger.info("Saved raw Census data to %s (%d records)", out_path, payload["record_count"])
    return out_path


def run():
    data = fetch_census_data()
    return save_raw(data)


if __name__ == "__main__":
    run()