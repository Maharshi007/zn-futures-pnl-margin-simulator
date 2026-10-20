"""Summary statistics, leverage table and rate-move table."""
import pandas as pd

from quotes import to_32nds


def summarize(ledger: pd.DataFrame, spec: dict, qty: int) -> dict:
    """Headline numbers for one run (all money in USD)."""
    first, last = ledger["close"].iloc[0], ledger["close"].iloc[-1]
    worst = ledger["daily_pnl"].idxmin()
    base = {
        "entry_price": f"{first:.6f} ({to_32nds(first)})",
        "exit_price": f"{last:.6f} ({to_32nds(last)})",
        "total_pnl": ledger["cum_pnl"].iloc[-1],
        "worst_day_pnl": ledger["daily_pnl"].min(),
        "worst_day": worst.date(),
        "best_day_pnl": ledger["daily_pnl"].max(),
        "best_day": ledger["daily_pnl"].idxmax().date(),
        "roll_days_neutralised": int(ledger["is_roll_day"].sum()),
        "underlying_pct_change": (last / first - 1) * 100,
        "notional_at_entry": first / 100 * spec["face_value"] * qty,
    }
    if "deposited" not in ledger.columns:          # P&L-only run
        return base
    initial_capital = ledger["deposited"].iloc[0]
    calls = ledger[ledger["margin_call"] > 0]
    return {**base,
        "num_margin_calls": len(calls),
        "calls_price_move": int((calls["call_reason"] == "price_move").sum()),
        "calls_margin_hike": int((calls["call_reason"] == "margin_hike").sum()),
        "total_margin_calls_usd": calls["margin_call"].sum(),
        "total_deposited": ledger["deposited"].iloc[-1],
        "final_balance": ledger["balance"].iloc[-1],
        "return_on_initial_margin_pct": ledger["cum_pnl"].iloc[-1] / initial_capital * 100,
        "effective_leverage": base["notional_at_entry"] / initial_capital,
    }


def leverage_table(price: float, spec: dict, qty: int, init_margin: float,
                   moves_pct=(0.5, 1, 2, 5)) -> pd.DataFrame:
    """How a % move in the futures price becomes a % move on margin.

    Notional = price/100 x face value (price is quoted per 100 of face).
    """
    notional = price / 100 * spec["face_value"] * qty
    rows = []
    for m in moves_pct:
        pnl = notional * m / 100
        rows.append({"price_move_%": m, "pnl_$": pnl,
                     "move_on_margin_%": pnl / (init_margin * qty) * 100})
    return pd.DataFrame(rows)


def rate_move_table(dv01: float, qty: int, init_margin: float = None,
                    bps=(1, 5, 10, 25)) -> pd.DataFrame:
    """P&L for a yield move, using the EMPIRICAL DV01 from validation.py.

    Intuition: traders think in basis points, not price points. A long
    loses DV01 x bp x qty when yields RISE; a short gains the same.
    """
    rows = []
    for bp in bps:
        pnl = dv01 * bp * qty
        row = {"yield_move_bp": bp,
               "long_pnl_if_yields_rise_$": -pnl,
               "short_pnl_if_yields_rise_$": pnl}
        if init_margin:                       # omitted while margins are unverified
            row["pct_of_initial_margin"] = pnl / (init_margin * qty) * 100
        rows.append(row)
    return pd.DataFrame(rows)
