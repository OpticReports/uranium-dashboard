"""Probabilistic / Deflated Sharpe Ratio and Minimum Track Record Length.

Bailey & López de Prado, "The Sharpe Ratio Efficient Frontier" (J. Risk, 2012)
and "The Deflated Sharpe Ratio" (J. Portfolio Mgmt, 2014).

All Sharpe ratios here are PER-PERIOD (not annualized) — annualization cancels
in the PSR statistic only if applied consistently, so we avoid it entirely.
Skew/kurtosis corrections matter: crypto and trend strategies are far from
Gaussian, and ignoring them overstates confidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

_EULER = 0.5772156649015329


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _phi_inv(p: float) -> float:
    # Acklam-style rational approximation is overkill; use bisection on erf
    # (monotone, cheap, no scipy dependency).
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _phi(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@dataclass
class SharpeStats:
    n: int
    sr: float          # per-period Sharpe (mean/std, ddof=1)
    skew: float
    kurt: float        # RAW kurtosis (Gaussian = 3), not excess


def sharpe_stats(returns: np.ndarray) -> SharpeStats:
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    n = len(r)
    if n < 3:
        raise ValueError(f"need >=3 returns, got {n}")
    mu, sd = r.mean(), r.std(ddof=1)
    if sd == 0:
        raise ValueError("zero-variance returns")
    z = (r - mu) / sd
    return SharpeStats(n=n, sr=mu / sd,
                       skew=float((z ** 3).mean()),
                       kurt=float((z ** 4).mean()))


def sr_std_error(s: SharpeStats) -> float:
    """Std error of the SR estimator under non-normal iid returns
    (Bailey & LdP 2012, eq. for sigma_SR; Mertens 2002)."""
    var = (1.0 - s.skew * s.sr + (s.kurt - 1.0) / 4.0 * s.sr ** 2) / (s.n - 1)
    if var <= 0:
        # pathological skew/kurt combination; fall back to Gaussian iid
        var = (1.0 + 0.5 * s.sr ** 2) / (s.n - 1)
    return math.sqrt(var)


def psr(returns: np.ndarray, sr_benchmark: float = 0.0) -> float:
    """P(true SR > sr_benchmark | observed track record). PSR > 0.95 is the
    conventional bar. sr_benchmark is per-period."""
    s = sharpe_stats(returns)
    return _phi((s.sr - sr_benchmark) / sr_std_error(s))


def min_trl(sr_hat: float, sr_benchmark: float, skew: float, kurt: float,
            confidence: float = 0.95) -> float:
    """Minimum track record length (in periods) so that PSR >= confidence,
    holding the observed SR/skew/kurt fixed (Bailey & LdP 2012).
    Returns +inf when sr_hat <= sr_benchmark (no track record can help)."""
    if sr_hat <= sr_benchmark:
        return float("inf")
    z = _phi_inv(confidence)
    num = 1.0 - skew * sr_hat + (kurt - 1.0) / 4.0 * sr_hat ** 2
    if num <= 0:
        num = 1.0 + 0.5 * sr_hat ** 2
    return 1.0 + num * (z / (sr_hat - sr_benchmark)) ** 2


def expected_max_sr(n_trials: int, sr_std_across_trials: float) -> float:
    """E[max SR] across n independent trials with zero true SR (LdP 2014):
    the deflation benchmark. sr_std_across_trials = std of the SR estimates
    across the trials actually run (from the trials registry)."""
    if n_trials <= 1:
        return 0.0
    e = math.e
    return sr_std_across_trials * (
        (1.0 - _EULER) * _phi_inv(1.0 - 1.0 / n_trials)
        + _EULER * _phi_inv(1.0 - 1.0 / (n_trials * e)))


def dsr(returns: np.ndarray, n_trials: int, sr_std_across_trials: float) -> float:
    """Deflated Sharpe Ratio: PSR against the expected-max-SR benchmark.
    Requires an HONEST trial count — undercounting trials is the #1 way this
    statistic gets gamed (our barbell trials registry is the source of truth)."""
    return psr(returns, expected_max_sr(n_trials, sr_std_across_trials))
