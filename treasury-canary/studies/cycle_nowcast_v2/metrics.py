"""Cycle nowcast v2 — metrics (pure numpy). Every function names the SPEC v1
section it implements so the verifier can map it:

  rmse                      v0 §1  population RMSE
  ex2020_mask               v1 §1  ex-2020 = drop targets 2020-01..2020-12,
                                   concatenate (gap closed) for RMSE, DM, percentiles
  label3 / phase_accuracy   v0 §1  3-phase labels; nowcast label == realized label
  transitions / transition_accuracy  v0 §1 A5: realized label(M) != label(M-1); 114/75 on F1
  directional_accuracy      v1 §1 (A8, F07): sign(yhat - COIN_real(M-1)) ==
                                   sign(COIN_real(M) - COIN_real(M-1)); ties wrong; n reported
  dm_test                   v1 §1 (F08): d = e_cand^2 - e_base^2, NW-6 Bartlett (1 - j/7),
                                   no small-sample correction; two-sided primary |t| >= 1.645
                                   with the required sign; one-sided kill t >= 1.282
  onset_table               v0 §1 A6: window [onset-6, onset+12], first sub -0.75 month,
                                   calendar advantage (m_c - m_n) + 1; missed if none
  false_alarms              v0 §3: nowcast < -0.75 with no realized < -0.75 within +/-3 months
  loyo_ratio                v1 §8: leave-one-calendar-year-out min/max of a ratio, with the year
  band_percentiles / expanding_band   v1 §2.2 (F03, DT-19): p10/p50/p90 of e = realized -
                                   completed; expanding (errors dated before the point)
  pattern_error_table       v1 §2.2: error distribution per bridged pattern on a mask
"""
from __future__ import annotations

import math

import numpy as np

COIN_RECESSION = -0.75
NW_LAG = 6
DM_TWO_SIDED_10PCT = 1.645
DM_ONE_SIDED_10PCT = 1.282


def _f(x) -> np.ndarray:
    return np.asarray(x, float)


def _finite(*arrs) -> np.ndarray:
    m = np.ones(len(arrs[0]), bool)
    for a in arrs:
        m &= np.isfinite(_f(a))
    return m


# ----------------------------------------------------------------------------
def rmse(e, mask=None) -> float:
    """Population RMSE sqrt(mean(e^2)) over finite entries (and mask)."""
    e = _f(e)
    m = np.isfinite(e) if mask is None else (np.isfinite(e) & np.asarray(mask, bool))
    if not m.any():
        return float("nan")
    return float(math.sqrt(np.mean(e[m] ** 2)))


def years_of(months) -> np.ndarray:
    return np.array([int(m[:4]) for m in months])


def ex2020_mask(months) -> np.ndarray:
    """True for every target not dated 2020-xx (v1 §1: the 12 rows of 2020 are
    dropped and the remaining series concatenated)."""
    return np.array([not str(m).startswith("2020") for m in months], bool)


def since_mask(months, start: str) -> np.ndarray:
    return np.array([str(m) >= start for m in months], bool)


# ----------------------------------------------------------------------------
def label3(x):
    if x is None or not np.isfinite(x):
        return None
    return "C" if x < COIN_RECESSION else "S" if x < 0 else "E"


def labels3(arr) -> list:
    return [label3(v) for v in _f(arr)]


def phase_accuracy(yhat, y, mask=None) -> dict:
    """share of targets with label3(yhat) == label3(y); n reported."""
    yhat, y = _f(yhat), _f(y)
    m = _finite(yhat, y) if mask is None else (_finite(yhat, y) & np.asarray(mask, bool))
    lh, ly = labels3(yhat[m]), labels3(y[m])
    hits = sum(a == b for a, b in zip(lh, ly))
    return {"accuracy_pct": 100.0 * hits / len(lh) if lh else float("nan"), "hits": hits, "n": len(lh)}


def transitions(y, y_prev, mask=None) -> np.ndarray:
    """realized transition at M: label3(COIN(M)) != label3(COIN(M-1))."""
    y, y_prev = _f(y), _f(y_prev)
    tr = np.array([a != b and a is not None and b is not None
                   for a, b in zip(labels3(y), labels3(y_prev))], bool)
    if mask is not None:
        tr &= np.asarray(mask, bool)
    return tr


def transition_accuracy(yhat, y, y_prev, mask=None) -> dict:
    """among realized transitions, share where label3(yhat) == label3(y)."""
    tr = transitions(y, y_prev, mask)
    yhat, y = _f(yhat), _f(y)
    ok = tr & _finite(yhat, y)
    lh, ly = labels3(yhat[ok]), labels3(y[ok])
    hits = sum(a == b for a, b in zip(lh, ly))
    n = int(tr.sum())
    return {"hits": hits, "n_transitions": n, "n_scored": int(ok.sum()),
            "accuracy_pct": 100.0 * hits / n if n else float("nan")}


def transition_months(months, y, y_prev, mask=None) -> list:
    tr = transitions(y, y_prev, mask)
    return [m for m, t in zip(months, tr) if t]


def directional_accuracy(yhat, y, y_prev_real, mask=None) -> dict:
    """v1 §1 (A8/F07): sign(yhat - COIN_real(M-1)) == sign(COIN_real(M) - COIN_real(M-1)),
    realized COIN(M-1) on BOTH sides; a zero on either side is a tie and counts
    as wrong; n = finite rows."""
    yhat, y, p = _f(yhat), _f(y), _f(y_prev_real)
    m = _finite(yhat, y, p) if mask is None else (_finite(yhat, y, p) & np.asarray(mask, bool))
    pred = np.sign(yhat[m] - p[m])
    real = np.sign(y[m] - p[m])
    hit = (pred == real) & (pred != 0) & (real != 0)
    ties = int(((pred == 0) | (real == 0)).sum())
    n = int(m.sum())
    return {"accuracy_pct": 100.0 * hit.sum() / n if n else float("nan"), "hits": int(hit.sum()),
            "ties": ties, "n": n}


# ----------------------------------------------------------------------------
def _phi(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def dm_test(e_cand, e_base, lag: int = NW_LAG, mask=None) -> dict:
    """Diebold-Mariano (v1 §1 F08): d_t = e_cand^2 - e_base^2 over finite rows
    (mask applied first, then concatenated — the ex-2020 convention), DM =
    mean(d) / sqrt(S/n) with S = gamma_0 + 2 sum_{j=1..lag} (1 - j/(lag+1)) gamma_j,
    gamma_j = (1/n) sum u_t u_{t-j}, u = d - mean(d). No small-sample correction.
    negative = candidate better. Returns t, n, mean_d, se, p-values and the two
    pre-registered verdicts: primary (two-sided |t| >= 1.645 with t < 0) and
    kill (one-sided t >= 1.282, H1 mean d > 0)."""
    e1, e0 = _f(e_cand), _f(e_base)
    m = _finite(e1, e0) if mask is None else (_finite(e1, e0) & np.asarray(mask, bool))
    d = e1[m] ** 2 - e0[m] ** 2
    n = len(d)
    if n < lag + 2:
        return {"t": float("nan"), "n": n}
    dbar = d.mean()
    u = d - dbar
    s = float(u @ u) / n
    for j in range(1, lag + 1):
        s += 2.0 * (1.0 - j / (lag + 1.0)) * float(u[j:] @ u[:-j]) / n
    se = math.sqrt(s / n) if s > 0 else float("nan")
    t = dbar / se if se and np.isfinite(se) and se > 0 else float("nan")
    return {"t": float(t), "n": n, "mean_d": float(dbar), "se": float(se), "lag": lag,
            "kernel": "Bartlett 1-j/(lag+1)",
            "p_two_sided": float(2.0 * (1.0 - _phi(abs(t)))) if np.isfinite(t) else float("nan"),
            "p_one_sided_cand_worse": float(1.0 - _phi(t)) if np.isfinite(t) else float("nan"),
            "primary_pass_cand_better": bool(np.isfinite(t) and t <= -DM_TWO_SIDED_10PCT),
            "kill_cand_worse": bool(np.isfinite(t) and t >= DM_ONE_SIDED_10PCT)}


# ----------------------------------------------------------------------------
def _first_below(months, values, lo: str, hi: str, thr: float):
    for m, v in zip(months, values):
        if lo <= m <= hi and v is not None and np.isfinite(v) and v < thr:
            return m
    return None


def _madd(m: str, k: int) -> str:
    i = int(m[:4]) * 12 + int(m[5:7]) - 1 + k
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def _mdiff(a: str, b: str) -> int:
    return (int(a[:4]) - int(b[:4])) * 12 + int(a[5:7]) - int(b[5:7])


def onset_table(months, realized, nowcast, onsets, pre: int = 6, post: int = 12,
                thr: float = COIN_RECESSION) -> dict:
    """v0 §1 A6: for each NBER onset, m_c = first month in [onset-pre, onset+post]
    with realized < thr; m_n = first month in the same window with nowcast < thr;
    calendar advantage = (m_c - m_n) + 1 months (the nowcast for m_n is in hand
    at the start of m_n+1; the realized m_c prints ~1 month later). Classes:
    earlier (adv >= 1), tie (0), later (<= -1), missed (no m_n)."""
    rows = []
    summary = {"earlier": 0, "tie": 0, "later": 0, "missed": 0}
    for on in onsets:
        lo, hi = _madd(on, -pre), _madd(on, post)
        mc = _first_below(months, realized, lo, hi, thr)
        mn = _first_below(months, nowcast, lo, hi, thr)
        if mc is None:
            adv, cls = None, "no_realized_cross"
        elif mn is None:
            adv, cls = None, "missed"
            summary["missed"] += 1
        else:
            adv = _mdiff(mc, mn) + 1
            cls = "earlier" if adv >= 1 else "tie" if adv == 0 else "later"
            summary[cls] += 1
        rows.append({"onset": on, "realized_cross": mc, "nowcast_cross": mn,
                     "calendar_advantage_months": adv, "class": cls})
    return {"rows": rows, "summary": summary,
            "realized_cross_months": [r["realized_cross"] for r in rows],
            "nowcast_cross_months": [r["nowcast_cross"] for r in rows],
            "window": [-pre, post], "threshold": thr}


def false_alarms(months, realized, nowcast, within: int = 3, thr: float = COIN_RECESSION) -> list:
    """v0 §3: months where nowcast < thr and no realized < thr within +/- `within`
    CALENDAR months (the window is resolved by month arithmetic, not by list
    position, so a gap-closed ex-2020 or windowed month list is handled)."""
    r = _f(realized)
    low = [j for j in range(len(months)) if np.isfinite(r[j]) and r[j] < thr]
    out = []
    for i, m in enumerate(months):
        v = nowcast[i]
        if v is None or not np.isfinite(v) or v >= thr:
            continue
        if not any(abs(_mdiff(months[j], m)) <= within for j in low):
            out.append(m)
    return out


# ----------------------------------------------------------------------------
def loyo_ratio(e_cand, e_base, months, mask=None) -> dict:
    """v1 §8: RMSE ratio cand/base dropping one calendar year at a time;
    returns the full ratio, min/max with the year that produces each."""
    e1, e0 = _f(e_cand), _f(e_base)
    yrs = years_of(months)
    base_mask = _finite(e1, e0) if mask is None else (_finite(e1, e0) & np.asarray(mask, bool))
    full = rmse(e1, base_mask) / rmse(e0, base_mask)
    out = {}
    for Y in sorted(set(yrs[base_mask])):
        mk = base_mask & (yrs != Y)
        out[int(Y)] = rmse(e1, mk) / rmse(e0, mk)
    ymin = min(out, key=out.get)
    ymax = max(out, key=out.get)
    return {"ratio": float(full), "min": float(out[ymin]), "min_drop_year": ymin,
            "max": float(out[ymax]), "max_drop_year": ymax, "by_year": out}


# ----------------------------------------------------------------------------
def band_percentiles(e, qs=(10, 50, 90), mask=None) -> dict:
    """p10/p50/p90 (numpy 'linear' interpolation), bias, RMSE and n of the
    completion error e = realized - completed (v1 §2.2)."""
    e = _f(e)
    m = np.isfinite(e) if mask is None else (np.isfinite(e) & np.asarray(mask, bool))
    v = e[m]
    if len(v) == 0:
        return {"n": 0}
    out = {f"p{q}": float(np.percentile(v, q, method="linear")) for q in qs}
    out.update({"n": int(len(v)), "bias": float(v.mean()), "rmse": float(math.sqrt(np.mean(v ** 2)))})
    return out


def expanding_band(months, e, at_month: str, qs=(10, 90), mask=None, min_n: int = 24) -> dict | None:
    """v1 §2.2 / DT-19: percentiles of errors dated BEFORE at_month (expanding);
    None if fewer than min_n errors. The live band uses all history."""
    e = _f(e)
    sel = np.array([str(m) < at_month for m in months], bool) & np.isfinite(e)
    if mask is not None:
        sel &= np.asarray(mask, bool)
    if sel.sum() < min_n:
        return None
    return band_percentiles(e, qs, sel)


def pattern_error_table(months, realized, completed, pattern_keys, mask=None,
                        require_bridged: bool = True) -> dict:
    """v1 §2.2: group e = realized - completed by the bridged-pattern key and
    return band_percentiles per key over the mask (PRIMARY: 1990-01+ ex-2020
    where >= 1 member is bridged)."""
    r, c = _f(realized), _f(completed)
    e = r - c
    n = len(months)
    mk = np.ones(n, bool) if mask is None else np.asarray(mask, bool)
    out = {}
    for key in sorted(set(pattern_keys)):
        if require_bridged and key.startswith("bridged[]"):
            continue
        sel = mk & np.array([k == key for k in pattern_keys], bool)
        out[key] = band_percentiles(e, (10, 50, 90), sel)
    return out


def pct_change(a: float, b: float) -> float:
    """100 * (a / b - 1): RMSE 'vs persistence' convention (negative = better)."""
    return float(100.0 * (a / b - 1.0))
