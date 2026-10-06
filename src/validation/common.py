"""
Shared validation framework.

Every source validator builds a list of CheckResult objects, writes a CSV report,
and calls enforce(). enforce() RAISES ValidationError if any check is in FAIL state,
which fails the Airflow task and stops downstream tasks (the quality gate).

Status rules:
    PASS : nothing failed
    WARN : severity == "warn", or failures are within the tolerated max_fail_pct
    FAIL : severity == "error" and failures exceed max_fail_pct
"""
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when a data-quality gate fails."""


@dataclass
class CheckResult:
    name: str
    failed: int
    total: int
    severity: str = "error"       # "error" blocks the pipeline, "warn" only reports
    max_fail_pct: float = 0.0     # tolerated % of failing rows for severity "error"
    detail: str = ""

    @property
    def fail_pct(self) -> float:
        return round(100.0 * self.failed / self.total, 4) if self.total else (0.0 if not self.failed else 100.0)

    @property
    def status(self) -> str:
        if self.failed == 0:
            return "PASS"
        if self.severity == "warn" or self.fail_pct <= self.max_fail_pct:
            return "WARN"
        return "FAIL"


def write_report(results: list, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "Rule": r.name,
                "Severity": r.severity,
                "Failed Rows": r.failed,
                "Total Rows": r.total,
                "Fail Pct": r.fail_pct,
                "Tolerance Pct": r.max_fail_pct,
                "Status": r.status,
                "Detail": r.detail,
            }
            for r in results
        ]
    ).to_csv(path, index=False)
    logger.info("Validation report written to %s", path)
    return path


def enforce(results: list, source: str) -> None:
    for r in results:
        line = "%s %s: %s of %s rows (%.3f%%) %s"
        args = (r.status, r.name, f"{r.failed:,}", f"{r.total:,}", r.fail_pct, r.detail)
        if r.status == "FAIL":
            logger.error(line, *args)
        elif r.status == "WARN":
            logger.warning(line, *args)
        else:
            logger.info(line, *args)

    failures = [r for r in results if r.status == "FAIL"]
    passed = sum(r.status == "PASS" for r in results)
    warned = sum(r.status == "WARN" for r in results)
    logger.info("%s validation: %d PASS, %d WARN, %d FAIL (of %d checks)", source, passed, warned, len(failures), len(results))
    if failures:
        raise ValidationError(f"{source} validation failed: " + ", ".join(r.name for r in failures))
