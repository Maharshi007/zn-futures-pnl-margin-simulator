"""Read CME clearing-advisory spreadsheets and write ZN rows into data/margins.csv.

Usage
  1. Open each advisory page listed in data/advisories_needed.csv in a normal
     browser (cmegroup.com blocks scripts, not browsers) and click
     "For the full text of this advisory, please click here" to download the .xlsx.
  2. Save it unchanged in data/raw/cme/advisories/ (e.g. Chadv22-018.xlsx).
  3. python import_advisories.py

Only values read from the spreadsheet are written, marked verified=true.
Advisories that contain no ZN outright row are recorded as 'no ZN change'.
"""
import re
from pathlib import Path

import pandas as pd

from config.settings import DATA_DIR, RAW_DIR
from margins import MARGINS_CSV

ADV_DIR = RAW_DIR / "cme" / "advisories"
NEEDED_CSV = DATA_DIR / "advisories_needed.csv"
ZN_CODE = "21"


def _header_row(df: pd.DataFrame) -> int:
    """Index of the row that contains the column titles.

    Intuition: CME sheets start with a few lines of notice text, so the
    real header is the first row mentioning a product/clearing code.
    """
    for i, row in df.iterrows():
        text = " ".join(str(v) for v in row.values).lower()
        if "code" in text and ("maint" in text or "rate" in text):
            return i
    raise ValueError("no header row found")


def zn_rows(xlsx: Path) -> pd.DataFrame:
    """All outright 10Y T-Note (clearing code 21) rows in one advisory file."""
    found = []
    for sheet, raw in pd.read_excel(xlsx, sheet_name=None, header=None, dtype=str).items():
        try:
            h = _header_row(raw)
        except ValueError:
            continue
        df = raw.iloc[h + 1:].copy()
        df.columns = [str(c).strip() for c in raw.iloc[h]]
        code_cols = [c for c in df.columns if re.search(r"code", c, re.I)]
        if not code_cols:
            continue
        is_zn = df[code_cols].apply(lambda s: s.astype(str).str.strip() == ZN_CODE).any(axis=1)
        text = df.astype(str).agg(" ".join, axis=1)
        outright = ~text.str.contains(r"\bvs\b|spread", case=False, regex=True)
        hit = df[is_zn & outright]
        if len(hit):
            hit = hit.assign(sheet=sheet, file=xlsx.name)
            found.append(hit)
    return pd.concat(found) if found else pd.DataFrame()


def new_maintenance(row: pd.Series) -> float:
    """Pick the NEW maintenance figure from a row (CME shows current and new)."""
    cols = [c for c in row.index if re.search(r"maint", c, re.I)]
    new = [c for c in cols if re.search(r"new", c, re.I)] or cols
    val = str(row[new[0]]).replace(",", "").replace("$", "").strip()
    return float(val)


def main() -> None:
    need = pd.read_csv(NEEDED_CSV, dtype=str)
    m = pd.read_csv(MARGINS_CSV, dtype=str)
    for _, adv in need.iterrows():
        path = ADV_DIR / f"{adv['advisory']}.xlsx"
        if not path.exists():
            print(f"[missing] {path.name}  <- download from {adv['notice_url']}")
            continue
        rows = zn_rows(path)
        m = m[~((m["kind"] == "advisory") & (m["notes"].str.contains(adv["advisory"], na=False)))]
        if rows.empty:
            print(f"[no ZN ] {path.name}: no outright 10Y T-Note row (ZN unchanged)")
            continue
        r = rows.iloc[0]
        maint = new_maintenance(r)
        tier = " ".join(str(r[c]) for c in r.index if re.search(r"period|month", c, re.I))
        print(f"[ZN    ] {path.name}: effective {adv['effective_date']} maintenance ${maint:,.0f} ({tier})")
        m.loc[len(m)] = [adv["effective_date"], "ZN", tier, maint, "advisory",
                         adv["notice_url"], "true",
                         f"{adv['advisory']} sheet '{r['sheet']}' read by import_advisories.py"]
    m.sort_values("effective_date").to_csv(MARGINS_CSV, index=False)
    print(f"\nWrote {MARGINS_CSV}")


if __name__ == "__main__":
    main()
