# Data Sources and Provenance

**Rule:** every number used in a calculation must appear in this file (or in a
downloaded dataset listed here) with a source URL and as-of date. Values that
could not be verified are marked `verified=false` and are **not used**.

**Access note:** `cmegroup.com` returns HTTP 403 to every scripted request
(curl, Python, WebFetch). Official CME documents were therefore read from
**Internet Archive (Wayback Machine) captures of the exact CME URLs**. A Wayback
capture is a byte-for-byte copy of the CME file as served on the capture date.
Both the original CME URL and the archived copy are recorded. Local copies are
in `data/raw/cme/`.

## 1. Parameters (single values)

| parameter | value | source URL | as-of date | how obtained | verified |
|---|---|---|---|---|---|
| face_value | $100,000 | [CBOT Rulebook Ch.19](https://www.cmegroup.com/content/dam/cmegroup/rulebook/CBOT/II/19.pdf) ([archive](https://web.archive.org/web/20220131091938/https://www.cmegroup.com/content/dam/cmegroup/rulebook/CBOT/II/19.pdf)) | 2022-01-31 | Rule 19102.B, text extracted with pdfplumber | true |
| dollars_per_point | $1,000 | same as above | 2022-01-31 | Rule 19102.C | true |
| multiplier (derived) | 1,000 = 100,000 / 100 | derived from face_value | n/a | face value / 100 points, then asserted equal to dollars_per_point | true |
| tick_size_points | 0.015625 (½ of 1/32) | [CME contract specs](https://www.cmegroup.com/trading/interest-rates/us-treasury/10-year-us-treasury-note_contractSpecs_futures.html) ([archive](https://web.archive.org/web/20210625003406/https://www.cmegroup.com/trading/interest-rates/us-treasury/10-year-us-treasury-note_contractSpecs_futures.html)) | 2021-06-25 | "Minimum Price Fluctuation" row | true |
| tick_value_usd | $15.625 | CBOT Rulebook Ch.19 (above) | 2022-01-31 | Rule 19102.C; test asserts tick_size × multiplier == tick_value | true |
| contract_months | H, M, U, Z (Mar/Jun/Sep/Dec) | CME contract specs (above) | 2021-06-25 | "Listed Contracts" row | true |
| last_trading_day_rule | 7 business days before last business day of contract month | CME contract specs (above) | 2021-06-25 | "Termination Of Trading" row | true |
| first_delivery_day_rule | first business day of contract month | CBOT Rulebook Ch.19 | 2022-01-31 | Rule 19104 | true |
| intention_notice_lead_days | 2 business days | CBOT Rulebook Ch.19 | 2022-01-31 | Rule 19104.A | true |
| hrp_initial_to_maintenance | 1.10 | [CME Performance Bonds/Margins](https://www.cmegroup.com/clearing/risk-management/performance-bonds-margins.html) ([archive](https://web.archive.org/web/20220526173049/https://www.cmegroup.com/clearing/risk-management/performance-bonds-margins.html)) | 2022-05-26 | quoted in §3 | true |
| call_tops_up_to_initial | rule | same as above | 2022-05-26 | quoted in §3 | true |
| ZN maintenance (snapshot) 2021-07-08 | $1,525 | [CME margins API, code 21](https://web.archive.org/web/20210708152845/https://www.cmegroup.com/CmeWS/mvc/Margins/OUTRIGHT?1=1&sortField=exchange&sortAsc=true&clearingCode=21&sector=INTEREST%20RATES&exchange=CBT&pageSize=12&pageNumber=1&isProtected&_t=1625758125618) | 2021-07-08 | JSON field `maintenanceRate: "1,525 USD"`; cross-check only | true |
| ZN maintenance (snapshot) 2022-03-23 | $1,600 | [CME margins CSV](https://web.archive.org/web/20220324010927/https://www.cmegroup.com/CmeWS/mvc/Margins/OUTRIGHT.csv) | 2022-03-23 (captured 2022-03-24 01:09 UTC) | CSV row `10Y TREASURY NOTE FUTURES, 21, 03/2022–12/2022, 1600`; cross-check only | true |

## 2. Downloaded datasets

| dataset | provider / series | source URL | period | cached file | downloaded on |
|---|---|---|---|---|---|
| ZN continuous front month | Yahoo Finance `ZN=F` via yfinance | https://finance.yahoo.com/quote/ZN=F | 2022-01-03 → 2022-12-30 | `data/raw/yf_ZN_F_2022-01-03_2022-12-30.csv` | 2026-10-20 |
| ZN individual months (probe) | Yahoo `ZNH22.CBT`, `ZNM22.CBT`, `ZNU22.CBT`, `ZNZ22.CBT`, `ZNH23.CBT` | https://finance.yahoo.com | 2022 | `data/raw/yf_ZN*_CBT_*.csv` (all empty: Yahoo returns 404 for expired months) | 2026-10-20 |
| 10Y Treasury yield | FRED `DGS10` (Board of Governors H.15, percent, daily) | https://fred.stlouisfed.org/series/DGS10 | 2022-01-03 → 2022-12-30 | `data/raw/fred_DGS10_2022-01-03_2022-12-30.csv` | 2026-10-20 |
| Fed funds target upper bound | FRED `DFEDTARU` (percent, daily) | https://fred.stlouisfed.org/series/DFEDTARU | 2021-12-03 → 2022-12-30 | `data/raw/fred_DFEDTARU_2021-12-03_2022-12-30.csv` | 2026-10-20 |
| CBOT Rulebook Chapter 19 | CME Group | see §1 | as of 2022-01-31 | `data/raw/cme/CBOT_rulebook_ch19_20220131.pdf` (+ `.txt`) | 2026-10-20 |
| ZN contract-specs page | CME Group | see §1 | as of 2021-06-25 and 2022-03-12 | `data/raw/cme/CME_ZN_specs_oldpage_20210625.html`, `CME_ZN_specs_page_20220312.html` | 2026-10-20 |
| Performance bonds page | CME Group | see §1 | as of 2022-05-26 | `data/raw/cme/CME_performance_bonds_page_20220526.html` | 2026-10-20 |
| CME margin snapshots | CME Group | see §1 | 2021-07-08, 2022-03-23 | `data/raw/cme/margins/` | 2026-10-20 |

## 3. Quoted rules (exchange text used to set logic)

| rule | quoted text | source URL | as-of date |
|---|---|---|---|
| Last trading day (sets when ZN=F switches contract) | "Trading terminates at 12:01 p.m. on the 7th business day prior to the last business day of the contract month." | CME contract specs (archive 2021-06-25) | 2021-06-25 |
| Delivery month (sets the roll window) | "Deliveries against an expiring contract can be made no earlier than the first business day of the contract's named month of expiration" (Rule 19104) | CBOT Rulebook Ch.19 (archive 2022-01-31) | 2022-01-31 |
| Intention day (why traders roll at end of Feb/May/Aug/Nov) | "No later than 6:00 p.m. on the second business day preceding the intended day of delivery, the short Clearing Member must tender to the Clearing House all notices of intention to make delivery" (Rule 19104.A) | CBOT Rulebook Ch.19 | 2022-01-31 |
| Initial = 110% × maintenance | "Heightened Risk Profile ("HRP") initial margin requirements for all products are set at 110% of the maintenance margin requirement for a given product." | CME Performance Bonds/Margins (archive 2022-05-26) | 2022-05-26 |
| Margin call restores initial | "If subsequently margin equity falls below maintenance margin, a call must be issued to bring the account up to initial margin." | same | 2022-05-26 |

## 4. Unverified / pending values

| parameter | why not verified | how to complete it |
|---|---|---|
| ZN maintenance margin timeline 2022 (`kind=advisory` rows in `data/margins.csv`) | CME published the 2022 interest-rate margin tables as `.xlsx` attachments to clearing advisories. cmegroup.com blocks scripts (HTTP 403) and the Wayback Machine never archived the `.xlsx` files. None of the 172 archived 2021–22 advisory PDFs contains an outright ZN row. | Download each advisory listed in `data/advisories_needed.csv` in a browser, save it to `data/raw/cme/advisories/`, then run `python import_advisories.py`. The list holds 67 "Interest Rate" performance-bond advisories effective 2021-09-02 → 2022-12-02 (45 in 2022), built from Wayback captures of the notice pages. 75 of 587 notice pages could not be fetched, so cross-check against CME's advisory search filtered to "Performance Bond" and "Interest Rate". **Status: this version ships P&L-only; the margin run stays gated.** |

## 5. Methodology parameters (choices, not market data)

These are design choices, explained in `DECISIONS.md`. They are not facts about the market, so they have no external source.

| parameter | value | where |
|---|---|---|
| Default period | 2022-01-03 → 2022-12-30 | `config/settings.py` |
| Roll window opens | 5 business days before first intention day | `rolls.ROLL_WINDOW_LEAD_BDAYS` |
| Roll window closes | 1 business day after last trading day | `rolls.contract_calendar` |
| Contract-switch volume jump | volume(t) / volume(t−1) ≥ 10 | `rolls.VOLUME_JUMP` |
| Roll rule (individual contracts) | close 1 business day before first intention day | `rolls.roll_schedule` |
| Outlier flag | \|daily change\| > 5 × rolling 20-day std (past days only) | `data_loader.quality_report` |
