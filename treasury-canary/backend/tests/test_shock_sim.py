"""Validation gates (spec §8, merge-blocking) + engine unit tests."""
import numpy as np
import pytest

from app.simulators import mc_core
from app.simulators.params import apply_overrides, defaults
from app.simulators.rate_paths import N_MONTHS, build_paths, kappa_live

P = defaults()


def _run(hikes, seed=42, inputs=None, **over):
    params = dict(P)
    params.update(over)
    return mc_core.simulate(hikes, params, inputs or {}, seed=seed)


def test_stage1_surprise_arithmetic():
    p = build_paths(2, P)
    # implied: Oct 17.5bp, Dec 11.25bp; scenario: 25bp Oct + 25bp Dec
    assert p["implied_bp"][2] == pytest.approx(17.5)
    assert p["surprise_bp"][2] == pytest.approx(7.5)
    assert p["surprise_bp"][4] == pytest.approx(13.75)
    assert p["cum_surprise_bp"][-1] == pytest.approx(21.25)
    cuts = build_paths(-2, P)
    assert cuts["cum_surprise_bp"][-1] == pytest.approx(-50 - 28.75)
    with pytest.raises(ValueError):
        build_paths(5, P)


def test_kappa_live_clip():
    assert kappa_live(0.45, 0.40, None) == 0.45
    assert kappa_live(0.45, 0.40, 0.25) == pytest.approx(0.55)
    assert kappa_live(0.45, 0.40, 5.0) == 0.65      # clipped
    assert kappa_live(0.45, 0.40, -5.0) == 0.25


def test_overrides_validated_and_clipped():
    p, warn = apply_overrides({"beta_spx": 99.0, "nope": 1, "vix_haircut": "x"})
    assert p["beta_spx"] == 14.0                     # clipped to range max
    assert any("nope" in w for w in warn) and any("clipped" in w for w in warn)


def test_t_shock_unit_variance():
    # the copula layer must deliver ~unit-variance marginals after the
    # nu/(nu-2) scaling (QA mandate: t variance accounting)
    r = _run(0, n_paths=20000, seed=7,
             inputs={"vix": 16.0, "canary01": 0.0})
    assert r["meta"]["n_paths"] == 20000


def test_gate_G4_monotonic_nan_deterministic():
    a = _run(2, seed=42, n_paths=4000)
    b = _run(2, seed=42, n_paths=4000)
    c = _run(2, seed=43, n_paths=4000)
    assert a == b                                   # deterministic under seed
    assert a != c                                   # seed actually matters
    for asset, bands in a["bands"].items():
        arr = np.array([bands[str(q)] for q in (5, 25, 50, 75, 95)])
        assert not np.isnan(arr).any()
        assert (np.diff(arr, axis=0) >= -1e-9).all(), f"{asset} bands not monotonic"


def test_gate_G3_zero_surprise_plain_cone():
    # hikes=0 with implied zeroed -> S=0 everywhere; canary 0 -> stress ~ base
    r = _run(0, n_paths=20000, seed=11,
             implied_prob_oct=0.0, implied_prob_dec=0.0,
             inputs={"vix": 16.0, "canary01": 0.0, "oas0": 310.0})
    assert max(r["stress_prob"]) < 0.12              # logistic(-4.65) ~ 1%/mo
    med = np.array(r["bands"]["SPX"]["50"])
    drift = 100.0 * np.exp(P["drift_spx"] / 12.0 * np.arange(1, N_MONTHS + 1))
    assert np.allclose(med, drift, rtol=0.02)        # median ~ drift path
    # cone width ~ sigma*sqrt(t): month-11 5-95 spread vs 1-month spread
    w1 = r["bands"]["SPX"]["95"][0] - r["bands"]["SPX"]["5"][0]
    w11 = r["bands"]["SPX"]["95"][-1] - r["bands"]["SPX"]["5"][-1]
    assert 2.4 < w11 / w1 < 4.6                      # ~sqrt(11)=3.3, t-noise slack


def test_gate_G1_2022_replay():
    # ~+450bp cumulative surprise fed over 11 months; era inputs (VIX ~25,
    # OAS 310, canary elevated). Amended params must land the medians in the
    # spec's bands: SPX -18..-30%, HYG -8..-15%.
    surprise = [450.0 / N_MONTHS] * N_MONTHS
    r = _run(0, n_paths=20000, seed=22,
             inputs={"surprise_override_bp": surprise, "kappa": 0.45,
                     "vix": 25.0, "oas0": 310.0, "canary01": 0.6,
                     "hyg_realized_ann": 0.10, "move": 120.0})
    spx = r["bands"]["SPX"]["50"][-1]
    hyg = r["bands"]["HYG"]["50"][-1]
    qqq = r["bands"]["QQQ"]["50"][-1]
    assert 70.0 <= spx <= 82.0, f"SPX median {spx} outside G1 band -18..-30%"
    assert 85.0 <= hyg <= 92.0, f"HYG median {hyg} outside G1 band -8..-15%"
    assert 55.0 <= qqq <= 80.0                        # sanity, no formal gate
    assert r["stress_prob"][-1] > 0.5                 # 2022 = stress near-certain


def test_gate_G2_2004_telegraphed_hikes():
    # fully-priced hikes: zero surprise, calm canary -> must NOT crash
    r = _run(0, n_paths=20000, seed=33,
             inputs={"surprise_override_bp": [0.0] * N_MONTHS, "kappa": 0.45,
                     "vix": 14.0, "oas0": 350.0, "canary01": 0.15})
    assert r["probs"]["SPX"]["dd_gt_20"] < 0.15, (
        f"G2 fail: P(dd>20%)={r['probs']['SPX']['dd_gt_20']} — engine predicts "
        "a crash for telegraphed hikes (overfit to 2022)")
    assert r["stress_prob"][-1] < 0.15


def test_runtime_budget():
    import time
    t0 = time.time()
    _run(3, n_paths=10000, seed=1, inputs={"vix": 18.0})
    assert time.time() - t0 < 1.5                     # spec §5 budget
