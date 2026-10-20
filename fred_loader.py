"""Download and cache official Federal Reserve data from FRED (fredapi).

DGS10     : 10-Year Treasury Constant Maturity yield, daily, percent
DFEDTARU  : Federal funds target range, upper limit, daily, percent
"""
import pandas as pd

from config.settings import RAW_DIR, ensure_dirs, get_fred_api_key

SERIES_URL = "https://fred.stlouisfed.org/series/{}"


def load_series(series_id: str, start: str, end: str) -> pd.Series:
    """One FRED series as a float Series, cached to data/raw/.

    Intuition: FRED marks bond-market holidays as missing (NaN). We keep
    them as NaN here and let the caller decide how to align with futures
    dates, rather than silently forward-filling a yield that never printed.
    """
    ensure_dirs()
    path = RAW_DIR / f"fred_{series_id}_{start}_{end}.csv"
    if path.exists():
        s = pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
    else:
        from fredapi import Fred
        s = Fred(api_key=get_fred_api_key()).get_series(
            series_id, observation_start=start, observation_end=end)
        s.index.name = "date"
        s.to_frame(series_id).to_csv(path)
    s.name = series_id
    return s.astype(float)


def fed_hike_dates(start: str, end: str) -> pd.DatetimeIndex:
    """Dates on which the Fed funds target upper bound rose.

    Look back one month before `start` so a hike on the first day of the
    window is still detected as a change.
    """
    pre = (pd.Timestamp(start) - pd.DateOffset(months=1)).strftime("%Y-%m-%d")
    s = load_series("DFEDTARU", pre, end).dropna()
    hikes = s[s.diff() > 0]
    return hikes.loc[start:end].index
