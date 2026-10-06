import json

import pytest

from src.load.cfpb_common import RAW_COLUMNS
from src.load.load_cfpb_api import normalize_record
from src.validation.common import CheckResult, ValidationError, enforce, write_report


def test_normalize_record_maps_api_names_to_raw_columns():
    rec = {
        "complaint_id": "123", "date_received": "2026-09-27T12:00:00-05:00",
        "date_sent_to_company": "2026-09-28T12:00:00-05:00", "product": "Mortgage",
        "company": " ACME BANK ", "state": "CA", "zip_code": "90210", "tags": None,
        "company_response": "Closed with explanation", "timely": "Yes",
    }
    row = dict(zip(RAW_COLUMNS, normalize_record(rec, "batch1")))
    assert row["complaint_id"] == 123
    assert str(row["date_received"]) == "2026-09-27"
    assert row["company"] == "ACME BANK"
    assert row["company_response_to_consumer"] == "Closed with explanation"
    assert row["timely_response"] == "Yes"
    assert row["tags"] is None
    assert row["source_system"] == "cfpb_api" and row["batch_id"] == "batch1"


def test_normalize_record_rejects_missing_id():
    assert normalize_record({"product": "x"}, "b") is None
    assert normalize_record({"complaint_id": "abc"}, "b") is None


def test_check_status_rules():
    assert CheckResult("a", 0, 100).status == "PASS"
    assert CheckResult("b", 5, 100, severity="warn").status == "WARN"
    assert CheckResult("c", 1, 100, max_fail_pct=2.0).status == "WARN"   # within tolerance
    assert CheckResult("d", 5, 100, max_fail_pct=2.0).status == "FAIL"   # over tolerance
    assert CheckResult("e", 1, 100).status == "FAIL"                      # zero tolerance


def test_enforce_raises_on_failure_and_passes_otherwise():
    enforce([CheckResult("ok", 0, 10), CheckResult("soft", 3, 10, severity="warn")], "Test")
    with pytest.raises(ValidationError, match="bad_rule"):
        enforce([CheckResult("bad_rule", 3, 10)], "Test")


def test_write_report(tmp_path):
    path = write_report([CheckResult("x", 1, 10, severity="warn")], tmp_path / "r.csv")
    assert "WARN" in path.read_text()
