"""Offline tests for the CFPB API extractor: a fake API stands in for the real service."""
from datetime import date, timedelta

from src.extract.extract_cfpb_api import CFPBApiClient


class FakeSession:
    """Mimics the search API: filters by date/product/state and pages with size/frm."""

    def __init__(self, records):
        self.records = records
        self.calls = 0

    def get(self, url, params, headers=None, timeout=None):
        self.calls += 1
        rows = [
            r for r in self.records
            if params["date_received_min"] <= r["date_received"][:10] <= params["date_received_max"]
            and ("product" not in params or r["product"] == params["product"])
            and ("state" not in params or r["state"] == params["state"])
        ]
        page = rows[params["frm"]: params["frm"] + params["size"]]
        body = {"hits": {"total": {"value": len(rows)}, "hits": [{"_source": r} for r in page]}}
        return type("Resp", (), {"raise_for_status": lambda self: None, "json": lambda self: body})()


def make_records(days=3, per_day=40, null_state_per_day=0):
    start = date(2026, 9, 1)
    out, cid = [], 1
    for d in range(days):
        day = (start + timedelta(days=d)).isoformat()
        for i in range(per_day):
            out.append({
                "complaint_id": str(cid),
                "date_received": f"{day}T12:00:00-05:00",
                "product": ["Credit reporting", "Mortgage"][i % 2],
                "state": None if i < null_state_per_day else ["CA", "NY", "TX"][i % 3],
            })
            cid += 1
    return out


def client_for(records, cap, page_size=7):
    return CFPBApiClient(
        "http://fake", page_size, cap,
        facet_levels=[("product", lambda: ["Credit reporting", "Mortgage"]), ("state", lambda: ["CA", "NY", "TX"])],
        session=FakeSession(records),
    )


def test_small_window_needs_no_splitting():
    records = make_records(days=2, per_day=10)
    c = client_for(records, cap=1000)
    got = c.collect(date(2026, 9, 1), date(2026, 9, 2))
    assert len(got) == 20 and not c.gaps


def test_large_window_splits_by_date_without_loss_or_duplicates():
    records = make_records(days=4, per_day=30)  # 120 total, cap 50 -> must split
    c = client_for(records, cap=50)
    got = c.collect(date(2026, 9, 1), date(2026, 9, 4))
    assert sorted(r["complaint_id"] for r in got) == sorted(r["complaint_id"] for r in records)
    assert len({r["complaint_id"] for r in got}) == len(got)
    assert not c.gaps


def test_busy_single_day_splits_by_product_then_state():
    records = make_records(days=1, per_day=60)  # one day, 60 records, cap 20 -> product -> state
    c = client_for(records, cap=20)
    got = c.collect(date(2026, 9, 1), date(2026, 9, 1))
    assert len(got) == 60 and not c.gaps


def test_unmatchable_rows_are_reported_as_a_gap_not_silently_lost():
    records = make_records(days=1, per_day=60, null_state_per_day=10)  # null-state rows can't be reached by state filter
    c = client_for(records, cap=20)
    got = c.collect(date(2026, 9, 1), date(2026, 9, 1))
    assert len(got) < 60
    assert c.gaps, "a shortfall must be recorded"


def test_parse_handles_envelope_and_list():
    assert CFPBApiClient.parse({"hits": {"total": {"value": 5}, "hits": [{"_source": {"a": 1}}]}}) == ([{"a": 1}], 5, None)
    assert CFPBApiClient.parse([{"_source": {"a": 2}}]) == ([{"a": 2}], None, None)


def test_parse_returns_last_sort_cursor():
    payload = {"hits": {"total": {"value": 2}, "hits": [
        {"_source": {"a": 1}, "sort": [10, "x"]},
        {"_source": {"a": 2}, "sort": [20, "y"]},
    ]}}
    assert CFPBApiClient.parse(payload) == ([{"a": 1}, {"a": 2}], 2, [20, "y"])


def test_retries_on_429_then_succeeds():
    class Flaky(FakeSession):
        def get(self, url, params, headers=None, timeout=None):
            resp = super().get(url, params, headers, timeout)
            resp.status_code = 429 if self.calls <= 2 else 200
            resp.headers = {}
            return resp

    sleeps = []
    c = CFPBApiClient("http://fake", 7, 1000, session=Flaky(make_records(days=1, per_day=5)), backoff=1, sleep=sleeps.append)
    assert len(c.collect(date(2026, 9, 1), date(2026, 9, 1))) == 5
    assert sleeps[:2] == [1, 2]  # exponential backoff