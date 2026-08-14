"""Two-sided CUSUM on standardized returns with ARL calibrated by Monte
Carlo on the strategy's OWN backtest distribution (block bootstrap), not by
Gaussian closed forms — fat tails and autocorrelation make Siegmund's
approximation optimistic on financial returns.

Page (1954) for CUSUM; ARL calibration by simulation is standard SPC
practice when the in-control distribution is non-normal.

Usage: calibrate once at baseline registration (threshold h for a target
in-control ARL, e.g. 500 trading days ~ one false alarm per two years),
then update the statistic online each day.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CusumState:
    """Detects a DOWNWARD mean shift in standardized returns (edge decay).
    s_neg accumulates evidence below the reference; alarm when > h."""
    k: float                 # reference value (half the shift to detect, in sigma)
    h: float                 # decision threshold (in sigma units)
    s_neg: float = 0.0
    s_pos: float = 0.0       # upward drift tracked too (regime change, not decay)
    alarmed: bool = False

    def update(self, z: float) -> bool:
        """z = (return - baseline_mean) / baseline_std. Returns True on alarm."""
        self.s_neg = max(0.0, self.s_neg + (-z) - self.k)
        self.s_pos = max(0.0, self.s_pos + z - self.k)
        self.alarmed = self.s_neg > self.h
        return self.alarmed

    def reset(self) -> None:
        self.s_neg = self.s_pos = 0.0
        self.alarmed = False


def run_length(z: np.ndarray, k: float, h: float) -> int:
    """First alarm index (1-based) of the downward CUSUM on z, or len(z)+1."""
    s = 0.0
    for i, zi in enumerate(z):
        s = max(0.0, s + (-zi) - k)
        if s > h:
            return i + 1
    return len(z) + 1


def calibrate_h(backtest_returns: np.ndarray, target_arl: float,
                k: float = 0.25, block: int = 20, n_sims: int = 2000,
                sim_len: int | None = None, seed: int = 7) -> dict:
    """Find h such that the in-control ARL (mean run length to a FALSE alarm
    when returns are drawn from the backtest distribution) ~= target_arl.

    Circular block bootstrap of the backtest's standardized returns preserves
    short-range dependence (vol clustering). Bisection on h; censored runs
    (no alarm within sim_len) enter at sim_len+1, so the reported ARL is a
    LOWER bound when censoring binds — conservative in the safe direction
    (true false-alarm rate is lower than reported).
    """
    r = np.asarray(backtest_returns, dtype=float)
    r = r[~np.isnan(r)]
    z0 = (r - r.mean()) / r.std(ddof=1)
    n = len(z0)
    sim_len = sim_len or int(4 * target_arl)
    rng = np.random.default_rng(seed)
    nblk = int(np.ceil(sim_len / block))
    starts = rng.integers(0, n, size=(n_sims, nblk))
    idx = ((starts[:, :, None] + np.arange(block)[None, None, :]) % n
           ).reshape(n_sims, -1)[:, :sim_len]
    Z = z0[idx]

    def arl(h: float) -> float:
        return float(np.mean([run_length(Z[i], k, h) for i in range(n_sims)]))

    lo, hi = 0.5, 30.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if arl(mid) < target_arl:
            lo = mid
        else:
            hi = mid
    h = 0.5 * (lo + hi)
    a = arl(h)
    return {"k": k, "h": round(h, 3), "achieved_arl": round(a, 1),
            "target_arl": target_arl, "censored_at": sim_len,
            "censoring_binds": bool(a >= 0.95 * (sim_len + 1)),
            "note": "ARL is a lower bound if censoring_binds"}
