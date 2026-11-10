"""Gate tests for the two pre-registered candidates (CANDIDATES.md) and the
per-leg MTM the attribution uses. Each candidate is an Options switch in
stress.py, default OFF: with both off the harness must reproduce the headline
run to the cent."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stress                                                      # noqa: E402
import run_all                                                     # noqa: E402
from stress import (BAR, DAY, Options, Trade, build_spliced,       # noqa: E402
                    fast_brake_mult, run_executor, run_path, synthetic_path)

NOW = stress.SEED_NOW


@pytest.fixture(scope="module")
def covid():
    bb = build_spliced("btcusd", "2020-02-13", now=NOW)
    be = build_spliced("ethusd", "2020-02-13", now=NOW)
    fund, _ = run_all.funding_for(bb.anchor_ts, len(bb.path), bb.t0, "XBTUSD")
    cr = run_all.run_carry(be, fund)
    return bb, cr.value, run_all.btc_funding_from(fund)


def _run(covid, opt: Options | None):
    bb, cv, bf = covid
    return run_path("cand_test", bb, 0.75, carry_value=cv, btc_funding=bf, save=False,
                    options=opt, extra=dict(offset_days=0))


# (i) options off == the headline run, to the cent; per-leg MTM identity -------
def test_options_off_is_the_headline_and_leg_mtm_closes(covid):
    r0 = _run(covid, None)
    r1 = _run(covid, Options())
    assert r0["options"]["tag"] == "base" and not Options().any()
    assert r0["balances"]["365"]["equity"] == pytest.approx(115_986.66, abs=0.01)   # results.json
    assert r0["max_dd"] == pytest.approx(-0.2102, abs=1e-4)
    assert r0["equity_total"] == r1["equity_total"]
    assert r0["brake_counts"] == dict(fast_binding=0, damped=0)
    for t in r0["trades"]:
        assert t["mult_live"] == t["size_mult"] and t["mult_fast"] == 1.0 and t["damp"] == 1.0
    pb, tr, eb = (np.asarray(r0["leg_mtm"]["pullback"]), np.asarray(r0["leg_mtm"]["trend"]),
                  np.asarray(r0["equity_btc"]))
    assert np.max(np.abs(70_000.0 + pb + tr - eb)) <= 0.02
    assert r0["realised_by_leg"]["pullback"] == pytest.approx(
        sum(t["pnl"] for t in r0["trades"] if t["leg"] == "pullback" and t["reason"] != "OPEN"), abs=0.05)


# (ii) C1: the pure function, then the pullback-only effect on the COVID path --
def test_fast_brake_mult_hand_values():
    ref = 0.01
    arr = np.full(3_000, ref)
    arr[-1] = 5 * ref                                   # now = 5 x ref -> floor
    assert fast_brake_mult(arr, len(arr) - 1)["m"] == pytest.approx(0.25)
    arr[-1] = 2 * ref
    assert fast_brake_mult(arr, len(arr) - 1)["m"] == pytest.approx(0.5)
    arr[-1] = 0.5 * ref                                 # calm: never above 1.0
    assert fast_brake_mult(arr, len(arr) - 1)["m"] == 1.0
    arr[-1] = 2 * ref
    assert fast_brake_mult(arr[:1_000], 999)["basis"] == "insufficient_history"   # < 0.9 x 2190 valid
    assert fast_brake_mult(arr, None)["m"] == 1.0
    assert fast_brake_mult(arr, len(arr) - 1)["basis"] == "fast_brake"


def test_fast_brake_scales_pullback_only(covid):
    bb, _, _ = covid
    r0 = _run(covid, None)
    r1 = _run(covid, Options(fast_brake=True))
    assert r1["options"]["tag"] == "C1"
    # the trend leg is untouched: same trades, same quantities
    tr0 = [t for t in r0["trades"] if t["leg"] == "trend"]
    tr1 = [t for t in r1["trades"] if t["leg"] == "trend"]
    assert [(t["entry_ts"], t["qty"]) for t in tr0] == [(t["entry_ts"], t["qty"]) for t in tr1]
    # the pullback leg: qty scales by min(m_live, m_fast) / m_live, m_fast recomputed
    # here independently from the engine's ATR at the signal bar
    from app.indicators import atr
    a = atr([b.high for b in bb], [b.low for b in bb], [b.close for b in bb], 14)
    frac = np.array([(x / b.close) if x is not None else np.nan for x, b in zip(a, bb)])
    idx = {b.ts: i for i, b in enumerate(bb)}
    pb0 = {t["entry_ts"]: t for t in r0["trades"] if t["leg"] == "pullback"}
    pb1 = {t["entry_ts"]: t for t in r1["trades"] if t["leg"] == "pullback"}
    assert pb0.keys() == pb1.keys()
    binding = 0
    for ts, t1 in pb1.items():
        t0 = pb0[ts]
        i = idx[ts - BAR]
        win = frac[i - 2_190 + 1:i + 1]
        m_fast = min(1.0, max(0.25, float(np.median(win[~np.isnan(win)])) / frac[i]))
        assert t1["mult_fast"] == pytest.approx(round(m_fast, 4), abs=1e-4)
        assert t1["mult_live"] == t0["size_mult"]
        assert t1["size_mult"] == pytest.approx(min(t0["size_mult"], t1["mult_fast"]), abs=1e-4)
        assert t1["qty"] == pytest.approx(t0["qty"] * t1["size_mult"] / t0["size_mult"], rel=1e-6)
        binding += t1["mult_fast"] < t1["mult_live"]
    assert binding >= 1 and r1["brake_counts"]["fast_binding"] == binding
    assert r1["brake_counts"]["damped"] == 0
    # the engine's trade lists and paper-book halts are not touched by sizing
    assert r1["published_trades"] == r0["published_trades"]
    assert r1["engine_halts_info"]["pullback"]["halt_date"] == r0["engine_halts_info"]["pullback"]["halt_date"]


# (iii) C2: the damper on a synthetic stop cluster; the trend leg untouched -------
def test_post_stop_damper_on_a_stop_cluster():
    real = stress.load_closed_bars("btcusd", now=NOW)
    c0 = real[-1].close
    sp = synthetic_path([c0] * 80, now=NOW)            # flat: every fill at c0, m_live = 1.0
    t0, px = sp.t0, sp[sp.seam].open
    mk = lambda e, x, reason: Trade("pullback", "L", t0 + e * BAR, px,  # noqa: E731
                                    t0 + x * BAR, px, reason)
    pullback = [
        mk(0, 2, "STOP"),            # stop 1
        mk(3, 5, "STOP"),            # re-entry 4h after stop 1 -> x0.5; stop 2
        mk(6, 8, "STOP"),            # re-entry 4h after stop 2 -> x0.25; stop 3
        mk(9, 11, "SIGNAL"),         # re-entry 4h after stop 3 -> x0.25; SIGNAL exit resets
        mk(12, 14, "STOP"),          # full size again (streak reset by the SIGNAL); stop
        mk(14 + 31, 60, "STOP"),     # 31 bars = 5d 4h after the stop: > 5 days -> full size
        mk(61, 63, "SIGNAL"),        # 4h after a stop -> x0.5
    ]
    trend = [Trade("trend", "S", t0, px, t0 + 70 * BAR, px, "TIME")]
    ex0 = run_executor(sp, {"pullback": pullback, "trend": trend}, 0.75)
    ex1 = run_executor(sp, {"pullback": pullback, "trend": trend}, 0.75,
                       options=Options(post_stop_damper=True))
    q0 = [t["qty"] for t in ex0.trades if t["leg"] == "pullback"]
    p1 = [t for t in ex1.trades if t["leg"] == "pullback"]
    assert all(t["size_mult"] == 1.0 for t in ex0.trades)       # precondition: flat path
    assert [t["damp"] for t in p1] == [1.0, 0.5, 0.25, 0.25, 1.0, 1.0, 0.5]
    assert [t["streak"] for t in p1] == [0, 1, 2, 3, 0, 0, 1]
    for q, t in zip(q0, p1):
        assert t["qty"] == pytest.approx(q * t["damp"], abs=1e-7)     # records round qty to 8 dp
        assert t["mult_fast"] == 1.0 and t["mult_live"] == 1.0
    assert ex1.brake_counts == dict(fast_binding=0, damped=4)
    # trend untouched
    assert [t["qty"] for t in ex0.trades if t["leg"] == "trend"] == \
        [t["qty"] for t in ex1.trades if t["leg"] == "trend"]
    # a window edge: exactly 5 days after the stop is still inside the window
    edge = [mk(0, 2, "STOP"), mk(2 + 30, 40, "SIGNAL")]
    ex2 = run_executor(sp, {"pullback": edge, "trend": []}, 0.75, options=Options(post_stop_damper=True))
    assert [t["damp"] for t in ex2.trades] == [1.0, 0.5]
    assert ex2.trades[1]["entry_ts"] - ex2.trades[0]["exit_ts"] == 5 * DAY


# (iv) both together compound on the pullback leg; run files carry the tag ------
def test_both_compound_and_run_file_tag(covid, monkeypatch, tmp_path):
    r1 = _run(covid, Options(fast_brake=True))
    r2 = _run(covid, Options(post_stop_damper=True))
    r12 = _run(covid, Options(fast_brake=True, post_stop_damper=True))
    assert r12["options"]["tag"] == "C1+C2"
    pb1 = {t["entry_ts"]: t for t in r1["trades"] if t["leg"] == "pullback"}
    pb2 = {t["entry_ts"]: t for t in r2["trades"] if t["leg"] == "pullback"}
    for t in r12["trades"]:
        if t["leg"] == "pullback":
            assert t["size_mult"] == pytest.approx(
                min(t["mult_live"], pb1[t["entry_ts"]]["mult_fast"]) * pb2[t["entry_ts"]]["damp"], abs=1e-4)
    assert r2["brake_counts"]["damped"] >= 1
    # file names: no tag for the book as deployed, a tag for every option set
    monkeypatch.setattr(stress, "RUNS_DIR", str(tmp_path))
    bb, cv, bf = covid
    rb = run_path("tag", bb, 0.75, carry_value=cv, btc_funding=bf, save=True, extra=dict(offset_days=0))
    rc = run_path("tag", bb, 0.75, carry_value=cv, btc_funding=bf, save=True, extra=dict(offset_days=0),
                  options=Options(True, True))
    assert "_opt" not in os.path.basename(rb["file"])
    assert os.path.basename(rc["file"]).endswith("_optC1_C2.json")   # _slug maps "+" to "_"
    assert os.path.exists(rb["file"]) and os.path.exists(rc["file"])
