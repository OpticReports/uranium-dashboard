"""Probability of Backtest Overfitting via CSCV.

Bailey, D.H., Borwein, J.M., López de Prado, M., Zhu, Q.J. (2015), "The
Probability of Backtest Overfitting", Journal of Computational Finance 20(4).

CSCV (Combinatorially Symmetric Cross-Validation):
  1. M is a T×N matrix of per-period returns for N strategy variants over the
     SAME T observations.
  2. Split rows into S contiguous, equal-size blocks. For every combination c
     of S/2 blocks: in-sample J = concat(c), out-of-sample J̄ = the rest.
  3. Rank strategies IS by Sharpe; let n* = argmax. Find n*'s OOS relative
     rank ω̄ ∈ (0,1) (fraction of strategies it beats OOS, mid-rank).
  4. Logit λ = ln(ω̄ / (1−ω̄)).  PBO = P(λ < 0): the fraction of splits where
     the IS winner is BELOW MEDIAN out of sample.

Interpretation: PBO ≈ 0.5 means selection carried no OOS information (pure
overfitting); PBO near 0 means IS selection kept working OOS.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np


def _sharpe_cols(m: np.ndarray) -> np.ndarray:
    mu = m.mean(axis=0)
    sd = m.std(axis=0, ddof=1)
    sd = np.where(sd == 0, np.nan, sd)
    return mu / sd


def cscv_pbo(returns: np.ndarray, n_blocks: int = 10, max_combinations: int = 3000,
             seed: int = 0) -> dict:
    """Run CSCV on a T×N strategy-returns matrix.

    n_blocks must be even (paper: S=16; default 10 → 252 splits for speed).
    If C(S, S/2) exceeds max_combinations, a seeded uniform subsample of
    combinations is used (documented in the output as sampled=True).
    """
    m = np.asarray(returns, dtype=float)
    if m.ndim != 2 or m.shape[1] < 2:
        raise ValueError("need a T×N matrix with N>=2 strategy variants")
    if n_blocks % 2:
        raise ValueError("n_blocks must be even")
    t, n = m.shape
    if t < n_blocks * 2:
        raise ValueError(f"too few observations ({t}) for {n_blocks} blocks")

    blocks = np.array_split(np.arange(t), n_blocks)
    combos = list(combinations(range(n_blocks), n_blocks // 2))
    sampled = False
    if len(combos) > max_combinations:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(combos), size=max_combinations, replace=False)
        combos = [combos[i] for i in idx]
        sampled = True

    logits, oos_sr_of_winner, is_sr_of_winner = [], [], []
    for c in combos:
        is_rows = np.concatenate([blocks[i] for i in c])
        oos_rows = np.concatenate([blocks[i] for i in range(n_blocks) if i not in c])
        sr_is = _sharpe_cols(m[is_rows])
        sr_oos = _sharpe_cols(m[oos_rows])
        star = int(np.nanargmax(sr_is))
        # mid-rank relative OOS rank of the IS winner, in (0,1)
        omega = (np.sum(sr_oos < sr_oos[star]) + 0.5 * np.sum(sr_oos == sr_oos[star])) / n
        omega = min(max(omega, 1.0 / (2 * n)), 1.0 - 1.0 / (2 * n))
        logits.append(np.log(omega / (1.0 - omega)))
        is_sr_of_winner.append(sr_is[star])
        oos_sr_of_winner.append(sr_oos[star])

    logits = np.array(logits)
    return {
        "pbo": float(np.mean(logits < 0)),
        "n_splits": len(combos),
        "sampled": sampled,
        "logit_mean": float(logits.mean()),
        # performance degradation: mean IS vs OOS Sharpe of the selected strategy
        "winner_is_sharpe_mean": float(np.mean(is_sr_of_winner)),
        "winner_oos_sharpe_mean": float(np.mean(oos_sr_of_winner)),
    }
