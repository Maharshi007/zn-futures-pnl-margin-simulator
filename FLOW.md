# Code Flow

There are four entry points. Each section lists the execution order and which function calls which.

| Entry point | Command | Purpose |
|---|---|---|
| 1 | `python main.py [--side --qty --start --end --price-source]` | Full simulation |
| 2 | `python import_advisories.py` | Turn downloaded CME advisory `.xlsx` files into verified rows in `data/margins.csv` |
| 3 | `python -m pytest -q` | Test suite |
| 4 | `python -m config.settings` / `python -m config.contract_specs` | Checks the setup / prints the spec |

---

## 1. `main.py` — full simulation

```
main.main(argv)
│
├─ 1. parse_args(argv)                              argparse → side, qty, start, end, price_source
├─ 2. config.settings.ensure_dirs()                 create data/raw/, outputs/
│
├─ 3. pipeline.prepare(start, end, source)
│     ├─ config.contract_specs.load_spec()
│     │     └─ load_spec_table()                    read data/contract_specs.csv
│     │        checks: every row verified; face/100 == $/point; tick × mult == tick value
│     │
│     ├─ pipeline.build_prices(start, end, source, spec)
│     │     ├─ rolls.contract_calendar(start, end, spec)   first intention / first delivery /
│     │     │                                              last trading day / roll window per contract
│     │     ├─ IF source == "continuous":
│     │     │     ├─ data_loader.load_continuous(start, end)
│     │     │     │     └─ download_daily("ZN=F", …)  cache hit → read CSV; miss → yfinance.download → save
│     │     │     ├─ rolls.detect_roll_days(df, cal)    volume jump ≥ 10× inside a roll window
│     │     │     └─ rolls.continuous_changes(close, is_roll)   diff(); roll days → 0
│     │     └─ IF source == "contracts":
│     │           ├─ data_loader.load_contracts(start, end)
│     │           │     └─ probe_contracts() → contract_symbols() → download_daily(sym) per month
│     │           │        (raises RuntimeError if Yahoo lacks any month)
│     │           ├─ rolls.roll_schedule(cal)           roll 1 bday before first intention day
│     │           └─ rolls.stitched_changes(closes, schedule)   change on contract held overnight
│     │     → DataFrame[close, change, is_roll_day]
│     │
│     ├─ margins.load_margins("ZN")                 read data/margins.csv
│     ├─ margins.initial_ratio()                    read data/margin_rules.csv (1.10, verified)
│     ├─ margins.margin_timeline(dates, m, ratio)   pd.merge_asof(backward) on advisory rows
│     │        GATE → raises MarginGateError if any day lacks a verified margin
│     └─ margins.check_snapshots(tl, m)             compare timeline with CME snapshots
│
│   ── on MarginGateError → print "REFUSED …", return 2
│   ── on RuntimeError (no data) → print "DATA ERROR …", return 3
│
├─ 4. pipeline.run_validation(prices, start, end, spec)
│     ├─ fred_loader.load_series("DGS10", …)        cache or fredapi → data/raw/
│     │     └─ config.settings.get_fred_api_key()   .env via python-dotenv
│     ├─ validation.align_changes(close, dgs10, is_roll)   common dates, dP & dY
│     ├─ validation.empirical_dv01(d, multiplier)   statsmodels OLS → slope, CI, R², DV01, duration
│     └─ validation.correlation(d)                  non-roll days
│
├─ 5. simulator.simulate(prices, side, qty, spec, timeline)
│     loop over days:
│       daily_pnl = dir × change × multiplier × qty
│       balance += daily_pnl
│       IF balance < maint × qty → call = init × qty − balance, call_reason
│       assert balance == deposited + cum_pnl
│       └─ _row(...) → quotes.to_32nds(close)
│     → ledger DataFrame
│
├─ 6. outputs
│     ├─ ledger.to_csv(outputs/ledger_<tag>.csv)
│     ├─ validation.scatter_plot(...) → outputs/validation_<start>_<end>.png
│     └─ plots.plot_ledger(ledger, title, fred_loader.fed_hike_dates(...), path)
│            fed_hike_dates → load_series("DFEDTARU") → dates where diff > 0
│            → outputs/chart_<tag>.png (price + rolls + hikes | cum P&L | balance + calls)
│
└─ 7. console report
      ├─ report.summarize(ledger, spec, qty)        P&L, worst day, calls by reason, leverage
      ├─ report.leverage_table(entry, spec, qty, init)
      └─ report.rate_move_table(dv01, qty, init)    1/5/10/25 bp using the EMPIRICAL DV01
```

### Data files read by each step
| Step | Reads | Writes |
|---|---|---|
| load_spec | `data/contract_specs.csv` | – |
| download_daily | `data/raw/yf_*.csv` (cache) | `data/raw/yf_*.csv` on first run |
| load_series | `data/raw/fred_*.csv` (cache) | `data/raw/fred_*.csv` on first run |
| load_margins / initial_ratio | `data/margins.csv`, `data/margin_rules.csv` | – |
| main outputs | – | `outputs/ledger_*.csv`, `outputs/chart_*.png`, `outputs/validation_*.png` |

---

## 2. `import_advisories.py` — margin data import

```
import_advisories.main()
├─ read data/advisories_needed.csv           advisory id, notice URL, effective date
├─ read data/margins.csv
└─ for each advisory:
      ├─ file missing → print "[missing] … download from <url>"
      ├─ zn_rows(xlsx)
      │     ├─ pandas.read_excel(sheet_name=None)       every sheet
      │     ├─ _header_row(df)                          find the title row
      │     └─ keep rows with clearing code "21" that are not spreads ("vs")
      ├─ no row → "[no ZN]" (ZN unchanged by that advisory)
      └─ row → new_maintenance(row) → append (effective_date, ZN, tier, maint,
                 kind=advisory, notice URL, verified=true)
└─ write data/margins.csv (sorted)
```
Then rerun `main.py`. The gate opens only when every day is covered.

---

## 3. Tests (`pytest`)

| File | What it proves | Calls |
|---|---|---|
| `tests/conftest.py` | puts the project root on `sys.path` | – |
| `test_settings.py` | folders exist, `.env` and `data/raw/` are git-ignored, key loads | `settings.ensure_dirs`, `get_fred_api_key` |
| `test_specs_and_quotes.py` | tick identity, multiplier = face/100, specs sourced, 32nds round-trip incl. `+`, bad input rejected | `load_spec`, `load_spec_table`, `to_32nds`, `from_32nds`, `is_on_tick` |
| `test_simulator.py` | ZN dry run, long/short mirror, accounting identity, **fake roll gap gives 0 P&L**, stitched changes use the same contract overnight, merge_asof, **gate refuses** (unverified / before first row / snapshot-only), `margin_hike` reason, 2022 calendar = CME dates | `simulate`, `continuous_changes`, `stitched_changes`, `margin_timeline`, `contract_calendar` |
| `test_provenance.py` | every spec/rule/margin row has a URL and date and appears in `SOURCES.md`; no literal DV01/duration in code; datasets listed | reads the CSVs and `SOURCES.md` |

---

## 4. Module dependency graph

```
main ──► pipeline ──► data_loader ──► config.settings
  │         │    └──► rolls
  │         │    └──► margins ──────► config.settings
  │         │    └──► fred_loader ──► config.settings (.env)
  │         │    └──► validation
  │         └──► config.contract_specs ──► config.settings
  ├──► simulator ──► quotes
  ├──► report ─────► quotes
  ├──► plots
  └──► validation (scatter)
import_advisories ──► margins, config.settings
```
No module imports `main`, so there are no cycles.
