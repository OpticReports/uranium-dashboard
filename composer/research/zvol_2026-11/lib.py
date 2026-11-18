"""Shared helpers for the ZVOL / volatility-harvester study (2026-11-18).
Everything is daily, close to close. 'tr' = total return (Yahoo adjusted close, distributions reinvested);
'px' = price return. END caps every series at the last complete session."""
import datetime as dt, json, math, os, random
import fetch_data as fd

END = "2026-11-17"            # last complete session when the study was run
ZVOL_START = "2023-04-19"


def load(t, cache):
    y = fd.yahoo(t, cache)
    y["rows"] = {d: v for d, v in y["rows"].items() if d <= END}
    y["divs"] = [x for x in y["divs"] if x[0] <= END]
    return y


def series(t, cache, field="adj"):
    r = load(t, cache)["rows"]
    return {d: (v[field] if v[field] is not None else v["close"]) for d, v in sorted(r.items())}


def rets(level):
    ds = sorted(level)
    return {ds[i]: level[ds[i]] / level[ds[i - 1]] - 1.0 for i in range(1, len(ds))}


def rsi(closes, n):
    """Wilder RSI on a list of closes; returns a list aligned with closes (None until n changes seen).
    Composer's relative-strength-index is Wilder-smoothed (shadow_runner reproduces Composer with it)."""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    g = l = 0.0
    for i in range(1, n + 1):
        ch = closes[i] - closes[i - 1]
        g += max(ch, 0.0); l += max(-ch, 0.0)
    g /= n; l /= n
    out[n] = 100.0 if l == 0 else 100.0 - 100.0 / (1.0 + g / l)
    for i in range(n + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        g = (g * (n - 1) + max(ch, 0.0)) / n
        l = (l * (n - 1) + max(-ch, 0.0)) / n
        out[i] = 100.0 if l == 0 else 100.0 - 100.0 / (1.0 + g / l)
    return out


# ---- VIX futures term structure -------------------------------------------------------------------
def vx_panel(cache, y0=2004, y1=2027):
    """[(expiry_date, {trade_date: settle})] for monthly contracts, sorted by expiry"""
    out = []
    for yy in range(y0, y1 + 1):
        for mm in range(1, 13):
            c = fd.vx_contract(yy, mm, cache)
            if c and c["settle"]:
                out.append((c["expiry"], {d: s for d, s in c["settle"].items() if d <= END}))
    out.sort(key=lambda x: x[0])
    return out


def curve_on(panel, d):
    """settles of the listed monthly contracts not yet expired on trade date d, nearest first:
    [(expiry, settle)]. A contract's last trade row is its expiry (final settlement) morning; the index
    is out of it before then, so contracts with expiry <= d are dropped."""
    return [(e, s[d]) for e, s in panel if e > d and d in s]


def midterm_index(panel):
    """Daily EXCESS return of the S&P 500 VIX Mid-Term Futures index (long 4th-7th month, rolling the 4th
    into the 7th evenly over each roll period) from Cboe settlements, plus the day's weights.
    Roll period: from the Tuesday before one monthly settlement (exclusive) to the Tuesday before the next.
    Returns {date: {"ret": r, "w": [w4, w5, w6, w7], "F": [F4..F7], "dr": days left, "dt": days in period}}"""
    exps = [e for e, _ in panel]
    tue = [(dt.date.fromisoformat(e) - dt.timedelta(days=1)).isoformat() for e in exps]   # roll dates
    days = sorted({d for _, s in panel for d in s})
    out, prev = {}, None
    for d in days:
        # the roll period containing d: (tue[i-1], tue[i]] -> front month = contract i
        i = next((k for k, t in enumerate(tue) if d <= t), None)
        if i is None or i == 0 or i + 6 >= len(panel):
            prev = None; continue
        period = [x for x in days if tue[i - 1] < x <= tue[i]]
        n = len(period); k = period.index(d) + 1 if d in period else None
        if k is None:
            prev = None; continue
        dr = n - k                                    # business days left in the roll period after today
        # contracts 4..7 counted from the front month i (1st = i)
        c = [panel[i + j] for j in (3, 4, 5, 6)]
        if any(d not in s for _, s in c):
            prev = None; continue
        F = [s[d] for _, s in c]
        w = [dr / n / 3.0, 1 / 3.0, 1 / 3.0, (n - dr) / n / 3.0]     # weights AFTER today's roll
        if prev is not None and prev["ids"] == [e for e, _ in c]:
            num = sum(pw * s[d] for pw, (_, s) in zip(prev["w"], c))
            den = sum(pw * s[prev["d"]] for pw, (_, s) in zip(prev["w"], c))
            r = num / den - 1.0
        elif prev is not None:
            # first day of a new roll period: yesterday's weights were [0, 1/3, 1/3, 1/3] on old 4..7 =
            # today's contracts shifted by one (old 5,6,7 = new 4,5,6)
            cc = c[:3]
            if all(prev["d"] in s for _, s in cc):
                r = sum(s[d] for _, s in cc) / sum(s[prev["d"]] for _, s in cc) - 1.0
            else:
                r = None
        else:
            r = None
        if r is not None:
            out[d] = {"ret": r, "w": w, "F": F, "dr": dr, "dt": n}
        prev = {"d": d, "w": w, "ids": [e for e, _ in c]}
    return out


def const_maturity(panel, d, months):
    """VIX futures level at a constant maturity of `months` (30-day months) by linear interpolation
    between the two listed contracts around it; None outside the listed range"""
    cur = curve_on(panel, d)
    if len(cur) < 2:
        return None
    t = months * 30.0
    x = [((dt.date.fromisoformat(e) - dt.date.fromisoformat(d)).days, s) for e, s in cur]
    for (a, fa), (b, fb) in zip(x, x[1:]):
        if a <= t <= b:
            return fa + (fb - fa) * (t - a) / (b - a)
    return None


# ---- statistics -----------------------------------------------------------------------------------
def stats(r, rf=None):
    """r: list of daily returns. CAGR, vol, Sharpe (excess over rf list if given), maxDD, CVaR5, worst day"""
    n = len(r)
    if n < 2:
        return {}
    lvl, peak, mdd = 1.0, 1.0, 0.0
    for x in r:
        lvl *= 1 + x; peak = max(peak, lvl); mdd = max(mdd, 1 - lvl / peak)
    ex = [a - b for a, b in zip(r, rf)] if rf else r
    m = sum(ex) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in ex) / (n - 1))
    srt = sorted(r); k = max(1, int(0.05 * n))
    return {"n": n, "cagr": lvl ** (252.0 / n) - 1, "total": lvl - 1, "vol": math.sqrt(252) * math.sqrt(sum((x - sum(r) / n) ** 2 for x in r) / (n - 1)),
            "sharpe": (m / sd * math.sqrt(252)) if sd > 0 else None, "maxdd": mdd, "cvar5": sum(srt[:k]) / k, "worst": srt[0]}


def stationary_bootstrap_idx(n, mean_block, rng):
    """Politis-Romano stationary bootstrap index path of length n"""
    out, i = [], rng.randrange(n)
    p = 1.0 / mean_block
    for _ in range(n):
        out.append(i)
        i = rng.randrange(n) if rng.random() < p else (i + 1) % n
    return out


def corr(a, b):
    n = len(a); ma = sum(a) / n; mb = sum(b) / n
    va = sum((x - ma) ** 2 for x in a); vb = sum((y - mb) ** 2 for y in b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb) if va > 0 and vb > 0 else None


def ols(y, X):
    """OLS with intercept; X: list of columns. Returns (betas incl. intercept, residuals). numpy-free."""
    import numpy as np
    A = np.column_stack([np.ones(len(y))] + [np.asarray(c, float) for c in X])
    b, *_ = np.linalg.lstsq(A, np.asarray(y, float), rcond=None)
    return b, np.asarray(y, float) - A @ b


def nw_t(y, x, lags):
    """slope, Newey-West t-stat and R2 of y on a single regressor x (with intercept)"""
    import numpy as np
    y = np.asarray(y, float); x = np.asarray(x, float)
    A = np.column_stack([np.ones(len(y)), x])
    b, *_ = np.linalg.lstsq(A, y, rcond=None)
    e = y - A @ b
    XtXi = np.linalg.inv(A.T @ A)
    S = (A * e[:, None]).T @ (A * e[:, None])
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        G = (A[L:] * e[L:, None]).T @ (A[:-L] * e[:-L, None])
        S += w * (G + G.T)
    V = XtXi @ S @ XtXi
    r2 = 1 - (e @ e) / ((y - y.mean()) @ (y - y.mean()))
    return b[1], b[1] / math.sqrt(V[1, 1]), r2
