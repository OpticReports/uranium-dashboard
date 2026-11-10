"""Baselines, and the shared machinery that turns a point forecast into a
calibrated set of quantiles.

EVERY MODEL IS DRESSED THE SAME WAY. A point forecaster emits one number;
the gate is about intervals. So each one's ratio distribution y/sigma_hat is
measured ON TRAIN ONLY and reused as the spread. Two consequences worth
stating plainly:

  1. In-sample coverage is 80% BY CONSTRUCTION. It proves nothing. The
     metric only means something on VALIDATE, where the question is whether
     that ratio distribution was stable.
  2. Any constant scale error in a point forecast is absorbed by the
     dressing, so ATR (a range measure) and EWMA (a return-std measure) are
     compared on shape and stability, not on units.

A foundation model that emits its own nine quantiles bypasses this and is
scored on the quantiles it actually produced - which is the fairer test of
the thing being evaluated, and is noted wherever it applies.
"""
from __future__ import annotations

import numpy as np

from .metrics import LEVELS


class QuantileDressing:
    """Empirical distribution of realized/predicted, fitted on TRAIN."""

    def __init__(self) -> None:
        self.ratios: np.ndarray | None = None

    def fit(self, y: np.ndarray, sigma_hat: np.ndarray) -> "QuantileDressing":
        ok = np.isfinite(y) & np.isfinite(sigma_hat) & (sigma_hat > 0)
        if ok.sum() < 30:
            raise ValueError(f"only {ok.sum()} usable TRAIN points to fit the "
                             f"spread; refusing to calibrate on that")
        self.ratios = np.quantile(y[ok] / sigma_hat[ok], LEVELS)
        return self

    def apply(self, sigma_hat: np.ndarray) -> np.ndarray:
        if self.ratios is None:
            raise RuntimeError("dressing used before it was fitted on TRAIN")
        return sigma_hat[:, None] * self.ratios[None, :]


def ewma_sigma(x: np.ndarray, lam: float = 0.94) -> np.ndarray:
    """RiskMetrics EWMA of squared per-bar volatility estimates.

    `x` is either close-to-close returns or a per-bar range estimate; the
    recursion is identical and the difference is entirely in what it is
    fed. sigma[t] uses data up to and INCLUDING t, and is the forecast for
    t+1 onwards."""
    out = np.full(x.shape, np.nan)
    var = np.nan
    for t in range(x.size):
        if not np.isfinite(x[t]):
            continue
        var = x[t] ** 2 if not np.isfinite(var) else lam * var + (1 - lam) * x[t] ** 2
        out[t] = np.sqrt(var)
    return out


def parkinson_sigma(bars: dict) -> np.ndarray:
    """Per-bar Parkinson range estimator: sqrt(ln(H/L)^2 / (4 ln 2)).

    HERE TO FALSIFY AN EXPLANATION, not to win. ATR beat EWMA and GARCH in
    the first run, and the obvious reason is not that ATR is a better MODEL
    but that it sees the high and the low while a close-to-close estimator
    sees neither - a bar that travelled 4% and came back looks flat to one
    and violent to the other. Range estimators are known to be several times
    more efficient than close-to-close for exactly this reason.

    If an EWMA fed this estimator closes the gap, the finding is about the
    INPUT and every close-only model inherits the handicap - including any
    foundation model handed a series of closes."""
    h, l = bars["high"], bars["low"]
    return np.sqrt(np.log(h / l) ** 2 / (4.0 * np.log(2.0)))


def trailing_sigma(r: np.ndarray, window: int) -> np.ndarray:
    """Realized vol over the last `window` bars - the random-walk forecast:
    'the next window looks like the last one'."""
    out = np.full(r.shape, np.nan)
    for t in range(window, r.size):
        w = r[t - window + 1:t + 1]
        if np.all(np.isfinite(w)):
            out[t] = float(np.std(w, ddof=1))
    return out


def garch11_fit(r: np.ndarray) -> tuple[float, float, float]:
    """(omega, alpha, beta) by Gaussian MLE on TRAIN returns.

    scipy only - the `arch` package is not a dependency of this service and
    a research script must not add one to a container that executes trades.
    Constrained to alpha+beta < 1 so the process is stationary and the
    multi-step forecast converges rather than exploding."""
    from scipy.optimize import minimize
    x = r[np.isfinite(r)]
    v0 = float(np.var(x, ddof=1))

    def nll(p):
        omega, alpha, beta = np.exp(p)          # positivity by construction
        if alpha + beta >= 0.999:
            return 1e6
        var, s = v0, 0.0
        for t in range(x.size):
            s += np.log(var) + x[t] ** 2 / var
            var = omega + alpha * x[t] ** 2 + beta * var
        return 0.5 * s

    start = np.log([v0 * 0.05, 0.08, 0.90])
    res = minimize(nll, start, method="Nelder-Mead",
                   options={"maxiter": 2000, "xatol": 1e-6, "fatol": 1e-6})
    omega, alpha, beta = np.exp(res.x)
    return float(omega), float(alpha), float(beta)


def garch11_sigma(r: np.ndarray, params: tuple[float, float, float],
                  horizon: int) -> np.ndarray:
    """Average conditional volatility over the next `horizon` bars.

    The target is realized vol ACROSS the window, so the right forecast is
    the mean of the per-step variance forecasts, not the one-step value -
    GARCH mean-reverts toward the long-run level over 8 steps and a one-step
    number would systematically misstate a calm or violent start."""
    omega, alpha, beta = params
    persist = alpha + beta
    uncond = omega / max(1e-12, 1.0 - persist)
    out = np.full(r.shape, np.nan)
    var = np.nan
    for t in range(r.size):
        if not np.isfinite(r[t]):
            continue
        var = r[t] ** 2 if not np.isfinite(var) else omega + alpha * r[t] ** 2 + beta * var
        # E[var at t+k] = uncond + persist^k (var_{t+1} - uncond)
        ks = np.arange(1, horizon + 1)
        out[t] = np.sqrt(float(np.mean(uncond + persist ** (ks - 1) * (var - uncond))))
    return out
