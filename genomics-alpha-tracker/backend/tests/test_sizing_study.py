"""Round-10 sizing study gates (docs/VARIANTS_PREREGISTRATION_R10_SIZING.md):
the sizing knobs on ExecCfg are default-preserving, slot_fill and
inverse_occupancy do the contract's arithmetic on the OPEN list, the
deployment statistic and the decision rule are checked on fixed numbers,
and the defaults reproduce the committed mirror book to the dollar."""
from __future__ import annotations

import math
from dataclasses import replace
from datetime import date

import pytest

from scripts import backtest_sizing_study as st
from scripts.backtest_executor_mirror import CAP, EXEC_T2, ExecCfg, run_executor_book
from scripts.backtest_variants_10y import START_EQUITY
from tests.test_executor_mirror import NOCOST, _knob_market, dates, exec_row, flat_bars, make_market

D0 = date(2024, 1, 1)


def _flat_market(n: int = 12, px: float = 1.0) -> tuple[list[date], dict]:
    ds = dates(n, start=D0)
    mkt = make_market({"AAA": flat_bars(ds, px)})
    mkt["px"]["AAA"] = {d: px for d in ds}
    return ds, mkt


# --- (a) defaults unchanged: sizing='risk' is the risk_frac arithmetic ------------------

def test_defaults_are_the_risk_rule_and_the_knobs_default_preserving():
    assert ExecCfg().sizing == "risk" and ExecCfg().risk_frac_max == 0.03 and ExecCfg().start_equity is None
    assert "sizing=" not in EXEC_T2.label
    assert "sizing=slot_fill" in replace(EXEC_T2, sizing="slot_fill").label
    ds, mkt = _flat_market()
    # three entries, hand-sized: floor(0.01 * size_eq / risk), size_eq = sleeve eq at the fire close
    rows = [exec_row("AAA", ds[2], ds[6], fill=1.0, entry_ref=1.0, risk=0.25, exit_px=1.0),
            exec_row("AAA", ds[2], ds[6], fill=1.0, entry_ref=1.0, risk=0.4, exit_px=1.0),
            exec_row("AAA", ds[4], ds[7], fill=1.0, entry_ref=1.0, risk=0.3, exit_px=1.0, fire_date=ds[3])]
    bk = run_executor_book(rows, mkt, NOCOST)
    q = [t["qty"] for t in bk["trades"]]
    assert q[0] == math.floor(0.01 * START_EQUITY / 0.25) == 4000
    assert q[1] == math.floor(0.01 * START_EQUITY / 0.4) == 2500
    assert q[2] == math.floor(0.01 * START_EQUITY / 0.3) == 3333   # flat px: sleeve eq still 100k
    # the explicit knob spelling is the same book
    bk2 = run_executor_book(rows, mkt, replace(NOCOST, sizing="risk", start_equity=None))
    assert bk2["curve"] == bk["curve"] and bk2["trades"] == bk["trades"]
    # an unknown mode is refused, not silently 'risk'
    with pytest.raises(ValueError):
        run_executor_book(rows, mkt, replace(NOCOST, sizing="bogus"))


def test_default_book_on_the_knob_market_is_unchanged_by_the_knobs():
    """The round-9 synthetic market through the full executor path: the
    explicit defaults are the implicit defaults, trade for trade."""
    from scripts.backtest_executor_mirror import build_exec_rows, gate_rows, select_capped_exec
    fires, mkt, tiers = _knob_market()
    rows, _ = build_exec_rows(fires, mkt, tiers, EXEC_T2)
    taken, _ = select_capped_exec(gate_rows(rows, mkt["xbi_above_prior"][200]), CAP)
    a = run_executor_book(taken, mkt, EXEC_T2)
    b = run_executor_book(taken, mkt, replace(EXEC_T2, sizing="risk", risk_frac_max=0.03, start_equity=None))
    assert a["curve"] == b["curve"] and a["trades"] == b["trades"]
    assert len(a["trades"]) > 5


# --- (b) slot_fill: spendable cash / free slots, on the OPEN list -----------------------

def test_slot_fill_sizes_by_free_slots_after_the_days_exits():
    ds, mkt = _flat_market(px=1.0)
    cfg = replace(NOCOST, sizing="slot_fill")
    C = START_EQUITY
    # day 2: nine same-day entries at entry_ref 100 with 0..8 open -> each gets C/10 (no costs,
    # fill == entry_ref): floor(C/10/100) = 100 shares, leaving C/10 of cash and 9 open.
    mkt["px"]["AAA"] = {d: 100.0 for d in ds}
    nine = [exec_row("AAA", ds[2], ds[8], fill=100.0, entry_ref=100.0, risk=10.0, exit_px=100.0)
            for _ in range(9)]
    # day 3: with 9 open the free-slot count is max(10-9, 1) = 1 -> floor(C_spendable/entry_ref)
    tenth = exec_row("AAA", ds[3], ds[8], fill=50.0, entry_ref=50.0, risk=5.0, exit_px=50.0, fire_date=ds[2])
    bk = run_executor_book(nine + [tenth], mkt, cfg)
    q = [t["qty"] for t in bk["trades"]]
    assert q[:9] == [math.floor(C / 10 / 100.0)] * 9 == [100] * 9
    assert bk["daily"][ds[2].isoformat()]["open_positions"] == 9
    assert bk["daily"][ds[2].isoformat()]["sleeve_cash"] == pytest.approx(C / 10)
    assert q[9] == math.floor((C / 10) / 50.0) == 200
    # the OPEN list is read after the day's exits: one of the nine exits on day 3 -> 8 open
    # -> free slots 2 -> floor((C/10 + proceeds) / 2 / entry_ref)
    nine_b = list(nine)
    nine_b[0] = exec_row("AAA", ds[2], ds[3], fill=100.0, entry_ref=100.0, risk=10.0, exit_px=100.0)
    bk2 = run_executor_book(nine_b + [tenth], mkt, cfg)
    cash_after_exit = C / 10 + 100 * 100.0
    assert bk2["trades"][9]["qty"] == math.floor(cash_after_exit / 2 / 50.0) == 200
    assert bk2["daily"][ds[3].isoformat()]["open_positions"] == 9
    # 0 open and cash C over 10 slots: floor(C/10/entry_ref)
    one = [exec_row("AAA", ds[2], ds[8], fill=7.0, entry_ref=7.0, risk=1.0, exit_px=7.0)]
    mkt["px"]["AAA"] = {d: 7.0 for d in ds}
    assert run_executor_book(one, mkt, cfg)["trades"][0]["qty"] == math.floor(C / 10 / 7.0) == 1428
    # the slot target never exceeds spendable cash, so the cash clip is redundant for slot_fill
    cfg_noclip = replace(cfg, cash_clip=False)
    assert run_executor_book(one, mkt, cfg_noclip)["trades"][0]["qty"] == 1428


# --- (c) inverse_occupancy clamps ----------------------------------------------------------

def test_inverse_occupancy_clamps_between_risk_frac_and_risk_frac_max():
    ds, mkt = _flat_market(px=1.0)
    cfg = replace(NOCOST, sizing="inverse_occupancy", risk_frac=0.01, risk_frac_max=0.03)
    # ten same-day entries, fill = risk = 1 so notional = risk$ and the clip never binds
    rows = [exec_row("AAA", ds[2], ds[8], fill=1.0, entry_ref=1.0, risk=1.0, exit_px=1.0) for _ in range(10)]
    bk = run_executor_book(rows, mkt, cfg)
    q = [t["qty"] for t in bk["trades"]]
    expect = [math.floor(min(0.03, max(0.01, 0.01 * CAP / (k + 1))) * START_EQUITY) for k in range(10)]
    assert q == expect
    assert q[0] == 3000                                 # 0 open -> 10% uncapped -> 3% cap
    assert q[1] == q[2] == 3000                         # 1, 2 open -> 5%, 3.3% -> still the 3% cap
    assert q[3] == 2500 and q[4] == 2000                # 3 open -> 2.5%; 4 open -> 2%
    assert q[9] == 1000                                 # 9 open -> 1% (= risk_frac, the floor)
    # the floor IS risk_frac: at 2% the 9-open entry sizes at 2%, the 0-open entry still at the 3% cap
    cfg2 = replace(cfg, risk_frac=0.02)
    q2 = [t["qty"] for t in run_executor_book(rows, mkt, cfg2)["trades"]]
    assert q2[0] == 3000 and q2[9] == 2000
    # size_eq is the sleeve equity at the fire close (the risk rule's reference)
    assert bk["daily"][ds[1].isoformat()]["sleeve_eq"] == START_EQUITY


# --- (d) deployment statistic on a hand-built daily dict ----------------------------------

def test_deployment_stats_arithmetic():
    def day(cash, eq, open_, entries=0, sk=0):
        return {"sleeve_cash": cash, "sleeve_eq": eq, "open_positions": open_, "entries": entries,
                "skipped_zero_qty": sk}
    daily = {
        "2024-01-01": day(30_000.0, 30_000.0, 0),            # 0% deployed
        "2024-01-02": day(15_000.0, 30_000.0, 3, entries=3),  # 50%
        "2024-01-03": day(-500.0, 30_000.0, 9, entries=6),    # negative cash -> 100%
        "2024-01-04": day(6_000.0, 30_000.0, 10, sk=2),       # 80%
        "2024-01-05": day(24_000.0, 32_000.0, 1),             # 25%
        "2024-01-09": day(0.0, 10.0, 0),                      # outside the window
    }
    d = st.deployment_stats(daily, date(2024, 1, 1), date(2024, 1, 5))
    assert d["n_days"] == 5
    assert d["deployed_mean"] == pytest.approx((0 + 0.5 + 1.0 + 0.8 + 0.25) / 5)
    # nearest-rank on the sorted [0, .25, .5, .8, 1.0]: p10 -> idx round(0.4)=0, p50 -> 2, p90 -> round(3.6)=4
    assert d["deployed_p10"] == 0.0 and d["deployed_p50"] == 0.5 and d["deployed_p90"] == 1.0
    assert d["share_days_ge9_open"] == pytest.approx(2 / 5)
    assert d["share_days_at_cap"] == pytest.approx(1 / 5)          # only the 10-open day (CAP == 10)
    assert d["share_days_zero_open"] == pytest.approx(1 / 5)       # only the first day
    assert d["deployed_mean_when_open"] == pytest.approx((0.5 + 1.0 + 0.8 + 0.25) / 4)
    assert d["max_open"] == 10 and d["entries"] == 9 and d["skipped_zero_qty"] == 2
    # a day with sleeve_eq <= 0 is excluded from the deployed series, not from the day count
    daily["2024-01-05"] = day(0.0, 0.0, 0)
    d2 = st.deployment_stats(daily, date(2024, 1, 1), date(2024, 1, 5))
    assert d2["n_days"] == 5 and d2["deployed_mean"] == pytest.approx((0 + 0.5 + 1.0 + 0.8) / 4)
    assert d2["share_days_zero_open"] == pytest.approx(2 / 5)      # the share counts every day
    # an empty window reports None shares, not a ZeroDivisionError
    e = st.deployment_stats(daily, date(2030, 1, 1), date(2030, 1, 2))
    assert e["n_days"] == 0 and e["share_days_at_cap"] is None and e["deployed_mean_when_open"] is None


def test_h15a_verdict_scores_each_half_on_its_own_number():
    base = {"deployed_mean": 0.372, "share_days_at_cap": 0.266, "share_days_ge9_open": 0.386,
            "share_days_zero_open": 0.285, "deployed_mean_when_open": 0.52, "deployed_p90": 0.74}
    h = st.h15a_verdict(base)
    assert h["deployment_verdict"] == "CONFIRMED" and h["cap_minority_verdict"] == "REFUTED"
    assert "deployment CONFIRMED" in h["verdict"] and "cap-minority REFUTED" in h["verdict"]
    # the prior is closed at both ends; the cap-minority bar is strict at CAP_MINORITY
    assert st.h15a_verdict({**base, "deployed_mean": 0.40})["deployment_verdict"] == "CONFIRMED"
    assert st.h15a_verdict({**base, "deployed_mean": 0.401})["deployment_verdict"] == "REFUTED"
    assert st.h15a_verdict({**base, "share_days_at_cap": 0.099})["cap_minority_verdict"] == "CONFIRMED"
    assert st.h15a_verdict({**base, "share_days_at_cap": st.CAP_MINORITY})["cap_minority_verdict"] == "REFUTED"
    assert st.h15a_verdict({**base, "deployed_mean": None})["deployment_verdict"] == "REFUTED"


def test_occupancy_basis_counts_slots_held_but_unfilled_on_the_entry_day():
    ds = dates(8, start=D0)
    def row(gate, entry, exit_):
        return {"gate_date": ds[gate], "entry_date": ds[entry], "exit_date": ds[exit_]}
    # A enters day 2 (gate 1); B gate 2 / entry 3 holds a slot on A's entry day but is unfilled;
    # C gate 3 / entry 4 is after A's day; D gate 2 / entry 2 is filled on day 2, so not pending.
    taken = [row(1, 2, 6), row(2, 3, 6), row(3, 4, 6), row(2, 2, 6)]
    o = st.occupancy_basis(taken)
    assert o["n_entries"] == 4
    # A: B pending (1). B (day 3): C pending (1). C (day 4): none. D (day 2): B pending (1).
    assert o["entries_with_slot_held_unfilled"] == 3 and o["max_slot_held_unfilled"] == 1
    assert o["share_entries_with_slot_held_unfilled"] == pytest.approx(3 / 4)
    # a row never counts itself; without gate_date the entry day is the gate day
    assert st.occupancy_basis([{"entry_date": ds[2], "exit_date": ds[5]}])["entries_with_slot_held_unfilled"] == 0
    assert st.occupancy_basis([])["share_entries_with_slot_held_unfilled"] is None


def test_worst_trade_pct_is_qty_times_exit_minus_fill_over_sleeve_eq_at_entry():
    ds, mkt = _flat_market(px=10.0)
    rows = [exec_row("AAA", ds[2], ds[5], fill=10.0, entry_ref=10.0, risk=1.0, exit_px=8.0),
            exec_row("AAA", ds[3], ds[6], fill=10.0, entry_ref=10.0, risk=2.0, exit_px=9.0, fire_date=ds[2])]
    bk = run_executor_book(rows, mkt, NOCOST)
    w = st.worst_trade_pct(bk, ds[0], ds[-1])
    t0 = bk["trades"][0]
    eq0 = bk["daily"][ds[2].isoformat()]["sleeve_eq"]
    assert t0["qty"] == 1000 and t0["fill"] == 10.0 and t0["exit"] == 8.0
    assert w["pct_of_sleeve_eq"] == pytest.approx(1000 * (8.0 - 10.0) / eq0)
    assert w["symbol"] == "AAA" and w["entry_date"] == ds[2].isoformat()


# --- (e) the decision rule, clause by clause ------------------------------------------------

def test_decision_rule_each_clause():
    ok = st.decide(bonf_lo=0.01, max_dd_arm=0.30, max_dd_s0=0.28, sharpe_delta_5y=0.05)
    assert ok["decision"] == "PROPOSE" and all(ok["reasons"].values())
    # (1) Bonferroni interval must lie above zero
    r = st.decide(bonf_lo=-0.001, max_dd_arm=0.30, max_dd_s0=0.28, sharpe_delta_5y=0.05)
    assert r["decision"] == "NULL" and r["reasons"]["bonferroni_interval_above_zero"] is False
    assert st.decide(bonf_lo=0.0, max_dd_arm=0.30, max_dd_s0=0.28, sharpe_delta_5y=0.05)["decision"] == "NULL"
    assert st.decide(bonf_lo=None, max_dd_arm=0.30, max_dd_s0=0.28, sharpe_delta_5y=0.05)["decision"] == "NULL"
    # (2) max DD no more than 2 pp worse than S0 (boundary included)
    assert st.decide(0.01, max_dd_arm=0.30, max_dd_s0=0.28, sharpe_delta_5y=0.05)["decision"] == "PROPOSE"
    r = st.decide(0.01, max_dd_arm=0.3001, max_dd_s0=0.28, sharpe_delta_5y=0.05)
    assert r["decision"] == "NULL" and r["reasons"]["max_dd_within_2pp_of_s0"] is False
    # (3) the 5y sign must be positive
    r = st.decide(0.01, max_dd_arm=0.30, max_dd_s0=0.28, sharpe_delta_5y=-0.01)
    assert r["decision"] == "NULL" and r["reasons"]["sharpe_delta_sign_holds_5y"] is False
    assert st.decide(0.01, 0.30, 0.28, 0.0)["decision"] == "NULL"
    assert st.decide(0.01, 0.30, 0.28, float("nan"))["decision"] == "NULL"
    # leverage tag: positive CAGR delta with a wider drawdown, independent of the verdict
    assert st.decide(-0.1, 0.35, 0.28, -0.1, cagr_delta_full=0.02)["leverage_not_improvement"] is True
    assert st.decide(-0.1, 0.27, 0.28, -0.1, cagr_delta_full=0.02)["leverage_not_improvement"] is False
    assert st.decide(-0.1, 0.35, 0.28, -0.1, cagr_delta_full=-0.02)["leverage_not_improvement"] is False


# --- (f) start_equity seeds both buckets ----------------------------------------------------

def test_start_equity_override_seeds_sleeve_and_core():
    ds, mkt = _flat_market()
    cfg = replace(NOCOST, sleeve_target=0.30, start_equity=120_000.0)
    bk = run_executor_book([], mkt, cfg)
    d0 = bk["daily"][ds[0].isoformat()]
    assert d0["sleeve_cash"] == pytest.approx(36_000.0) and d0["core_cash"] == pytest.approx(84_000.0)
    assert bk["curve"][0][1] == pytest.approx(120_000.0)
    # None -> START_EQUITY, and the 1.0 sleeve gets all of it
    bk2 = run_executor_book([], mkt, replace(NOCOST, start_equity=None))
    assert bk2["daily"][ds[0].isoformat()]["sleeve_cash"] == START_EQUITY
    assert bk2["daily"][ds[0].isoformat()]["core_cash"] == 0.0
    # whole-share rounding is what the live base is for: the arm cfg carries it
    assert st.arm_cfg({"risk_frac": 0.01}, 120_000.0).start_equity == 120_000.0
    assert st.arm_cfg({"risk_frac": 0.01}, 120_000.0).sleeve_target == 0.30


# --- reduction gate: the defaults reproduce the committed mirror to the dollar ---------------

def test_defaults_reproduce_the_stored_mirror_blend_book_to_the_dollar():
    """S0 at $100k through the study's path (grade once, gate, cap, book with
    BIL carry and SPY) ends within $1 of the stored blend3070_t2_carry."""
    from scripts.backtest_executor_mirror import CACHE, load_inputs
    from scripts.backtest_exit_ablation import stored_mirror_end
    stored = stored_mirror_end(st.MIRROR_VARIANT)
    if stored is None or not CACHE.exists():
        pytest.skip("no stored mirror end value / bars cache on this host")
    inp = load_inputs(refresh_bars_if_missing=False)
    if inp.get("bil") is None or inp.get("spy_px") is None:
        pytest.skip("BIL / SPY series absent")
    taken, _ = st.taken_rows(inp["fire_rows"], inp["mkt"], inp["tiers"])
    bk = run_executor_book(taken, inp["mkt"], st.arm_cfg({"risk_frac": 0.01}, START_EQUITY),
                           cash_yield=inp["bil"], spy_px=inp["spy_px"])
    got = bk["curve"][-1][1]
    assert abs(got - stored) <= st.REDUCTION_TOL_USD, f"S0 ${got:,.2f} vs stored ${stored:,.2f}"
    # and the default-spelled cfg (no sizing/start_equity knobs) is the same book
    bk_def = run_executor_book(taken, inp["mkt"], replace(EXEC_T2, sleeve_target=0.30),
                               cash_yield=inp["bil"], spy_px=inp["spy_px"])
    assert bk_def["curve"] == bk["curve"]
