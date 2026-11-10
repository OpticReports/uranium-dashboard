"""Series and splits for the forecasting-foundation-model study.

Every constant here is FROZEN by RESEARCH_FORECAST_FM.md and derived from
the record rather than chosen: the horizon is the median holding period of
the reference pullback trades (32h = 8 bars of 4h), so the forecast covers
the period a position is actually exposed for.

THE TARGET IS STRICTLY FORWARD. Features at bar t use data up to and
including t; the target uses t+1..t+H and never t itself. That boundary is
the one thing in this file that a bug would silently turn into a spectacular
result.
"""
from __future__ import annotations

import csv
import os

import numpy as np

BAR_SECONDS = 4 * 3600
HORIZON_BARS = 8            # 32h median hold, from btc_pullback_trades_optimized
ATR_N = 14                  # what the live sizer uses today

# Chronological, fixed before any model was run. HOLDOUT is sealed: see
# split_masks(). Dates are bar-open UTC.
TRAIN_END = "2024-06-30"
VALIDATE_END = "2025-09-30"


def _ts(datestr: str) -> int:
    import datetime as dt
    d = dt.datetime.strptime(datestr, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())


def load_bars(path: str) -> dict:
    """4h OHLCV as float arrays, ascending by time. Refuses a file that is
    not strictly ordered - an out-of-order bar would make 'forward' mean
    nothing."""
    ts, o, h, l, c = [], [], [], [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            ts.append(int(row["ts_open_unix"]))
            o.append(float(row["open"]))
            h.append(float(row["high"]))
            l.append(float(row["low"]))
            c.append(float(row["close"]))
    a = {k: np.asarray(v, dtype=float) for k, v in
         (("open", o), ("high", h), ("low", l), ("close", c))}
    a["ts"] = np.asarray(ts, dtype=np.int64)
    if np.any(np.diff(a["ts"]) <= 0):
        raise ValueError("bars are not strictly increasing in time")
    return a


def log_returns(close: np.ndarray) -> np.ndarray:
    """r[t] = log(close[t]/close[t-1]); r[0] = nan, so index alignment with
    the bar arrays is preserved rather than shifted by one."""
    r = np.full(close.shape, np.nan)
    r[1:] = np.log(close[1:] / close[:-1])
    return r


def forward_realized_vol(close: np.ndarray, horizon: int = HORIZON_BARS
                         ) -> np.ndarray:
    """Per-bar realized volatility over the NEXT `horizon` bars.

    sigma[t] = std(r[t+1 .. t+horizon]). nan where the window runs off the
    end. Sample std (ddof=1): with 8 points the population estimator is
    biased low by ~6%, and a systematically low target would flatter every
    model equally but make the absolute numbers wrong."""
    r = log_returns(close)
    n = close.size
    out = np.full(n, np.nan)
    for t in range(n - horizon):
        w = r[t + 1:t + 1 + horizon]
        if not np.any(np.isnan(w)):
            out[t] = float(np.std(w, ddof=1))
    return out


def trailing_atr_frac(bars: dict, n: int = ATR_N) -> np.ndarray:
    """ATR(n)/close - the INCUMBENT risk estimate.

    This is what the live sizer uses right now: notional = equity * risk /
    (stop_atr * ATR/entry). It is a trailing estimate standing in for
    forward risk, which is exactly the substitution this study tests. It is
    therefore the baseline that matters; beating EWMA while losing to this
    would change nothing about how the book is sized.

    Wilder smoothing, matching app/indicators.py."""
    h, l, c = bars["high"], bars["low"], bars["close"]
    tr = np.full(c.shape, np.nan)
    tr[1:] = np.maximum.reduce([h[1:] - l[1:],
                                np.abs(h[1:] - c[:-1]),
                                np.abs(l[1:] - c[:-1])])
    atr = np.full(c.shape, np.nan)
    seed = np.nanmean(tr[1:n + 1])
    atr[n] = seed
    for i in range(n + 1, c.size):
        atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    return atr / c


def split_masks(ts: np.ndarray, unseal_holdout: bool = False) -> dict:
    """TRAIN / VALIDATE / HOLDOUT boolean masks.

    HOLDOUT IS SEALED. It comes back all-False unless explicitly unsealed,
    because a holdout you can reach by accident is a validation set with a
    grander name. RESEARCH_PROTOCOL.md section 8 allows it to be touched
    ONCE, after the earlier rules pass."""
    a, b = _ts(TRAIN_END), _ts(VALIDATE_END)
    train = ts <= a
    validate = (ts > a) & (ts <= b)
    holdout = ts > b
    if not unseal_holdout:
        holdout = np.zeros_like(holdout)
    return {"train": train, "validate": validate, "holdout": holdout}


def eval_index(mask: np.ndarray, valid: np.ndarray,
               horizon: int = HORIZON_BARS) -> np.ndarray:
    """Non-overlapping evaluation points, every `horizon` bars.

    CONSECUTIVE TARGETS OVERLAP: sigma[t] and sigma[t+1] share 7 of their 8
    returns, so scoring every bar would count almost the same observation
    eight times and make every difference look far more significant than it
    is. Stepping by the horizon gives independent windows at the cost of
    1/8th the sample."""
    idx = np.flatnonzero(mask & valid)
    if idx.size == 0:
        return idx
    return idx[::horizon]


def bars_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "..", "tests", "fixtures",
                        "bars_4h_btcusd.csv")
