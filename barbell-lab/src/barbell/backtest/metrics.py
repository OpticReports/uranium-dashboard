"""Portfolio performance metrics. All inputs are DAILY simple returns."""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def cagr(returns: pd.Series) -> float:
    """Geometric annualized growth from daily returns."""
    n = len(returns)
    if n == 0:
        raise ValueError("empty return series")
    wealth = float((1 + returns).prod())
    return wealth ** (TRADING_DAYS / n) - 1.0


def ann_vol(returns: pd.Series) -> float:
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS))


def max_drawdown(returns: pd.Series) -> float:
    """Most negative peak-to-trough drawdown (a negative number)."""
    wealth = (1 + returns).cumprod()
    dd = wealth / wealth.cummax() - 1.0
    return float(dd.min())


def cvar(returns: np.ndarray | pd.Series, alpha: float = 0.05) -> float:
    """Historical CVaR: mean of the worst alpha-fraction of outcomes
    (a negative number for loss tails). Works on any horizon's returns —
    callers must pass ANNUAL returns for the sleeve's annual-CVaR constraint."""
    r = np.sort(np.asarray(returns, dtype=float))
    k = max(1, int(np.ceil(alpha * r.size)))
    return float(r[:k].mean())


def rolling_annual_returns(returns: pd.Series) -> pd.Series:
    """Overlapping 252-day compounded returns — the HISTORICAL approximation
    for annual-horizon risk metrics (the Monte Carlo lab computes them from
    simulated non-overlapping years; both are reported, labeled)."""
    lw = np.log1p(returns)
    roll = lw.rolling(TRADING_DAYS).sum().dropna()
    return np.expm1(roll)


def summary(returns: pd.Series) -> dict:
    ann = rolling_annual_returns(returns)
    return {
        "n_days": int(len(returns)),
        "start": str(returns.index.min().date()),
        "end": str(returns.index.max().date()),
        "cagr": cagr(returns),
        "ann_vol": ann_vol(returns),
        "sharpe_daily": float(returns.mean() / returns.std(ddof=1)),
        "sharpe_annual": float(returns.mean() / returns.std(ddof=1) * np.sqrt(TRADING_DAYS)),
        "max_drawdown": max_drawdown(returns),
        "cvar5_annual_overlapping": cvar(ann, 0.05) if len(ann) else None,
        "worst_day": float(returns.min()),
    }
