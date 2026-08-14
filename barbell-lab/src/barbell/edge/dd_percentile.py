"""Live drawdown vs the backtest's Monte Carlo drawdown distribution.

The question a drawdown should trigger is never "does it feel big" but
"what percentile of the backtest-implied distribution is it, at THIS track
length". Two statistics per check, both length-matched:

- max_dd_pctile: live max drawdown over the live window vs the distribution
  of max drawdowns over same-length windows bootstrapped from the backtest.
- underwater_pctile: CURRENT underwater depth vs the distribution of
  end-of-window underwater depths (a live DD you are still inside is not a
  completed max-DD draw; comparing it to max-DD is biased toward calm).

Circular block bootstrap preserves vol clustering; window length matching
removes the "longer windows have deeper DDs" artifact.
"""
from __future__ import annotations

import numpy as np


def _dd_stats(r: np.ndarray) -> tuple[float, float]:
    eq = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    return float(dd.min()), float(dd[-1])          # (max_dd, end_underwater)


def dd_percentiles(live_returns: np.ndarray, backtest_returns: np.ndarray,
                   block: int = 20, n_sims: int = 4000, seed: int = 11) -> dict:
    live = np.asarray(live_returns, dtype=float)
    live = live[~np.isnan(live)]
    bt = np.asarray(backtest_returns, dtype=float)
    bt = bt[~np.isnan(bt)]
    L, n = len(live), len(bt)
    if L < 5:
        return {"insufficient": True, "n_live": L, "min_needed": 5}
    live_max_dd, live_uw = _dd_stats(live)

    rng = np.random.default_rng(seed)
    nblk = int(np.ceil(L / block))
    starts = rng.integers(0, n, size=(n_sims, nblk))
    idx = ((starts[:, :, None] + np.arange(block)[None, None, :]) % n
           ).reshape(n_sims, -1)[:, :L]
    R = bt[idx]
    eq = np.cumprod(1.0 + R, axis=1)
    peak = np.maximum.accumulate(eq, axis=1)
    dd = eq / peak - 1.0
    sim_max = dd.min(axis=1)
    sim_uw = dd[:, -1]

    # percentile = fraction of simulations LESS BAD than live (higher = worse)
    return {
        "insufficient": False, "n_live": L,
        "live_max_dd": round(live_max_dd, 4),
        "max_dd_pctile": round(float((sim_max > live_max_dd).mean()) * 100, 1),
        "live_underwater": round(live_uw, 4),
        "underwater_pctile": round(float((sim_uw > live_uw).mean()) * 100, 1),
        "backtest_p95_max_dd_at_this_length":
            round(float(np.percentile(sim_max, 5)), 4),
        "backtest_p99_max_dd_at_this_length":
            round(float(np.percentile(sim_max, 1)), 4),
    }
