import pytest

from src.load.cfpb_common import RAW_COLUMNS
from src.utils import config
from src.validation.contracts import column_names, load_contract, load_rules

EXPECTED_CFPB_RULES = {
    "null_core_fields",
    "invalid_timely_enum",
    "missing_or_negative_sla_lag",
    "future_date_received",
    "invalid_zip_format",
}


def test_cfpb_contract_has_required_structure():
    contract = load_contract("cfpb_complaints")
    assert contract["table"] == "raw.raw_cfpb_complaints"
    assert contract["primary_key"] == ["complaint_id"]


def test_cfpb_contract_columns_match_the_raw_table():
    assert set(column_names("cfpb_complaints")) == set(RAW_COLUMNS) | {"ingested_at"}


def test_cfpb_rules_load_with_severity_tolerance_and_condition():
    rules = load_rules("cfpb_complaints")
    assert set(rules) == EXPECTED_CFPB_RULES
    severity, tolerance, condition = rules["null_core_fields"]
    assert severity == "error"
    assert tolerance == config.MAX_REJECT_PCT          # "default" resolves to the environment value
    assert "complaint_id IS NULL" in condition
    assert rules["invalid_zip_format"][0] == "warn"
    assert rules["invalid_zip_format"][1] == 0.0


def test_missing_contract_raises():
    with pytest.raises(FileNotFoundError):
        load_contract("does_not_exist")


def test_bad_severity_is_rejected(tmp_path):
    (tmp_path / "bad.yml").write_text(
        "contract: bad\nversion: 1\ntable: t\ngrain: g\nprimary_key: [id]\ncolumns: []\n"
        "rules:\n  - {name: r, severity: maybe, failing_condition: 'x IS NULL'}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_rules("bad", directory=tmp_path)


def test_every_contract_column_is_documented_in_the_data_dictionary():
    dictionary = (config.PROJECT_ROOT / "docs" / "data_dictionary.md").read_text(encoding="utf-8")
    for name in column_names("cfpb_complaints") + column_names("census_state"):
        assert f"`{name}`" in dictionary, f"{name} missing from docs/data_dictionary.md"