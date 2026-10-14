"""
Loads data contracts from contracts/*.yml so validation rules are defined once, in the
contract, instead of being hard-coded in each validate_*.py file.

    from src.validation.contracts import load_rules
    RULES = load_rules("cfpb_complaints")   # {rule_name: (severity, tolerance_pct, failing_condition)}
"""
from pathlib import Path

import yaml

from src.utils import config

CONTRACT_DIR = config.PROJECT_ROOT / "contracts"
VALID_SEVERITIES = {"error", "warn"}


def load_contract(name: str, directory: Path = None) -> dict:
    """Reads contracts/<name>.yml and checks the minimum structure."""
    path = Path(directory or CONTRACT_DIR) / f"{name}.yml"
    if not path.exists():
        raise FileNotFoundError(f"Data contract not found: {path}")
    contract = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key in ("contract", "version", "table", "grain", "primary_key", "columns"):
        if key not in contract:
            raise ValueError(f"{path.name}: missing required key '{key}'")
    return contract


def _tolerance(value) -> float:
    """'default' means the environment-wide MAX_REJECT_PCT; anything else is a number."""
    if value is None or str(value).strip().lower() == "default":
        return config.MAX_REJECT_PCT
    return float(value)


def load_rules(name: str, directory: Path = None) -> dict:
    """Returns {rule_name: (severity, tolerance_pct, failing_condition)} from the contract's `rules` block."""
    contract = load_contract(name, directory)
    rules = {}
    for rule in contract.get("rules", []):
        severity = rule.get("severity", "error")
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"{name}.yml rule '{rule.get('name')}': severity must be one of {sorted(VALID_SEVERITIES)}")
        if not rule.get("name") or not rule.get("failing_condition"):
            raise ValueError(f"{name}.yml: every rule needs a 'name' and a 'failing_condition'")
        rules[rule["name"]] = (severity, _tolerance(rule.get("tolerance_pct")), rule["failing_condition"])
    return rules


def column_names(name: str, directory: Path = None) -> list:
    return [c["name"] for c in load_contract(name, directory)["columns"]]