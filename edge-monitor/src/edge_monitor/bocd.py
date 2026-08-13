"""Bayesian Online Changepoint Detection (Adams & MacKay 2007) with a
Normal-Inverse-Gamma conjugate model -> Student-t predictive.

Run on VOL-STANDARDIZED returns (divide by a slow EWMA vol) or the detector
mostly finds volatility regimes instead of edge changes — vol clustering is
the dominant nonstationarity in raw financial returns and it is NOT the
thing we want to alarm on here (the vol layer owns that).

Output per day: P(run length = 0..small | data) — "probability the
return-generating process changed recently". The monitoring layer reads
p_change_recent = P(r_t < w) for a small window w (e.g. 10 days).

Numerics: run-length distribution is truncated at r_max and renormalized;
probabilities are propagated in linear space with per-step normalization
(adequate for daily scale; log-space is overkill at these lengths).
"""
from __future__ import annotations

import math

import numpy as np


class Bocd:
    def __init__(self, hazard: float = 1.0 / 250.0,
                 mu0: float = 0.0, kappa0: float = 1.0,
                 alpha0: float = 1.0, beta0: float = 1.0,
                 r_max: int = 1000):
        self.h = hazard
        self.r_max = r_max
        self.mu0, self.kappa0, self.alpha0, self.beta0 = mu0, kappa0, alpha0, beta0
        # sufficient statistics per run length
        self.mu = np.array([mu0])
        self.kappa = np.array([kappa0])
        self.alpha = np.array([alpha0])
        self.beta = np.array([beta0])
        self.rl = np.array([1.0])          # P(run length) — starts at r=0

    @staticmethod
    def _t_pdf(x: np.ndarray, df: np.ndarray, loc: np.ndarray,
               scale2: np.ndarray) -> np.ndarray:
        z2 = (x - loc) ** 2 / scale2
        lg = (np.vectorize(math.lgamma)((df + 1) / 2)
              - np.vectorize(math.lgamma)(df / 2))
        return np.exp(lg) / np.sqrt(df * math.pi * scale2) * \
            (1 + z2 / df) ** (-(df + 1) / 2)

    def update(self, x: float) -> dict:
        # Student-t predictive per run length
        df = 2.0 * self.alpha
        scale2 = self.beta * (self.kappa + 1.0) / (self.alpha * self.kappa)
        pred = self._t_pdf(np.full_like(self.mu, x), df, self.mu, scale2)

        growth = self.rl * pred * (1.0 - self.h)
        cp = float((self.rl * pred).sum() * self.h)
        rl_new = np.concatenate([[cp], growth])
        s = rl_new.sum()
        if s <= 0 or not np.isfinite(s):     # numerical wipeout: hard reset
            self.__init__(self.h, self.mu0, self.kappa0, self.alpha0,
                          self.beta0, self.r_max)
            return {"p_change_recent": 1.0, "map_run_length": 0, "reset": True}
        self.rl = rl_new / s

        # posterior updates (prepend fresh prior for r=0)
        mu_n = (self.kappa * self.mu + x) / (self.kappa + 1.0)
        beta_n = self.beta + self.kappa * (x - self.mu) ** 2 / (2.0 * (self.kappa + 1.0))
        self.mu = np.concatenate([[self.mu0], mu_n])
        self.kappa = np.concatenate([[self.kappa0], self.kappa + 1.0])
        self.alpha = np.concatenate([[self.alpha0], self.alpha + 0.5])
        self.beta = np.concatenate([[self.beta0], beta_n])

        if len(self.rl) > self.r_max:        # truncate tail, renormalize
            keep = self.r_max
            self.rl = self.rl[:keep] / self.rl[:keep].sum()
            self.mu, self.kappa = self.mu[:keep], self.kappa[:keep]
            self.alpha, self.beta = self.alpha[:keep], self.beta[:keep]

        return {"p_change_recent": float(self.rl[:10].sum()),
                "map_run_length": int(self.rl.argmax()), "reset": False}


def standardize(returns: np.ndarray, halflife: int = 20) -> np.ndarray:
    """Divide by a LAGGED EWMA vol so the standardization at t uses only
    data through t-1 (no contemporaneous leakage)."""
    r = np.asarray(returns, dtype=float)
    lam = 0.5 ** (1.0 / halflife)
    var = np.empty(len(r))
    v = r[: min(20, len(r))].var() or 1e-8
    for i in range(len(r)):
        var[i] = v                     # var known BEFORE observing r[i]
        v = lam * v + (1 - lam) * r[i] ** 2
    return r / np.sqrt(np.maximum(var, 1e-12))
