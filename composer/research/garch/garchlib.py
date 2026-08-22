"""GARCH(1,1) with STRICT real-time (expanding-window) refitting.

Fitted by MLE on Gaussian log-likelihood, Nelder-Mead (hand-rolled to avoid
scipy dependency issues). Every forecast at time t uses ONLY data through
t-1 -- the house methodology standard (results.md 19b: real-time labels only).
"""
import numpy as np, json


def _nll(params, r):
    omega, alpha, beta = params
    if omega <= 1e-12 or alpha < 0 or beta < 0 or alpha + beta >= 0.9999:
        return 1e10
    n = len(r)
    h = np.empty(n)
    h[0] = np.var(r)
    for i in range(1, n):
        h[i] = omega + alpha * r[i-1]**2 + beta * h[i-1]
        if h[i] <= 1e-14:
            return 1e10
    return 0.5 * np.sum(np.log(h) + r**2 / h)


def _nelder_mead(f, x0, args=(), iters=400, step=0.35):
    n = len(x0)
    pts = [np.array(x0, float)]
    for i in range(n):
        p = np.array(x0, float)
        p[i] = p[i] * (1 + step) + 1e-8
        pts.append(p)
    pts = np.array(pts)
    vals = np.array([f(p, *args) for p in pts])
    for _ in range(iters):
        o = np.argsort(vals); pts, vals = pts[o], vals[o]
        if abs(vals[-1] - vals[0]) < 1e-9:
            break
        cen = pts[:-1].mean(axis=0)
        xr = cen + (cen - pts[-1]); fr = f(xr, *args)
        if fr < vals[0]:
            xe = cen + 2 * (cen - pts[-1]); fe = f(xe, *args)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = cen + 0.5 * (pts[-1] - cen); fc = f(xc, *args)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                pts[1:] = pts[0] + 0.5 * (pts[1:] - pts[0])
                vals[1:] = [f(p, *args) for p in pts[1:]]
    o = np.argsort(vals)
    return pts[o][0]


def fit(r):
    """MLE fit on a return array (demeaned inside)."""
    r = np.asarray(r, float)
    r = r - r.mean()
    v = np.var(r)
    best, bestf = None, 1e18
    for a0, b0 in ((0.08, 0.90), (0.05, 0.93), (0.15, 0.80)):
        x = _nelder_mead(_nll, [v * (1 - a0 - b0), a0, b0], args=(r,))
        fv = _nll(x, r)
        if fv < bestf:
            best, bestf = x, fv
    return best


def filter_h(params, r):
    """Conditional variance path h_t given params (h_t uses r up to t-1)."""
    omega, alpha, beta = params
    r = np.asarray(r, float); r = r - r.mean()
    n = len(r); h = np.empty(n); h[0] = np.var(r)
    for i in range(1, n):
        h[i] = omega + alpha * r[i-1]**2 + beta * h[i-1]
    return h


def realtime_sigma(r, warmup=750, refit_every=21):
    """1-step-ahead conditional vol forecast for each t, using ONLY r[:t].

    Returns array aligned to r; entries before `warmup` are NaN. Params are
    refit every `refit_every` observations on the expanding window; between
    refits the recursion is rolled forward with the last fitted params (this
    is what a live desk does, and it uses no future information).
    """
    r = np.asarray(r, float)
    n = len(r)
    out = np.full(n, np.nan)
    params = None
    h_prev = None
    mu = 0.0
    for t in range(warmup, n):
        if params is None or (t - warmup) % refit_every == 0:
            params = fit(r[:t])                    # data through t-1 only
            mu = r[:t].mean()
            h_path = filter_h(params, r[:t])
            h_prev = h_path[-1]
            e_prev = r[t-1] - mu
        omega, alpha, beta = params
        h_t = omega + alpha * e_prev**2 + beta * h_prev   # forecast for day t
        out[t] = np.sqrt(h_t * 252)
        h_prev, e_prev = h_t, r[t] - mu
    return out
