"""Contract calendar, roll windows and roll-safe daily price changes.

Rules used (all from CME documents, see data/contract_specs.csv):
  * first delivery day   = first business day of the contract month (19104)
  * first intention day  = 2 business days before that              (19104.A)
  * last trading day     = 7 business days before the last business
                           day of the contract month          (contract specs)
"""
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

# US federal holidays approximate the CBOT Treasury calendar well enough to
# locate month-end business days; Good Friday is the main difference and
# never falls on a month boundary that matters here.
BDAY = CustomBusinessDay(calendar=USFederalHolidayCalendar())
MONTH_OF = {"H": 3, "M": 6, "U": 9, "Z": 12}

ROLL_WINDOW_LEAD_BDAYS = 5     # window opens 5 bdays before first intention day
VOLUME_JUMP = 10.0             # volume(t)/volume(t-1) that marks a contract switch


def contract_calendar(start: str, end: str, spec: dict) -> pd.DataFrame:
    """Key dates for each quarterly contract whose delivery month touches [start, end+3m].

    Intuition: every roll question ("when must I be out?", "when does Yahoo
    switch?") is answered by three dates derived from the CME rules above.
    """
    s = pd.Timestamp(start) - pd.DateOffset(months=1)
    e = pd.Timestamp(end) + pd.DateOffset(months=3)
    lead = spec["intention_notice_lead_bdays"]
    ltd_n = spec["last_trade_bdays_before_month_end"]
    rows = []
    for year in range(s.year, e.year + 1):
        for code in spec["contract_months"]:
            m0 = pd.Timestamp(year=year, month=MONTH_OF[code], day=1)
            if not (s <= m0 <= e):
                continue
            first_bday = m0 + 0 * BDAY if BDAY.is_on_offset(m0) else m0 + BDAY
            last_bday = (m0 + pd.offsets.MonthEnd(0))
            if not BDAY.is_on_offset(last_bday):
                last_bday = last_bday - BDAY
            fid = first_bday - lead * BDAY
            ltd = last_bday - ltd_n * BDAY
            rows.append({
                "contract": f"ZN{code}{str(year)[-2:]}",
                "first_intention_day": fid,
                "first_delivery_day": first_bday,
                "last_trading_day": ltd,
                "window_start": fid - ROLL_WINDOW_LEAD_BDAYS * BDAY,
                "window_end": ltd + 1 * BDAY,
            })
    return pd.DataFrame(rows)


def in_roll_window(dates: pd.DatetimeIndex, cal: pd.DataFrame) -> pd.Series:
    """Boolean Series: is each date inside any contract's roll window?"""
    flag = pd.Series(False, index=dates)
    for _, r in cal.iterrows():
        flag |= (dates >= r["window_start"]) & (dates <= r["window_end"])
    return flag


def detect_roll_days(df: pd.DataFrame, cal: pd.DataFrame,
                     jump: float = VOLUME_JUMP) -> pd.Series:
    """Mark the day the continuous series switched contract (ZN=F only).

    Intuition: Yahoo's ZN=F keeps quoting the expiring contract (volume
    collapses to a few thousand lots in the delivery month) and then jumps to
    the next contract, whose volume is ~1-2 million lots. That volume jump is
    unmistakable, whereas the PRICE gap between two ZN contracts is often
    smaller than a normal day's move, so a price-only test misses rolls.
    We accept at most ONE switch per roll window, and only inside a window,
    so a random volume spike elsewhere can never be called a roll.
    """
    ratio = df["volume"] / df["volume"].shift(1)
    is_roll = pd.Series(False, index=df.index)
    for _, r in cal.iterrows():
        w = ratio.loc[r["window_start"]:r["window_end"]]
        if len(w) and w.max() >= jump:
            is_roll[w.idxmax()] = True
    return is_roll


def continuous_changes(close: pd.Series, is_roll: pd.Series) -> pd.Series:
    """Day-on-day price change with roll days forced to 0.

    Intuition: on a roll day yesterday's close belongs to the OLD contract
    and today's to the NEW one; their difference is the calendar spread,
    not a profit or loss anybody earned. Zeroing it is conservative: we lose
    that day's genuine move but never book a fake one.
    """
    chg = close.diff().fillna(0.0)
    chg[is_roll.reindex(chg.index, fill_value=False)] = 0.0
    return chg


def roll_schedule(cal: pd.DataFrame, rule_bdays_before_fid: int = 1) -> pd.DataFrame:
    """For individual contracts: date to roll OUT of each contract.

    Rule: roll at the close 1 business day before the first intention day,
    i.e. the last day a long can hold without risk of being assigned delivery.
    """
    out = cal[["contract"]].copy()
    out["roll_date"] = cal["first_intention_day"] - rule_bdays_before_fid * BDAY
    return out.sort_values("roll_date").reset_index(drop=True)


def stitched_changes(closes: dict, schedule: pd.DataFrame) -> pd.DataFrame:
    """Roll-safe changes from individual contracts.

    closes   : {contract: pd.Series of closes}
    schedule : output of roll_schedule (contract, roll_date)

    Intuition: the change from t-1 to t is ALWAYS measured on the contract
    held overnight from t-1. If we roll at the close of day R, day R's change
    uses the old contract and day R+1's change uses the new one, so the gap
    between the two contracts never enters any change.
    """
    sched = schedule.sort_values("roll_date").reset_index(drop=True)

    def held_after_close(d):
        """Contract held after the close of day d."""
        later = sched[sched["roll_date"] > d]
        return later["contract"].iloc[0] if len(later) else sched["contract"].iloc[-1]

    dates = sorted(set().union(*[s.index for s in closes.values()]))
    rows = []
    for i, d in enumerate(dates):
        if i == 0:
            c = held_after_close(d)
            rows.append({"date": d, "contract": c, "close": closes[c][d],
                         "change": 0.0, "is_roll_day": False})
            continue
        prev = dates[i - 1]
        c = held_after_close(prev)                  # held overnight prev -> d
        rows.append({"date": d, "contract": c, "close": closes[c][d],
                     "change": closes[c][d] - closes[c][prev],
                     "is_roll_day": held_after_close(d) != c})
    return pd.DataFrame(rows).set_index("date")
