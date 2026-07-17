"""Stats module tests.

The DSR/PBO papers' exhibit tables aren't reproduced verbatim here (we don't
ship the PDFs); instead each formula is verified the stronger way:
  * exact analytic invariants (PSR at the benchmark = 0.5, N=1 → no deflation),
  * an independent Monte Carlo check that E[max SR] across N pure-noise trials
    matches the False Strategy theorem's SR0 formula,
  * CSCV PBO ≈ 0.5 on exchangeable noise and → 0 on genuine signal,
  * Holm-Bonferroni against a hand-computed textbook example.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy import stats as sps

from barbell.stats.corrections import holm_bonferroni
from barbell.stats.dsr import (
    deflated_sharpe,
    expected_max_sharpe,
    moments,
    psr,
    sharpe_ratio,
)
from barbell.stats.pbo import cscv_pbo


class TestPSR:
    def test_at_benchmark_is_half(self):
        assert psr(0.1, 1000, sr_benchmark=0.1) == pytest.approx(0.5)

    def test_normal_case_matches_hand_formula(self):
        # skew 0, kurt 3: z = SR*sqrt(T-1)/sqrt(1 + SR^2/2)
        sr, t = 0.05, 253
        z = sr * np.sqrt(t - 1) / np.sqrt(1 + sr**2 / 2)
        assert psr(sr, t) == pytest.approx(float(sps.norm.cdf(z)), abs=1e-12)

    def test_negative_skew_hurts_fat_tails_hurt(self):
        base = psr(0.08, 500)
        assert psr(0.08, 500, skew=-1.0) < base
        assert psr(0.08, 500, kurt=8.0) < base

    def test_more_data_more_confidence(self):
        assert psr(0.05, 2000) > psr(0.05, 200)


class TestFalseStrategyTheorem:
    def test_single_trial_no_deflation(self):
        assert expected_max_sharpe(1, 0.5) == 0.0

    def test_monotone_in_trials_and_variance(self):
        a = expected_max_sharpe(10, 1.0)
        b = expected_max_sharpe(100, 1.0)
        c = expected_max_sharpe(100, 4.0)
        assert 0 < a < b < c

    def test_matches_monte_carlo_max_of_noise(self):
        # 2000 experiments: max of N=50 iid N(0, var_sr) draws; the formula is
        # an asymptotic expected-max approximation — tolerance 5%.
        rng = np.random.default_rng(11)
        n, var_sr = 50, 0.04
        maxes = rng.normal(0, np.sqrt(var_sr), size=(2000, n)).max(axis=1)
        pred = expected_max_sharpe(n, var_sr)
        assert pred == pytest.approx(float(maxes.mean()), rel=0.05)

    def test_dsr_deflates_lucky_noise_below_psr(self):
        # A "best" SR of 0.07/day picked from 200 trials with cross-trial var
        # typical of noise should NOT look significant.
        res = deflated_sharpe(0.07, 400, n_trials=200, var_sr_trials=0.002)
        naive = psr(0.07, 400)
        assert res["dsr"] < naive
        assert res["dsr"] < 0.95  # not significant at 5%


class TestPBO:
    def test_pure_noise_pbo_near_half(self):
        # PBO ≈ 0.5 holds in EXPECTATION over datasets; a single dataset's
        # CSCV splits are correlated, so average over independent noise draws.
        pbos = []
        for seed in range(10):
            rng = np.random.default_rng(seed)
            m = rng.normal(0, 0.01, size=(1200, 20))
            pbos.append(cscv_pbo(m, n_blocks=10)["pbo"])
        assert 0.40 < float(np.mean(pbos)) < 0.60

    def test_true_signal_pbo_near_zero(self):
        rng = np.random.default_rng(4)
        m = rng.normal(0, 0.01, size=(1200, 20))
        m[:, 7] += 0.004  # one genuinely superior strategy (SR≈0.4/period)
        res = cscv_pbo(m, n_blocks=10)
        assert res["pbo"] < 0.05

    def test_overfit_degradation_visible(self):
        rng = np.random.default_rng(5)
        m = rng.normal(0, 0.01, size=(1200, 20))
        res = cscv_pbo(m, n_blocks=10)
        # selected IS Sharpe should collapse OOS on noise
        assert res["winner_is_sharpe_mean"] > res["winner_oos_sharpe_mean"]

    def test_rejects_bad_input(self):
        with pytest.raises(ValueError):
            cscv_pbo(np.zeros((100, 1)))
        with pytest.raises(ValueError):
            cscv_pbo(np.zeros((100, 5)), n_blocks=7)


class TestHolm:
    def test_textbook_example(self):
        # Holm (1979) mechanics, hand-computed:
        # sorted p: .005, .01, .03, .04 with m=4 →
        # adj: .02, .03, .06, .06 (running max of (m-i)*p, clipped)
        p = [0.01, 0.04, 0.03, 0.005]
        adj = holm_bonferroni(p)
        assert adj[3] == pytest.approx(0.02)   # .005*4
        assert adj[0] == pytest.approx(0.03)   # .01*3
        assert adj[2] == pytest.approx(0.06)   # .03*2
        assert adj[1] == pytest.approx(0.06)   # max(.04*1, previous)=.06
        # ordering preserved: adjusted never below raw
        assert (adj >= np.array(p)).all()

    def test_single_p_unchanged(self):
        assert holm_bonferroni([0.03])[0] == pytest.approx(0.03)

    def test_invalid_p_rejected(self):
        with pytest.raises(ValueError):
            holm_bonferroni([0.5, 1.2])


class TestMomentsAndSharpe:
    def test_sharpe_known_value(self):
        r = np.array([0.01, -0.01, 0.02, 0.0, 0.01])
        assert sharpe_ratio(r) == pytest.approx(r.mean() / r.std(ddof=1))

    def test_moments_normal_sample(self):
        rng = np.random.default_rng(0)
        m = moments(rng.normal(size=100_000))
        assert m["skew"] == pytest.approx(0.0, abs=0.05)
        assert m["kurt"] == pytest.approx(3.0, abs=0.1)
