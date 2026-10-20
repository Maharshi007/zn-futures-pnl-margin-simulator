"""Glue: turn (start, end, price source) into roll-safe prices + margin timeline.

Kept separate from main.py so tests and notebooks can call the same steps
without going through argparse.
"""
import pandas as pd

import data_loader
import fred_loader
import margins
import rolls
import validation
from config.contract_specs import load_spec


def build_prices(start: str, end: str, source: str, spec: dict) -> pd.DataFrame:
    """Roll-safe price table: close, change (points), is_roll_day.

    'contracts'  : stitch individual months on the fixed roll schedule.
    'continuous' : ZN=F with roll days detected and their change set to 0.
    """
    cal = rolls.contract_calendar(start, end, spec)
    if source == "contracts":
        closes = {sym.split(".")[0]: df["close"]
                  for sym, df in data_loader.load_contracts(start, end).items()}
        out = rolls.stitched_changes(closes, rolls.roll_schedule(cal))
        return out.loc[start:end]
    df = data_loader.load_continuous(start, end)
    is_roll = rolls.detect_roll_days(df, cal)
    return pd.DataFrame({
        "close": df["close"],
        "change": rolls.continuous_changes(df["close"], is_roll),
        "is_roll_day": is_roll,
    })


def run_validation(prices: pd.DataFrame, start: str, end: str, spec: dict) -> dict:
    """FRED validation 1 (correlation) and 2 (empirical DV01)."""
    d = validation.align_changes(prices["close"],
                                 fred_loader.load_series("DGS10", start, end),
                                 prices["is_roll_day"])
    dv = validation.empirical_dv01(d, spec["multiplier"])
    dv["correlation"] = validation.correlation(d)
    dv["aligned"] = d
    return dv


def prepare(start: str, end: str, source: str = "continuous",
            pnl_only: bool = False) -> dict:
    """Everything the simulator needs, with all gates applied.

    pnl_only=True skips margins entirely (no margin number is read or used).
    """
    spec = load_spec()
    prices = build_prices(start, end, source, spec)
    if pnl_only:
        return {"spec": spec, "prices": prices, "timeline": None}
    m = margins.load_margins("ZN")
    tl = margins.margin_timeline(prices.index, m, margins.initial_ratio())
    return {"spec": spec, "prices": prices, "margins": m, "timeline": tl,
            "snapshots": margins.check_snapshots(tl, m)}
