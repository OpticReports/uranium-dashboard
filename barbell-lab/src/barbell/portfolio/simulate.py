"""Monte Carlo scenario engines for the portfolio lab.

Two REQUIRED generators (spec: report both, disagreement is information):

1. Multivariate Student-t (df 4–6, config): captures joint fat tails but
   assumes a static elliptical dependence.
2. Stationary block bootstrap (Politis & Romano 1994, geometric block length,
   mean = config block_len_days) from the ACTUAL joint return history:
   captures autocorrelation, vol clustering and non-elliptical co-crashes,
   but can only replay dependence patterns that happened.

Both simulate DAILY returns (no monthly shortcuts — drawdown constraints are
evaluated at daily resolution), chunked to bound memory.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _mvt_params(returns: pd.DataFrame, df: float) -> tuple[np.ndarray, np.ndarray]:
    """Location + scale matrix so that the t draws reproduce the sample
    mean/covariance: cov = scale * df/(df-2)  =>  scale = cov * (df-2)/df."""
    if df <= 2:
        raise ValueError("t df must exceed 2 for finite covariance")
    mu = returns.mean().values
    cov = returns.cov().values
    scale = cov * (df - 2.0) / df
    return mu, np.linalg.cholesky(scale + 1e-12 * np.eye(len(mu)))


def mvt_paths(returns: pd.DataFrame, weights: np.ndarray, n_paths: int,
              horizon_years: int, df: float, seed: int = 0,
              chunk: int = 1000) -> dict:
    """Multivariate-t daily paths projected onto fixed weights."""
    mu, chol = _mvt_params(returns, df)
    days = horizon_years * TRADING_DAYS
    rng = np.random.default_rng(seed)
    return _accumulate(
        lambda n: _mvt_chunk(rng, n, days, mu, chol, df) @ weights,
        n_paths, days, horizon_years, chunk,
    )


def _mvt_chunk(rng, n, days, mu, chol, df) -> np.ndarray:
    k = len(mu)
    z = rng.standard_normal((n, days, k))
    g = rng.chisquare(df, size=(n, days, 1)) / df
    return mu + (z @ chol.T) / np.sqrt(g)


def bootstrap_paths(returns: pd.DataFrame, weights: np.ndarray, n_paths: int,
                    horizon_years: int, block_len: int, seed: int = 0,
                    chunk: int = 1000) -> dict:
    """Stationary block bootstrap of the JOINT rows (dependence preserved by
    construction), projected onto fixed weights."""
    r = returns.values
    t = len(r)
    if t < block_len * 5:
        raise ValueError(f"history too short ({t} rows) for block length {block_len}")
    days = horizon_years * TRADING_DAYS
    rng = np.random.default_rng(seed)
    port_daily = r @ weights

    def gen(n: int) -> np.ndarray:
        idx = _stationary_indices(rng, n, days, t, block_len)
        return port_daily[idx]

    return _accumulate(gen, n_paths, days, horizon_years, chunk)


def _stationary_indices(rng, n_paths, days, t, mean_block) -> np.ndarray:
    """Politis-Romano stationary bootstrap index matrix (n_paths × days):
    geometric block lengths (p = 1/mean_block), wrap-around continuation."""
    p = 1.0 / mean_block
    restart = rng.random((n_paths, days)) < p
    restart[:, 0] = True
    starts = rng.integers(0, t, size=(n_paths, days))
    idx = np.zeros((n_paths, days), dtype=np.int64)
    prev = starts[:, 0]
    idx[:, 0] = prev
    for j in range(1, days):
        cont = (prev + 1) % t
        prev = np.where(restart[:, j], starts[:, j], cont)
        idx[:, j] = prev
    return idx


def _accumulate(gen, n_paths, days, horizon_years, chunk) -> dict:
    """Run the generator chunk-wise; collect per-path terminal wealth, per-year
    returns, and daily-resolution max drawdown."""
    terminal, annual, maxdd = [], [], []
    done = 0
    while done < n_paths:
        n = min(chunk, n_paths - done)
        pr = gen(n)                                   # (n, days) daily returns
        logw = np.cumsum(np.log1p(pr), axis=1)
        terminal.append(np.exp(logw[:, -1]))
        # non-overlapping annual returns per path
        year_marks = logw[:, TRADING_DAYS - 1::TRADING_DAYS]
        ann = np.diff(np.concatenate([np.zeros((n, 1)), year_marks], axis=1), axis=1)
        annual.append(np.expm1(ann).ravel())
        peak = np.maximum.accumulate(logw, axis=1)
        maxdd.append(np.expm1((logw - peak).min(axis=1)))
        done += n
    return {
        "terminal_wealth": np.concatenate(terminal),
        "annual_returns": np.concatenate(annual),
        "max_drawdowns": np.concatenate(maxdd),
        "n_paths": n_paths,
        "horizon_years": horizon_years,
    }


def path_metrics(paths: dict) -> dict:
    tw = paths["terminal_wealth"]
    ann = paths["annual_returns"]
    dd = paths["max_drawdowns"]
    yrs = paths["horizon_years"]
    k = max(1, int(np.ceil(0.05 * ann.size)))
    return {
        "cagr_median": float(np.median(tw) ** (1 / yrs) - 1),
        "cagr_p5": float(np.percentile(tw, 5) ** (1 / yrs) - 1),
        "terminal_p5": float(np.percentile(tw, 5)),
        "terminal_p50": float(np.median(tw)),
        "cvar5_annual": float(np.sort(ann)[:k].mean()),
        "maxdd_p5": float(np.percentile(dd, 5)),
        "prob_loss_10y": float((tw < 1.0).mean()),
    }
