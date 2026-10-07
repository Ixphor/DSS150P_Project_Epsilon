"""
Do institutions / products / geographies get systematically slower or less favourable resolution?
    python -m src.analytics.insights
Writes findings.md, insight_*.csv and run_manifest.json (audit trail) to outputs/analytics/.
"""
import json
import logging
from datetime import datetime, timezone

import pandas as pd
from scipy import stats

from src.analytics import common as C
from src.utils import config
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

DIMENSIONS = {
    "institution (company)": ("company_name", 100, C.STRATA),
    "institution type (FDIC tier)": ("institution_group", 100, C.STRATA),
    "product category": ("product_name", 100, "received_year"),
    "geography (state)": ("state_abbr", 100, C.STRATA),
}
OUTCOMES = {"untimely": "slower (untimely response)", "unfavorable": "less favourable (closed without relief)"}
MIN_EVENTS = 30


def persistence(df, by, flag, min_n=50) -> pd.DataFrame:
    """'Systematic' = repeated: in how many years was the group worse than its product mix predicts?"""
    d = df.dropna(subset=[flag]).copy()
    d["_exp"] = d.groupby("product_name")[flag].transform("mean")
    g = d.groupby([by, "received_year"]).agg(n=(flag, "size"), obs=(flag, "sum"), exp=("_exp", "sum")).reset_index()
    g = g[g["n"] >= min_n]
    g["worse"] = g["obs"] > g["exp"]
    out = g.groupby(by).agg(years_observed=("worse", "size"), years_worse=("worse", "sum")).reset_index()
    out["persistent_worse"] = (out["years_observed"] >= 2) & (out["years_worse"] == out["years_observed"])
    return out


def validation_status() -> dict:
    status = {}
    for f in sorted(config.VALIDATION_DIR.glob("*.csv")):
        try:
            r = pd.read_csv(f)
            if "Status" in r:
                status[f.name] = r["Status"].value_counts().to_dict()
        except Exception as exc:
            status[f.name] = f"unreadable: {exc}"
    return status


def run(df: pd.DataFrame) -> None:
    C.ensure_dirs()
    lines = ["# Findings: is complaint resolution systematically slower / less favourable?\n",
             f"Data: {len(df):,} complaints, {df['period'].min():%Y-%m} to {df['period'].max():%Y-%m}. "
             "Groups are compared with a product-mix-adjusted expectation (indirect standardisation), "
             "exact Poisson tests, Benjamini-Hochberg FDR q<0.05.\n"]
    verdict_rows = []
    for flag, flag_label in OUTCOMES.items():
        events = int(df[flag].sum())
        lines.append(f"\n## Outcome: {flag_label}  (overall {100 * df[flag].mean():.2f}%, {events:,} events)\n")
        if events < MIN_EVENTS:
            msg = f"Only {events} events - too rare to compare groups. Widen CFPB_BULK_MIN_DATE and re-run the pipeline."
            lines.append(f"**Not testable:** {msg}\n"); logger.warning(msg); continue
        for dim, (col, min_n, strata) in DIMENSIONS.items():
            data = df.dropna(subset=[col])
            t = C.standardized_table(data, col, flag, strata=strata, min_n=min_n)
            if t.empty:
                continue
            if col in ("company_name", "state_abbr"):
                t = t.merge(persistence(data, col, flag), on=col, how="left")
            t.to_csv(C.TAB_DIR / f"insight_{flag}_{col}.csv", index=False)
            chi2, p, v = C.cramers_v(data, col, flag)
            worse, better = (t["signal"] == "WORSE than expected").sum(), (t["signal"] == "BETTER than expected").sum()
            verdict_rows.append({"outcome": flag, "dimension": dim, "groups_tested": len(t), "worse": worse,
                                 "better": better, "max_sir": t["sir"].max(), "cramers_v": v, "chi2_p": p})
            lines.append(f"### {dim}\n- {len(t)} groups tested; **{worse} worse**, {better} better than expected; "
                         f"association strength Cramer's V = {v:.3f} (p={p:.2g}).")
            for _, r in t[t["signal"] == "WORSE than expected"].head(5).iterrows():
                lines.append(f"  - {r[col]}: {r['rate_pct']:.2f}% vs expected {100 * r['expected'] / r['n']:.2f}% "
                             f"(SIR {r['sir']:.2f}, n={int(r['n']):,}, q={r['q_value']:.2g})")
            lines.append("")
    if df["unfavorable"].notna().any():
        s = C.standardized_table(df.dropna(subset=["state_abbr"]), "state_abbr", "unfavorable", C.STRATA, 100)
        s = s.merge(df.groupby("state_abbr")[["state_poverty_rate_pct", "state_median_income"]].first().reset_index(), on="state_abbr")
        if len(s) >= 10:
            for c in ("state_poverty_rate_pct", "state_median_income"):
                rho, p = stats.spearmanr(s[c], s["sir"], nan_policy="omit")
                lines.append(f"- State SIR (closed w/o relief) vs {c}: Spearman rho={rho:.2f}, p={p:.3f}, {len(s)} states")
    pd.DataFrame(verdict_rows).to_csv(C.TAB_DIR / "insight_verdict_summary.csv", index=False)
    (C.OUT_DIR / "findings.md").write_text("\n".join(lines), encoding="utf-8")

    manifest = {  # governed + auditable: which data produced these numbers, and did it pass validation?
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows_analysed": int(len(df)), "date_range": [str(df["period"].min().date()), str(df["period"].max().date())],
        "distinct_batch_ids": int(df["batch_id"].nunique()), "latest_batch_id": str(df["batch_id"].dropna().max()),
        "pct_still_open_excluded_from_unfavorable": round(100 * df["unfavorable"].isna().mean(), 2),
        "pct_fdic_matched": round(100 * df["institution_cert"].notna().mean(), 2),
        "pipeline_validation_status": validation_status(),
    }
    (C.OUT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("findings.md and run_manifest.json written to %s", C.OUT_DIR)


if __name__ == "__main__":
    setup_logging()
    run(C.load_fact())