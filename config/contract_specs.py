"""Load the ZN contract specification from data/contract_specs.csv.

Every number here was read from an official CME document; the CSV row holds
the source URL, the archived copy, the as-of date and the exact quoted text.
"""
import pandas as pd

from config.settings import DATA_DIR

SPECS_CSV = DATA_DIR / "contract_specs.csv"


def load_spec_table() -> pd.DataFrame:
    """Return the raw provenance table (one row per parameter)."""
    return pd.read_csv(SPECS_CSV, dtype={"value": str})


def load_spec() -> dict:
    """Build the spec dict the simulator uses, refusing unverified rows.

    Intuition: the multiplier is DERIVED (face value / 100 points) and then
    cross-checked against two independent CME statements ($1,000 per point
    and $15.625 per tick). If any check fails, the config is wrong and no
    P&L number can be trusted, so we stop immediately.
    """
    t = load_spec_table()
    bad = t[t["verified"].astype(str).str.lower() != "true"]
    if len(bad):
        raise ValueError(f"Unverified spec rows: {bad['parameter'].tolist()}")
    v = dict(zip(t["parameter"], t["value"]))

    face = float(v["face_value"])
    multiplier = face / 100          # 100 points = par, so 1 point = face/100 dollars
    tick_size = float(v["tick_size_points"])
    tick_value = float(v["tick_value_usd"])

    if multiplier != float(v["dollars_per_point"]):
        raise ValueError("face_value/100 disagrees with CME's stated $ per point")
    if abs(tick_size * multiplier - tick_value) > 1e-9:
        raise ValueError("tick_size x multiplier != tick_value")

    return {
        "name": "10-Year U.S. Treasury Note futures (CBOT)",
        "root": "ZN",
        "face_value": face,
        "multiplier": multiplier,        # $ per 1.00 point per contract
        "tick_size": tick_size,          # points
        "tick_value": tick_value,        # $
        "contract_months": v["contract_months"].split(","),
        "last_trade_bdays_before_month_end": int(v["last_trading_day_rule"]),
        "intention_notice_lead_bdays": int(v["intention_notice_lead_days"]),
    }


if __name__ == "__main__":
    for k, val in load_spec().items():
        print(f"{k:34s} {val}")
