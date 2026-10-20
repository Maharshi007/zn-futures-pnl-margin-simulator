"""Daily mark-to-market simulation of a ZN futures position."""
import pandas as pd

from quotes import to_32nds


def simulate(prices: pd.DataFrame, side: str, qty: int, spec: dict,
             margin_tl: pd.DataFrame) -> pd.DataFrame:
    """Day-by-day P&L, margin balance and margin calls.

    prices    : index=date, columns close, change (roll-safe, points), is_roll_day
    margin_tl : index=date, columns maint_per_contract, init_per_contract

    Entry at the first close with initial margin deposited. Each later day:
      1. P&L = direction x change x multiplier x qty   (change is 0 on roll days)
      2. balance += P&L
      3. if balance < maintenance x qty -> call = initial x qty - balance
         call_reason = 'margin_hike' if yesterday's requirement would NOT have
         triggered a call (only the CME increase did), else 'price_move'.
      4. assert balance == deposited + cum_pnl  (accounting identity)

    Intuition: a futures account is a state machine. Today's state depends
    only on yesterday's state, today's price change and today's rules.
    """
    if side not in ("long", "short"):
        raise ValueError("side must be 'long' or 'short'")
    if qty < 1:
        raise ValueError("qty must be >= 1")
    direction = 1 if side == "long" else -1
    mult = spec["multiplier"]
    tl = margin_tl.reindex(prices.index)
    if tl["maint_per_contract"].isna().any():
        raise ValueError("margin timeline does not cover every price date")

    first = prices.index[0]
    balance = deposited = tl.at[first, "init_per_contract"] * qty
    cum_pnl = 0.0
    prev_maint_total = tl.at[first, "maint_per_contract"] * qty
    rows = [_row(first, prices.loc[first], 0.0, 0.0, tl.loc[first], qty,
                 balance, 0.0, "", balance, deposited)]

    for date in prices.index[1:]:
        p, m = prices.loc[date], tl.loc[date]
        daily_pnl = direction * p["change"] * mult * qty + 0.0   # avoid -0.0 on roll days
        cum_pnl += daily_pnl
        balance += daily_pnl
        before_call = balance

        maint_total = m["maint_per_contract"] * qty
        init_total = m["init_per_contract"] * qty
        call, reason = 0.0, ""
        if balance < maint_total:
            call = init_total - balance             # top up to INITIAL
            reason = ("margin_hike"
                      if balance >= prev_maint_total and maint_total > prev_maint_total
                      else "price_move")
            balance += call
            deposited += call

        assert abs(balance - (deposited + cum_pnl)) < 1e-6, f"identity broken {date}"
        rows.append(_row(date, p, p["change"], daily_pnl, m, qty, before_call,
                         call, reason, balance, deposited, cum_pnl))
        prev_maint_total = maint_total

    return pd.DataFrame(rows).set_index("date")


def pnl_path(prices: pd.DataFrame, side: str, qty: int, spec: dict) -> pd.DataFrame:
    """P&L only, with no margin account. Used while margins are unverified.

    Intuition: P&L depends only on price changes, multiplier, quantity and
    direction. Margin decides how much CASH you need, not how much you make,
    so these numbers are valid even when the margin gate is closed.
    """
    if side not in ("long", "short"):
        raise ValueError("side must be 'long' or 'short'")
    direction = 1 if side == "long" else -1
    out = pd.DataFrame(index=prices.index)
    out["close"] = prices["close"]
    out["close_32nds"] = prices["close"].map(to_32nds)
    out["is_roll_day"] = prices["is_roll_day"].astype(bool)
    out["change_pts"] = prices["change"]
    out["daily_pnl"] = direction * prices["change"] * spec["multiplier"] * qty + 0.0  # +0.0 turns -0.0 into 0.0
    out.iloc[0, out.columns.get_loc("daily_pnl")] = 0.0
    out["cum_pnl"] = out["daily_pnl"].cumsum()
    return out


def _row(date, p, change, daily_pnl, m, qty, before_call, call, reason,
         balance, deposited, cum_pnl=0.0) -> dict:
    """One ledger line. Prices shown in decimals AND in 32nds."""
    return {
        "date": date,
        "close": p["close"],
        "close_32nds": to_32nds(p["close"]),
        "is_roll_day": bool(p.get("is_roll_day", False)),
        "change_pts": change,
        "daily_pnl": daily_pnl,
        "cum_pnl": cum_pnl,
        "maint_per_contract": m["maint_per_contract"],
        "init_per_contract": m["init_per_contract"],
        "maint_total": m["maint_per_contract"] * qty,
        "balance_before_call": before_call,
        "margin_call": call,
        "call_reason": reason,
        "balance": balance,
        "deposited": deposited,
    }
