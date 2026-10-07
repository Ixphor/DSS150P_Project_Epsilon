"""Shared loading, outcome definitions and statistics for the analytics bonus."""
import logging

import numpy as np
import pandas as pd
from scipy import stats

from src.utils import config

logger = logging.getLogger(__name__)

FACT_ROOT = config.CURATED_DIR / "fact_complaints"
OUT_DIR = config.OUTPUT_DIR / "analytics"
FIG_DIR = OUT_DIR / "figures"
TAB_DIR = OUT_DIR / "tables"

COLUMNS = [
    "complaint_id", "received_year", "received_month", "response_lag_days",
    "company_name", "product_name", "state_abbr", "state_name",
    "state_median_income", "state_poverty_rate_pct", "institution_cert",
    "institution_name", "institution_asset_tier", "submitted_via",
    "company_response_to_consumer", "is_timely", "batch_id",
]

RELIEF = {"Closed with monetary relief", "Closed with non-monetary relief", "Closed with relief"}
OPEN = {"In progress"}

STRATA = ["product_name", "received_year"]
TIER_ORDER = ["Under $1B", "$1B - $10B", "$10B - $250B", "Over $250B", "Not FDIC-matched"]
esc = lambda s: str(s).replace("$", r"\$")

def ensure_dirs():
    for d in (FIG_DIR, TAB_DIR):
        d.mkdir(parents=True, exist_ok=True)


def derive(df: pd.DataFrame) -> pd.DataFrame:
    """Outcome flags: 1 = worse for the consumer, NaN = not measurable."""
    df = df.copy()
    df["untimely"] = df["is_timely"].map({True: 0, False: 1}).astype("float")
    resp = df["company_response_to_consumer"]
    closed = resp.notna() & ~resp.isin(OPEN)
    df["unfavorable"] = np.where(closed, (~resp.isin(RELIEF)).astype(float), np.nan)
    df["institution_group"] = df["institution_asset_tier"].fillna("Not FDIC-matched")
    df["state_abbr"] = df["state_abbr"].replace({"NA": np.nan})
    df["period"] = pd.to_datetime(dict(year=df["received_year"], month=df["received_month"], day=1))
    df = df[df["period"] <= df["period"].max() - pd.DateOffset(months=2)]
    return df


def load_fact(columns=None, since_year=None) -> pd.DataFrame:
    import pyarrow.dataset as ds

    if not FACT_ROOT.exists():
        raise FileNotFoundError(f"{FACT_ROOT} not found - run src.export.export_curated first")
    dataset = ds.dataset(FACT_ROOT, format="parquet", partitioning="hive")
    flt = (ds.field("received_year") >= since_year) if since_year else None
    df = dataset.to_table(columns=columns or COLUMNS, filter=flt).to_pandas()
    logger.info("Loaded %s complaints from %s", f"{len(df):,}", FACT_ROOT)
    return derive(df)


def wilson(k, n, z=1.96):
    k, n = np.asarray(k, float), np.asarray(n, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = k / n
        d = 1 + z**2 / n
        c = p + z**2 / (2 * n)
        a = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
        return (c - a) / d, (c + a) / d


def bh_fdr(p):
    """Benjamini-Hochberg adjusted p-values. NaNs stay NaN."""
    p = np.asarray(p, float)
    q = np.full_like(p, np.nan)
    ok = ~np.isnan(p)
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order] * len(pv) / (np.arange(len(pv)) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(pv)
    out[order] = np.clip(ranked, 0, 1)
    q[ok] = out
    return q


def rate_table(df, by, flag, min_n=30) -> pd.DataFrame:
    d = df.dropna(subset=[flag])
    g = d.groupby(by, observed=True)[flag].agg(n="size", events="sum").reset_index()
    g = g[g["n"] >= min_n].copy()
    g["rate_pct"] = 100 * g["events"] / g["n"]
    lo, hi = wilson(g["events"], g["n"])
    g["ci_low_pct"], g["ci_high_pct"] = 100 * lo, 100 * hi
    return g.sort_values("rate_pct", ascending=False).reset_index(drop=True)


def standardized_table(df, by, flag, strata="product_name", min_n=30) -> pd.DataFrame:
    """
    Indirect standardisation: expected = events if every complaint resolved at the overall
    rate of its product. SIR = observed / expected (>1 = worse than product mix explains).
    Exact Poisson test, BH-adjusted across groups.
    """
    d = df.dropna(subset=[flag]).copy()
    d["_exp"] = d.groupby(strata, observed=True)[flag].transform("mean") if strata else d[flag].mean()
    g = d.groupby(by, observed=True).agg(n=(flag, "size"), observed=(flag, "sum"), expected=("_exp", "sum")).reset_index()
    g = g[g["n"] >= min_n].copy()
    g["rate_pct"] = 100 * g["observed"] / g["n"]
    g["sir"] = g["observed"] / g["expected"].replace(0, np.nan)
    up = stats.poisson.sf(g["observed"] - 1, g["expected"])
    lo = stats.poisson.cdf(g["observed"], g["expected"])
    g["p_value"] = np.minimum(1.0, 2 * np.minimum(up, lo))
    g["q_value"] = bh_fdr(g["p_value"].to_numpy())
    g["signal"] = np.select(
        [(g["q_value"] < 0.05) & (g["sir"] > 1), (g["q_value"] < 0.05) & (g["sir"] < 1)],
        ["WORSE than expected", "BETTER than expected"], default="no clear signal")
    return g.sort_values("sir", ascending=False).reset_index(drop=True)


def cramers_v(df, by, flag):
    d = df.dropna(subset=[flag, by])
    tab = pd.crosstab(d[by], d[flag])
    if tab.shape[0] < 2 or tab.shape[1] < 2:
        return np.nan, np.nan, np.nan
    chi2, p, _, _ = stats.chi2_contingency(tab)
    return chi2, p, np.sqrt(chi2 / (tab.values.sum() * (min(tab.shape) - 1)))