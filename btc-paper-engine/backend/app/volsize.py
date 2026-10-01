"""Volatility-targeted entry size: the down-only form of RESEARCH_SHARPE.md H1.

For an entry whose SIGNAL closed on bar s (pullback: limit fills on s+1;
donchian: market at s+1's open), the size multiplier is

    m = clip(sigma_ref / sigma_now, 0.5, 1.0)

    sigma_now = stdev (ddof 0) of the 180 4h log returns ending at bar s
    sigma_ref = median of sigma_now over the 2,190 bars ending at bar s

i.e. the backtest's `weight_fn(T = entry bar)` using bars through T-1. It only
ever SHRINKS a trade (calm or normal market -> 1.0, today's size; turbulent
-> down to half), so it cannot push the book past any cap or rail.

Computed on a dense 4h time grid. A missing bar makes the returns touching it
NaN; a window needs >= 90% valid values or m falls back to 1.0 - today's size,
the status quo the executor already trades - with basis "insufficient_history"
so the fallback is visible rather than silent."""
from __future__ import annotations

import math

import numpy as np

BAR = 14_400
VOL_WIN = 180
VOL_REF = 2_190
M_LO, M_HI = 0.5, 1.0
MIN_VALID = 0.9
NEED_BARS = VOL_WIN + VOL_REF          # bars of history behind the signal bar


def _rolling_std(r: np.ndarray, win: int) -> np.ndarray:
    """Population stdev of the `win` values ending at each index (NaN-aware;
    NaN where fewer than MIN_VALID * win are valid)."""
    ok = ~np.isnan(r)
    x = np.where(ok, r, 0.0)
    c1 = np.concatenate([[0.0], np.cumsum(x)])
    c2 = np.concatenate([[0.0], np.cumsum(x * x)])
    cn = np.concatenate([[0], np.cumsum(ok)])
    out = np.full(len(r), np.nan)
    for j in range(win - 1, len(r)):
        n = cn[j + 1] - cn[j + 1 - win]
        if n < MIN_VALID * win:
            continue
        m = (c1[j + 1] - c1[j + 1 - win]) / n
        v = (c2[j + 1] - c2[j + 1 - win]) / n - m * m
        out[j] = math.sqrt(max(v, 0.0))
    return out


def size_mult(closes: dict[int, float], signal_ts: int) -> dict:
    """{'m', 'basis', 'sigma_now', 'sigma_ref'} for an entry signalled on the
    bar opening at `signal_ts`. Uses only closes at or before that bar."""
    if signal_ts is None or signal_ts not in closes:
        return {"m": 1.0, "basis": "insufficient_history",
                "sigma_now": None, "sigma_ref": None}
    t0 = signal_ts - (NEED_BARS - 1) * BAR
    grid = np.arange(t0, signal_ts + BAR, BAR, dtype=np.int64)
    px = np.array([closes.get(int(t), np.nan) for t in grid], dtype=float)
    lr = np.full(len(px), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        lr[1:] = np.log(px[1:] / px[:-1])
    s_now = _rolling_std(lr, VOL_WIN)
    tail = s_now[-VOL_REF:]
    valid = tail[~np.isnan(tail)]
    now = s_now[-1]
    if now != now or now <= 0 or len(valid) < MIN_VALID * VOL_REF:
        return {"m": 1.0, "basis": "insufficient_history",
                "sigma_now": None if now != now else float(now),
                "sigma_ref": None}
    ref = float(np.median(valid))
    m = min(M_HI, max(M_LO, ref / now))
    return {"m": round(float(m), 4), "basis": "vol_target",
            "sigma_now": float(now), "sigma_ref": ref}
