"""README tests adapted to ZN, plus rolls, margins and the verification gate.

All prices/margins in these tests are SYNTHETIC unit-test fixtures chosen to
make hand arithmetic easy; they never feed a reported result.
"""
import pandas as pd
import pytest

import rolls
from config.contract_specs import load_spec
from margins import MarginGateError, margin_timeline
from quotes import from_32nds
from simulator import simulate

SPEC = load_spec()
D = pd.date_range("2025-01-06", periods=4, freq="B")


def _prices(quotes, rolls_=None):
    close = pd.Series([from_32nds(q) for q in quotes], index=D[:len(quotes)])
    is_roll = pd.Series(rolls_ or [False] * len(quotes), index=close.index)
    return pd.DataFrame({"close": close,
                         "change": rolls.continuous_changes(close, is_roll),
                         "is_roll_day": is_roll})


def _flat_margin(dates, maint, ratio=1.10):
    m = pd.DataFrame({"effective_date": [dates[0]], "maintenance": [maint],
                      "kind": ["advisory"], "verified": [True], "source_url": ["test"]})
    return margin_timeline(dates, m, ratio)


def test_dry_run_zn_long():
    # 110-00 -> 110-16 -> 108-24 -> 109-08, maint 1,600, init 1,760
    p = _prices(["110-00", "110-16", "108-24", "109-08"])
    led = simulate(p, "long", 1, SPEC, _flat_margin(p.index, 1600))
    assert led["daily_pnl"].tolist() == [0, 500, -1750, 500]
    assert led["margin_call"].iloc[2] == 1250            # 1,760 - 510
    assert led["call_reason"].iloc[2] == "price_move"
    assert led["balance"].iloc[-1] == 2260
    assert led["deposited"].iloc[-1] == 3010
    assert led["close_32nds"].tolist() == ["110-00", "110-16", "108-24", "109-08"]


def test_short_is_mirror_of_long():
    p = _prices(["110-00", "111-00+", "109-31"])
    tl = _flat_margin(p.index, 1e9)                       # huge margin, no calls
    L = simulate(p, "long", 1, SPEC, tl)
    S = simulate(p, "short", 1, SPEC, tl)
    assert (L["cum_pnl"] == -S["cum_pnl"]).all()


def test_accounting_identity_with_calls():
    p = _prices(["120-00", "118-00", "116-00", "121-00"])
    led = simulate(p, "long", 2, SPEC, _flat_margin(p.index, 1600))
    assert ((led["deposited"] + led["cum_pnl"] - led["balance"]).abs() < 1e-6).all()
    assert (led["margin_call"] > 0).sum() >= 1


def test_fake_roll_gap_never_enters_pnl():
    # Day 2 jumps 3 points only because the series switched contract.
    p = _prices(["110-00", "113-00", "113-16"], rolls_=[False, True, False])
    led = simulate(p, "long", 1, SPEC, _flat_margin(p.index, 1600))
    assert led["daily_pnl"].tolist() == [0, 0, 500]       # gap ignored, next day real


def test_stitched_changes_use_same_contract_overnight():
    d = pd.date_range("2025-02-24", periods=3, freq="B")
    closes = {"ZNH25": pd.Series([110.0, 110.5, 111.0], index=d),
              "ZNM25": pd.Series([109.0, 109.5, 112.0], index=d)}
    sched = pd.DataFrame({"contract": ["ZNH25", "ZNM25"],
                          "roll_date": [d[1], pd.Timestamp("2025-05-23")]})
    out = rolls.stitched_changes(closes, sched)
    # day1: held H overnight -> 110.5-110.0 ; roll at day1 close
    # day2: held M overnight -> 112.0-109.5 ; the H/M gap (1.0) never appears
    assert out["change"].tolist() == [0.0, 0.5, 2.5]
    assert out["contract"].tolist() == ["ZNH25", "ZNH25", "ZNM25"]


def test_margin_merge_asof_backward():
    dates = pd.date_range("2025-01-01", "2025-01-10", freq="B")
    m = pd.DataFrame({"effective_date": pd.to_datetime(["2024-12-15", "2025-01-07"]),
                      "maintenance": [1500, 1700], "kind": "advisory",
                      "verified": [True, True], "source_url": "test"})
    tl = margin_timeline(dates, m, 1.10)
    assert tl.loc["2025-01-06", "maint_per_contract"] == 1500
    assert tl.loc["2025-01-07", "maint_per_contract"] == 1700   # effective that day
    assert tl.loc["2025-01-10", "init_per_contract"] == pytest.approx(1870)


def test_gate_refuses_unverified_margin():
    dates = pd.date_range("2025-01-01", "2025-01-10", freq="B")
    m = pd.DataFrame({"effective_date": pd.to_datetime(["2024-12-15", "2025-01-07"]),
                      "maintenance": [1500, 1700], "kind": "advisory",
                      "verified": [True, False], "source_url": "test"})
    with pytest.raises(MarginGateError):
        margin_timeline(dates, m, 1.10)


def test_gate_refuses_days_before_first_margin():
    dates = pd.date_range("2025-01-01", "2025-01-10", freq="B")
    m = pd.DataFrame({"effective_date": pd.to_datetime(["2025-01-07"]),
                      "maintenance": [1700], "kind": "advisory",
                      "verified": [True], "source_url": "test"})
    with pytest.raises(MarginGateError):
        margin_timeline(dates, m, 1.10)


def test_snapshots_never_open_the_gate():
    dates = pd.date_range("2025-01-01", "2025-01-03", freq="B")
    m = pd.DataFrame({"effective_date": pd.to_datetime(["2024-12-01"]),
                      "maintenance": [1500], "kind": "snapshot",
                      "verified": [True], "source_url": "test"})
    with pytest.raises(MarginGateError):
        margin_timeline(dates, m, 1.10)


def test_call_reason_margin_hike():
    # Flat price; CME raises maintenance from 1,600 to 2,000 on day 2.
    p = _prices(["110-00", "110-00", "110-00"])
    m = pd.DataFrame({"effective_date": [p.index[0], p.index[2]],
                      "maintenance": [1600, 2000], "kind": "advisory",
                      "verified": [True, True], "source_url": "test"})
    led = simulate(p, "long", 1, SPEC, margin_timeline(p.index, m, 1.10))
    assert led["call_reason"].iloc[2] == "margin_hike"
    assert led["margin_call"].iloc[2] == pytest.approx(2200 - 1760)


def test_contract_calendar_matches_cme_rules_2022():
    cal = rolls.contract_calendar("2022-01-03", "2022-12-30", SPEC).set_index("contract")
    assert cal.loc["ZNH22", "last_trading_day"] == pd.Timestamp("2022-03-22")
    assert cal.loc["ZNU22", "first_intention_day"] == pd.Timestamp("2022-08-30")
    assert cal.loc["ZNZ22", "last_trading_day"] == pd.Timestamp("2022-12-20")
