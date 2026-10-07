"""
Advanced analytics supporting the answer:
  A. Adjusted logistic regression - do institution type / geography matter after product mix?
  B. Funnel-plot anomaly detection - which companies are outliers given size and product mix?
  C. Geospatial - product-adjusted state map.
    python -m src.analytics.advanced
"""
import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from src.analytics import common as C
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)
MIN_EVENTS = 200
TOP_PRODUCTS = 12


def adjusted_regression(df: pd.DataFrame, flag: str) -> None:
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    d = df.dropna(subset=[flag, "state_abbr", "state_poverty_rate_pct"]).copy()
    if d[flag].sum() < MIN_EVENTS:
        logger.warning("%s: only %d events (<%d) - regression skipped", flag, d[flag].sum(), MIN_EVENTS)
        return
    top = d["product_name"].value_counts().head(TOP_PRODUCTS).index
    d["product"] = np.where(d["product_name"].isin(top), d["product_name"], "Other")
    d["year"] = d["received_year"].astype(str)
    cells = (d.groupby(["product", "institution_group", "submitted_via", "year", "state_abbr", "state_poverty_rate_pct"], observed=True)[flag]
               .agg(events="sum", n="size").reset_index())
    cells["rate"] = cells["events"] / cells["n"]
    cells["poverty_z"] = (cells["state_poverty_rate_pct"] - cells["state_poverty_rate_pct"].mean()) / cells["state_poverty_rate_pct"].std()
    prod_levels = d["product"].value_counts().index.tolist()          # most common product = reference
    inst_levels = ["Not FDIC-matched"] + [g for g in cells["institution_group"].unique() if g != "Not FDIC-matched"]
    cells["product"] = pd.Categorical(cells["product"], categories=prod_levels)
    cells["institution_group"] = pd.Categorical(cells["institution_group"], categories=inst_levels)
    formula = "rate ~ product + institution_group + submitted_via + year + poverty_z"
    model = smf.glm(formula, data=cells, family=sm.families.Binomial(), freq_weights=cells["n"]).fit()
    ci = model.conf_int()
    res = pd.DataFrame({"term": model.params.index, "odds_ratio": np.exp(model.params.values),
                        "or_ci_low": np.exp(ci[0].values), "or_ci_high": np.exp(ci[1].values), "p_value": model.pvalues.values})
    res = res[res["term"] != "Intercept"].sort_values("p_value")
    res.to_csv(C.TAB_DIR / f"adv_regression_{flag}.csv", index=False)
    logger.info("[%s] adjusted odds ratios (n_cells=%d):\n%s", flag, len(cells), res.head(10).to_string(index=False))

    inst = res[res["term"].str.contains("institution_group")].iloc[::-1]
    if len(inst):
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.errorbar(inst["odds_ratio"], inst["term"].str.extract(r"\[T\.(.*)\]")[0],
                    xerr=[inst["odds_ratio"] - inst["or_ci_low"], inst["or_ci_high"] - inst["odds_ratio"]], fmt="o")
        ax.axvline(1, color="grey", ls="--"); ax.set_xlabel("Adjusted odds ratio vs non-FDIC-matched (95% CI)")
        ax.set_title(f"Institution type effect on '{flag}' after product/channel/year/poverty control")
        fig.tight_layout(); fig.savefig(C.FIG_DIR / f"adv_forest_{flag}.png", dpi=150); plt.close(fig)


def funnel(df: pd.DataFrame, flag: str, min_n: int = 100) -> None:
    t = C.standardized_table(df.dropna(subset=["company_name"]), "company_name", flag, C.STRATA, min_n)
    if t.empty or t["observed"].sum() < 30:
        logger.warning("%s: funnel skipped (too few events)", flag); return
    E = np.logspace(np.log10(max(t["expected"].min(), 0.5)), np.log10(t["expected"].max()), 200)
    hi95, hi998 = stats.poisson.ppf(.975, E) / E, stats.poisson.ppf(.999, E) / E
    lo95, lo998 = stats.poisson.ppf(.025, E) / E, stats.poisson.ppf(.001, E) / E
    t["outlier"] = np.where(t["observed"] > stats.poisson.ppf(.999, t["expected"]), "above 99.8% limit",
                    np.where(t["observed"] < stats.poisson.ppf(.001, t["expected"]), "below 99.8% limit", "within limits"))
    t.to_csv(C.TAB_DIR / f"adv_funnel_{flag}.csv", index=False)
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(t["expected"], t["sir"], s=14, c=np.where(t["outlier"] == "above 99.8% limit", "tab:red", "tab:blue"))
    for q, lo, hi, ls in ((95, lo95, hi95, ":"), (99.8, lo998, hi998, "--")):
        ax.plot(E, hi, "k", ls=ls, lw=1, label=f"{q}% limits"); ax.plot(E, lo, "k", ls=ls, lw=1)
    ax.axhline(1, color="grey"); ax.set_xscale("log"); ax.set_xlabel("expected events (size x product mix)")
    ax.set_ylabel("SIR = observed / expected")
    for _, r in t[t["outlier"] == "above 99.8% limit"].head(8).iterrows():
        ax.annotate(str(r["company_name"])[:22], (r["expected"], r["sir"]), fontsize=7)
    ax.set_title(f"Company funnel plot - {flag}"); ax.legend()
    fig.tight_layout(); fig.savefig(C.FIG_DIR / f"adv_funnel_{flag}.png", dpi=150); plt.close(fig)
    logger.info("[%s] %d of %d companies above the 99.8%% limit", flag, (t["outlier"] == "above 99.8% limit").sum(), len(t))


def state_map(df: pd.DataFrame, flag: str = "unfavorable") -> None:
    s = C.standardized_table(df.dropna(subset=["state_abbr"]), "state_abbr", flag, C.STRATA, 100)
    if s.empty:
        return
    s.to_csv(C.TAB_DIR / f"adv_state_{flag}.csv", index=False)
    try:
        import plotly.express as px
    except ImportError:
        logger.warning("plotly not installed - state map skipped (table still written)"); return
    fig = px.choropleth(s, locations="state_abbr", locationmode="USA-states", color="sir", scope="usa",
                        color_continuous_scale="RdBu_r", color_continuous_midpoint=1,
                        hover_data=["n", "rate_pct", "q_value", "signal"],
                        title=f"State SIR for '{flag}' (1.0 = as expected for product mix)")
    fig.write_html(C.FIG_DIR / f"adv_state_map_{flag}.html")


def run(df: pd.DataFrame) -> None:
    C.ensure_dirs()
    for flag in ("unfavorable", "untimely"):
        try:
            adjusted_regression(df, flag)
        except ImportError:
            logger.warning("statsmodels not installed - regression skipped")
        funnel(df, flag)
    state_map(df)


if __name__ == "__main__":
    setup_logging()
    run(C.load_fact())