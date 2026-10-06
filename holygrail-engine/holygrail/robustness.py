"""How much should we trust the scorecard?  Sampling error, correlation
sensitivity, regime dependence and estimator dependence of N_eff and Sharpe.
All resampling is seeded."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .core import effective_bets, mean_pairwise_correlation, validate_covariance
from .errors import ValidationError
from .estimate import (common_window, ewma_cov, ledoit_wolf_constant_corr, ledoit_wolf_identity, nearest_correlation,
                       sample_cov)
from .forward import stationary_bootstrap_indices

_MEASURES = ("dr2", "equal_rho", "pca_entropy", "prc_inverse_hhi", "min_torsion")


def _measures(w, S) -> dict:
    eb = effective_bets(w, S)
    return {m: getattr(eb, m) for m in _MEASURES}


def bootstrap_neff_sharpe(returns: pd.DataFrame, weights, *, periods_per_year: float, n_boot: int = 500,
                          mean_block: float | None = None, seed: int = 0, rf_period: float = 0.0,
                          level: float = 0.90) -> dict:
    """Stationary-block-bootstrap percentile CIs (``level``) for every N_eff
    measure and for the realised Sharpe of the constant-mix book w'r, on a
    common-window return history.  Each replicate resamples T rows, re-estimates
    the sample covariance and recomputes the statistics at FIXED weights.
    Sharpe = mean(r_p - rf)/std(r_p - rf) sqrt(q).  Default mean block =
    max(1, sqrt(T)) periods."""
    R = common_window(returns, min_obs=30)
    X = R.to_numpy(float)
    T = X.shape[0]
    w = np.asarray(weights, float)
    if len(w) != X.shape[1]:
        raise ValidationError("weights length differs from return columns")
    mb = mean_block or max(1.0, math.sqrt(T))
    rng = np.random.default_rng(seed)
    idx = stationary_bootstrap_indices(T, T, n_boot, mb, rng)

    def sharpe(x):
        rp = x @ w + (1 - w.sum()) * rf_period - rf_period
        sd = rp.std(ddof=1)
        return float(rp.mean() / sd * math.sqrt(periods_per_year)) if sd > 0 else np.nan

    point = _measures(w, sample_cov(X))
    point["sharpe"] = sharpe(X)
    reps = {k: [] for k in point}
    for b in range(n_boot):
        Xb = X[idx[b]]
        try:
            m = _measures(w, sample_cov(Xb))
        except Exception:  # a degenerate replicate (e.g. zero variance) is skipped and counted
            continue
        m["sharpe"] = sharpe(Xb)
        for k, v in m.items():
            reps[k].append(v)
    a = (1 - level) / 2
    out = {"n_boot": n_boot, "n_ok": len(reps["dr2"]), "mean_block": mb, "level": level, "T": T,
           "periods_per_year": periods_per_year}
    for k, v in point.items():
        arr = np.asarray(reps[k], float)
        out[k] = {"point": v, "lo": float(np.nanquantile(arr, a)), "hi": float(np.nanquantile(arr, 1 - a)),
                  "sd": float(np.nanstd(arr, ddof=1))}
    return out


def shift_correlations(S, delta: float) -> tuple[np.ndarray, bool]:
    """Add ``delta`` to every off-diagonal correlation (clipped to [-1, 1]),
    keep vols, and Higham-repair if the result is not PSD.  Returns
    (S_shifted, repaired)."""
    S = validate_covariance(S)
    sig = np.sqrt(np.diag(S))
    if np.any(sig == 0):
        raise ValidationError("shift_correlations needs positive variances")
    C = S / np.outer(sig, sig)
    off = ~np.eye(len(sig), dtype=bool)
    C2 = C.copy()
    C2[off] = np.clip(C[off] + delta, -1.0, 1.0)
    repaired = False
    if np.linalg.eigvalsh(C2)[0] < -1e-12:
        C2 = nearest_correlation(C2)
        repaired = True
    return C2 * np.outer(sig, sig), repaired


def neff_sensitivity(w, S, deltas=(-0.2, -0.1, -0.05, 0.0, 0.05, 0.1, 0.2)) -> list:
    """N_eff measures and portfolio vol after shifting all pairwise
    correlations by each delta (shift_correlations)."""
    rows = []
    w = np.asarray(w, float)
    for d in deltas:
        Sd, rep = shift_correlations(S, d)
        m = _measures(w, Sd)
        m.update({"delta_rho": float(d), "vol": float(math.sqrt(w @ Sd @ w)), "repaired": rep})
        rows.append(m)
    return rows


def stress_mask(market_levels: pd.Series, *, dd_window: int = 63, dd_threshold: float = 0.10,
                vix: pd.Series | None = None, vix_threshold: float = 30.0) -> pd.Series:
    """Stress-regime indicator: True when the market is more than
    ``dd_threshold`` below its rolling ``dd_window``-period high
    (P_t / max_{t-w+1..t} P - 1 < -threshold), OR VIX (as-of) > vix_threshold."""
    p = pd.Series(market_levels, dtype=float).dropna()
    dd = p / p.rolling(dd_window, min_periods=1).max() - 1.0
    m = dd < -dd_threshold
    if vix is not None:
        v = pd.Series(vix, dtype=float).dropna()
        v = v.reindex(v.index.union(p.index)).ffill().reindex(p.index)
        m = m | (v > vix_threshold).fillna(False)
    return m.rename("stress")


def regime_correlations(returns: pd.DataFrame, mask: pd.Series, min_obs: int = 20) -> dict:
    """Correlation matrices in calm vs stress periods (``mask`` True = stress,
    aligned by date; common window), with counts and mean pairwise rho."""
    R = common_window(returns)
    m = pd.Series(mask).reindex(R.index)
    if m.isna().any():
        raise ValidationError("stress mask does not cover every return date")
    m = m.astype(bool)
    out = {"n_calm": int((~m).sum()), "n_stress": int(m.sum())}
    for label, sel in (("calm", ~m), ("stress", m)):
        sub = R[sel.to_numpy()]
        if len(sub) < min_obs:
            out[label] = None
            out[f"mean_rho_{label}"] = float("nan")
            continue
        C = sub.corr()
        out[label] = C
        out[f"mean_rho_{label}"] = mean_pairwise_correlation(C.to_numpy())
    return out


def rolling_correlation(returns: pd.DataFrame, window: int, pairs=None) -> pd.DataFrame:
    """Rolling ``window``-period correlation for each pair (default: all)."""
    cols = list(returns.columns)
    pairs = pairs or [(a, b) for i, a in enumerate(cols) for b in cols[i + 1:]]
    out = {}
    for a, b in pairs:
        out[f"{a}|{b}"] = returns[a].rolling(window, min_periods=window).corr(returns[b])
    return pd.DataFrame(out)


def rolling_neff(returns: pd.DataFrame, weights, window: int) -> pd.DataFrame:
    """Rolling DR^2 (headline N_eff), mean pairwise rho and book vol (per period)
    on trailing ``window`` complete rows, at fixed weights."""
    R = returns.dropna(how="any")
    w = np.asarray(weights, float)
    rows, idx = [], []
    X = R.to_numpy(float)
    for k in range(window, len(R) + 1):
        S = sample_cov(X[k - window:k])
        sig = np.sqrt(np.diag(S))
        if np.any(sig == 0):
            continue
        sp = math.sqrt(w @ S @ w)
        rows.append({"dr2": (w @ sig / sp) ** 2, "mean_rho": mean_pairwise_correlation(S / np.outer(sig, sig)),
                     "vol_period": sp})
        idx.append(R.index[k - 1])
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


def shrinkage_comparison(returns: pd.DataFrame, weights, *, periods_per_year: float,
                         halflife: float | None = None) -> list:
    """Book vol, N_eff (DR^2 and the others), mean pairwise rho, condition
    number and shrinkage intensity under each estimator on the same window."""
    R = common_window(returns)
    w = np.asarray(weights, float)
    T = len(R)
    ests = {"sample": (sample_cov(R), None)}
    ests["lw_identity"] = ledoit_wolf_identity(R)
    ests["lw_constant_corr"] = ledoit_wolf_constant_corr(R)
    ests["ewma"] = (ewma_cov(R, halflife or max(5.0, T / 4.0), demean=True), None)
    rows = []
    for name, (S, shrink) in ests.items():
        Sa = S * periods_per_year
        sig = np.sqrt(np.diag(Sa))
        m = _measures(w, Sa)
        lam = np.linalg.eigvalsh(Sa)
        m.update({"estimator": name, "vol": float(math.sqrt(w @ Sa @ w)),
                  "mean_rho": mean_pairwise_correlation(Sa / np.outer(sig, sig)),
                  "condition_number": float(lam[-1] / lam[0]) if lam[0] > 0 else float("inf"),
                  "shrinkage": shrink, "n_obs": T})
        rows.append(m)
    return rows
