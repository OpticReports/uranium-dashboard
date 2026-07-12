"""Horizon-specific recession probit — fit from FRED data (3m10y + USREC).

We reproduce (and extend to multiple horizons) the Estrella-Mishkin approach:
for horizon h, fit  P(recession within h months) = Phi(b0 + b1 * spread)  by
maximum likelihood (IRLS), on monthly-averaged 3m10y and NBER recession dates.

Everything is pure-Python (no numpy/scipy) — only 2 parameters, so the linear
algebra is a hand-rolled 2x2. We return the coefficient covariance so callers can
put a CONFIDENCE BAND on the probability, plus in-sample AUC so the number carries
its own track record instead of pretending to be certain.
"""
from __future__ import annotations

import math
import threading
import time
from datetime import date

HORIZONS = (6, 12, 18, 24)
_SQRT2PI = math.sqrt(2.0 * math.pi)


def _phi(x: float) -> float:            # standard normal pdf
    return math.exp(-0.5 * x * x) / _SQRT2PI


def _Phi(x: float) -> float:            # standard normal cdf
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _clip(p: float, lo: float = 1e-6, hi: float = 1.0 - 1e-6) -> float:
    return max(lo, min(hi, p))


# --- monthly alignment -------------------------------------------------------

def monthly_mean(dates: list[date], vals: list[float | None]) -> dict[tuple[int, int], float]:
    """Average a daily series into {(year, month): mean} over non-null values."""
    acc: dict[tuple[int, int], list[float]] = {}
    for d, v in zip(dates, vals):
        if v is None:
            continue
        acc.setdefault((d.year, d.month), []).append(v)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def monthly_usrec(dates: list[date], vals: list[float | None]) -> dict[tuple[int, int], float]:
    return {(d.year, d.month): (v or 0.0) for d, v in zip(dates, vals)}


def _add_months(ym: tuple[int, int], k: int) -> tuple[int, int]:
    y, m = ym
    idx = (y * 12 + (m - 1)) + k
    return idx // 12, idx % 12 + 1


def build_dataset(spread_monthly: dict, usrec_monthly: dict, horizon: int
                  ) -> tuple[list[float], list[int]]:
    """(spread_t, y_t) where y_t = 1 if a recession occurs in any month (t+1..t+h)."""
    xs: list[float] = []
    ys: list[int] = []
    for ym, sp in sorted(spread_monthly.items()):
        future = [usrec_monthly.get(_add_months(ym, k)) for k in range(1, horizon + 1)]
        if any(f is None for f in future):
            continue  # not enough future to label
        xs.append(sp)
        ys.append(1 if any((f or 0.0) >= 1.0 for f in future) else 0)
    return xs, ys


# --- probit MLE via IRLS (2 params) ------------------------------------------

def fit_probit(xs: list[float], ys: list[int], iters: int = 25
               ) -> tuple[float, float, list[list[float]]]:
    """Return (b0, b1, cov[2][2]). cov is the inverse Fisher information at the MLE."""
    b0, b1 = 0.0, 0.0
    cov = [[0.0, 0.0], [0.0, 0.0]]
    for _ in range(iters):
        # Accumulate X'WX (2x2) and X'Wz (2) for the IRLS update.
        s00 = s01 = s11 = 0.0
        t0 = t1 = 0.0
        for x, y in zip(xs, ys):
            eta = b0 + b1 * x
            P = _clip(_Phi(eta))
            phi = _phi(eta)
            w = phi * phi / (P * (1.0 - P))          # probit working weight
            z = eta + (y - P) / phi                    # working response
            s00 += w
            s01 += w * x
            s11 += w * x * x
            t0 += w * z
            t1 += w * x * z
        det = s00 * s11 - s01 * s01
        if abs(det) < 1e-12:
            break
        inv00, inv01, inv11 = s11 / det, -s01 / det, s00 / det
        nb0 = inv00 * t0 + inv01 * t1
        nb1 = inv01 * t0 + inv11 * t1
        cov = [[inv00, inv01], [inv01, inv11]]        # (X'WX)^-1 == coef covariance
        if abs(nb0 - b0) < 1e-9 and abs(nb1 - b1) < 1e-9:
            b0, b1 = nb0, nb1
            break
        b0, b1 = nb0, nb1
    return b0, b1, cov


def predict(b0: float, b1: float, cov: list[list[float]], spread: float, z: float = 1.96
            ) -> dict:
    """Probability + confidence band at `spread`. CI is formed on the linear index
    eta and mapped through Phi so it stays inside [0,1]."""
    eta = b0 + b1 * spread
    # Var(eta) = g' cov g with g = [1, spread]
    var_eta = cov[0][0] + 2 * spread * cov[0][1] + spread * spread * cov[1][1]
    se = math.sqrt(var_eta) if var_eta > 0 else 0.0
    return {
        "probability_pct": round(100.0 * _Phi(eta), 1),
        "ci_low_pct": round(100.0 * _Phi(eta - z * se), 1),
        "ci_high_pct": round(100.0 * _Phi(eta + z * se), 1),
    }


def auc(xs: list[float], ys: list[int], b1_sign: float = -1.0) -> float | None:
    """In-sample AUC. Score = -spread (lower spread => higher risk), so a good model
    has AUC > 0.5. Rank-based (Mann-Whitney)."""
    scores = [b1_sign * x for x in xs]  # default: more negative spread ranks as higher risk
    pos = [s for s, y in zip(scores, ys) if y == 1]
    neg = [s for s, y in zip(scores, ys) if y == 0]
    if not pos or not neg:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # average rank (1-based) for ties
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    rank_pos = sum(r for r, y in zip(ranks, ys) if y == 1)
    n_pos, n_neg = len(pos), len(neg)
    u = rank_pos - n_pos * (n_pos + 1) / 2.0
    return round(u / (n_pos * n_neg), 3)


def build_models(spread_dates: list[date], spread_vals: list[float | None],
                 usrec_dates: list[date], usrec_vals: list[float | None]) -> dict[int, dict]:
    """Fit every horizon. Returns {h: {b0,b1,cov,auc,n_obs,n_pos}} (empty if no data)."""
    sm = monthly_mean(spread_dates, spread_vals)
    um = monthly_usrec(usrec_dates, usrec_vals)
    if not sm or not um:
        return {}
    out: dict[int, dict] = {}
    for h in HORIZONS:
        xs, ys = build_dataset(sm, um, h)
        if sum(ys) < 5 or len(xs) < 30:      # need enough recession months to fit
            continue
        b0, b1, cov = fit_probit(xs, ys)
        out[h] = {"b0": b0, "b1": b1, "cov": cov, "auc": auc(xs, ys),
                  "n_obs": len(xs), "n_pos": sum(ys)}
    return out


# --- cached fit over the live FRED bundle ------------------------------------
_MODEL_TTL_SECONDS = 6 * 3600
_model_cache: dict[str, object] = {"ts": 0.0, "models": None, "spread": None}
_model_lock = threading.Lock()


def cached_models_and_spread() -> tuple[dict[int, dict], float | None]:
    """(models, current_3m10y_spread), fit from the memoized FRED bundle. Cached so
    /recession-prob and /recession-model don't refit the probit on every request."""
    now = time.time()
    if _model_cache["models"] is not None and now - float(_model_cache["ts"]) < _MODEL_TTL_SECONDS:
        return _model_cache["models"], _model_cache["spread"]  # type: ignore[return-value]
    with _model_lock:
        now = time.time()
        if _model_cache["models"] is not None and now - float(_model_cache["ts"]) < _MODEL_TTL_SECONDS:
            return _model_cache["models"], _model_cache["spread"]  # type: ignore[return-value]
        from ..sources.fred import fetch_bundle
        from .curve import build_spread
        bundle = fetch_bundle()
        d3, v3 = bundle.get("3mo", ([], []))
        d10, v10 = bundle.get("10y", ([], []))
        sdates, spread = build_spread(d3, v3, d10, v10)     # 10y - 3m, daily
        rdates, rvals = bundle.get("recession", ([], []))
        models = build_models(sdates, spread, rdates, rvals)
        latest = next((v for v in reversed(spread) if v is not None), None)
        _model_cache["models"] = models
        _model_cache["spread"] = latest
        _model_cache["ts"] = time.time()
        return models, latest
