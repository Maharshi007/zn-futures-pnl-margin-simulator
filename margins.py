"""Margin (performance bond) timeline built only from verified CME documents.

data/margins.csv columns
  effective_date : date the rate applies from (end-of-day check on that date)
  product        : 'ZN'
  tier           : contract months covered, as printed by CME
  maintenance    : $ per contract
  kind           : 'advisory' (sets the timeline) or 'snapshot' (cross-check only)
  source_url     : official CME document
  verified       : true only if read directly from that document
  notes          : free text

data/margin_rules.csv holds the initial/maintenance ratio with its CME quote.
"""
import pandas as pd

from config.settings import DATA_DIR

MARGINS_CSV = DATA_DIR / "margins.csv"
RULES_CSV = DATA_DIR / "margin_rules.csv"


class MarginGateError(RuntimeError):
    """Raised when any simulated day lacks a verified margin."""


def _is_true(col: pd.Series) -> pd.Series:
    return col.astype(str).str.strip().str.lower() == "true"


def load_margins(product: str = "ZN") -> pd.DataFrame:
    """All margin rows for one product, sorted by effective date."""
    m = pd.read_csv(MARGINS_CSV, parse_dates=["effective_date"])
    m = m[m["product"] == product].copy()
    m["verified"] = _is_true(m["verified"])
    return m.sort_values("effective_date").reset_index(drop=True)


def initial_ratio() -> float:
    """Initial / maintenance ratio, refused unless the CME rule is verified."""
    r = pd.read_csv(RULES_CSV)
    row = r[r["parameter"] == "hrp_initial_to_maintenance"]
    if row.empty or not _is_true(row["verified"]).iloc[0]:
        raise MarginGateError("Initial-margin ratio is not verified in margin_rules.csv")
    return float(row["value"].iloc[0])


def margin_timeline(dates: pd.DatetimeIndex, margins: pd.DataFrame,
                    ratio: float) -> pd.DataFrame:
    """Maintenance and initial margin in force on each simulated date.

    Intuition: an advisory says "from date X the rate is Y". For any day d,
    the rate in force is the LAST advisory with effective_date <= d. That
    is exactly pd.merge_asof(direction="backward").

    Verification gate: we match against ALL advisory rows (verified or not).
    If the row in force on any day is unverified, or no row exists yet,
    we refuse to simulate - a made-up margin would make every margin-call
    number in the output fiction.
    """
    adv = margins[margins["kind"] == "advisory"]
    left = pd.DataFrame({"date": pd.DatetimeIndex(dates)}).sort_values("date")
    right = adv[["effective_date", "maintenance", "verified", "source_url"]] \
        .sort_values("effective_date")
    tl = pd.merge_asof(left, right, left_on="date", right_on="effective_date",
                       direction="backward")
    bad = tl[tl["maintenance"].isna() | ~tl["verified"].fillna(False).astype(bool)]
    if len(bad):
        first, last = bad["date"].min().date(), bad["date"].max().date()
        raise MarginGateError(
            f"{len(bad)} day(s) between {first} and {last} have no VERIFIED "
            "CME margin. Add the missing advisory to data/margins.csv "
            "(see data/SOURCES.md, section 4) - refusing to simulate.")
    tl["maint_per_contract"] = tl["maintenance"].astype(float)
    # Round to cents: 1.10 x 1600 is 1760.0000000000002 in binary floating point.
    tl["init_per_contract"] = (tl["maint_per_contract"] * ratio).round(2)
    return tl.set_index("date")[["maint_per_contract", "init_per_contract",
                                 "effective_date", "source_url"]]


def check_snapshots(tl: pd.DataFrame, margins: pd.DataFrame) -> pd.DataFrame:
    """Compare the advisory-built timeline with independent CME snapshots.

    Intuition: a snapshot of CME's live margin table is a second, independent
    observation. If the timeline disagrees with it, an advisory is missing.
    """
    snaps = margins[(margins["kind"] == "snapshot") & margins["verified"]]
    rows = []
    for _, s in snaps.iterrows():
        d = s["effective_date"]
        if tl.index.min() <= d <= tl.index.max():
            in_force = tl["maint_per_contract"].asof(d)
            rows.append({"snapshot_date": d.date(), "snapshot": s["maintenance"],
                         "timeline": in_force,
                         "match": float(in_force) == float(s["maintenance"])})
    return pd.DataFrame(rows)
