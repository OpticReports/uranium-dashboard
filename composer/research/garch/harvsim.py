"""Exact replica of 'VIX Harvester + HYG Credit Guard'.

Tree (from /score): equal weight over 9 sub-strategies, SPY-RSI windows 2..10.
Each sub-strategy:
    if RSI(SPY, w) < 25:        -> if RSI(UVXY,14) > 70: PULS else ZVOL
    elif RSI(SPY, w) > 80:      -> VXZ
    else:                       -> PULS
Decisions use close(t-1); the position earns the t-1 -> t return.
"""
import numpy as np


def rsi(prices, window):
    """Wilder RSI, matching Composer's convention."""
    p = np.asarray(prices, float)
    d = np.diff(p)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    n = len(p)
    out = np.full(n, np.nan)
    if n <= window:
        return out
    ag = gain[:window].mean(); al = loss[:window].mean()
    out[window] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(window, len(d)):
        ag = (ag * (window - 1) + gain[i]) / window
        al = (al * (window - 1) + loss[i]) / window
        out[i + 1] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def simulate(dates, px, sizer=None, gate=None):
    """px: dict ticker -> np.array aligned to dates.

    sizer(t) -> float in [0, inf): multiplier on the ZVOL (short-vol) leg;
                the remainder goes to PULS. 1.0 = unchanged.
    gate(t)  -> bool: if False, ZVOL legs are routed to PULS that day.
    Returns (daily_returns, weights_history) aligned to dates[1:].
    """
    spy, uvxy = px["SPY"], px["UVXY"]
    rsis = {w: rsi(spy, w) for w in range(2, 11)}
    ruvxy = rsi(uvxy, 14)
    rets = {t: np.concatenate([[np.nan], np.diff(a) / a[:-1]]) for t, a in px.items()}

    n = len(dates)
    out = np.full(n, np.nan)
    hist = []
    for t in range(1, n):
        i = t - 1                                   # decision uses close(t-1)
        w = {"ZVOL": 0.0, "VXZ": 0.0, "PULS": 0.0}
        for win in range(2, 11):
            rs = rsis[win][i]
            if np.isnan(rs):
                w["PULS"] += 1 / 9
                continue
            if rs < 25:
                if not np.isnan(ruvxy[i]) and ruvxy[i] > 70:
                    w["PULS"] += 1 / 9
                else:
                    w["ZVOL"] += 1 / 9
            elif rs > 80:
                w["VXZ"] += 1 / 9
            else:
                w["PULS"] += 1 / 9
        if gate is not None and not gate(i):         # gate: ZVOL -> PULS
            w["PULS"] += w["ZVOL"]; w["ZVOL"] = 0.0
        if sizer is not None and w["ZVOL"] > 0:
            m = sizer(i)
            z = w["ZVOL"] * m
            spare = w["ZVOL"] - z                    # +/- goes to/from PULS
            w["ZVOL"], w["PULS"] = z, w["PULS"] + spare
        r = 0.0
        for tk, wt in w.items():
            if wt:
                rt = rets[tk][t]
                r += wt * (0.0 if np.isnan(rt) else rt)
        out[t] = r
        hist.append(dict(w))
    return out, hist
