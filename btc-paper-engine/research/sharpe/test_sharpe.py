"""Gate tests for the Sharpe study. Run: python3 -m pytest -q test_sharpe.py
(also run ../cagr/test_harness.py: the signal_fn hook must leave the
production path untouched)."""
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sharpe_lib as S                                             # noqa: E402
H = S.H
B = H.BAR_S
DAY = S.DAY


@pytest.fixture(scope="module")
def W():
    return S.World()


# ---- hook / production path ------------------------------------------------
def test_identity_signal_fn_reproduces_production_trades(W):
    t0 = S.ts_of("2019-01-01")
    a = H.leg_trades(W.bars, "pullback", start_ts=t0, inds=W.inds)
    b = H.leg_trades(W.bars, "pullback", start_ts=t0, inds=W.inds,
                     signal_fn=lambda i, bar, ind, sig: sig)
    assert len(a) > 50 and a == b


def test_gate_never_lets_a_signal_through_on_the_wrong_side(W):
    t0 = S.ts_of("2013-01-01")
    tr = H.leg_trades(W.bars, "pullback", start_ts=t0, inds=W.inds,
                      signal_fn=W.gate_fn)
    base = H.leg_trades(W.bars, "pullback", start_ts=t0, inds=W.inds)
    assert 0 < len(tr) < len(base)
    for t in tr:
        i = W.idx[t.entry_ts - B]                    # signal bar: fill is next bar
        sma = W.sma_gate[i]
        if t.side == "L":
            assert W.close[i] > sma
        else:
            assert W.close[i] < sma


def test_gate_uses_200_days_including_the_signal_close(W):
    i = 5000
    assert W.sma_gate[i] == pytest.approx(W.close[i - 1199:i + 1].mean())


# ---- H1 vol multiplier -----------------------------------------------------
def test_vol_mult_is_causal_and_bounded(W):
    T = int(W.ts[20000])
    m = W.vol_mult(T)
    j = 20000 - 1
    lr = np.diff(np.log(W.close[j - 180:j + 1]))
    now = lr.std()
    assert W.sigma_now[j] == pytest.approx(now)
    assert S.M_LO <= m <= S.M_HI
    # perturbing bar T's own close must not move m(T)
    saved = W.close[20000]
    W2 = S.World.__new__(S.World)
    W2.__dict__.update(W.__dict__)
    c = W.close.copy()
    c[20000] *= 3
    import pandas as pd
    lr2 = np.full(len(c), np.nan)
    lr2[1:] = np.diff(np.log(c))
    s_now = pd.Series(lr2).rolling(S.VOL_WIN).std(ddof=0)
    W2.sigma_now = s_now.to_numpy()
    W2.sigma_ref = s_now.rolling(S.VOL_REF).median().to_numpy()
    assert W2.vol_mult(T) == m
    assert W.close[20000] == saved


def test_vol_mult_direction_on_synthetic(W):
    W2 = S.World.__new__(S.World)
    W2.idx = {i * B: i for i in range(10)}
    W2.sigma_ref = np.full(10, 0.02)
    W2.sigma_now = np.array([0.01, 0.02, 0.04, 0.1, 0.0001] + [np.nan] * 5)
    assert W2.vol_mult(1 * B) == pytest.approx(1.33)      # calm -> capped up
    assert W2.vol_mult(2 * B) == pytest.approx(1.0)
    assert W2.vol_mult(3 * B) == pytest.approx(0.5)       # 2x vol -> half
    assert W2.vol_mult(4 * B) == pytest.approx(0.5)       # floor
    assert W2.vol_mult(6 * B) == 1.0                      # no history


# ---- H3 carry ---------------------------------------------------------------
def _flat(days, px=100.0, rate=1e-4):
    grid = np.arange(0, days * DAY, B, dtype=np.int64)
    closes = {int(t): px for t in grid}
    fts = np.arange(8 * 3600, days * DAY + 1, 8 * 3600, dtype=np.int64)
    return grid, closes, fts, np.full(len(fts), rate)


def test_static_carry_hand_arithmetic():
    grid, closes, fts, fr = _flat(10)
    pnl, m = S.carry(grid, closes, fts, fr, gated=False, notional=30_000,
                     spot_bps=7.0, perp_bps=4.32)
    entry_fee = 30_000 * 11.32e-4
    # enters at bar 1's open (last known close = bar 0's); stamps from 08:00
    n_stamps = int(((fts > grid[1]) & (fts <= grid[-1] + B)).sum())
    assert m["fees"] == pytest.approx(entry_fee)
    assert pnl[-1] == pytest.approx(-entry_fee + n_stamps * 1e-4 * 30_000)
    assert m["funding"] > 0                    # +rate credits the short


def test_negative_funding_costs_the_short():
    grid, closes, fts, fr = _flat(5, rate=-2e-4)
    pnl, m = S.carry(grid, closes, fts, fr, gated=False)
    assert m["funding"] < 0


def test_resize_only_at_month_start_and_beyond_drift():
    # 70 days from 1970-01-01 (a month start): price doubles on day 3
    grid = np.arange(0, 70 * DAY, B, dtype=np.int64)
    closes = {int(t): (100.0 if t < 3 * DAY else 200.0) for t in grid}
    fts = np.array([], dtype=np.int64)
    pnl, m = S.carry(grid, closes, fts, np.array([]), gated=False,
                     notional=30_000, spot_bps=10, perp_bps=0)
    # entry 30k; Feb 1 (day 31): notional 60k -> resize to 30k (dq*px=30k);
    # Mar 1 (day 59): 30k, no drift
    assert m["fees"] == pytest.approx(30_000e-3 + 30_000e-3)
    assert m["switches"] == 1
    step = np.diff(np.concatenate([[0.0], pnl]))
    hits = grid[np.where(step < 0)[0]] // DAY
    assert list(hits) == [0, 31]                  # entry, then Feb 1 only


def test_no_resize_inside_the_drift_band():
    grid = np.arange(0, 40 * DAY, B, dtype=np.int64)
    closes = {int(t): (100.0 if t < 3 * DAY else 120.0) for t in grid}
    pnl, m = S.carry(grid, closes, np.array([], dtype=np.int64), np.array([]),
                     gated=False, notional=30_000, spot_bps=10, perp_bps=0)
    assert m["fees"] == pytest.approx(30_000e-3)  # +20% drift: entry fee only


def test_hl_funding_file_is_read_in_seconds():
    ts, r = S.load_funding("funding_hyperliquid_btc.csv")
    assert S.ts_of("2023-05-01") < ts[0] < S.ts_of("2023-06-01")
    assert np.all(np.diff(ts) > 0)


def test_gate_hysteresis_and_no_lookahead():
    days = 120
    grid = np.arange(0, days * DAY, B, dtype=np.int64)
    closes = {int(t): 100.0 for t in grid}
    fts = np.arange(8 * 3600, days * DAY + 1, 8 * 3600, dtype=np.int64)
    ann = np.where(fts < 50 * DAY, 0.12, np.where(fts < 90 * DAY, 0.06, 0.02))
    fr = ann / (3 * 365)
    pnl, m = S.carry(grid, closes, fts, fr, gated=True)
    # on from day 30 (first full window, 12%), stays on through the 6% band
    # (hysteresis), turns off once the 30d mean drops under 5%
    assert m["switches"] == 2
    step = np.diff(np.concatenate([[0.0], pnl]))
    earning = np.where(step > 0)[0]
    assert grid[earning[0]] >= 30 * DAY            # nothing before day 30
    # 30d mean = 6%*(90-d)/30 + 2%*(d-90)/30 ... crosses 5% at day 97.5,
    # so the gate turns off at the day-98 decision; a single 8% threshold
    # (no hysteresis) would turn off near day 70 (audit mutation M3)
    off = grid[earning[-1]] // DAY
    assert off == 97


def test_gate_does_not_arm_below_8_percent():
    days = 90
    grid = np.arange(0, days * DAY, B, dtype=np.int64)
    closes = {int(t): 100.0 for t in grid}
    fts = np.arange(8 * 3600, days * DAY + 1, 8 * 3600, dtype=np.int64)
    pnl, m = S.carry(grid, closes, fts, np.full(len(fts), 0.079 / (3 * 365)),
                     gated=True)
    assert m["switches"] == 0 and m["fees"] == 0.0
    pnl, m = S.carry(grid, closes, fts, np.full(len(fts), 0.081 / (3 * 365)),
                     gated=True)
    assert m["switches"] == 1


def test_funding_priced_at_the_stamp_bars_close():
    grid = np.arange(0, 2 * DAY, B, dtype=np.int64)
    closes = {int(t): 100.0 + i for i, t in enumerate(grid)}
    fts = np.array([16 * 3600], dtype=np.int64)          # closes bar 3 (12:00 open)
    pnl, m = S.carry(grid, closes, fts, np.array([1e-3]), gated=False,
                     notional=30_000, spot_bps=0, perp_bps=0)
    q = 30_000 / 100.0                                    # entered at bar 0's close
    assert m["funding"] == pytest.approx(1e-3 * q * 103.0)


# ---- metric ------------------------------------------------------------------
def test_gate_decision_ignores_a_stamp_at_the_decision_time():
    days = 60
    grid = np.arange(0, days * DAY, B, dtype=np.int64)
    closes = {int(t): 100.0 for t in grid}
    fts = np.arange(8 * 3600, days * DAY + 1, 8 * 3600, dtype=np.int64)
    # a rate spike on stamp s must not switch the gate before day(s)+1
    fr2 = np.full(len(fts), 0.0)
    fr2[fts == 40 * DAY] = 0.5                     # one huge stamp at 00:00 day 40
    pnl2, m2 = S.carry(grid, closes, fts, fr2, gated=True)
    first_cost = np.argmax(np.diff(np.concatenate([[0.0], pnl2])) < 0)
    assert grid[first_cost] >= 41 * DAY           # stamp at 00:00 is s < ts only next day


def test_daily_pnl_and_sharpe():
    ts = np.arange(0, 3 * DAY, B)
    cum = np.arange(1, len(ts) + 1, dtype=float)   # +1 per bar
    d, p = S.daily_pnl(ts, cum)
    assert list(p) == [6.0, 6.0, 6.0]
    assert math.isnan(S.sharpe(p))
    assert S.sharpe([1.0, -1.0, 1.0, -1.0]) == 0.0


def test_bootstrap_of_identical_series_is_zero():
    rng = np.random.default_rng(1)
    a = rng.normal(10, 100, 900)
    lo, hi = S.boot_delta(a, a, n=200)
    assert lo == hi == 0.0


def test_max_dd_usd():
    assert S.max_dd_usd([100, 50, 200, 120]) == -80.0
    assert S.max_dd_usd([-30, 10]) == -30.0
