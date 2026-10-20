"""Download and cache ZN futures prices from Yahoo Finance (yfinance).

Two sources:
  * individual contract months, e.g. ZNH22.CBT (preferred: roll-safe)
  * continuous front month ZN=F (fallback: needs roll neutralisation)
"""
from datetime import date, timedelta

import pandas as pd

from config.settings import RAW_DIR, ensure_dirs

MONTH_CODES = {"H": 3, "M": 6, "U": 9, "Z": 12}


def _cache_path(symbol: str, start: str, end: str):
    safe = symbol.replace("=", "_").replace(".", "_")
    return RAW_DIR / f"yf_{safe}_{start}_{end}.csv"


def download_daily(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Daily Close + Volume for one Yahoo symbol, cached in data/raw/.

    Intuition: cache first, network second. Yahoo can revise or delete
    history (expired contracts disappear), so the first successful download
    is frozen to disk and every later run reads exactly the same numbers.
    An empty result is cached too, so we don't re-ask Yahoo every run.
    """
    ensure_dirs()
    path = _cache_path(symbol, start, end)
    if path.exists():
        return pd.read_csv(path, index_col=0, parse_dates=True)

    import yfinance as yf  # imported lazily: tests never touch the network

    # yfinance's `end` is exclusive, so add one day to include `end` itself.
    end_incl = (pd.Timestamp(end) + timedelta(days=1)).strftime("%Y-%m-%d")
    raw = yf.download(symbol, start=start, end=end_incl, progress=False,
                      auto_adjust=False)
    if raw.empty:
        df = pd.DataFrame(columns=["close", "volume"])
    else:
        if isinstance(raw.columns, pd.MultiIndex):     # newer yfinance
            raw.columns = raw.columns.get_level_values(0)
        df = raw[["Close", "Volume"]].rename(columns=str.lower)
    df.index.name = "date"
    df.to_csv(path)
    return df


def contract_symbols(start: str, end: str) -> list:
    """Yahoo symbols for every ZN contract that could be front month in [start, end].

    Intuition: a contract is front month until it expires in its delivery
    month, so we need every quarterly contract from start's quarter to one
    quarter beyond end.
    """
    s, e = pd.Timestamp(start), pd.Timestamp(end) + pd.DateOffset(months=3)
    out = []
    for year in range(s.year, e.year + 1):
        for code, month in MONTH_CODES.items():
            expiry_month = pd.Timestamp(year=year, month=month, day=1)
            if s - pd.DateOffset(months=1) <= expiry_month <= e:
                out.append(f"ZN{code}{str(year)[-2:]}.CBT")
    return out


def probe_contracts(start: str, end: str) -> pd.DataFrame:
    """Try every individual contract for the period; report rows returned."""
    rows = []
    for sym in contract_symbols(start, end):
        df = download_daily(sym, start, end)
        rows.append({"symbol": sym, "rows": len(df),
                     "first": df.index.min() if len(df) else None,
                     "last": df.index.max() if len(df) else None})
    return pd.DataFrame(rows)


def load_continuous(start: str, end: str) -> pd.DataFrame:
    """Continuous front-month ZN=F with columns close, volume."""
    df = download_daily("ZN=F", start, end).dropna(subset=["close"])
    if df.empty:
        raise RuntimeError("Yahoo returned no ZN=F data for this period")
    return df


def load_contracts(start: str, end: str) -> dict:
    """{symbol: DataFrame} for individual contracts; raises if any is missing.

    Intuition: a stitched series with a hole would silently mis-state P&L,
    so we refuse rather than mix sources.
    """
    probe = probe_contracts(start, end)
    missing = probe.loc[probe["rows"] == 0, "symbol"].tolist()
    if missing:
        raise RuntimeError(
            f"Yahoo has no data for {missing}. Expired contract months are "
            "removed by Yahoo; use --price-source continuous.")
    return {s: download_daily(s, start, end) for s in probe["symbol"]}


def quality_report(df: pd.DataFrame, k: float = 5.0, window: int = 20) -> dict:
    """Row count, date range, missing business days, duplicates, outliers.

    Intuition: an outlier is a day whose change exceeds k times the recent
    typical move (rolling std of the previous `window` days). Using only
    PAST days means one huge move cannot hide itself by inflating its own std.
    """
    close = df["close"]
    chg = close.diff()
    roll_std = chg.rolling(window).std().shift(1)
    outliers = chg[(chg.abs() > k * roll_std) & roll_std.notna()]
    bdays = pd.bdate_range(close.index.min(), close.index.max())
    missing = bdays.difference(close.index)
    return {
        "rows": len(df),
        "first_date": close.index.min().date(),
        "last_date": close.index.max().date(),
        "duplicate_dates": int(close.index.duplicated().sum()),
        "missing_business_days": len(missing),
        "missing_dates": [d.date() for d in missing],
        "nan_closes": int(close.isna().sum()),
        "outlier_days": {d.date(): round(v, 4) for d, v in outliers.items()},
    }
