"""Probabilistic & Deflated Sharpe Ratio.

Implemented directly from the papers (per spec, since library versions vary):

PSR — Bailey, D.H. & López de Prado, M. (2012), "The Sharpe Ratio Efficient
Frontier", Journal of Risk 15(2). For an estimated (per-period, non-annualized)
Sharpe ratio SR̂ over T observations, with return skewness γ3 and (raw,
non-excess) kurtosis γ4, the probability that the true SR exceeds a benchmark
SR* is

    PSR(SR*) = Φ( (SR̂ − SR*) · sqrt(T − 1)
                  / sqrt(1 − γ3·SR̂ + (γ4 − 1)/4 · SR̂²) )

DSR — Bailey, D.H. & López de Prado, M. (2014), "The Deflated Sharpe Ratio:
Correcting for Selection Bias, Backtest Overfitting, and Non-Normality",
Journal of Portfolio Management 40(5). The expected maximum SR under the null
of N independent zero-skill trials with cross-trial variance V[SR̂] is

    SR0 = sqrt(V[SR̂]) · ( (1 − γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)) )

with γ the Euler–Mascheroni constant (≈0.5772). Then DSR = PSR(SR0): the
probability the observed best-of-N SR beats what pure selection bias would
produce. DSR is the deflation of the SELECTED (best) strategy's SR̂.

Everything here is per-period: annualized inputs must be de-annualized by the
caller (sharpe_daily = sharpe_annual / sqrt(252)); mixing conventions is the
classic way to get a confidently wrong number.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import stats as sps

EULER_GAMMA = 0.5772156649015329


def sharpe_ratio(returns: np.ndarray, rf_per_period: float = 0.0) -> float:
    """Per-period Sharpe ratio (NOT annualized)."""
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        raise ValueError("need >=2 observations for a Sharpe ratio")
    ex = r - rf_per_period
    sd = ex.std(ddof=1)
    if sd == 0:
        raise ValueError("zero return volatility — Sharpe undefined")
    return float(ex.mean() / sd)


def psr(sr_hat: float, n_obs: int, skew: float = 0.0, kurt: float = 3.0,
        sr_benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio (Bailey & López de Prado 2012).

    kurt is RAW kurtosis (normal = 3), matching the paper's γ4.
    """
    if n_obs < 2:
        raise ValueError("PSR needs n_obs >= 2")
    denom_sq = 1.0 - skew * sr_hat + (kurt - 1.0) / 4.0 * sr_hat**2
    if denom_sq <= 0:
        raise ValueError(
            f"PSR variance term non-positive (skew={skew}, kurt={kurt}, sr={sr_hat}) — "
            "inputs are inconsistent with a valid return distribution"
        )
    z = (sr_hat - sr_benchmark) * math.sqrt(n_obs - 1) / math.sqrt(denom_sq)
    return float(sps.norm.cdf(z))


def expected_max_sharpe(n_trials: int, var_sr: float, mean_sr: float = 0.0) -> float:
    """E[max SR̂] across n_trials independent trials under the null (the
    'False Strategy' theorem, Bailey & López de Prado 2014). Per-period units.
    """
    if n_trials < 1:
        raise ValueError("n_trials must be >= 1")
    if var_sr < 0:
        raise ValueError("var_sr must be >= 0")
    if n_trials == 1:
        return mean_sr  # no selection bias with a single trial
    sd = math.sqrt(var_sr)
    z1 = sps.norm.ppf(1.0 - 1.0 / n_trials)
    z2 = sps.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(mean_sr + sd * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2))


def deflated_sharpe(sr_hat: float, n_obs: int, n_trials: int, var_sr_trials: float,
                    skew: float = 0.0, kurt: float = 3.0) -> dict:
    """DSR of the best-of-N selected strategy.

    Returns a dict with sr0 (the selection-bias hurdle), dsr (probability the
    selected SR̂ is genuine skill rather than selection bias), and the p-value
    (1 - dsr) used by Holm-Bonferroni across the trial registry.
    """
    sr0 = expected_max_sharpe(n_trials, var_sr_trials)
    d = psr(sr_hat, n_obs, skew=skew, kurt=kurt, sr_benchmark=sr0)
    return {"sr0": sr0, "dsr": d, "p_value": 1.0 - d,
            "n_trials": n_trials, "n_obs": n_obs}


def moments(returns: np.ndarray) -> dict:
    """skew + RAW kurtosis in the papers' convention."""
    r = np.asarray(returns, dtype=float)
    return {
        "skew": float(sps.skew(r, bias=False)),
        "kurt": float(sps.kurtosis(r, bias=False, fisher=False)),  # raw, normal=3
    }
