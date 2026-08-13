"""Gates: every detector must (a) fire on synthetic data with KNOWN injected
decay, (b) stay quiet at its calibrated false-alarm rate on the null, and
(c) say 'insufficient' honestly when the sample can't support a verdict."""
from __future__ import annotations

import math

import numpy as np
import pytest

from edge_monitor import bocd, cusum, dd_percentile, psr

RNG = np.random.default_rng(42)


def _daily(n, sr_annual, vol_annual=0.15, rng=RNG):
    mu = sr_annual * vol_annual / 252.0
    sd = vol_annual / math.sqrt(252.0)
    return rng.normal(mu, sd, n)


# ------------------------------------------------------------------- PSR --
def test_gate_psr_null_calibration():
    """Under H0 (true SR = 0) the PSR is asymptotically U(0,1): its mean is
    ~0.5 and P(PSR > 0.95) ~ 5%. A single-draw bound would be a coin flip —
    calibration is the correct gate."""
    rng = np.random.default_rng(1)
    ps = [psr.psr(_daily(2000, 0.0, rng=rng), 0.0) for _ in range(400)]
    assert 0.45 < float(np.mean(ps)) < 0.55
    fa = float(np.mean(np.array(ps) > 0.95))
    assert 0.02 < fa < 0.09          # ~5% nominal
    # power sanity: a genuinely strong track is recognized
    assert psr.psr(_daily(2000, 2.0, rng=rng), 0.0) > 0.99


def test_gate_psr_skew_penalty():
    """Negative skew must REDUCE confidence at the same SR (Mertens/BLdP
    correction direction)."""
    n = 1500
    g = RNG.normal(0, 1, n)
    neg = np.where(RNG.random(n) < 0.03, -4.0, 0.12)      # crash-like skew
    for r in (g, neg):
        pass
    # rescale both to identical SR
    def with_sr(x, sr):
        x = (x - x.mean()) / x.std(ddof=1)
        return x + sr
    sr = 0.05
    p_gauss = psr.psr(with_sr(g, sr))
    p_skew = psr.psr(with_sr(neg, sr))
    s = psr.sharpe_stats(with_sr(neg, sr))
    assert s.skew < -1.0
    assert p_skew < p_gauss


def test_gate_mintrl_roundtrip():
    """A track of exactly MinTRL length with the assumed moments gives
    PSR ~= confidence (self-consistency of the closed form)."""
    sr, skew, kurt = 0.08, -0.5, 5.0
    n = psr.min_trl(sr, 0.0, skew, kurt, 0.95)
    z = psr._phi_inv(0.95)
    num = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2
    assert n == pytest.approx(1.0 + num * (z / sr) ** 2, rel=1e-6)
    assert psr.min_trl(0.0, 0.0, 0.0, 3.0) == float("inf")


def test_gate_dsr_deflation_direction():
    """More trials -> higher benchmark -> lower DSR. 1 trial -> DSR == PSR."""
    r = _daily(1000, 1.0)
    assert psr.dsr(r, 1, 0.02) == pytest.approx(psr.psr(r, 0.0))
    assert psr.dsr(r, 28, 0.02) < psr.dsr(r, 5, 0.02) < psr.dsr(r, 1, 0.02)
    assert psr.expected_max_sr(28, 0.02) > 0


# ----------------------------------------------------------------- CUSUM --
def test_gate_cusum_calibration_and_detection():
    """Calibrated h achieves ~target ARL under the null, and detects an
    injected dead edge well before the false-alarm horizon.

    k is HALF THE SHIFT TO CATCH, in daily sigma: an SR-1.2 edge dying is a
    ~0.076 sigma/day mean drop, so k~0.04 — NOT the textbook 0.25/0.5, which
    would be nearly blind to SR-sized decay. The honest headline this gate
    pins: at 1 false alarm / ~2y, a fully dead edge takes months (~half a
    year median) to flag from daily returns. Nothing statistical beats that
    at this signal-to-noise; faster answers come from per-trade slippage
    charts, where shifts are many sigma."""
    bt = _daily(1500, 1.2)
    shift = 1.2 / math.sqrt(252.0)            # dead edge, in daily sigma
    cal = cusum.calibrate_h(bt, target_arl=500.0, k=shift / 2, n_sims=800, seed=3)
    assert not cal["censoring_binds"]
    assert 0.7 * 500 < cal["achieved_arl"] < 1.4 * 500

    mu, sd = bt.mean(), bt.std(ddof=1)
    rng = np.random.default_rng(9)
    detect = []
    for _ in range(200):
        dead = rng.normal(0.0, sd, 2000)      # mean gone, vol unchanged
        z = (dead - mu) / sd
        detect.append(cusum.run_length(z, cal["k"], cal["h"]))
    med = float(np.median(detect))
    assert med < 250            # ~months, not the 2y false-alarm horizon
    assert med < 0.55 * cal["achieved_arl"]


def test_gate_cusum_state_machine():
    st = cusum.CusumState(k=0.25, h=5.0)
    for _ in range(200):
        st.update(0.0)          # on-target: no alarm from k-drift
    assert not st.alarmed and st.s_neg == 0.0
    fired = False
    for _ in range(100):
        fired = st.update(-0.8) or fired
    assert fired
    st.reset()
    assert st.s_neg == 0.0 and not st.alarmed


# ------------------------------------------------------------ DD percentile --
def test_gate_dd_percentile_calibration_and_power():
    """Null calibration over many draws (single-draw percentiles are uniform
    by construction — that's the point of the statistic), then power on an
    injected dead edge."""
    bt = _daily(2000, 1.2)
    rng = np.random.default_rng(5)
    null_alarms = 0
    for i in range(120):
        live = rng.normal(bt.mean(), bt.std(ddof=1), 120)
        p = dd_percentile.dd_percentiles(live, bt, n_sims=1000, seed=1)
        null_alarms += p["max_dd_pctile"] > 95.0
    assert null_alarms / 120 < 0.12          # ~5% nominal, allow noise
    # decay: strong negative drift -> both percentiles extreme, most draws
    hits = 0
    for i in range(40):
        live_bad = rng.normal(-3 * abs(bt.mean()), bt.std(ddof=1), 120)
        p1 = dd_percentile.dd_percentiles(live_bad, bt, n_sims=1000, seed=1)
        hits += (p1["max_dd_pctile"] > 95.0) and (p1["underwater_pctile"] > 90.0)
    assert hits / 40 > 0.6


def test_gate_dd_insufficient_is_first_class():
    out = dd_percentile.dd_percentiles(np.array([0.01, -0.02]), _daily(500, 1.0))
    assert out["insufficient"] is True and out["min_needed"] == 5


def test_gate_dd_length_matching():
    """Longer live windows must be compared against longer simulated windows:
    the p95 max-DD bound must deepen with track length."""
    bt = _daily(2000, 1.2)
    p_short = dd_percentile.dd_percentiles(_daily(30, 1.2), bt, seed=2)
    p_long = dd_percentile.dd_percentiles(_daily(500, 1.2), bt, seed=2)
    assert p_long["backtest_p95_max_dd_at_this_length"] < \
        p_short["backtest_p95_max_dd_at_this_length"]


# ------------------------------------------------------------------ BOCD --
def test_gate_bocd_detects_clear_changepoint():
    """A clear break (0.7-sigma mean shift in standardized units) must spike
    the changepoint posterior and restart the MAP run length."""
    rng = np.random.default_rng(21)
    a = rng.normal(0.08, 1.0, 400)          # healthy standardized edge
    b = rng.normal(-0.60, 1.0, 80)          # clear break
    det = bocd.Bocd(hazard=1 / 250)
    for x in a:
        out = det.update(float(x))
    p_at_cp = out["p_change_recent"]
    map_before = out["map_run_length"]
    peaks = []
    for x in b:
        out = det.update(float(x))
        peaks.append(out["p_change_recent"])
    assert map_before > 300                  # long stable run recognized
    assert max(peaks) > 5 * max(p_at_cp, 0.02)   # posterior spikes after break
    assert out["map_run_length"] < 100           # MAP run restarted post-break


def test_gate_bocd_blind_to_sr_sized_mean_shifts():
    """HONESTY GATE, not a bug: an SR-sized daily mean shift (~0.18 sigma)
    is near-invisible to BOCD at n=60 — the MAP run does NOT restart. This
    is why BOCD is a corroborator in the blueprint, never the first-line
    mean-decay detector (CUSUM owns that). If this gate ever 'improves',
    re-audit before believing it."""
    rng = np.random.default_rng(21)
    det = bocd.Bocd(hazard=1 / 250)
    for x in rng.normal(0.08, 1.0, 400):
        det.update(float(x))
    for x in rng.normal(-0.10, 1.0, 60):     # edge dead, SR-sized shift
        out = det.update(float(x))
    assert out["map_run_length"] > 100       # old run still MAP: no detection


def test_gate_bocd_quiet_on_null():
    rng = np.random.default_rng(33)
    det = bocd.Bocd(hazard=1 / 250)
    spikes = 0
    for x in rng.normal(0.05, 1.0, 600):
        if det.update(float(x))["p_change_recent"] > 0.5:
            spikes += 1
    assert spikes < 12                        # <2% of days scream on the null


def test_gate_standardize_no_lookahead():
    """Vol standardization at t must not use r[t]: perturbing r[t] must not
    change z[t]'s denominator (only later ones)."""
    r = RNG.normal(0, 0.01, 100)
    z1 = bocd.standardize(r)
    r2 = r.copy()
    r2[50] *= 100.0
    z2 = bocd.standardize(r2)
    assert z2[50] == pytest.approx(z1[50] * 100.0)   # same denominator at t
    assert not np.allclose(z1[51:], z2[51:])          # affects only t+1..
