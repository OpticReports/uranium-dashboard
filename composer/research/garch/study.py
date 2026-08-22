"""GARCH vol-regime variants on the VIX Harvester.

METHODOLOGY (house standard, results.md 19b):
  * GARCH refit on a rolling 10y window, monthly, 1-step-ahead forecast --
    every sigma_t uses only data through t-1.
  * All regime thresholds are EXPANDING-WINDOW quantiles (real-time), never
    full-sample -- a full-sample median is lookahead and flatters every gate.
  * Variants act ONLY on the ZVOL (short-vol) leg; VXZ/PULS legs untouched.
"""
import json, numpy as np, sys
sys.path.insert(0, "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/garch")
import harvsim as H

SC = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad"


def expanding_quantile(x, q, minobs=252):
    """Real-time quantile: value at t uses only x[:t]."""
    out = np.full(len(x), np.nan)
    for t in range(minobs, len(x)):
        seg = x[:t][~np.isnan(x[:t])]
        if len(seg) >= minobs:
            out[t] = np.quantile(seg, q)
    return out


def stats(r):
    x = np.array([v for v in r if not np.isnan(v)])
    if len(x) < 30:
        return dict(cagr=np.nan, dd=np.nan, sharpe=np.nan, sortino=np.nan)
    c = np.cumprod(1 + x)
    yrs = len(x) / 252
    peak = np.maximum.accumulate(c)
    dn = x[x < 0]
    return dict(cagr=c[-1] ** (1 / yrs) - 1,
                dd=float(np.max(1 - c / peak)),
                sharpe=float(np.mean(x) / np.std(x) * np.sqrt(252)),
                sortino=float(np.mean(x) / np.std(dn) * np.sqrt(252)) if len(dn) else np.nan,
                vol=float(np.std(x) * np.sqrt(252)))


def build(dates, px, sigma):
    """Return {variant_name: daily_return_array} for all tested designs."""
    n = len(dates)
    q25 = expanding_quantile(sigma, 0.25)
    q50 = expanding_quantile(sigma, 0.50)
    q75 = expanding_quantile(sigma, 0.75)
    q33 = expanding_quantile(sigma, 1/3)
    q67 = expanding_quantile(sigma, 2/3)
    dsig = np.full(n, np.nan)
    dsig[1:] = sigma[1:] / sigma[:-1] - 1

    def ok(i, arr):                      # guard: unknown regime -> no change
        return not (np.isnan(sigma[i]) or np.isnan(arr[i]))

    V = {}
    V["BASELINE"] = H.simulate(dates, px)[0]
    # --- gates ---
    V["G1 calm-only"]     = H.simulate(dates, px, gate=lambda i: not ok(i, q50) or sigma[i] < q50[i])[0]
    V["G2 storm-only"]    = H.simulate(dates, px, gate=lambda i: not ok(i, q50) or sigma[i] > q50[i])[0]
    V["G3 spike-exit"]    = H.simulate(dates, px, gate=lambda i: np.isnan(dsig[i]) or dsig[i] < 0.20)[0]
    V["G4 tail-avoid"]    = H.simulate(dates, px, gate=lambda i: not ok(i, q75) or sigma[i] < q75[i])[0]
    # --- sizers ---
    def inv_vol(i, target=0.15, lo=0.5, hi=2.0):
        if np.isnan(sigma[i]) or sigma[i] <= 0:
            return 1.0
        return float(np.clip(target / sigma[i], lo, hi))
    V["S1 inverse-vol"]   = H.simulate(dates, px, sizer=inv_vol)[0]
    V["S2 size-up calm"]  = H.simulate(dates, px,
        sizer=lambda i: 1.5 if ok(i, q33) and sigma[i] < q33[i] else 1.0)[0]
    V["S3 up-calm/down-storm"] = H.simulate(dates, px,
        sizer=lambda i: 1.5 if ok(i, q33) and sigma[i] < q33[i]
        else (0.5 if ok(i, q67) and sigma[i] > q67[i] else 1.0))[0]
    V["S4 aggressive 2x calm"] = H.simulate(dates, px,
        sizer=lambda i: 2.0 if ok(i, q25) and sigma[i] < q25[i] else 1.0)[0]
    return V
