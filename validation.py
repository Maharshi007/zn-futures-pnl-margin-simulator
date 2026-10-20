"""Validate ZN prices against the official 10Y yield and measure DV01.

Validation 1: correlation of daily ZN price changes with daily DGS10 changes.
Validation 2: OLS slope of price change on yield change -> empirical DV01.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import statsmodels.api as sm


def align_changes(close: pd.Series, dgs10: pd.Series, is_roll: pd.Series) -> pd.DataFrame:
    """Join futures closes with yields on common dates; daily changes of both.

    Intuition: futures trade on some days when the bond market is shut
    (e.g. Columbus Day), so FRED has NaN there. We keep only dates where BOTH
    exist and difference across those, so each price change and yield change
    cover exactly the same interval.
    """
    d = pd.DataFrame({"close": close, "yld": dgs10}).dropna()
    d["dP"] = d["close"].diff()                  # points
    d["dY"] = d["yld"].diff()                    # percentage points
    d["is_roll_day"] = is_roll.reindex(d.index, fill_value=False)
    return d.dropna(subset=["dP", "dY"])


def correlation(d: pd.DataFrame) -> float:
    """Validation 1: Pearson correlation on non-roll days (expect ~ -1)."""
    clean = d[~d["is_roll_day"]]
    return float(clean["dP"].corr(clean["dY"]))


def empirical_dv01(d: pd.DataFrame, multiplier: float) -> dict:
    """Validation 2: regress dP (points) on dY (percentage points).

    slope b = points gained per +1.00 pp yield move (negative).
    1 pp = 100 bp, so DV01 per contract = -b / 100 * multiplier  ($ per bp)
    implied duration = -b / (average price) * 100
        because  dP/P = -D * dY_decimal  and  dY_decimal = dY_pp / 100.

    Intuition: we don't trust a textbook duration; we let one year of real
    data tell us how many dollars a contract actually moved per basis point.
    """
    clean = d[~d["is_roll_day"]]
    X = sm.add_constant(clean["dY"])
    fit = sm.OLS(clean["dP"], X).fit()
    b = float(fit.params["dY"])
    ci_lo, ci_hi = fit.conf_int().loc["dY"]
    avg_price = float(clean["close"].mean())
    return {
        "slope_points_per_pp": b,
        "slope_ci95": (float(ci_lo), float(ci_hi)),
        "r_squared": float(fit.rsquared),
        "n_days": int(fit.nobs),
        "dv01_usd_per_bp": -b / 100 * multiplier,
        "dv01_ci95": (-ci_hi / 100 * multiplier, -ci_lo / 100 * multiplier),
        "avg_price": avg_price,
        "implied_duration": -b / avg_price * 100,
        "intercept": float(fit.params["const"]),
    }


def scatter_plot(d: pd.DataFrame, dv: dict, out_path) -> None:
    """Scatter of dP vs dY with the fitted line; roll days shown separately."""
    clean, rolls = d[~d["is_roll_day"]], d[d["is_roll_day"]]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(clean["dY"] * 100, clean["dP"], s=12, alpha=0.6,
               label="Normal day")
    if len(rolls):
        ax.scatter(rolls["dY"] * 100, rolls["dP"], s=40, marker="x",
                   color="red", label="Roll day (excluded)")
    xs = pd.Series([clean["dY"].min(), clean["dY"].max()])
    ax.plot(xs * 100, dv["intercept"] + dv["slope_points_per_pp"] * xs,
            color="black", lw=1,
            label=f"OLS: DV01 ≈ ${dv['dv01_usd_per_bp']:.2f}/bp, R² {dv['r_squared']:.2f}")
    ax.axhline(0, lw=0.5, color="grey"); ax.axvline(0, lw=0.5, color="grey")
    ax.set_xlabel("Daily change in 10Y Treasury yield, DGS10 (bp)")
    ax.set_ylabel("Daily change in ZN price (points)")
    ax.set_title("ZN price change vs 10Y yield change")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(out_path, dpi=120); plt.close(fig)
