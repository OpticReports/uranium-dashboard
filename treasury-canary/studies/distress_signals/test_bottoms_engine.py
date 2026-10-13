"""Synthetic checks of bottoms_engine (no project data).

    python3 -m pytest -q test_bottoms_engine.py
"""
from __future__ import annotations

import numpy as np
import pytest

import bottoms_engine as B

R = B.Rule()


def test_growth_matches_hand_computation_and_respects_masks_and_span():
    vals = {t: 100.0 for t in range(0, 40)}
    for t in range(24, 40):
        vals[t] = 150.0
    g = B.growth(vals, R)
    assert min(g) == 17                       # first t with 2w inputs back to t-17
    assert g[23] == pytest.approx(0.0)
    assert g[29] == pytest.approx(0.5)        # 6 x 150 vs 6 x 100 a year earlier
    assert g[26] == pytest.approx((3 * 150 + 3 * 100) / 600 - 1)
    # a masked input period makes g uncomputable; a masked non-input (the gap
    # between the two sums) does not
    gm = B.growth(vals, R, bad={20})          # 20 is a current input for t=20..25, a base input for t=32..37
    assert 25 not in gm and 26 in gm and 31 in gm and 32 not in gm and 37 not in gm and 38 in gm
    gm2 = B.growth(vals, R, bad={30})         # for t=36, month 30 sits in the gap between the two sums
    assert 35 not in gm2 and 36 in gm2
    # span: the whole t-17..t range must sit inside the segment
    gs = B.growth(vals, R, span=(5, 39))
    assert min(gs) == 22


LEAD = [0.0] * 12          # a computable lead-in so the 12-period trailing high is defined


def test_rollover_fires_after_k_periods_below_the_drop_and_rearms_on_a_reacceleration():
    path = LEAD + [0.05, 0.15, 0.30, 0.28, 0.21, 0.19, 0.18, 0.10, 0.12, 0.25, 0.40, 0.20, 0.19]
    g = dict(enumerate(path))
    sig = B.signals(g, range(len(path)), R)
    # high 0.30 (t=14) -> drop needs g <= 0.20; 0.19 at t=17, 0.18 at t=18 -> fires at 18
    assert sig[0]["t"] == 18 and sig[0]["high"] == pytest.approx(0.30) and sig[0]["high_at"] == 14
    # re-arm needs a rise of d = 0.10 from the lowest g since the signal (0.10 at t=19):
    # 0.12 at t=20 is not enough, 0.25 at t=21 is
    assert sig[0]["rearmed_at"] == 21
    # H restarts at 21 (0.25, then 0.40 at t=22) -> drop needs g <= 0.2667: 0.20, 0.19 -> fires at t=24
    assert sig[1]["t"] == 24 and sig[1]["rearmed_at"] is None


def test_the_next_cycle_rearms_from_the_post_signal_low():
    # a roll-over while growth is still high (0.18), a slump to -0.20, then a milder
    # second rise to +0.20: re-arms on the way up (rise of d from the low), then fires again
    path = LEAD + [0.10, 0.30, 0.25, 0.18, 0.18] + [-0.20] * 6 + [-0.05, 0.10, 0.20, 0.13, 0.12]
    g = dict(enumerate(path))
    sig = B.signals(g, range(len(path)), R)
    # re-arms at t=23 (-0.05 >= -0.20 + 0.10); H restarts there, peaks at 0.20 (t=25);
    # 0.13 and 0.12 are both <= 0.20 - 0.0667 -> fires at t=27
    assert [x["t"] for x in sig] == [16, 27] and sig[0]["rearmed_at"] == 23


def test_a_stale_high_rolling_off_does_not_rearm():
    # g rises to 0.40, falls to 0.25 and stays flat: one signal, and no re-arm when
    # the 0.40 leaves the trailing window (re-arm needs a rise of d = 0.133 from 0.25)
    path = LEAD + [0.10, 0.20, 0.30, 0.40] + [0.25] * 30
    g = dict(enumerate(path))
    sig = B.signals(g, range(len(path)), R)
    assert len(sig) == 1 and sig[0]["t"] == 17 and sig[0]["rearmed_at"] is None
    assert sig[0]["high_at"] == 15 and sig[0]["d"] == pytest.approx(0.40 / 3)


def test_the_trailing_high_needs_a_full_window():
    g = {t: 0.30 for t in range(0, 20)}
    del g[15]
    g.update({16: 0.15, 17: 0.15, 18: 0.15, 19: 0.15})
    # the gap at 15 leaves H undefined for t = 15..26, so no signal can fire at 16..19
    assert B.signals(g, range(20), R) == []
    assert B.trailing_high(g, 14, 12) == (0.30, 3)


def test_floor_and_uncomputable_break():
    g = dict(enumerate(LEAD + [0.12, 0.08, 0.07, 0.07]))
    assert B.signals(g, range(16), R)[0]["t"] == 15       # floor: 0.12 - 0.05 = 0.07, two periods at <= 0.07
    # an uncomputable period breaks the run and leaves H undefined for 11 periods
    g2 = dict(enumerate(LEAD + [0.12, 0.07]))
    g2.update({15: 0.07, 16: 0.07})
    assert B.signals(g2, range(17), R) == []
    assert B.signals(dict(enumerate(LEAD + [0.09, 0.0, 0.0])), range(15), R) == []   # never armed


def test_classify_windows_and_first_released():
    assert [B.classify(e, -6, 3) for e in (-7, -6, 3, 4, None)] == ["EARLY", "HIT", "HIT", "LATE", "MISS"]
    sigs = [{"t": 10}, {"t": 20}]
    assert B.first_released(sigs, lambda t: t + 1, 12, 30)["release"] == 21
    assert B.first_released(sigs, lambda t: t + 1, 30, 40) is None


def test_loo_clock_and_null():
    arms, targets = [0, 10, 20, None], [5, 17, 27, 40]
    # others' lags: ep0 -> median(7,7)=7; ep1 -> median(5,7)=6; ep2 -> median(5,7)=6
    assert B.loo_clock(arms, targets) == [7, 16, 26, None]
    rng = np.random.default_rng(1)
    h = B.null_hits([[5], [0, 30], [], [40]], [5, 0, 9, 40], -1, 1, 4000, rng)
    assert set(np.unique(h)) <= {2, 3} and abs(h.mean() - 2.5) < 0.05
    assert B.p_upper(np.array([0, 1, 2, 3]), 3) == pytest.approx(2 / 5)


def test_trader_view_helpers():
    eq = {m: 100.0 for m in range(0, 40)}
    eq.update({10: 80.0, 11: 70.0, 12: 75.0, 23: 95.0})
    s = B.entry_stats(eq, 12, low=11)
    assert s["ret_12m"] == pytest.approx(100 / 75 - 1) and s["worst_dd_12m"] == pytest.approx(0.0)
    assert s["rebound_missed"] == pytest.approx((75 - 70) / (95 - 70))
    assert B.entry_stats(eq, 10, low=11)["worst_dd_12m"] == pytest.approx(70 / 80 - 1)
    assert B.drawdown_trigger(eq, 0, 39) == 10
