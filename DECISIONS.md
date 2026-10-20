# Design Decisions

Each entry records what was chosen, why, and why the alternatives were rejected.

---

## A. Scope and domain

### A1. Market: US 10-Year T-Note futures (CBOT `ZN`) only
- **Chosen because:** ZN is the benchmark US interest-rate future and the most liquid point on the Treasury futures curve, so it exercises the rates mechanics (price vs yield, DV01, 32nds, delivery rolls) that equity or commodity futures don't.
- **Not ES / CL / GC:** equity, energy and metals futures share the margin mechanics but have no yield, DV01 or 32nds quoting.
- **Not 2Y/5Y/30Y or SOFR futures:** one contract done properly is better than several done thinly. The code takes the spec from a CSV, so another tenor can be added later.

### A2. Default period: 2022-01-03 → 2022-12-30
- **Chosen because:** the Fed raised rates 7 times (0.25% → 4.50%, from FRED `DFEDTARU`), the 10Y yield rose sharply, and margins were reviewed often. That gives big moves, real margin calls and a clear directional story.
- **Not a calm year (e.g. 2019):** there would be few margin calls and little to learn.
- **Not 2020:** the COVID shock is dominated by a single event, and Treasury futures liquidity was disrupted.

---

## B. Data sources

### B1. Contract specs from official CME documents, read via Wayback Machine captures
- **Chosen because:** the exchange is the only source of truth for contract terms. `cmegroup.com` returns HTTP 403 to every scripted client, so we read Internet Archive captures of the **exact CME URLs**. These are unmodified copies of the CME files as served on the capture date.
- **Not broker or third-party sites (Barchart, Investopedia):** they are not the official source and can be outdated.
- **Not values from memory:** that breaks the "no invented numbers" rule.
- **Two independent documents (rulebook + specs page):** the face value, $1,000 per point and $15.625 tick are cross-checked against each other in code (`config/contract_specs.py`).

### B2. Prices: yfinance, continuous `ZN=F` (individual contracts tested first)
- **Tested first:** individual months `ZNH22.CBT … ZNH23.CBT`. Yahoo returns HTTP 404 for all of them because it deletes expired contracts, so stitching is impossible for 2022.
- **Fallback chosen:** `ZN=F` (251 rows, no duplicates, no outliers, and the 9 missing days are all US holidays).
- **Not CME DataMine / Bloomberg / Refinitiv:** they are paid or require institutional access.
- **Not Nasdaq Data Link continuous futures:** the free Wiki continuous futures feed was discontinued, and it would need another API key with similar roll issues.
- **Kept the `--price-source contracts` path anyway:** it works for current or future periods where Yahoo still lists the months, and it is the roll-safe method (see C3).

### B3. Official yields from FRED (`fredapi`): `DGS10` and `DFEDTARU`
- **Chosen because:** FRED republishes the Federal Reserve's H.15 data. It is official, free, versioned and has a stable API. `DGS10` is the yield traders quote for "the 10-year".
- **Not Yahoo `^TNX`:** it is a CBOE index scaled by 10, not the official series, and Yahoo can revise it silently.
- **Not the Treasury.gov XML feed:** it gives the same numbers in a more awkward format, and `fredapi` already handles caching and dates.

### B4. API key in `.env` via `python-dotenv`
- **Why:** keys in source code end up on GitHub. `.env` is listed in `.gitignore`, and a test checks that.
- **Not OS environment variables only:** that's harder for a beginner to set up on Windows, and `.env` is the common convention.

### B5. Cache every download in `data/raw/`, and never re-download
- **Why:** reproducibility. Yahoo revises and deletes data, so the first successful download is frozen. Empty responses are cached too, so the contract probe doesn't hit Yahoo on every run.
- **Not a database:** a few thousand rows fit easily in CSV, and CSVs can be opened and checked in Excel.

---

## C. Rolls

### C1. Roll timing follows CME rules, not a guessed date
- **First intention day** = 2 business days before the first business day of the contract month (Rule 19104.A). This is the end of Feb, May, Aug and Nov. Traders roll before it to avoid being assigned delivery.
- **Last trading day** = 7 business days before the last business day of the contract month (contract specs).

### C2. Continuous `ZN=F`: detect the switch by the **volume jump**, not by the price residual alone
- **Finding from the data:** Yahoo's `ZN=F` does not switch at the end of Feb/May/Aug/Nov. It keeps the expiring contract through the delivery month, where volume falls to roughly 500–5,000 lots, and switches on the **CME last trading day**: 2022-03-22, 06-21, 09-21 and 12-20. Volume jumps 700–3,000× on those days.
- **Why not the residual-vs-DGS10 test (the original prompt):** the residual on those four switch days was −0.08, +0.09, −0.65 and +0.28 points, while the residual standard deviation is 0.17. Two of the four rolls would be invisible to a residual test, and real CPI/FOMC days would be falsely flagged.
- **Rule used:** window = [first intention day − 5 bdays, last trading day + 1 bday]. Inside each window, the day with the largest volume ratio is the roll day if the ratio is ≥ 10. At most one roll per window, and never outside a window.
- **Residual kept as a diagnostic:** roll days are shown as red crosses on the validation scatter.

### C3. Roll-day P&L is set to 0
- **Why:** yesterday's close belongs to the old contract and today's to the new one, so their difference is the calendar spread, not P&L. Setting it to 0 is conservative. We lose one real day of movement but never book a fake one.
- **Not "back-adjusting" the series (shifting history by the gap):** the gap can't be measured without both contracts' prices on the same day, which Yahoo doesn't provide, and back-adjusting changes the historical price levels shown in the ledger.
- **Not replacing the day with a DV01-predicted move:** that would put a modelled number into a ledger meant to hold only observed numbers.

### C4. Individual-contracts path: roll at the close 1 business day before first intention day
- **Why:** this is the last moment a long can hold without risk of delivery assignment. It is a fixed, documented, data-free rule.
- **Not "when next volume > front volume":** it needs volume for both contracts, which Yahoo doesn't have for expired months, and the result depends on data quality.
- **Invariant (tested):** the change from t−1 to t is always computed on the contract held overnight from t−1.

---

## D. Validation and DV01

### D1. Validation 1: correlation of daily ZN price change with daily DGS10 change
- **Why:** it is an independent check that the price series is sensible. Bond prices must move opposite to yields. Result for 2022: **−0.959**.

### D2. Validation 2: empirical DV01 from an OLS regression (`statsmodels`)
- **Why:** the prompt forbids a hard-coded duration, and the regression measures what the contract actually did. DV01 = −slope / 100 × $1,000 per point. Result: **$73.05 per bp** (95% CI 70.30–75.80), implied duration **6.15**, R² 0.92.
- **Not `numpy.polyfit`:** it gives no confidence interval or R². `statsmodels` reports them, which makes the result honest about its uncertainty.
- **Not a CTD/conversion-factor DV01:** that needs the deliverable basket and conversion factors, which are out of scope and are more data we'd have to verify.
- **Caveat:** DGS10 is the on-the-run 10Y yield, while ZN tracks the cheapest-to-deliver note (about 6.5–8 years), so the slope is a "futures vs benchmark yield" sensitivity. That's what a trader uses in practice.

### D3. Align on common dates before differencing
- **Why:** futures trade on some bond-market holidays (FRED shows NaN there). Differencing only over dates where both exist means each price change and yield change cover the same interval.
- **Not forward-filling yields:** that would invent a 0 bp move on days when the yield didn't print.

---

## E. Margins

### E1. Margin values only from official CME documents; the simulator refuses otherwise
- **Why:** the prompt's rule. A made-up margin turns every margin-call number into fiction.
- **Gate:** `margins.margin_timeline` raises `MarginGateError` if any simulated day has no verified advisory row in force. The CLI prints `REFUSED` and exits with code 2.

### E2. Two kinds of rows: `advisory` (builds the timeline) and `snapshot` (cross-check only)
- **Why:** a snapshot of CME's live margin table proves the rate on that date but not when it started. Using it as a start date would be an assumption. Snapshots are therefore used to **verify** the advisory timeline (`check_snapshots`), never to fill it, and a test enforces this.
- **Snapshots found:** $1,525 (2021-07-08) and $1,600 (2022-03-23).

### E3. Advisory spreadsheets are imported by a script, not typed by hand
- **Why:** CME's 2022 interest-rate advisories are `.xlsx` files that scripts can't download (403) and that were never archived. A browser can download them. `import_advisories.py` reads only the clearing-code-21 outright row, so no number is typed by hand.
- **Not third-party margin histories (broker PDFs, forums):** they are not official and fail rule E.

### E4. Initial margin = 1.10 × maintenance
- **Source:** CME Performance Bonds page, quoted in `SOURCES.md`. Stored in `data/margin_rules.csv` with `verified=true`, and the code refuses to start without it.
- **Not 1.00× (non-HRP):** the simulated account is a speculative trader, which is CME's heightened-risk profile.

### E5. Margin in force each day via `pd.merge_asof(direction="backward")`
- **Why:** "the rate on day d is the last advisory effective on or before d" is exactly a backward as-of join, and pandas does it in one call.
- **Effective-date convention:** CME says "effective after the close of business on X". We apply the new rate to the end-of-day check **on X**. This is conservative (calls come one day earlier rather than later).

### E6. `call_reason`: `margin_hike` vs `price_move`
- **Rule:** `margin_hike` if today's balance would still have passed **yesterday's** maintenance and maintenance went up. Otherwise `price_move`.
- **Why:** it separates "the market moved against me" from "CME raised the bar". That distinction mattered in 2022.

### E7. A margin call tops up to **initial**, not maintenance
- **Source:** quoted CME rule. Restoring only to maintenance would leave the account one bad day away from another call.

---

## F. Engineering

### F1. Explicit Python loop for the simulator (not vectorised)
- **Why:** each day depends on yesterday's balance, deposits and margin regime. A loop mirrors that state machine and is easy to debug. 251 rows take milliseconds.
- **Not vectorised pandas:** margin calls make the path dependent, so vectorising needs awkward cumulative tricks that hide the logic.

### F2. Accounting identity asserted every day
- `balance == deposited + cum_pnl`, checked inside the loop. A bug anywhere stops the run immediately.

### F3. Ledger shows prices in decimals **and** 32nds
- **Why:** traders read `112-09+`, and code needs `112.296875`. `to_32nds` counts half-32nds as integers (`round(price × 64)`) so floating-point noise can't produce invalid quotes.

### F4. One module per job (`data_loader`, `fred_loader`, `rolls`, `validation`, `margins`, `simulator`, `report`, `plots`, `pipeline`, `main`)
- **Why:** each module can be tested in isolation, and `pipeline.py` lets tests and notebooks run the same steps without argparse.
- **Not one script:** it's hard to test and hard to reason about.

### F5. `config/` package plus CSV data files instead of a Python dict of constants
- **Why:** CSV rows carry the source URL, as-of date and quoted text next to each value, and a provenance test reads them. A Python dict can't hold that metadata cleanly.

### F6. `argparse` command line
- **Why:** it is in the standard library, so there's no extra dependency. `click` and `typer` are nicer but are one more library to learn.

### F7. `matplotlib` static PNG charts
- **Why:** PNGs embed in a GitHub README and need no server.
- **Not Plotly or Streamlit:** interactive, but more to learn, and they don't render inside a README.
- **Style:** thin lines, a stepped maintenance line, call markers whose **shape** encodes `call_reason` (colour is a second cue), Fed hikes shaded, roll days dotted, and no dual axes.

### F8. `pytest` with hand-computed fixtures
- **Why:** each test uses numbers that can be checked by hand (e.g. 110-00 → 110-16 = +$500). The provenance test fails if any calculation input lacks a source.
- **Not `unittest`:** more boilerplate for the same coverage.

### F9. `pdfplumber` for CME PDFs; `openpyxl` for advisory spreadsheets
- **pdfplumber:** pure Python, extracts text line by line, and needs no Java (unlike tabula). PyPDF2 extracts text less reliably.
- **openpyxl:** the engine pandas uses for `.xlsx`. No alternative is needed.

### F10. No backtesting framework
- **Why:** Backtrader and vectorbt hide exactly the mechanics this project exists to show (mark-to-market, margin calls, rolls).

---

## G. Delivery

### G1. Ship with P&L-only results; keep the margin run gated (2026-10-20)
- **Why:** the 2022 ZN margin history exists only in about 45 CME `.xlsx` advisories that scripts can't fetch and the archive never stored. Downloading them by hand was judged not worth the time for this version. P&L, DV01 and roll handling don't depend on margins, so they are reported in full (`--pnl-only`).
- **Not "use the $1,600 snapshot for the whole year":** it would invent a value for 250 of the 251 days, which breaks the no-invented-numbers rule.
- **Not "use broker-published margin histories":** they are not official CME documents.
- **Path to finish later:** `data/advisories_needed.csv` → download the `.xlsx` files → `python import_advisories.py` → `python main.py --side short --qty 2`.
