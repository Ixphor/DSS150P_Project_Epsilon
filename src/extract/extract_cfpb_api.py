"""
CFPB API extract (INCREMENTAL source).

After the bulk CSV bootstrap, this pulls only the complaints received since the
latest one already in raw.raw_cfpb_complaints (minus a lookback overlap), paging
through the public Consumer Complaint search API. Results are saved untouched as
JSON in data/raw/cfpb_api/ together with ingestion metadata; load_cfpb_api.py
upserts them.

The API cannot page past ~10,000 hits per query, and busy days exceed that. So a
query whose total is over the cap is split automatically: by date range first,
then (for a single day) by product, then by state. Every split is checked
(sum of parts vs. expected total) and any gap is logged and recorded in the file.

Usage:
    python -m src.extract.extract_cfpb_api                  # watermark - lookback -> today
    python -m src.extract.extract_cfpb_api --since 2026-09-20 --until 2026-09-27
    python -m src.extract.extract_cfpb_api --probe          # tiny test call, writes nothing
"""
import argparse
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from src.utils import config
from src.utils.db import get_connection
from src.utils.http import build_browser_session
from src.utils.logging_config import setup_logging
from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)


class CFPBApiError(RuntimeError):
    pass


class CFPBApiClient:
    def __init__(self, base_url, page_size, window_cap, facet_levels=None, session=None,
                 max_retries=6, backoff=5.0, min_interval=0.0, sleep=time.sleep):
        self.base_url = base_url
        self.max_retries = max_retries      # retries per request on 429/5xx
        self.backoff = backoff              # first wait in seconds; doubles each retry
        self.min_interval = min_interval    # polite pause between requests
        self._sleep = sleep
        self._last_request = 0.0
        self.page_size = page_size
        self.window_cap = window_cap
        # ordered list of (api_filter_name, callable returning the values to split on)
        self.facet_levels: list[tuple[str, Callable[[], list]]] = facet_levels or []
        self.session = session or build_browser_session()
        self.gaps: list[dict] = []
        self.requests_made = 0

    # ---------- low level ----------
    def _get(self, params: dict) -> dict:
        self.requests_made += 1
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.consumerfinance.gov/data-research/consumer-complaints/",
        }
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
            self._last_request = time.monotonic()
            resp = self.session.get(self.base_url, params=params, headers=headers, timeout=60)
            status = getattr(resp, "status_code", 200)
            if status in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                delay = self.backoff * (2 ** attempt)
                retry_after = getattr(resp, "headers", {}).get("Retry-After")
                if retry_after and str(retry_after).isdigit():
                    delay = max(delay, int(retry_after))
                logger.warning("HTTP %s from API; retry %d/%d in %.0fs", status, attempt + 1, self.max_retries, delay)
                self._sleep(delay)
                continue
            break
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError as exc:
            raise CFPBApiError(f"API returned non-JSON content: {resp.text[:200]!r}") from exc

    @staticmethod
    def parse(payload) -> tuple[list[dict], Optional[int], Optional[list]]:
        """Returns (records, total_hits, last_sort_cursor). Handles the Elasticsearch-style envelope.

        last_sort_cursor is the 'sort' array on the final hit, used to build the
        search_after parameter for the next page -- CFPB's frm parameter alone
        does not actually advance pagination (see cfpb/cfpb.github.io#292).
        """
        if isinstance(payload, dict) and isinstance(payload.get("hits"), dict):
            hits = payload["hits"]
            total = hits.get("total")
            if isinstance(total, dict):
                total = total.get("value")
            raw_hits = hits.get("hits", [])
            rows = [h.get("_source", h) for h in raw_hits]
            last_sort = raw_hits[-1].get("sort") if raw_hits else None
            return rows, (int(total) if total is not None else None), last_sort
        if isinstance(payload, list):
            return [h.get("_source", h) for h in payload], None, None
        raise CFPBApiError(f"Unrecognised API response shape: {str(payload)[:200]!r}")

    def _params(self, filters: dict, size: int, frm: int, search_after: Optional[str] = None) -> dict:
        params = {
            **filters,
            "size": size,
            "frm": frm,
            "sort": "created_date_desc",
            "field": "all",
            "no_aggs": "true",
        }
        if search_after:
            params["search_after"] = search_after
        return params

    # ---------- counting and paging ----------
    def count(self, filters: dict) -> int:
        _, total, _ = self.parse(self._get(self._params(filters, size=1, frm=0)))
        if total is None:
            raise CFPBApiError("API response did not include a total hit count")
        return total

    def paginate(self, filters: dict, total: int) -> list[dict]:
        limit = min(total, self.window_cap)
        records: list[dict] = []
        frm = 0
        search_after: Optional[str] = None
        while frm < limit:
            payload = self._get(self._params(filters, size=self.page_size, frm=frm, search_after=search_after))
            rows, _, last_sort = self.parse(payload)
            if not rows:
                logger.warning("Empty page at frm=%d for %s (expected %d)", frm, filters, total)
                break
            records.extend(rows)
            frm += self.page_size
            # Advance the cursor for the next request. frm alone is unreliable past
            # page 1 (CFPB API bug), so search_after does the real pagination work.
            if last_sort:
                search_after = f"{last_sort[0]}_{last_sort[1]}"
        return records

    # ---------- splitting ----------
    def collect(self, date_min: date, date_max: date, facets: Optional[dict] = None) -> list[dict]:
        facets = facets or {}
        filters = {
            "date_received_min": date_min.isoformat(),
            "date_received_max": date_max.isoformat(),
            **facets,
        }
        total = self.count(filters)
        if total == 0:
            return []
        if total <= self.window_cap:
            logger.info("Slice %s: %d records", filters, total)
            return self.paginate(filters, total)

        # Too big for one query -> split.
        if date_min < date_max:
            mid = date_min + (date_max - date_min) // 2
            logger.info("Slice %s has %d records (> cap %d): splitting dates at %s", filters, total, self.window_cap, mid)
            return self.collect(date_min, mid, facets) + self.collect(mid + timedelta(days=1), date_max, facets)

        for facet_name, values_fn in self.facet_levels:
            if facet_name in facets:
                continue
            logger.info("Single day %s has %d records: splitting by %s", date_min, total, facet_name)
            out: list[dict] = []
            for value in values_fn():
                out.extend(self.collect(date_min, date_max, {**facets, facet_name: value}))
            if len(out) < total:
                self._record_gap(filters, expected=total, fetched=len(out), reason=f"split by {facet_name}")
            return out

        logger.warning("Slice %s has %d records but cannot be split further: truncating at cap", filters, total)
        records = self.paginate(filters, total)
        self._record_gap(filters, expected=total, fetched=len(records), reason="exceeds cap, no split left")
        return records

    def _record_gap(self, filters, expected, fetched, reason):
        gap = {"filters": filters, "expected": expected, "fetched": fetched, "reason": reason}
        self.gaps.append(gap)
        logger.warning("GAP: expected %d, fetched %d (%s) for %s", expected, fetched, reason, filters)


# ---------- database helpers ----------
def get_watermark() -> Optional[date]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(date_received) FROM raw.raw_cfpb_complaints;")
            return cur.fetchone()[0]
    finally:
        conn.close()


def distinct_values(column: str) -> list[str]:
    allowed = {"product", "state"}
    if column not in allowed:
        raise ValueError(column)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT {column} FROM raw.raw_cfpb_complaints WHERE {column} IS NOT NULL ORDER BY 1;")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


# ---------- raw persistence ----------
def save_raw(records, since, until, expected_total, gaps, batch_id) -> str:
    config.CFPB_API_RAW_DIR.mkdir(parents=True, exist_ok=True)
    document = {
        "source": "CFPB Consumer Complaint Database API",
        "source_url": config.CFPB_API_BASE_URL,
        "batch_id": batch_id,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "expected_total": expected_total,
        "record_count": len(records),
        "complete": not gaps and len(records) >= expected_total,
        "gaps": gaps,
        "records": records,
    }
    path = config.CFPB_API_RAW_DIR / f"cfpb_api_{batch_id}.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    logger.info("Saved raw CFPB API data to %s (%d records, complete=%s)", path, len(records), document["complete"])
    return str(path)


def run(since: Optional[date] = None, until: Optional[date] = None, lookback_days: Optional[int] = None) -> str:
    lookback_days = config.CFPB_API_LOOKBACK_DAYS if lookback_days is None else lookback_days
    until = until or datetime.now(timezone.utc).date()

    if since is None:
        watermark = get_watermark()
        if watermark is None:
            since = until - timedelta(days=max(lookback_days, 30))
            logger.warning("raw.raw_cfpb_complaints is empty (no watermark); defaulting to %s", since)
        else:
            since = watermark - timedelta(days=lookback_days)
            logger.info("Watermark (latest date_received) = %s; restarting %d days earlier at %s", watermark, lookback_days, since)
    if since > until:
        raise ValueError(f"since ({since}) is after until ({until})")

    client = CFPBApiClient(
        config.CFPB_API_BASE_URL,
        config.CFPB_API_PAGE_SIZE,
        config.CFPB_API_WINDOW_CAP,
        facet_levels=[("product", lambda: distinct_values("product")), ("state", lambda: distinct_values("state"))],
        min_interval=config.CFPB_API_MIN_INTERVAL,
    )

    expected_total = client.count({"date_received_min": since.isoformat(), "date_received_max": until.isoformat()})
    logger.info("API reports %d complaints between %s and %s", expected_total, since, until)

    records = client.collect(since, until)

    # De-duplicate (slice boundaries / unstable sort ordering can repeat a record).
    unique = {str(r.get("complaint_id")): r for r in records if r.get("complaint_id") is not None}
    if len(unique) != len(records):
        logger.info("Dropped %d duplicate records from overlapping pages", len(records) - len(unique))
    records = list(unique.values())

    if len(records) < expected_total:
        logger.warning("Fetched %d of %d expected records (see gaps in the raw file)", len(records), expected_total)

    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logger.info("API requests made: %d", client.requests_made)
    return save_raw(records, since, until, expected_total, client.gaps, batch_id)


def probe() -> None:
    client = CFPBApiClient(config.CFPB_API_BASE_URL, 2, config.CFPB_API_WINDOW_CAP)
    until = datetime.now(timezone.utc).date()
    filters = {"date_received_min": (until - timedelta(days=7)).isoformat(), "date_received_max": until.isoformat()}
    payload = client._get(client._params(filters, size=2, frm=0))
    rows, total, _ = client.parse(payload)
    print(f"Total hits last 7 days: {total}")
    print(f"Records returned: {len(rows)}")
    if rows:
        print("Fields:", sorted(rows[0].keys()))
        print("Sample:", json.dumps(rows[0], indent=2)[:1200])


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", type=date.fromisoformat, help="YYYY-MM-DD (default: watermark - lookback)")
    parser.add_argument("--until", type=date.fromisoformat, help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--lookback-days", type=int, help="overlap before the watermark")
    parser.add_argument("--probe", action="store_true", help="test the API and print field names only")
    args = parser.parse_args()
    if args.probe:
        probe()
    else:
        run(args.since, args.until, args.lookback_days)