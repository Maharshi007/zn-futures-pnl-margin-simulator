"""CLI entry point: python main.py --side short --qty 2 --start 2022-01-03 --end 2022-12-30"""
import argparse

import fred_loader
import pipeline
import validation
from config.settings import DEFAULT_END, DEFAULT_START, OUTPUT_DIR, ensure_dirs
from margins import MarginGateError
from plots import plot_ledger
from report import leverage_table, rate_move_table, summarize
from simulator import pnl_path, simulate


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="ZN (10Y T-Note) futures P&L and margin simulator")
    p.add_argument("--side", choices=["long", "short"], default="short")
    p.add_argument("--qty", type=int, default=1)
    p.add_argument("--start", default=DEFAULT_START)
    p.add_argument("--end", default=DEFAULT_END)
    p.add_argument("--price-source", choices=["contracts", "continuous"],
                   default="continuous",
                   help="individual contract months (roll-safe, if Yahoo has them) "
                        "or continuous ZN=F with roll days neutralised")
    p.add_argument("--pnl-only", action="store_true",
                   help="P&L without a margin account (use while margins are unverified)")
    a = p.parse_args(argv)
    if a.qty < 1:
        p.error("--qty must be >= 1")
    return a


def main(argv=None) -> int:
    a = parse_args(argv)
    ensure_dirs()
    try:
        ctx = pipeline.prepare(a.start, a.end, a.price_source, a.pnl_only)
    except MarginGateError as e:
        print(f"REFUSED: {e}")
        return 2
    except RuntimeError as e:          # e.g. Yahoo has no individual contracts
        print(f"DATA ERROR: {e}")
        return 3
    spec, prices, tl = ctx["spec"], ctx["prices"], ctx["timeline"]

    val = pipeline.run_validation(prices, a.start, a.end, spec)
    ledger = (pnl_path(prices, a.side, a.qty, spec) if a.pnl_only
              else simulate(prices, a.side, a.qty, spec, tl))

    tag = f"ZN_{a.side}_{a.qty}_{a.start}_{a.end}_{a.price_source}" + ("_pnl" if a.pnl_only else "")
    ledger.to_csv(OUTPUT_DIR / f"ledger_{tag}.csv")
    validation.scatter_plot(val["aligned"], val, OUTPUT_DIR / f"validation_{a.start}_{a.end}.png")
    plot_ledger(ledger, f"{spec['name']} | {a.side} {a.qty} | {a.start} to {a.end}",
                fred_loader.fed_hike_dates(a.start, a.end),
                OUTPUT_DIR / f"chart_{tag}.png")

    print(f"\n=== {spec['name']} | {a.side} {a.qty} | {a.start} -> {a.end} ===")
    for k, v in summarize(ledger, spec, a.qty).items():
        print(f"{k:32s} {v:,.2f}" if isinstance(v, float) else f"{k:32s} {v}")
    print(f"\nValidation: corr(dP, dY) = {val['correlation']:.3f} | "
          f"empirical DV01 = ${val['dv01_usd_per_bp']:.2f}/bp "
          f"(95% CI {val['dv01_ci95'][0]:.2f}-{val['dv01_ci95'][1]:.2f}) | "
          f"implied duration = {val['implied_duration']:.2f}")
    if a.pnl_only:
        print("\nRate-move table (empirical DV01):")
        print(rate_move_table(val["dv01_usd_per_bp"], a.qty).round(2).to_string(index=False))
        print("\nMargins skipped (--pnl-only): no margin calls, deposits or leverage reported.")
        print(f"Outputs written to {OUTPUT_DIR}")
        return 0
    if len(ctx["snapshots"]):
        print("\nMargin timeline vs independent CME snapshots:")
        print(ctx["snapshots"].to_string(index=False))

    init0 = tl["init_per_contract"].iloc[0]
    print("\nLeverage table (entry price, initial margin at entry):")
    print(leverage_table(prices["close"].iloc[0], spec, a.qty, init0).round(2).to_string(index=False))
    print("\nRate-move table (empirical DV01):")
    print(rate_move_table(val["dv01_usd_per_bp"], a.qty, init0).round(2).to_string(index=False))
    print(f"\nOutputs written to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
