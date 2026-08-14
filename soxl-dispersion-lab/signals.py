#!/usr/bin/env python3
"""Regime signals and gates (Step 4). All are strictly causal.

Every series here is computed from data available STRICTLY BEFORE the day it
is used: `_shift1` pushes each signal forward one day so a gate evaluated at
the close of day t can only have seen day t-1. Signals that peek are the
single easiest way to manufacture a fake gate, so the shift is applied
centrally and tested in tests/test_gates.py rather than left to each caller.
"""
import math

import numpy as np

from datalib import TRADING_DAYS, build_basket, month_ends


def _shift1(a):
    out = np.full(len(a), np.nan)
    out[1:] = a[:-1]
    return out


def sma(px, w):
    out = np.full(len(px), np.nan)
    c = np.cumsum(np.nan_to_num(px))
    for i in range(w, len(px)):
        seg = px[i - w:i]
        if np.isfinite(seg).all():
            out[i] = seg.mean()
    return out


def realized_vol(r, w):
    out = np.full(len(r), np.nan)
    for i in range(w, len(r)):
        seg = r[i - w:i]
        if np.isfinite(seg).all():
            out[i] = seg.std(ddof=1) * math.sqrt(TRADING_DAYS)
    return out


def rolling_pctile(x, w):
    """Percentile rank of x[i] within the trailing w observations."""
    out = np.full(len(x), np.nan)
    for i in range(w, len(x)):
        seg = x[i - w:i]
        seg = seg[np.isfinite(seg)]
        if len(seg) > w // 2 and np.isfinite(x[i]):
            out[i] = (seg < x[i]).mean()
    return out


def drawdown(nav):
    return nav / np.maximum.accumulate(nav) - 1.0


class Signals:
    """Precomputed, causally-shifted signal panel over the full calendar."""

    def __init__(self, data):
        self.d = data
        px = data.px["SOXX"]
        r = data.ret("SOXX")
        self.px_soxx = px
        self.trend100 = _shift1(px - sma(px, 100))
        self.trend200 = _shift1(px - sma(px, 200))
        self.vol20 = _shift1(realized_vol(r, 20))
        self.vol20_pct = _shift1(rolling_pctile(realized_vol(r, 20), 252))
        vix = data.vix.get("^VIX")
        vix3 = data.vix.get("^VIX3M")
        if vix is not None and vix3 is not None:
            with np.errstate(invalid="ignore", divide="ignore"):
                ts = vix / vix3
            self.vix_ts = _shift1(ts)          # >1 = inverted = stress
            self.vix_pct = _shift1(rolling_pctile(vix, 252))
        else:
            self.vix_ts = np.full(len(px), np.nan)
            self.vix_pct = np.full(len(px), np.nan)
        # semis vs market: SOX/SPX ratio momentum (slow macro overlay)
        ratio = px / data.px["SPY"]
        self.ratio_mom = _shift1(_mom(ratio, 126))
        self.xsec_disp = _shift1(_dispersion_series(data))
        self.xsec_disp_pct = _shift1(rolling_pctile(_dispersion_series(data), 252))


def _mom(x, w):
    out = np.full(len(x), np.nan)
    for i in range(w, len(x)):
        if np.isfinite(x[i]) and np.isfinite(x[i - w]) and x[i - w] > 0:
            out[i] = x[i] / x[i - w] - 1.0
    return out


def _dispersion_series(data, window=21, n_names=30):
    """Cross-sectional sd of trailing 21d constituent returns, monthly, ffilled."""
    out = np.full(len(data.dates), np.nan)
    for me in month_ends(data.dates):
        w = build_basket(data, me, n_names, "cap")
        rs = []
        for t in w:
            p = data.px[t]
            if me - window < 0 or np.isnan(p[me]) or np.isnan(p[me - window]):
                continue
            rs.append(p[me] / p[me - window] - 1.0)
        if len(rs) > 5:
            out[me] = float(np.std(rs, ddof=1))
    last = np.nan
    for i in range(len(out)):
        if np.isfinite(out[i]):
            last = out[i]
        else:
            out[i] = last
    return out


# --------------------------------------------------------------------------
# gate factories -> each returns gate_fn(data, i) -> scale in [0, 1]
# --------------------------------------------------------------------------
def gate_trend(sig, window=200, invert=True):
    """Run the book only when SOXX is BELOW its moving average (invert=True).

    The decomposition showed the short leg's entire positive carry lives
    below the 200dma, so this is the theory-motivated direction. The
    opposite direction is also tested, to show the gate is not free.
    """
    tr = sig.trend200 if window == 200 else sig.trend100

    def fn(data, i):
        v = tr[i]
        if not np.isfinite(v):
            return 1.0
        below = v < 0
        return 1.0 if (below if invert else not below) else 0.0
    return fn


def gate_vol(sig, pct=0.5):
    """Run only when 20d realized vol is above its trailing 1y `pct` quantile."""
    def fn(data, i):
        v = sig.vol20_pct[i]
        if not np.isfinite(v):
            return 1.0
        return 1.0 if v >= pct else 0.0
    return fn


def gate_vix_ts(sig, thresh=1.0):
    """Run when the VIX term structure is inverted (VIX/VIX3M >= thresh)."""
    def fn(data, i):
        v = sig.vix_ts[i]
        if not np.isfinite(v):
            return 1.0
        return 1.0 if v >= thresh else 0.0
    return fn


def gate_dispersion(sig, pct=0.5):
    """Run only when cross-sectional dispersion is in the upper `pct`."""
    def fn(data, i):
        v = sig.xsec_disp_pct[i]
        if not np.isfinite(v):
            return 1.0
        return 1.0 if v >= pct else 0.0
    return fn


def gate_macro(sig, thresh=0.0):
    """Semis-vs-market ratio momentum below threshold = cycle rolling over."""
    def fn(data, i):
        v = sig.ratio_mom[i]
        if not np.isfinite(v):
            return 1.0
        return 1.0 if v < thresh else 0.0
    return fn


def gate_all(*gates):
    def fn(data, i):
        s = 1.0
        for g in gates:
            s *= g(data, i)
        return s
    return fn


def gate_any(*gates):
    def fn(data, i):
        return 1.0 if any(g(data, i) > 0 for g in gates) else 0.0
    return fn
