"""Scoring for quantile forecasts.

The primary gate is CALIBRATION, fixed in RESEARCH_FORECAST_FM.md section 3:
does the 10-90 band actually contain 80% of outcomes? A sizer punished by an
overconfident interval does not care that the median was close, so a sharp
but dishonest forecast must lose here.
"""
from __future__ import annotations

import numpy as np

# The nine levels TimesFM-3 and Chronos-2 both emit.
LEVELS = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
COVERAGE_TARGET = 0.80          # the 10-90 band
COVERAGE_TOLERANCE = 0.05       # +/- 5pp, section 4 rule 1


def pinball(y: np.ndarray, q: np.ndarray, tau: float) -> np.ndarray:
    """Per-observation pinball (quantile) loss at level tau.

    Under-prediction is charged tau, over-prediction (1-tau). At tau=0.9 an
    outcome above the forecast costs 9x what one below it costs, which is
    what makes the high quantiles refuse to be optimistic."""
    d = y - q
    return np.where(d >= 0, tau * d, (tau - 1.0) * d)


def mean_pinball(y: np.ndarray, Q: np.ndarray) -> float:
    """Mean over observations and all nine levels. Q is (n, 9)."""
    if Q.shape[1] != LEVELS.size:
        raise ValueError(f"expected {LEVELS.size} quantile columns, got {Q.shape[1]}")
    return float(np.mean([np.mean(pinball(y, Q[:, i], t))
                          for i, t in enumerate(LEVELS)]))


def crps(y: np.ndarray, Q: np.ndarray) -> float:
    """CRPS approximated from the nine quantiles.

    CRPS = 2 * integral of pinball over tau in (0,1). With nine evenly
    spaced levels this is a coarse Riemann sum, and it says nothing about
    the tails beyond the 10th and 90th - reported as a secondary number for
    exactly that reason."""
    return 2.0 * mean_pinball(y, Q)


def coverage(y: np.ndarray, Q: np.ndarray) -> float:
    """Empirical fraction inside the 10-90 band. Target 0.80."""
    return float(np.mean((y >= Q[:, 0]) & (y <= Q[:, -1])))


def coverage_by_level(y: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """P(y <= q_tau) at each level - the calibration curve.

    A perfectly calibrated forecaster returns LEVELS itself. Deviations say
    WHERE it lies: a curve below the diagonal at the top end means the high
    quantiles are too low, i.e. it is blind to violent periods, which is the
    failure that actually costs money in a sizer."""
    return np.array([float(np.mean(y <= Q[:, i])) for i in range(Q.shape[1])])


def passes_coverage_gate(y: np.ndarray, Q: np.ndarray) -> bool:
    """Section 4 rule 1. Rejected here means rejected for sizing, whatever
    else the model scores."""
    return abs(coverage(y, Q) - COVERAGE_TARGET) <= COVERAGE_TOLERANCE


def summary(y: np.ndarray, Q: np.ndarray) -> dict:
    return {"n": int(y.size), "coverage": coverage(y, Q),
            "pinball": mean_pinball(y, Q), "crps": crps(y, Q),
            "gate": passes_coverage_gate(y, Q)}
