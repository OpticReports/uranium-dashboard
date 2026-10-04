"""Executor-mirror replay (scripts/backtest_executor_mirror.py) on SYNTHETIC
bars — one test per executor-vs-paper delta, the window/stat helpers, the
bootstrap, and the /blend3070/mirror-backtest routes. No cache, no network:
every market here is built in-test by `make_market`.
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import replace
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.calls.rules import BarLike
from scripts import backtest_executor_mirror as mod
from scripts.backtest_executor_mirror import (
    EXEC_T1,
    EXEC_T2,
    R2A_MODE,
    build_exec_rows,
    curve_points,
    extra_stats,
    gate_rows,
    grade_executor,
    ibkr_fixed,
    longest_underwater,
    paper_blend_curve,
    run_executor_book,
    run_mirror,
    stationary_bootstrap,
    window_bounds,
)
from scripts.backtest_signals import atr_series
from scripts.backtest_variants_10y import (
    START_EQUITY,
    grade_trailing,
    run_call_book,
    seg_stats,
    select_capped,
)
from scripts.backtest_variants_r2 import build_trailing_rows
from scripts.backtest_variants_r3 import max_dd_of

D0 = date(2024, 1, 1)


# --- synthetic market helpers ------------------------------------------------------

def dates(n: int, start: date = D0, weekdays_only: bool = False) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if not weekdays_only or d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def flat_bars(ds: list[date], close: float = 100.0, rng: float = 1.0) -> list[BarLike]:
    """Flat bars with a 2*rng range => ATR14 = 2*rng after 15 bars."""
    return [BarLike(d, close + rng, close - rng, close, close) for d in ds]


def make_market(bars_by_sym: dict[str, list[BarLike]], gate: bool | dict = True) -> dict:
    """A minimal mkt dict with load_market's shape: XBI calendar = the union
    of all bar dates (flat XBI bars), px forward-filled, prior-close 200dma
    gate = `gate` (bool for all days or {date: bool})."""
    cal = sorted({b.date for bs in bars_by_sym.values() for b in bs})
    bars = dict(bars_by_sym)
    bars.setdefault("XBI", flat_bars(cal))
    px = {}
    for sym, bs in bars.items():
        by = {b.date: b.close for b in bs}
        last, series = None, {}
        for d in cal:
            if d in by:
                last = by[d]
            series[d] = last
        px[sym] = series
    above = ({d: gate for d in cal} if isinstance(gate, bool) else dict(gate))
    return {"bars": bars, "calendar": cal, "px": px,
            "xbi_above": {200: {}}, "xbi_above_prior": {200: above}}


def fire_row(bars: list[BarLike], i: int, symbol: str, flag: str = "rel_strength_60d") -> dict:
    """A stored-row-shaped fire (backtest_calls_10y.make_call conventions:
    entry = next open, risk = min(3*ATR14 through the fire bar, 0.5*entry))."""
    atrs = atr_series(bars)
    eb = bars[i + 1]
    risk = min(3.0 * atrs[i], 0.5 * eb.open)
    return {"fire_date": bars[i].date.isoformat(), "entry_date": eb.date.isoformat(),
            "entry": eb.open, "risk": risk, "symbol": symbol, "flag": flag, "regime_up": True}


def exec_row(symbol: str, entry_date: date, exit_date: date, *, fill: float, entry_ref: float,
             risk: float, exit_px: float, status: str = "stopped", bps: float = 0.0,
             fire_date: date | None = None) -> dict:
    fire_date = fire_date or (entry_date - timedelta(days=1))
    return {"fire_date": fire_date.isoformat(), "entry_date": entry_date.isoformat(),
            "gate_date": entry_date.isoformat(), "symbol": symbol, "flag": "f_exec",
            "entry": fill, "fill": fill, "entry_ref": entry_ref, "risk": risk, "stop0": entry_ref - risk,
            "exit": exit_px, "exit_date": exit_date.isoformat(), "status": status,
            "prefill_exit": False, "bps": bps, "r": (exit_px - fill) / risk,
            "r_net": (exit_px * (1 - bps) - fill * (1 + bps)) / risk,
            "hold_days": (exit_date - entry_date).days}


NOCOST = replace(EXEC_T1, commission_model="none", bil_order_cost=False, carry=False)
TIERS_A = {"AAA": "A", "BBB": "A", "CCC": "A", "S": "A"}


def trending_bars(ds: list[date], start: float = 100.0, step: float = 0.5, rng: float = 1.0):
    out, c = [], start
    for d in ds:
        out.append(BarLike(d, c + rng, c - rng, c, c))
        c += step
    return out


# --- 1. reduction: the new engine in R2A_MODE IS the paper R2-A -----------------------

def test_reduction_to_r2a():
    ds = dates(140)
    bars = {"AAA": trending_bars(ds, 100, 0.4), "BBB": trending_bars(ds, 50, -0.1),
            "CCC": trending_bars(ds, 80, 0.0)}
    # a dip so trailing stops actually fire on two of them
    for sym, k in (("AAA", 60), ("BBB", 45)):
        b = bars[sym][k]
        bars[sym][k] = BarLike(b.date, b.high, b.low - 20, b.close - 15, b.open)
    mkt = make_market(bars)
    rows = [fire_row(bars[s], 20, s) for s in bars] + [fire_row(bars["AAA"], 30, "AAA", "volume_anomaly")]
    tiers = {s: "A" for s in bars}

    ref_rows, ref_open = build_trailing_rows(rows, mkt, tiers)
    got_rows, meta = build_exec_rows(rows, mkt, tiers, R2A_MODE)
    assert meta["open_at_end_excluded"] == ref_open
    assert len(got_rows) == len(ref_rows) == 4
    for a, b in zip(sorted(ref_rows, key=lambda t: (t["fire_date"], t["symbol"], t["flag"])),
                    sorted(got_rows, key=lambda t: (t["fire_date"], t["symbol"], t["flag"]))):
        assert (a["entry"], a["exit"], a["exit_date"], a["status"]) == \
               (b["entry"], b["exit"], b["exit_date"], b["status"])
        assert a["r_net"] == pytest.approx(b["r_net"], abs=1e-12)
    assert {t["status"] for t in got_rows} >= {"stopped"}

    ta, _ = select_capped(got_rows, 10)
    ref_curve = run_call_book(ta, mkt)
    got = run_executor_book(ta, mkt, R2A_MODE)["curve"]
    assert len(got) == len(ref_curve)
    for (d1, v1), (d2, v2) in zip(ref_curve, got):
        assert d1 == d2 and abs(v1 - v2) <= 1e-6
    assert ref_curve[-1][1] != START_EQUITY   # something actually traded


# --- 2. entry lag ---------------------------------------------------------------------

def test_entry_lag_t1_vs_t2():
    ds = dates(140)
    bars = flat_bars(ds)
    i = 20
    bars[i + 1] = BarLike(ds[i + 1], 101.0, 99.0, 100.0, 100.0)
    bars[i + 2] = BarLike(ds[i + 2], 104.0, 102.0, 103.0, 103.0)
    atrs = atr_series(bars)
    r1 = grade_executor(bars, atrs, i, NOCOST)
    r2 = grade_executor(bars, atrs, i, replace(NOCOST, entry_lag=2))
    assert r1["fill"] == 100.0 and r1["entry_date"] == ds[i + 1]
    assert r2["fill"] == 103.0 and r2["entry_date"] == ds[i + 2]
    for r in (r1, r2):
        assert r["risk"] == pytest.approx(3 * atrs[i])
        assert r["entry_ref"] == bars[i].close
        assert r["gate_date"] == ds[i + 1]

    # the 200dma gate is keyed on fire_date+1 for BOTH lags
    gate = {d: True for d in ds}
    gate[ds[i + 2]] = False
    mkt = make_market({"AAA": bars}, gate=gate)
    rows = [fire_row(bars, i, "AAA")]
    for lag in (1, 2):
        got, _ = build_exec_rows(rows, mkt, TIERS_A, replace(NOCOST, entry_lag=lag))
        assert len(gate_rows(got, mkt["xbi_above_prior"][200])) == 1
    mkt["xbi_above_prior"][200][ds[i + 1]] = False
    for lag in (1, 2):
        got, _ = build_exec_rows(rows, mkt, TIERS_A, replace(NOCOST, entry_lag=lag))
        assert gate_rows(got, mkt["xbi_above_prior"][200]) == []

    # the lag-2 book pays 103 instead of 100 for the same quantity
    b1 = run_executor_book(build_exec_rows(rows, mkt, TIERS_A, NOCOST)[0], mkt, NOCOST)
    b2 = run_executor_book(build_exec_rows(rows, mkt, TIERS_A, replace(NOCOST, entry_lag=2))[0],
                           mkt, replace(NOCOST, entry_lag=2))
    q1, q2 = b1["trades"][0]["qty"], b2["trades"][0]["qty"]
    assert q1 == q2 > 0
    assert b1["curve"][-1][1] - b2["curve"][-1][1] == pytest.approx(q1 * (103.0 - 100.0) * (1 + 0.001))


# --- 3. sizing: whole shares, cash clip, zero-qty skip, no clip at the fill --------------

def test_sizing_integer_and_cash_clip():
    ds = dates(10)
    bars = flat_bars(ds, 1000.0)
    mkt = make_market({"AAA": bars})
    cfg = NOCOST
    # risk 6 at $100k sleeve -> floor(1000/6) = 166 (fractional 166.67 in r2a mode)
    row = exec_row("AAA", ds[2], ds[5], fill=6.0, entry_ref=6.0, risk=6.0, exit_px=6.0)
    mkt["px"]["AAA"] = {d: 6.0 for d in ds}
    bk = run_executor_book([row], mkt, cfg)
    assert bk["trades"][0]["qty"] == 166
    bk_frac = run_executor_book([row], mkt, replace(cfg, integer_shares=False, cash_clip=False))
    assert bk_frac["trades"][0]["qty"] == pytest.approx(1000 / 6)
    # cash clip: entry_ref 1000 -> floor(100000/1000) = 100 < 166
    row = exec_row("AAA", ds[2], ds[5], fill=1000.0, entry_ref=1000.0, risk=6.0, exit_px=1000.0)
    mkt["px"]["AAA"] = {d: 1000.0 for d in ds}
    bk = run_executor_book([row], mkt, cfg)
    assert bk["trades"][0]["qty"] == 100
    # entry_ref above the whole sleeve -> qty 0 -> skipped, no position
    row0 = exec_row("AAA", ds[2], ds[5], fill=200_000.0, entry_ref=200_000.0, risk=6.0, exit_px=200_000.0)
    bk0 = run_executor_book([row0], mkt, cfg)
    assert bk0["meta"]["skipped_zero_qty"] == 1 and bk0["trades"] == []
    assert all(v == START_EQUITY for _, v in bk0["curve"])
    # a fill above entry_ref may push sleeve cash below zero on the fill day (no clip at the fill)
    row = exec_row("AAA", ds[2], ds[5], fill=1010.0, entry_ref=1000.0, risk=6.0, exit_px=1010.0)
    bk = run_executor_book([row], mkt, cfg)
    assert bk["trades"][0]["qty"] == 100
    assert bk["daily"][ds[2].isoformat()]["sleeve_cash"] < 0
    assert bk["daily"][ds[2].isoformat()]["open_positions"] == 1


# --- 4. uncapped 3xATR risk vs the paper 0.5*entry cap; no sizing reference ------------

def test_uncapped_risk_vs_r2a_cap():
    ds = dates(140)
    # TR 20 on a 100 close -> ATR 20 -> 3*ATR = 60 = 0.6*close, L0 = 40 > 0
    bars = [BarLike(d, 110.0, 90.0, 100.0, 100.0) for d in ds]
    atrs = atr_series(bars)
    i = 20
    ex = grade_executor(bars, atrs, i, NOCOST)
    assert ex["risk"] == pytest.approx(60.0) and ex["stop0"] == pytest.approx(40.0)
    pr = grade_executor(bars, atrs, i, R2A_MODE)
    assert pr["risk"] == pytest.approx(0.5 * bars[i + 1].open) == pytest.approx(50.0)
    # 3*ATR >= close -> L0 <= 0 -> the tracker never publishes a stop row -> skipped
    bars2 = [BarLike(d, 120.0, 80.0, 100.0, 100.0) for d in ds]
    mkt = make_market({"AAA": bars2})
    got, meta = build_exec_rows([fire_row(bars2, i, "AAA")], mkt, TIERS_A, NOCOST)
    assert got == [] and meta["skip_no_sizing_reference"] == 1


# --- 5. day-zero protective stop and gap-through fills ---------------------------------

def test_day_zero_stop_and_gap():
    ds = dates(140)
    i = 20
    bars = flat_bars(ds)                      # ATR 2 -> L0 = 100 - 6 = 94
    atrs = atr_series(bars)
    L0 = bars[i].close - 3 * atrs[i]
    assert L0 == pytest.approx(94.0)
    # fill bar pierces L0 intrabar -> stopped at L0 on the fill bar
    b = list(bars)
    b[i + 1] = BarLike(ds[i + 1], 101.0, 90.0, 100.0, 100.0)
    r = grade_executor(b, atr_series(b), i, NOCOST)
    assert r["status"] == "stopped" and r["exit_date"] == ds[i + 1] and r["exit"] == pytest.approx(L0)
    # fill bar OPENS below L0 -> exit at the open == fill
    b[i + 1] = BarLike(ds[i + 1], 93.0, 85.0, 90.0, 92.0)
    r = grade_executor(b, atr_series(b), i, NOCOST)
    assert r["status"] == "stopped" and r["exit"] == r["fill"] == 92.0
    # the paper grader never stops on the entry bar
    pr = grade_executor(b, atr_series(b), i, R2A_MODE)
    assert pr["exit_date"] != ds[i + 1]


# --- 6. ratchet-up-only vs the imported (falling) grade_trailing -----------------------

def test_ratchet_up_only_vs_grade_trailing():
    ds = dates(130)
    i = 20
    bars = flat_bars(ds)                                       # ATR 2, trail 94 after fill
    bars[26] = BarLike(ds[26], 111.0, 109.0, 110.0, 110.0)     # new peak 110
    bars[27] = BarLike(ds[27], 160.0, 108.0, 112.0, 110.0)     # ATR blowout, peak 112, low above trail
    bars[28] = BarLike(ds[28], 109.0, 100.0, 105.0, 108.0)     # low 100: between the two levels
    for k in range(29, len(bars)):
        bars[k] = BarLike(ds[k], 106.0, 104.0, 105.0, 105.0)
    atrs = atr_series(bars)
    trail_27 = 110.0 - 3 * atrs[26]                            # level through bar 26 (ratcheted)
    fallen_28 = 112.0 - 3 * atrs[27]                           # level through bar 27 (after blowout)
    assert fallen_28 < 100.0 < trail_27
    ex = grade_executor(bars, atrs, i, NOCOST)
    assert ex["status"] == "stopped" and ex["exit_date"] == ds[28]
    assert ex["exit"] == pytest.approx(trail_27)
    ref = grade_trailing(bars, atrs, i + 1, bars[i + 1].open, ds[i + 1] + timedelta(days=90))
    assert ref is not None and ref[1] > ds[28]                 # the fallen trail did not stop it
    # the non-ratchet engine reproduces the imported grader's call
    nr = grade_executor(bars, atrs, i, replace(NOCOST, ratchet=False, peak_seed="entry_close",
                                               day_zero_stop=False, time_stop_anchor="entry",
                                               time_stop_fill="deadline_close"))
    assert (nr["status"], nr["exit_date"], nr["exit"]) == (ref[0], ref[1], pytest.approx(ref[2]))


# --- 7. peak seeded at the fire close vs the first post-entry close ----------------------

def test_peak_seed_fire_close():
    ds = dates(140)
    i = 20
    bars = flat_bars(ds)
    bars[i] = BarLike(ds[i], 111.0, 99.0, 110.0, 100.0)        # fire close 110
    bars[i + 1] = BarLike(ds[i + 1], 101.0, 99.5, 100.5, 100.0)  # gap down to 100
    for k in range(i + 2, len(bars)):
        bars[k] = BarLike(ds[k], 103.0, 101.0, 102.0, 102.0)   # closes 102, lows 101
    atrs = atr_series(bars)
    L0 = 110.0 - 3 * atrs[i]
    r2a_level = bars[i + 1].close - 3 * atrs[i + 1]
    assert r2a_level < 101.0 < L0                              # later lows sit between the levels
    # executor: the resting day-zero stop at L0 sits above the gap open -> filled at the open
    ex = grade_executor(bars, atrs, i, NOCOST)
    assert ex["status"] == "stopped" and ex["exit_date"] == ds[i + 1] and ex["exit"] == 100.0
    # without the day-zero stop the fire-close-seeded trail still stops on the next bar
    ex2 = grade_executor(bars, atrs, i, replace(NOCOST, day_zero_stop=False))
    assert ex2["status"] == "stopped" and ex2["exit_date"] == ds[i + 2]
    assert ex2["exit"] == pytest.approx(max(L0, 100.5 - 3 * atrs[i + 1]))
    # paper: peak seeded at the first post-entry close -> no stop there
    pr = grade_executor(bars, atrs, i, R2A_MODE)
    assert pr["exit_date"] > ds[i + 2]


# --- 8. lag 2: the pre-fill bar pierces the trail -> tracker exit on the fill morning ----

def test_prefill_tracker_exit_lag2():
    ds = dates(140)
    i = 20
    bars = flat_bars(ds)                      # L0 = 94
    bars[i + 1] = BarLike(ds[i + 1], 101.0, 93.0, 100.0, 100.0)   # pierces L0 intrabar
    bars[i + 2] = BarLike(ds[i + 2], 102.0, 99.0, 101.0, 100.5)   # does not
    atrs = atr_series(bars)
    r = grade_executor(bars, atrs, i, replace(NOCOST, entry_lag=2))
    assert r["status"] == "prefill_exit" and r["prefill_exit"]
    assert r["entry_date"] == ds[i + 2] and r["fill"] == 100.5
    assert r["exit_date"] == ds[i + 2] and r["exit"] == 101.0    # same-day MKT ~ close
    # the resting L0 stop fills first when the fill bar opens below it
    bars[i + 2] = BarLike(ds[i + 2], 95.0, 90.0, 92.0, 93.0)
    r = grade_executor(bars, atr_series(bars), i, replace(NOCOST, entry_lag=2))
    assert r["status"] == "prefill_exit" and r["exit"] == 93.0 == r["fill"]
    # counted in the build meta
    mkt = make_market({"AAA": bars})
    _, meta = build_exec_rows([fire_row(bars, i, "AAA")], mkt, TIERS_A, replace(NOCOST, entry_lag=2))
    assert meta["prefill_exit"] == 1


# --- 9. time stop: anchor and fill convention -------------------------------------------

def test_time_stop_anchor_and_fill():
    # weekday-only bars so a deadline can land on a weekend
    ds = dates(110, start=date(2024, 1, 1), weekdays_only=True)
    bars = flat_bars(ds, 100.0, 0.5)                             # ATR 1 -> trail 97, never touched
    atrs = atr_series(bars)
    # case A: fire Mon 01-29 -> fire+90 = Sun 04-28 -> executor exits Mon 04-29 OPEN;
    #         paper: entry Tue 01-30 + 90 = Mon 04-29 (a bar) -> exit at its CLOSE
    # case B: fire Fri 01-26 -> fire+90 = Thu 04-25 -> executor exits Fri 04-26 OPEN;
    #         paper: entry Mon 01-29 + 90 = Sun 04-28 -> exit at Fri 04-26 CLOSE (deadline_close)
    for i, fire_dl, exec_exit, paper_exit in ((20, date(2024, 4, 28), date(2024, 4, 29), date(2024, 4, 29)),
                                             (19, date(2024, 4, 25), date(2024, 4, 26), date(2024, 4, 26))):
        fire, entry = ds[i], ds[i + 1]
        assert fire + timedelta(days=90) == fire_dl
        ex = grade_executor(bars, atrs, i, NOCOST)
        nxt = next(d for d in ds if d > fire + timedelta(days=90))
        assert ex["status"] == "expired" and ex["exit_date"] == nxt == exec_exit
        assert ex["exit"] == bars[ds.index(nxt)].open
        pr = grade_executor(bars, atrs, i, R2A_MODE)
        last = max(d for d in ds if d <= entry + timedelta(days=90))
        assert pr["status"] == "expired" and pr["exit_date"] == last == paper_exit
        assert pr["exit"] == bars[ds.index(last)].close
        ref = grade_trailing(bars, atrs, i + 1, bars[i + 1].open, entry + timedelta(days=90))
        assert (ref[0], ref[1], ref[2]) == (pr["status"], pr["exit_date"], pr["exit"])
    assert date(2024, 4, 28).weekday() == 6 and date(2024, 4, 25).weekday() == 3


# --- 10. commissions ------------------------------------------------------------------

def test_commissions():
    ds = dates(10)
    mkt = make_market({"AAA": flat_bars(ds, 50.0)})
    row = exec_row("AAA", ds[2], ds[5], fill=50.0, entry_ref=50.0, risk=1.0, exit_px=50.0)
    base = run_executor_book([row], mkt, NOCOST)["curve"][-1][1]
    flat = run_executor_book([row], mkt, replace(NOCOST, commission_model="flat"))["curve"][-1][1]
    assert base - flat == pytest.approx(2.0)
    both = run_executor_book([row], mkt, replace(NOCOST, commission_model="flat", bil_order_cost=True))
    assert base - both["curve"][-1][1] == pytest.approx(4.0)
    assert both["meta"]["commissions_paid"] == pytest.approx(4.0) and both["meta"]["bil_orders"] == 2
    assert ibkr_fixed(100, 5000) == 1.0
    assert ibkr_fixed(1000, 5000) == 5.0
    assert ibkr_fixed(1000, 300) == 3.0
    assert ibkr_fixed(50, 10) == pytest.approx(0.10)
    # $1 flat x 2 legs x n trades
    rows = [exec_row("AAA", ds[k], ds[k + 2], fill=50.0, entry_ref=50.0, risk=1.0, exit_px=50.0)
            for k in (1, 3, 5)]
    for r, f in zip(rows, ("a", "b", "c")):
        r["flag"] = f
    n = len(run_executor_book(rows, mkt, NOCOST)["trades"])
    assert n == 3
    cost = run_executor_book(rows, mkt, replace(NOCOST, commission_model="flat"))["curve"][-1][1]
    assert START_EQUITY - cost == pytest.approx(2.0 * n)


# --- 11. BIL carry on idle sleeve cash --------------------------------------------------

def test_bil_carry_on_off():
    ds = dates(30)
    mkt = make_market({"AAA": flat_bars(ds, 50.0)})
    y = {d: 0.0001 for d in ds}
    carry = run_executor_book([], mkt, replace(NOCOST, carry=True), cash_yield=y)
    assert carry["curve"][-1][1] == pytest.approx(START_EQUITY * 1.0001 ** (len(ds) - 1), abs=1e-6)
    flat = run_executor_book([], mkt, NOCOST, cash_yield=None)
    assert all(v == START_EQUITY for _, v in flat["curve"])
    # with a position open the accrual base is the prior-close CASH only
    row = exec_row("AAA", ds[1], ds[len(ds) - 1], fill=50.0, entry_ref=50.0, risk=1.0, exit_px=50.0)
    bk = run_executor_book([row], mkt, replace(NOCOST, carry=True), cash_yield=y)
    qty = bk["trades"][0]["qty"]
    d1 = ds[1].isoformat()
    cash_after_entry = bk["daily"][d1]["sleeve_cash"]
    assert cash_after_entry == pytest.approx(START_EQUITY * 1.0001 - qty * 50.0)   # day-1 carry, then the buy
    assert bk["daily"][ds[2].isoformat()]["carry"] == pytest.approx(cash_after_entry * 0.0001)


# --- 12. 30/70: band rebalance + SPY core; sizing on SLEEVE equity -----------------------

def test_30_70_band_rebalance():
    ds = dates(12)
    mkt = make_market({"AAA": flat_bars(ds, 50.0)})
    spy = {d: 100.0 for d in ds}
    cfg = replace(NOCOST, sleeve_target=0.30, commission_model="flat")
    bk = run_executor_book([], mkt, cfg, spy_px=spy)
    d0 = bk["daily"][ds[0].isoformat()]
    assert d0["spy_qty"] == 700 and d0["sleeve_eq"] == pytest.approx(30_000.0)
    # SPY doubles: w = 30000/170000 = 0.176 < 0.25 -> sell round(0.1235*170000/200) = 105 shares
    spy2 = {d: (100.0 if k < 5 else 200.0) for k, d in enumerate(ds)}
    bk = run_executor_book([], mkt, cfg, spy_px=spy2)
    d5 = bk["daily"][ds[5].isoformat()]
    assert d5["spy_qty"] == 700 - 105 and d5["rebalances"] == 1
    assert d5["sleeve_cash"] == pytest.approx(30_000.0 + 105 * 200 * (1 - 0.001) - 1.0)
    w = d5["sleeve_eq"] / d5["equity"]
    assert abs(w - 0.30) <= 0.05
    # SPY halves: w > 0.35 -> move cash sleeve->core, then core_buy floor(core_cash/px)
    spy3 = {d: (100.0 if k < 5 else 50.0) for k, d in enumerate(ds)}
    bk = run_executor_book([], mkt, replace(cfg, bil_order_cost=True), spy_px=spy3)
    d5 = bk["daily"][ds[5].isoformat()]
    assert d5["rebalances"] == 1 and d5["spy_qty"] > 700 and d5["bil_orders"] == 1
    assert abs(d5["sleeve_eq"] / d5["equity"] - 0.30) <= 0.05
    assert d5["core_cash"] < 50.0
    # sizing uses 1% of SLEEVE equity (30k -> $300 of risk), not the book
    row = exec_row("AAA", ds[2], ds[8], fill=50.0, entry_ref=50.0, risk=3.0, exit_px=50.0)
    bk = run_executor_book([row], mkt, cfg, spy_px=spy)
    assert bk["trades"][0]["qty"] == 100            # floor(300/3)
    # sleeve-only never rebalances and never buys SPY
    bk = run_executor_book([], mkt, NOCOST, spy_px=spy2)
    assert bk["meta"]["rebalances"] == 0 and bk["meta"]["end_spy_qty"] == 0


def test_paper_blend_mix_is_daily_return_mix():
    ds = dates(6)
    sleeve = [(d, 100_000.0 * (1.01 ** k)) for k, d in enumerate(ds)]
    spy = {d: 100.0 * (0.99 ** k) for k, d in enumerate(ds)}
    mix = paper_blend_curve(sleeve, spy, w=0.30)
    assert [d for d, _ in mix] == ds
    for k in range(1, len(ds)):
        r = mix[k][1] / mix[k - 1][1] - 1
        assert r == pytest.approx(0.3 * 0.01 + 0.7 * (-0.01))


# --- 13. windows & stats --------------------------------------------------------------

def test_window_slicing_and_stats():
    cal = dates(int(7 * 365.25) + 1, start=date(2019, 1, 1))
    end = cal[-1]
    curve = [(d, 100_000.0 * (1 + 0.0002) ** k * (1 - 0.3 * math.exp(-((k - 900) / 60) ** 2)))
             for k, d in enumerate(cal)]
    wb = window_bounds(cal, end)
    assert wb["full"] == (cal[0], end)
    for name, yrs in (("5y", 5), ("2y", 2)):
        lo = next(d for d in cal if d >= end - timedelta(days=yrs * 365.25))
        assert wb[name] == (lo, end)
    full = seg_stats(curve, *wb["full"])
    two = seg_stats(curve, *wb["2y"])
    lo, hi = wb["2y"]
    seg = [(d, v) for d, v in curve if lo <= d <= hi]
    days = (seg[-1][0] - seg[0][0]).days
    assert two["cagr"] == pytest.approx((seg[-1][1] / seg[0][1]) ** (365.25 / days) - 1)
    assert two["max_dd"] == pytest.approx(max_dd_of([v for _, v in seg]))
    assert two["max_dd"] <= full["max_dd"]
    pts = curve_points(curve, lo, hi)
    assert len(pts) <= 401 and pts[-1][0] == hi.isoformat()
    assert max(p[2] for p in pts) <= full["max_dd"] + 1e-9
    # per-point dd = drawdown from the running peak on the DAILY prefix (its max = max_dd_of)
    by = {d.isoformat(): v for d, v in seg}
    vals = [v for _, v in seg]
    for ds_, v, dd in pts:
        prefix = vals[: [d.isoformat() for d, _ in seg].index(ds_) + 1]
        assert dd == pytest.approx(1 - v / max(prefix), abs=1e-5)
        assert dd <= max_dd_of(prefix) + 1e-5
    assert by[pts[0][0]] == pytest.approx(pts[0][1], abs=0.01)   # downsample rounds to cents


def test_underwater_and_worst_year():
    ds = dates(5)
    seg = list(zip(ds, [100.0, 120.0, 90.0, 100.0, 130.0]))
    assert max_dd_of([v for _, v in seg]) == pytest.approx(0.25)
    uw = longest_underwater(seg)
    assert uw["peak_date"] == ds[1].isoformat() and uw["recovery_date"] == ds[4].isoformat()
    assert uw["days_trading"] == 3 and uw["days_calendar"] == 3 and not uw["open"]
    seg2 = list(zip(ds, [100.0, 120.0, 90.0, 100.0, 110.0]))
    uw2 = longest_underwater(seg2)
    assert uw2["open"] and uw2["recovery_date"] is None and uw2["days_calendar"] == 3
    # worst year across 3 calendar years, first (partial) year flagged
    cal = dates(800, start=date(2021, 6, 1))
    vals = []
    for d in cal:
        base = {2021: 100.0, 2022: 110.0, 2023: 80.0}[d.year]
        vals.append(base)
    curve = list(zip(cal, vals))
    st = extra_stats(curve, cal[0], cal[-1])
    assert st["worst_year"]["year"] == 2023
    assert st["worst_year"]["return"] == pytest.approx(80 / 110 - 1)
    years = {y["year"]: y for y in st["years"]}
    assert years[2021]["partial"] and not years[2022]["partial"] and years[2023]["partial"]


# --- 14. bootstrap ---------------------------------------------------------------------

def test_bootstrap_determinism():
    rets = [0.001 * ((k % 7) - 3) for k in range(300)]
    a = stationary_bootstrap(rets, 1.2, draws=50, mean_block=21, seed=1)
    b = stationary_bootstrap(rets, 1.2, draws=50, mean_block=21, seed=1)
    c = stationary_bootstrap(rets, 1.2, draws=50, mean_block=21, seed=2)
    assert a == b and a["cagr_pct"] != c["cagr_pct"] and a["draws"] == 50
    const = stationary_bootstrap([0.0005] * 252, 1.0, draws=20, seed=3)
    exp = 1.0005 ** 252 - 1
    for p in ("p5", "p50", "p95"):
        assert const["cagr_pct"][p] == pytest.approx(exp)
        assert const["max_dd_pct"][p] == 0.0
    assert const["prob_cagr_negative"] == 0.0


# --- 15. the whole study on a tiny market -------------------------------------------

def _study_inputs():
    ds = dates(int(3 * 365.25) + 40, start=date(2022, 1, 3))
    bars = {"AAA": trending_bars(ds, 100, 0.05), "BBB": trending_bars(ds, 60, 0.02),
            "CCC": trending_bars(ds, 80, -0.01)}
    for sym, ks in (("AAA", (90, 300, 700)), ("BBB", (150, 500)), ("CCC", (200,))):
        for k in ks:
            b = bars[sym][k]
            bars[sym][k] = BarLike(b.date, b.high, b.low - 15, b.close - 10, b.open)
    mkt = make_market(bars)
    rows = []
    for sym in bars:
        for i in range(20, len(ds) - 5, 37):
            rows.append(fire_row(bars[sym], i, sym))
    tiers = {s: "A" for s in bars}
    bil = {d: 0.00015 for d in ds}
    spy = {d: 400.0 * (1 + 0.0003) ** k for k, d in enumerate(ds)}
    return rows, mkt, tiers, bil, spy


def test_variant_ladder_shape_and_deltas():
    rows, mkt, tiers, bil, spy = _study_inputs()
    ref_rows, _ = build_trailing_rows(rows, mkt, tiers)
    ta, _ = select_capped(gate_rows(ref_rows, mkt["xbi_above_prior"][200], key="entry_date"), 10)
    r2a_end = run_call_book(ta, mkt)[-1][1]
    res = run_mirror(rows, mkt, tiers, r2a_stored_end=r2a_end, bil=bil, spy_px=spy,
                     spy_source="synthetic", draws=20, seed=7)
    names = ["r2a_ref", "r2a_ref_carry", "exec_t1_nocost_nocarry", "exec_t1_nocarry",
             "exec_t2_nocarry", "exec_t2_carry", "exec_t1_carry", "blend3070_t2_carry",
             "blend3070_t1_carry", "blend3070_paper_t2_carry"]
    assert list(res["variants"]) == names
    assert res["protocol"]["cache_verified"] is True
    assert res["machinery"]["reduction_check_max_abs_diff"] <= 1e-6
    assert res["machinery"]["row_reduction_mismatches"] == 0
    assert set(res["windows"]) == {"full", "5y", "2y"}
    for name, v in res["variants"].items():
        assert set(v["windows"]) == {"full", "2y"} or set(v["windows"]) == {"full", "5y", "2y"}
        for w, s in v["windows"].items():
            for k in ("cagr", "max_dd", "sharpe", "sortino", "calmar", "longest_underwater", "worst_year"):
                assert k in s
            pts = v["curves"][w]
            assert all(len(p) == 3 for p in pts) and len(pts) <= 401
        assert ("bootstrap" in v) == (name in ("exec_t2_carry", "blend3070_t2_carry"))
    v4, v5, v3, v0 = (res["variants"][n]["windows"]["full"] for n in
                      ("exec_t2_carry", "exec_t1_carry", "exec_t2_nocarry", "r2a_ref"))
    assert res["deltas"]["t1_vs_t2"]["full"]["cagr"] == pytest.approx(v5["cagr"] - v4["cagr"])
    assert res["deltas"]["carry_on_vs_off"]["full"]["end_value"] == pytest.approx(v4["end_value"] - v3["end_value"])
    assert res["deltas"]["exec_vs_r2a"]["full"]["max_dd"] == pytest.approx(v4["max_dd"] - v0["max_dd"])
    assert v4["end_value"] > v3["end_value"]                     # carry only adds
    assert v4["trades"]["n_trades"] > 0 and v4["trades"]["bil_orders"] > 0
    assert res["variants"]["exec_t1_nocarry"]["windows"]["full"]["end_value"] < \
           res["variants"]["exec_t1_nocost_nocarry"]["windows"]["full"]["end_value"]
    bt = res["variants"]["exec_t2_carry"]["bootstrap"]["full"]
    assert bt["draws"] == 20 and bt["cagr"] == bt["cagr_pct"] and bt["max_dd"] == bt["max_dd_pct"]
    assert v4["n_trades"] == v4["trades"]["n_trades"]
    assert res["rows"]["1"]["n_taken"] > 0 and res["rows"]["2"]["n_taken"] > 0
    assert len(res["honesty"]) >= 8
    json.dumps(mod._round(res), default=str)                    # serializable


def test_machinery_check_refuses_drift(tmp_path, monkeypatch):
    rows, mkt, tiers, bil, spy = _study_inputs()
    ref_rows, _ = build_trailing_rows(rows, mkt, tiers)
    ta, _ = select_capped(gate_rows(ref_rows, mkt["xbi_above_prior"][200], key="entry_date"), 10)
    r2a_end = run_call_book(ta, mkt)[-1][1]
    big = 0.05 * r2a_end                    # 5% off: outside the +/-1% V0 tolerance
    with pytest.raises(SystemExit, match="MACHINERY CHECK FAILED"):
        run_mirror(rows, mkt, tiers, r2a_stored_end=r2a_end + big, bil=bil, spy_px=spy, draws=5)
    res = run_mirror(rows, mkt, tiers, r2a_stored_end=r2a_end + big, bil=bil, spy_px=spy,
                     draws=5, allow_cache_drift=True)
    assert res["protocol"]["cache_verified"] is False
    assert res["protocol"]["cache_exact"] is False
    assert res["protocol"]["r2a_reproduction"]["abs_diff"] == pytest.approx(big)
    assert res["protocol"]["r2a_reproduction"]["rel_diff"] == pytest.approx(big / (r2a_end + big), rel=1e-9)
    # inside the tolerance but not to the dollar: verified, not exact, honesty line, lane recorded
    small = 0.004 * r2a_end
    res2 = run_mirror(rows, mkt, tiers, r2a_stored_end=r2a_end + small, bil=bil, spy_px=spy,
                      draws=5, cache_basis={"lane": "fmp dividend-adjusted", "normalized": {}})
    assert res2["protocol"]["cache_verified"] is True and res2["protocol"]["cache_exact"] is False
    assert res2["protocol"]["cache_basis"]["lane"] == "fmp dividend-adjusted"
    assert any("NOT THE AUGUST CAMPAIGN CACHE" in h and "fmp dividend-adjusted" in h
               for h in res2["honesty"])
    # to the dollar: exact, no basis line
    res3 = run_mirror(rows, mkt, tiers, r2a_stored_end=r2a_end + 0.5, bil=bil, spy_px=spy, draws=5)
    assert res3["protocol"]["cache_verified"] is True and res3["protocol"]["cache_exact"] is True
    assert not any("NOT THE AUGUST" in h for h in res3["honesty"])
    # the strict dollar standard is still available as a parameter
    with pytest.raises(SystemExit):
        run_mirror(rows, mkt, tiers, r2a_stored_end=r2a_end + small, bil=bil, spy_px=spy,
                   draws=5, machinery_tol_rel=0.0)
    big = r2a_end + big
    # main(): a failed check writes nothing; --allow-cache-drift writes the JSON + report section
    out, rep = tmp_path / "res.json", tmp_path / "doc.md"
    rep.write_text("# doc\n\nintro\n\n" + mod.REPORT_BEGIN + "\nold\n" + mod.REPORT_END + "\n\ntail\n")
    monkeypatch.setattr(mod, "load_inputs", lambda fetch_missing=False, **kw: {
        "fire_rows": rows, "tiers": tiers, "mkt": mkt, "bil": bil, "proxy_days": [],
        "spy_px": spy, "spy_source": "synthetic", "r2a_stored_end": big, "r3": None})
    with pytest.raises(SystemExit):
        mod.main(["--out", str(out), "--report", str(rep), "--draws", "5"])
    assert not out.exists() and "old" in rep.read_text()
    assert mod.main(["--out", str(out), "--report", str(rep), "--draws", "5",
                     "--allow-cache-drift"]) == 0
    data = json.loads(out.read_text())
    assert data["protocol"]["cache_verified"] is False
    text = rep.read_text()
    assert "old" not in text and "RED: cache NOT verified" in text
    assert text.startswith("# doc\n\nintro") and text.rstrip().endswith("tail")
    assert "exec_t2_carry" in text


def test_load_inputs_rebuilds_a_missing_cache_on_the_fmp_lane(tmp_path, monkeypatch):
    """The August campaign cache is gone: a missing cache is rebuilt via
    scripts/refresh_backtest_bars (needs FMP), never silently analysed around;
    the sidecar it writes is carried into the results as cache_basis."""
    missing = tmp_path / "backtest_bars.json"
    monkeypatch.setattr(mod, "CACHE", missing)
    monkeypatch.setattr(mod, "BASIS_SIDECAR", tmp_path / "backtest_bars_basis.json")
    monkeypatch.setattr(mod, "R2A_DAILY", tmp_path / "r2a_daily.json")
    calls = []
    monkeypatch.setattr(mod, "refresh_bars", lambda: calls.append("refresh"))
    # no rebuild requested -> the SystemExit names the refresh script
    with pytest.raises(SystemExit, match="refresh_backtest_bars"):
        mod.load_inputs()
    assert calls == []
    # rebuild requested -> refresh runs; the cache is still absent here (stub), so it exits
    with pytest.raises(SystemExit):
        mod.load_inputs(refresh_bars_if_missing=True)
    assert calls == ["refresh"]
    # force refresh runs even when the cache exists; stop right after it
    missing.write_text("{}")
    monkeypatch.setattr(mod, "load_market", lambda: (_ for _ in ()).throw(RuntimeError("stop")))
    with pytest.raises(RuntimeError, match="stop"):
        mod.load_inputs(force_refresh=True)
    assert calls == ["refresh", "refresh"]
    # a lane cache (sidecar) without spy_bars_raw.json is incomplete -> rebuilt
    monkeypatch.setattr(mod, "SPY_RAW", tmp_path / "spy_bars_raw.json")
    (tmp_path / "backtest_bars_basis.json").write_text(json.dumps({"lane": "fmp dividend-adjusted"}))
    assert mod._cache_incomplete().startswith("incomplete")
    with pytest.raises(RuntimeError, match="stop"):
        mod.load_inputs(refresh_bars_if_missing=True)
    assert calls == ["refresh", "refresh", "refresh"]
    # an unreadable cache is incomplete too; a complete lane cache is not
    missing.write_text("{not json")
    assert mod._cache_incomplete() == "unreadable"
    missing.write_text("{}")
    (tmp_path / "spy_bars_raw.json").write_text(json.dumps({"data": []}))
    assert mod._cache_incomplete() is None
    # the sidecar is read when present
    (tmp_path / "backtest_bars_basis.json").write_text(
        json.dumps({"lane": "fmp dividend-adjusted", "normalized": {"ATAI": {"factor": 0.0728}}}))
    assert mod.load_cache_basis()["normalized"]["ATAI"]["factor"] == 0.0728


def test_bars_past_the_campaign_data_end_are_clipped_and_counted():
    """Bars after END would ENTER the open-at-end calls the campaign excluded
    (counter-agent HIGH): clip them and report the trade-set counts."""
    rows, mkt, tiers, bil, spy = _study_inputs()
    last = max(b.date for bars in mkt["bars"].values() for b in bars)
    end = last - timedelta(days=120)
    ref_rows, open_before = build_trailing_rows(rows, mkt, tiers)
    info = mod.clip_bars_to(mkt, end)
    assert info["last_bar_before_clip"] == last.isoformat() and info["clipped_to"] == end.isoformat()
    assert info["bars_dropped"] > 0 and info["gate_defined_from"]
    assert all(b.date <= end for bars in mkt["bars"].values() for b in bars)
    ref_after, open_after = build_trailing_rows(rows, mkt, tiers)
    # the late fires are now open at data end or never graded: never ENTERED
    assert open_after >= open_before and len(ref_after) < len(ref_rows)
    # run_mirror reports the counts against a stored meta and flags a mismatch in honesty
    ta, sa = select_capped(gate_rows(ref_after, mkt["xbi_above_prior"][200], key="entry_date"), 10)
    r2a_curve = run_call_book(ta, mkt)
    meta = {"n_regraded": len(ref_after), "open_at_end_excluded": open_after,
            "n_taken": len(ta), "skipped_at_cap": sa}
    res = run_mirror(rows, mkt, tiers, r2a_stored_end=r2a_curve[-1][1] + 0.002 * r2a_curve[-1][1],
                     bil=bil, spy_px=spy, draws=5, end=end, r2a_stored_meta=meta,
                     r2a_stored_curve=r2a_curve, bars_info=info,
                     cache_basis={"lane": "fmp dividend-adjusted"})
    m = res["machinery"]
    assert m["rows"]["match"] is True and m["bars"]["clipped_to"] == end.isoformat()
    assert m["curve"]["max_rel_diff"] == 0 and m["curve_within_tolerance"] is True
    assert res["protocol"]["cache_verified"] is True and res["protocol"]["cache_exact"] is False
    line = [h for h in res["honesty"] if "NOT THE AUGUST" in h][0]
    assert "clipped to " + end.isoformat() in line and "trade set identical" in line
    # a stored meta that disagrees is named, not hidden
    res2 = run_mirror(rows, mkt, tiers, r2a_stored_end=r2a_curve[-1][1] + 0.002 * r2a_curve[-1][1],
                      bil=bil, spy_px=spy, draws=5, end=end,
                      r2a_stored_meta=dict(meta, n_taken=meta["n_taken"] + 1),
                      r2a_stored_curve=r2a_curve, bars_info=info)
    assert res2["machinery"]["rows"]["match"] is False
    assert res2["machinery"]["bar_coverage_matches_stored"] is True       # n_taken is report-only
    assert res2["protocol"]["cache_verified"] is True
    assert any("TRADE SET DIFFERS" in h for h in res2["honesty"])
    # a bar-coverage count that differs GATES the verdict (counter-agent N1)
    with pytest.raises(SystemExit, match="trade set"):
        run_mirror(rows, mkt, tiers, r2a_stored_end=r2a_curve[-1][1], bil=bil, spy_px=spy, draws=5,
                   end=end, r2a_stored_meta=dict(meta, open_at_end_excluded=meta["open_at_end_excluded"] + 1),
                   r2a_stored_curve=r2a_curve, bars_info=info)
    # exact end + differing taken count still gets an honesty line
    res3 = run_mirror(rows, mkt, tiers, r2a_stored_end=r2a_curve[-1][1], bil=bil, spy_px=spy, draws=5,
                      end=end, r2a_stored_meta=dict(meta, n_taken=meta["n_taken"] + 1),
                      r2a_stored_curve=r2a_curve, bars_info=info)
    assert res3["protocol"]["cache_exact"] is True
    assert any("TRADE SET DIFFERS" in h for h in res3["honesty"])
    # a stored curve with a missing date is a calendar mismatch and refuses (counter-agent N2)
    short = r2a_curve[:-3]
    chk = mod._curve_reproduction(r2a_curve, short)
    assert chk["n_compared"] == chk["n_stored"] == len(short) and chk["n_got"] == len(r2a_curve)
    with pytest.raises(SystemExit, match="calendar mismatch"):
        run_mirror(rows, mkt, tiers, r2a_stored_end=r2a_curve[-1][1], bil=bil, spy_px=spy, draws=5,
                   end=end, r2a_stored_curve=short)


def test_curve_level_check_refuses_a_different_drawdown():
    """Same end value, different path: the end-only check passed, the curve
    check must not (counter-agent MED)."""
    rows, mkt, tiers, bil, spy = _study_inputs()
    ref_rows, _ = build_trailing_rows(rows, mkt, tiers)
    ta, _ = select_capped(gate_rows(ref_rows, mkt["xbi_above_prior"][200], key="entry_date"), 10)
    curve = run_call_book(ta, mkt)
    # a stored curve with the same end but a 30% dip in the middle
    k = len(curve) // 2
    dipped = [(d, v * (0.7 if k - 20 <= i <= k + 20 else 1.0)) for i, (d, v) in enumerate(curve)]
    chk = mod._curve_reproduction(curve, dipped)
    assert chk["n_compared"] == len(curve) and chk["max_rel_diff"] > 0.3
    assert chk["max_dd_abs_diff"] > mod.MAXDD_TOL
    with pytest.raises(SystemExit, match="curve max point-wise gap"):
        run_mirror(rows, mkt, tiers, r2a_stored_end=curve[-1][1], bil=bil, spy_px=spy, draws=5,
                   r2a_stored_curve=dipped)
    res = run_mirror(rows, mkt, tiers, r2a_stored_end=curve[-1][1], bil=bil, spy_px=spy, draws=5,
                     r2a_stored_curve=dipped, allow_cache_drift=True)
    assert res["protocol"]["cache_verified"] is False and res["machinery"]["end_within_tolerance"] is True
    # the stored curve as ISO-date strings (the JSON on disk) compares identically
    iso = [(d.isoformat(), v) for d, v in curve]
    assert mod._curve_reproduction(curve, iso)["max_rel_diff"] == 0
    assert mod._curve_reproduction(curve, None) is None


def test_refresh_script_resolves_seed_data_and_writes_atomically(tmp_path, monkeypatch):
    """On Render the disk is mounted AT data/ and hides the committed inputs
    (counter-agent HIGH); and nothing may be written until every fetch is in
    hand (MED)."""
    import scripts.refresh_backtest_bars as rb
    data, seed = tmp_path / "data", tmp_path / "seed_data"
    data.mkdir(); seed.mkdir()
    (seed / "backtest_calls_10y_results.json").write_text(json.dumps({
        "tiers": {"AAA": "A"}, "call_rows": {"f": [{"symbol": "AAA", "entry_date": "2020-01-02", "entry": 10.0}]}}))
    monkeypatch.setattr(rb, "DATA", data); monkeypatch.setattr(rb, "SEED_DATA", seed)
    monkeypatch.setattr(rb, "CALLS_RESULTS", data / "backtest_calls_10y_results.json")
    monkeypatch.setattr(rb, "BARS_CACHE", data / "backtest_bars.json")
    monkeypatch.setattr(rb, "BASIS_SIDECAR", data / "backtest_bars_basis.json")
    monkeypatch.setattr(rb, "SPY_RAW", data / "spy_bars_raw.json")
    monkeypatch.setattr(rb, "LANE_CACHE", data / "lane")
    assert rb.universe() == ["AAA", "XBI"]            # resolved from seed_data
    row = {"date": "2020-01-02", "adjOpen": 10.0, "adjHigh": 11.0, "adjLow": 9.0, "adjClose": 10.5, "volume": 1}
    # SPY fetch fails -> nothing written at all
    def fetch_fail(sym, start, cache_dir):
        if sym == "SPY":
            raise RuntimeError("rate limited")
        return [row]
    monkeypatch.setattr(rb, "fmp_bars", fetch_fail)
    with pytest.raises(RuntimeError):
        rb.main()
    assert not (data / "backtest_bars.json").exists() and not (data / "spy_bars_raw.json").exists()
    assert not list(data.glob("*.tmp"))
    # all fetches succeed -> all three files, the cache last, the lane start recorded
    monkeypatch.setattr(rb, "fmp_bars", lambda sym, start, cache_dir: [row])
    rb.main()
    assert json.loads((data / "backtest_bars.json").read_text())["AAA"][0]["close"] == 10.5
    assert json.loads((data / "spy_bars_raw.json").read_text())["data"] == [{"t": "2020-01-02", "a": 10.5}]
    side = json.loads((data / "backtest_bars_basis.json").read_text())
    assert side["lane"] == "fmp dividend-adjusted" and side["start"] == rb.START == "2015-07-23"
    assert not list(data.glob("*.tmp"))
    # a failure INSIDE the atomic write leaves neither a tmp file nor a target (counter-agent N4)
    import os
    target = data / "atomic_probe.json"
    monkeypatch.setattr(rb.os, "replace", lambda a, b: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        rb._write_atomic(target, "{}")
    assert not target.exists() and not list(data.glob("atomic_probe.json.*"))


def test_divergence_report_names_the_first_date_and_the_suspect_exits():
    rows, mkt, tiers, bil, spy = _study_inputs()
    ref_rows, _ = build_trailing_rows(rows, mkt, tiers)
    ta, _ = select_capped(gate_rows(ref_rows, mkt["xbi_above_prior"][200], key="entry_date"), 10)
    curve = run_call_book(ta, mkt)
    assert mod.divergence_report(curve, curve, ta, mkt)["first_divergence"] is None
    # the frozen curve departs after an exit in the middle of the run
    k = len(curve) // 2
    d0 = curve[k][0]
    exits = sorted(t["exit_date"] for t in ta if date.fromisoformat(t["exit_date"]) <= d0)
    stored = [(d, v * (1.02 if i >= k else 1.0)) for i, (d, v) in enumerate(curve)]
    rep = mod.divergence_report(curve, stored, ta, mkt)
    assert rep["first_divergence"]["date"] == d0.isoformat()
    assert rep["first_divergence"]["rel_diff"] == pytest.approx(-0.02 / 1.02, rel=1e-6)
    # the step is the largest jump, and it is the same date
    assert rep["jumps"][0]["date"] == d0.isoformat()
    assert rep["jumps"][0]["delta"] == pytest.approx(0.02 / 1.02, rel=1e-6)
    assert rep["jumps"][0]["rel_diff_before"] == 0 and len(rep["jumps"]) == 5
    sus = rep["jumps"][0]["suspects"]
    full = next(c for c in rep["crossings"] if c["threshold"] == 0.005)["suspects"]
    assert all(len(s["bars_around_exit"]) >= 5 and {"open", "high", "low", "close"} <= set(s["bars_around_exit"][0])
               for s in full if s["bars_around_exit"])
    lo = (d0 - timedelta(days=15)).isoformat(); hi = (d0 + timedelta(days=2)).isoformat()
    assert all(lo <= s["exit_date"] <= hi or lo <= s["entry_date"] <= hi for s in sus)
    assert all("bars_around_exit" not in s for s in sus)      # jumps are slim; bars live on the 0.5% crossing
    assert sus == sorted(sus, key=lambda t: t["exit_date"])
    assert rep["first_divergence"]["suspects"] == [{k: v for k, v in t.items() if k != "bars_around_exit"} for t in sus]
    # crossings: a 2% step crosses 0.1 / 0.5 / 1% on the same date, never 2% or 5%
    assert [c["threshold"] for c in rep["crossings"]] == [0.001, 0.005, 0.01]
    assert all(c["date"] == d0.isoformat() for c in rep["crossings"])
    c5 = next(c for c in rep["crossings"] if c["threshold"] == 0.005)
    assert [{k: v for k, v in t.items() if k != "bars_around_exit"} for t in c5["suspects"]] == sus and all("bars_around_exit" not in t for t in rep["crossings"][0]["suspects"])
    assert all(t["entry_date"] <= d0.isoformat() <= t["exit_date"] for t in c5["open_positions"])
    assert len(c5["open_positions"]) == sum(1 for t in ta if t["entry_date"] <= d0.isoformat() <= t["exit_date"])
    # the ISO-string shape of the on-disk curve works too
    assert mod.divergence_report(curve, [(d.isoformat(), v) for d, v in stored], ta, mkt)["first_divergence"]["date"] == d0.isoformat()


def test_refresh_basis_factor_catches_a_sub_percent_constant_offset():
    """ILMN on the FMP lane is a constant 0.095% below the frozen entries;
    a 0.5% unity tolerance left it alone and the replay drifted 8.7%."""
    import scripts.refresh_backtest_bars as rb
    entries = [(f"2020-01-{d:02d}", 100.0 + d) for d in range(2, 12)]
    lane = {d: {"open": e * 0.99905} for d, e in entries}
    f = rb.basis_factor(lane, entries)
    assert f is not None and f["factor"] == pytest.approx(0.99905, abs=1e-6) and f["n"] == 10
    # a genuinely-on-basis series (rounding noise only) is left alone
    noise = {d: {"open": e * (1 + ((i % 3) - 1) * 2e-5)} for i, (d, e) in enumerate(entries)}
    assert rb.basis_factor(noise, entries) is None
    # a DRIFTING ratio is left alone so the machinery gate sees it
    drift = {d: {"open": e * (1 + 0.002 * i)} for i, (d, e) in enumerate(entries)}
    assert rb.basis_factor(drift, entries) is None


def test_row_mismatch_examples_name_the_rows():
    a = [{"fire_date": "2026-07-17", "symbol": "ATAI", "flag": "x_trail", "entry_date": "2026-07-23",
          "exit_date": "2026-07-31", "status": "stopped", "entry": 2.99, "exit": 2.43, "r_net": -1.09}]
    b = [dict(a[0], entry_date="2026-07-21")]
    assert mod._row_mismatches(a, b) == 1
    assert mod._row_mismatch_examples(a, b) == [["2026-07-17", "ATAI", "x"]]
    assert mod._row_mismatch_examples(a, a) == []


# --- 16. API ---------------------------------------------------------------------------

class _FakeProc:
    def __init__(self, rc=0):
        self.done = threading.Event()
        self.rc = rc
        self.pid = 4242

    def wait(self):
        self.done.wait(timeout=10)
        return self.rc


@pytest.fixture
def api(tmp_path, monkeypatch):
    from app.main import app
    from app.routers import mirror_backtest as mb

    disk, committed = tmp_path / "disk" / "res.json", tmp_path / "committed" / "res.json"
    monkeypatch.setattr(mb, "disk_path", lambda: disk)
    monkeypatch.setattr(mb, "committed_path", lambda: committed)
    monkeypatch.setattr(mb, "_state", {"running": False, "started_at": None, "finished_at": None,
                                       "returncode": None, "error": None, "pid": None})
    return TestClient(app), mb, disk, committed


def test_api_mirror_backtest_get_and_status(api):
    client, mb, disk, committed = api
    r = client.get("/blend3070/mirror-backtest")
    assert r.status_code == 404 and "not run yet" in r.json()["detail"]
    st = client.get("/blend3070/mirror-backtest/status").json()
    assert set(st) == {"running", "started_at", "finished_at", "returncode", "error",
                       "last_run", "results_present", "served_from"}
    assert st["results_present"] is False and st["running"] is False
    committed.parent.mkdir()
    committed.write_text(json.dumps({"generated": "c", "variants": {}}))
    r = client.get("/blend3070/mirror-backtest")
    assert r.status_code == 200 and r.json()["served_from"] == "committed"
    disk.parent.mkdir()
    disk.write_text(json.dumps({"generated": "d", "variants": {}}))
    r = client.get("/blend3070/mirror-backtest")
    assert r.json()["served_from"] == "disk" and r.json()["generated"] == "d"
    st = client.get("/blend3070/mirror-backtest/status").json()
    assert st["last_run"] == "d" and st["results_present"] and st["served_from"] == "disk"


def test_api_mirror_backtest_run_single_flight(api, monkeypatch):
    client, mb, disk, committed = api
    procs: list[_FakeProc] = []
    calls: list[dict] = []

    def fake_popen(cmd, rc=0, text="replay ok\n", **kw):
        calls.append({"cmd": cmd, **kw})
        kw["stdout"].write(text)            # the child's stdout is the log file
        p = _FakeProc(rc=rc)
        procs.append(p)
        return p

    monkeypatch.setattr(mb, "popen", fake_popen)
    r = client.post("/blend3070/mirror-backtest/run")
    assert r.status_code == 202 and r.json()["started_at"]
    assert calls[0]["cmd"][1:3] == ["-m", "scripts.backtest_executor_mirror"]
    assert "--out" in calls[0]["cmd"] and str(disk) in calls[0]["cmd"] and "--fetch-missing" in calls[0]["cmd"]
    assert "--no-report" in calls[0]["cmd"]          # the doc is not writable on the host
    assert client.post("/blend3070/mirror-backtest/run").status_code == 409
    assert client.get("/blend3070/mirror-backtest/status").json()["running"] is True
    procs[0].done.set()
    for _ in range(100):
        if not client.get("/blend3070/mirror-backtest/status").json()["running"]:
            break
        threading.Event().wait(0.02)
    st = client.get("/blend3070/mirror-backtest/status").json()
    assert st["running"] is False and st["returncode"] == 0 and st["error"] is None
    # a failing run surfaces the log tail as the error
    assert (disk.parent / mb.LOG_NAME).read_text() == "replay ok\n"
    monkeypatch.setattr(mb, "popen", lambda cmd, **kw: fake_popen(
        cmd, rc=1, text="line1\nMACHINERY CHECK FAILED: bars cache missing\n", **kw))
    assert client.post("/blend3070/mirror-backtest/run").status_code == 202
    procs[-1].done.set()
    for _ in range(100):
        st = client.get("/blend3070/mirror-backtest/status").json()
        if not st["running"]:
            break
        threading.Event().wait(0.02)
    assert st["returncode"] == 1 and "MACHINERY CHECK FAILED" in st["error"]
    assert client.post("/blend3070/mirror-backtest/run").status_code == 202   # free again
    procs[-1].done.set()


def test_api_mirror_backtest_run_skips_refresh_when_cache_present(api, tmp_path, monkeypatch):
    client, mb, disk, committed = api
    cache = tmp_path / "backtest_bars.json"
    monkeypatch.setattr(mb, "bars_cache_path", lambda: cache)
    calls = []
    def fake_popen(cmd, **kw):
        calls.append(cmd); p = _FakeProc(); p.done.set(); return p
    monkeypatch.setattr(mb, "popen", fake_popen)
    assert client.post("/blend3070/mirror-backtest/run").status_code == 202
    assert "--refresh-bars" in calls[0]
    import time
    for _ in range(50):
        if not mb._state["running"]: break
        time.sleep(0.05)
    cache.write_text("{}")
    assert client.post("/blend3070/mirror-backtest/run").status_code == 202
    assert "--refresh-bars" not in calls[1]


def test_api_mirror_backtest_basic_auth_gate(api, monkeypatch):
    from app.config import settings as cfg

    client, mb, disk, committed = api
    monkeypatch.setattr(cfg, "dashboard_user", "casey")
    monkeypatch.setattr(cfg, "dashboard_password", "pw")
    monkeypatch.setattr(cfg, "blend_api_token", "tok-123")
    assert client.get("/blend3070/mirror-backtest/status").status_code == 401
    assert client.post("/blend3070/mirror-backtest/run").status_code == 401
    # the intents-only token does NOT open these routes
    assert client.get("/blend3070/mirror-backtest/status",
                      headers={"X-API-Token": "tok-123"}).status_code == 401
    assert client.get("/blend3070/mirror-backtest/status", auth=("casey", "pw")).status_code == 200
    assert client.get("/blend3070/mirror-backtest", auth=("casey", "pw")).status_code == 404


def test_api_mirror_backtest_seed_fallback(api, tmp_path, monkeypatch):
    """On Render the disk mount hides the committed file: the image's
    seed_data copy is the last fallback, labelled so the UI can say so."""
    client, mb, disk, committed = api
    seed = tmp_path / "seed_data" / "res.json"
    monkeypatch.setattr(mb, "seed_path", lambda: seed)
    assert client.get("/blend3070/mirror-backtest").status_code == 404
    seed.parent.mkdir()
    seed.write_text(json.dumps({"generated": "s", "variants": {}}))
    r = client.get("/blend3070/mirror-backtest")
    assert r.status_code == 200 and r.json()["served_from"].startswith("seed")
    # the mounted disk and the committed path coinciding is labelled, not "committed"
    monkeypatch.setattr(mb, "committed_path", lambda: disk)
    disk.parent.mkdir()
    disk.write_text(json.dumps({"generated": "d", "variants": {}}))
    assert client.get("/blend3070/mirror-backtest").json()["served_from"] == "disk (same path as committed)"


def test_spy_is_adjusted_detects_a_price_return_cache(tmp_path):
    from scripts import backtest_executor_mirror as mod
    cache = tmp_path / "bars.json"
    cache.write_text(json.dumps({"XBI": [{"close": 1.0, "adj_close": 0.9}]}))
    assert mod.spy_is_adjusted(cache) is None                       # no SPY
    cache.write_text(json.dumps({"SPY": [{"close": 100.0, "adj_close": 100.0},
                                         {"close": 101.0, "adj_close": 101.0}]}))
    assert mod.spy_is_adjusted(cache) is False                      # FMP-style: price return only
    cache.write_text(json.dumps({"SPY": [{"close": 100.0, "adj_close": 98.7},
                                         {"close": 101.0, "adj_close": 101.0}]}))
    assert mod.spy_is_adjusted(cache) is True
    assert mod.spy_is_adjusted(tmp_path / "missing.json") is None
    # a price-return SPY adds the honesty line to the results
    import inspect
    src = inspect.getsource(mod.run_mirror)
    assert "SPY IS PRICE-RETURN ONLY" in src and "spy_adjusted is False" in src
