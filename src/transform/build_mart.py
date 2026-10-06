"""
Builds the consumption-ready curated data products (denormalised view + two marts).

    python -m src.transform.build_mart
"""
import logging

from src.utils import config
from src.utils.db import get_connection, run_sql_file, scalar
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

MARTS = ("mart_complaints_monthly", "mart_institution_scorecard")


def build() -> dict:
    conn = get_connection()
    try:
        logger.info("Building marts from curated.fact_complaints ...")
        run_sql_file(config.SQL_DIR / "curated" / "build_mart.sql", conn)
        conn.commit()
        counts = {}
        with conn.cursor() as cur:
            for mart in MARTS:
                counts[mart] = scalar(cur, f"SELECT COUNT(*) FROM curated.{mart};")
                logger.info("curated.%s: %s rows", mart, f"{counts[mart]:,}")
        return counts
    except Exception:
        conn.rollback()
        logger.exception("Mart build failed - transaction rolled back")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    setup_logging()
    build()