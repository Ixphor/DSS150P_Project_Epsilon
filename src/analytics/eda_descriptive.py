"""
EDA + visualisation + descriptive statistics on the curated fact Parquet.
    python -m src.analytics.eda_descriptive
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


def save(fig, name):
    fig.tight_layout()
    fig.savefig(C.FIG_DIR / f"{name}.png", dpi=150)
    plt.close(fig)
    logger.info("figure saved: %s.png", name)


def run(df: pd.DataFrame) -> None:
    C.ensure_dirs()
    overall_unfav, overall_late = df["unfavorable"].mean() * 100, df["untimely"].mean() * 100

    # 1. descriptive overview
    overview = pd.Series({
        "complaints": len(df), "date_from": df["period"].min().date(), "date_to": df["period"].max().date(),
        "companies": df["company_name"].nunique(), "products": df["product_name"].nunique(),
        "states_with_data": df["state_abbr"].nunique(),
        "pct_fdic_matched": round(100 * df["institution_cert"].notna().mean(), 2),
        "pct_missing_state": round(100 * df["state_abbr"].isna().mean(), 2),
        "untimely_rate_pct": round(overall_late, 3), "unfavorable_rate_pct": round(overall_unfav, 2),
        "pct_still_open": round(100 * df["unfavorable"].isna().mean(), 2),
    }, name="value")
    overview.to_csv(C.TAB_DIR / "eda_overview.csv")
    lag = df["response_lag_days"].describe(percentiles=[.5, .9, .99]).round(2)
    lag.to_csv(C.TAB_DIR / "eda_intake_lag_describe.csv")
    df["company_response_to_consumer"].value_counts(dropna=False).rename("n").to_csv(C.TAB_DIR / "eda_response_categories.csv")
    logger.info("overview:\n%s\nintake lag:\n%s", overview, lag)

    # 2. volume + outcomes over time
    m = df.groupby("period").agg(n=("complaint_id", "size"), late=("untimely", "mean"), unfav=("unfavorable", "mean"))
    fig, ax = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
    ax[0].plot(m.index, m["n"]); ax[0].set_ylabel("complaints")
    ax[1].plot(m.index, 100 * m["late"], color="tab:red"); ax[1].set_ylabel("% untimely")
    ax[2].plot(m.index, 100 * m["unfav"], color="tab:purple"); ax[2].set_ylabel("% closed w/o relief")
    ax[0].set_title("Monthly volume and resolution outcomes")
    save(fig, "eda_01_monthly_trend")

    # 3. product x outcome with CIs
    for flag, label in (("unfavorable", "closed without relief"), ("untimely", "untimely response")):
        t = (C.rate_table(df, "product_name", flag, min_n=100)
            .sort_values("n", ascending=False).head(15)
            .sort_values("rate_pct").reset_index(drop=True))
        fig, ax = plt.subplots(figsize=(9, 6))
        ax.errorbar(t["rate_pct"], t["product_name"], xerr=[t["rate_pct"] - t["ci_low_pct"], t["ci_high_pct"] - t["rate_pct"]], fmt="o")
        ax.axvline(100 * df[flag].mean(), ls="--", color="grey", label="overall")
        ax.set_xlabel(f"% {label} (95% Wilson CI)"); ax.legend()
        ax.set_title(f"Product categories: {label}")
        t.to_csv(C.TAB_DIR / f"eda_product_{flag}.csv", index=False)
        save(fig, f"eda_02_product_{flag}")

    # 4. institution group outcome mix
    mix = pd.crosstab(df["institution_group"], df["company_response_to_consumer"], normalize="index") * 100
    mix.to_csv(C.TAB_DIR / "eda_outcome_mix_by_institution_group.csv")
    mix = mix.reindex(C.TIER_ORDER)
    mix.index = [C.esc(i) for i in mix.index]
    ax = mix.plot(kind="barh", stacked=True, figsize=(10, 4)); ax.set_xlabel("% of complaints")
    ax.set_title("Company response by institution type (FDIC asset tier)"); ax.legend(fontsize=7, bbox_to_anchor=(1, 1))
    save(ax.figure, "eda_03_outcome_mix_institution")

    # 5. product x institution heatmap
    top = df["product_name"].value_counts().head(8).index
    sub = df[df["product_name"].isin(top)]
    h = sub.pivot_table(index="product_name", columns="institution_group", values="unfavorable", aggfunc="mean").reindex(columns=C.TIER_ORDER) * 100
    cnt = sub.pivot_table(index="product_name", columns="institution_group", values="complaint_id", aggfunc="size").reindex(columns=C.TIER_ORDER)
    h = h.where(cnt >= 100)
    fig, ax = plt.subplots(figsize=(9, 5)); im = ax.imshow(h.values, aspect="auto", cmap="Reds")
    ax.set_xticks(range(h.shape[1])); ax.set_xticklabels(h.columns, rotation=30, ha="right")
    ax.set_yticks(range(h.shape[0])); ax.set_yticklabels(h.index)
    ax.set_xticklabels([C.esc(c) for c in h.columns], rotation=30, ha="right")
    for i in range(h.shape[0]):
        for j in range(h.shape[1]):
            if not np.isnan(h.values[i, j]):
                ax.text(j, i, f"{h.values[i, j]:.0f}\nn={int(cnt.values[i, j]):,}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, label="% closed without relief"); ax.set_title("Product x institution type")
    save(fig, "eda_04_product_by_institution_heatmap")

    # 6. geography
    s = C.rate_table(df.dropna(subset=["state_abbr"]), "state_abbr", "unfavorable", min_n=100)
    s = s.merge(df.groupby("state_abbr")[["state_poverty_rate_pct", "state_median_income"]].first().reset_index(), on="state_abbr")
    s.to_csv(C.TAB_DIR / "eda_state_unfavorable.csv", index=False)
    rho, p = stats.spearmanr(s["state_poverty_rate_pct"], s["rate_pct"], nan_policy="omit")
    fig, ax = plt.subplots(figsize=(8, 6)); ax.scatter(s["state_poverty_rate_pct"], s["rate_pct"])
    for _, r in s.iterrows():
        ax.annotate(r["state_abbr"], (r["state_poverty_rate_pct"], r["rate_pct"]), fontsize=7)
    ax.set_xlabel("State poverty rate % (Census ACS)"); ax.set_ylabel("% closed without relief")
    ax.set_title(f"States: poverty vs. unfavourable outcome (Spearman rho={rho:.2f}, p={p:.3f})")
    save(fig, "eda_05_state_poverty_scatter")

    # 7. descriptive tests (significance AND effect size)
    rows = []
    for dim in ("product_name", "institution_group", "state_abbr", "submitted_via"):
        for flag in ("untimely", "unfavorable"):
            chi2, pv, v = C.cramers_v(df, dim, flag)
            rows.append({"dimension": dim, "outcome": flag, "chi2": chi2, "p_value": pv, "cramers_v": v})
    tests = pd.DataFrame(rows)
    tests["effect_size"] = pd.cut(tests["cramers_v"], [-1, .1, .3, 1], labels=["negligible/small", "moderate", "large"])
    tests.to_csv(C.TAB_DIR / "eda_association_tests.csv", index=False)
    logger.info("association tests:\n%s", tests)
    groups = [g["response_lag_days"].dropna().values for _, g in df.groupby("institution_group") if len(g) > 30]
    if len(groups) > 1:
        logger.info("Kruskal-Wallis intake lag across institution groups: %s", stats.kruskal(*groups))


if __name__ == "__main__":
    setup_logging()
    run(C.load_fact())