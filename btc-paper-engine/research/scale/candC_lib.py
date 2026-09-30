"""CANDIDATE C shared harness. Written ONCE and imported by every candC_*
script (cost-discipline rule: read once, pass down).

The bootstrap / drawdown machinery is LIFTED VERBATIM from blend_corr.py,
where it was already validated against app.engine.kelly's own
stationary_bootstrap_idx (P(idx[i+1]==idx[i]+1): ref 0.8991 vs 0.8991,
target 0.9000). It is re-validated on import by candC_multi.py so a copy
that drifts from the reference is caught, not trusted.

WHY a vectorised copy at all: kelly.py's bootstrap is O(n) pure Python per
draw and unusable at n=5,000 x 6 assets x a k-bisection.
"""
from __future__ import annotations
import csv, dataclasses, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import numpy as np                                               # noqa: E402
import app.engine.core as core                                   # noqa: E402
from app.engine.core import Bar                                  # noqa: E402
from app.engine.replay import run_replay                         # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

DATA = os.path.join(HERE, "candC_data")
SEED = 20260804
BARS_PER_YEAR = 2190
HORIZON = 2 * BARS_PER_YEAR              # fixed 2.00y DD horizon, every case
DD_LIMIT, P_LIMIT = 0.30, 0.10           # KELLY.md's own budget
EQUITY = 100_055.0
REF_LEV = 1.5
LIVE_GROSS = 0.20 * REF_LEV * 50_000.0   # $15,000 shipped today

# Venue fees measured 2026-09-28 from {"type":"userFees"} for this account
# (4% referral discount applied): cross 4.32 bp, add 1.44 bp per side.
FEE_TAKER_RT = 8.64      # PRIMARY: what the book pays TODAY (both sides cross)
FEE_MAKER_RT = 5.76      # maker entry + taker exit (phase 1's FIX 1)
FEE_ENGINE_RT = 12.00    # TradeCfg's registered objective


def load_bars(path):
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(path))]


def asset_path(coin):
    return os.path.join(DATA, f"bars_4h_{coin.lower()}.csv")


# ---- per-bar MTM capture, exactly blend_corr.py's hook -------------------
_ORIG_MTM = core._mark_to_market


def replay_mtm(bars, rt_bps, books=None, warmup=210):
    """Run the SHIPPED engine over `bars` and return, per book:
        mtm  : per-bar mark-to-market equity (open position valued at close)
        inpos: bool, position open at that close
        trades: the ClosedTrade list
    `rt_bps` is the ROUND-TRIP taker cost; both Position construction sites
    charge 2 x TradeCfg.taker_fee_bps, so we pass rt/2.
    NOTHING about the strategy is changed per asset -- same SignalCfg, same
    TradeCfg, same BookCfgs. That is the whole point of the test."""
    books = books or RESEARCH_BOOKS
    trace: dict[str, list] = {}

    def traced(book, close):
        _ORIG_MTM(book, close)
        trace.setdefault(book.cfg.name, []).append(
            (book.mtm_equity, book.position is not None))

    core._mark_to_market = traced
    try:
        res = run_replay(bars, books, RESEARCH_SIGNAL,
                         dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=rt_bps / 2.0),
                         warmup_bars=warmup, cash_apy=0.0)
    finally:
        core._mark_to_market = _ORIG_MTM
    mtm = {k: np.array([x[0] for x in v]) for k, v in trace.items()}
    inpos = {k: np.array([x[1] for x in v]) for k, v in trace.items()}
    return mtm, inpos, {k: b.trades for k, b in res.books.items()}


# ---- vectorised stationary bootstrap (blend_corr.py, validated) ----------
def sb_idx(n, out_len, rng, mean_block):
    p = 1.0 / mean_block
    restart = rng.random(out_len) < p
    restart[0] = True
    seg = np.cumsum(restart) - 1
    nseg = int(seg[-1]) + 1
    pos = np.arange(out_len)
    seg_start = np.zeros(nseg, dtype=np.int64)
    seg_start[seg[restart]] = pos[restart]
    starts = rng.integers(0, n, nseg)
    return (starts[seg] + (pos - seg_start[seg])) % n


def sb_idx_restricted(pool, out_len, rng, mean_block, n_total):
    """Stationary bootstrap whose BLOCK STARTS are restricted to `pool`
    (an index array), blocks then running forward through the real series.
    Used for the crash-only future: resample from stress episodes only, which
    preserves the EMPIRICAL joint tail dependence across assets instead of
    imposing a copula."""
    p = 1.0 / mean_block
    restart = rng.random(out_len) < p
    restart[0] = True
    seg = np.cumsum(restart) - 1
    nseg = int(seg[-1]) + 1
    pos = np.arange(out_len)
    seg_start = np.zeros(nseg, dtype=np.int64)
    seg_start[seg[restart]] = pos[restart]
    starts = pool[rng.integers(0, len(pool), nseg)]
    return (starts[seg] + (pos - seg_start[seg])) % n_total


def dd_prob(r, m, dd_limit=DD_LIMIT, horizon=HORIZON, draws=400,
            mean_block=60, seed=SEED, pool=None):
    r = np.asarray(r, float)
    rng = np.random.default_rng(seed + 1)
    n = len(r)
    hits = done = 0
    CH = 80
    while done < draws:
        k = min(CH, draws - done)
        if pool is None:
            idx = np.stack([sb_idx(n, horizon, rng, mean_block) for _ in range(k)])
        else:
            idx = np.stack([sb_idx_restricted(pool, horizon, rng, mean_block, n)
                            for _ in range(k)])
        path = 1.0 + m * r[idx]
        bad = np.any(path <= 0, axis=1)
        eq = np.cumprod(np.where(path <= 0, 1e-12, path), axis=1)
        mdd = (eq / np.maximum.accumulate(eq, axis=1) - 1.0).min(axis=1)
        hits += int(np.sum(bad | (mdd < -dd_limit)))
        done += k
    return hits / draws


def dd_constrained(r, dd_limit=DD_LIMIT, p_limit=P_LIMIT, horizon=HORIZON,
                   cap=30.0, mean_block=60, seed=SEED, steps=14, pool=None):
    """Largest k = gross/equity with P(maxDD > dd_limit) <= p_limit."""
    r = np.asarray(r, float)
    if r.mean() <= 0:
        return 0.0
    mn = r.min()
    hi = cap if mn >= 0 else min(cap, 0.99 / abs(mn))
    if dd_prob(r, hi, dd_limit, horizon, mean_block=mean_block, seed=seed,
               pool=pool) <= p_limit:
        return round(hi, 3)
    lo = 0.0
    for _ in range(steps):
        mid = (lo + hi) / 2
        if dd_prob(r, mid, dd_limit, horizon, mean_block=mean_block, seed=seed,
                   pool=pool) <= p_limit:
            lo = mid
        else:
            hi = mid
    return round(lo, 3)


def kstar_rows(R, cap=30.0, npts=121):
    out = np.zeros(len(R))
    grid = np.linspace(0, 1, npts)
    for i in range(len(R)):
        r = R[i]
        if r.mean() <= 0:
            continue
        mn = r.min()
        hi = cap if mn >= 0 else min(cap, 0.99 / abs(mn))
        ms = grid * hi
        x = 1.0 + np.outer(ms, r)
        g = np.where(np.any(x <= 0, axis=1), -np.inf,
                     np.log(np.maximum(x, 1e-300)).mean(axis=1))
        out[i] = ms[int(np.argmax(g))]
    return out


def boot_stats(r, draws=300, mean_block=60, cap=30.0, seed=SEED):
    """Bootstrap p10/p50/P(edge<=0) of k* -- the estimation-error picture."""
    r = np.asarray(r, float)
    rng = np.random.default_rng(seed)
    n = len(r)
    idx = np.stack([sb_idx(n, n, rng, mean_block) for _ in range(draws)])
    stars = kstar_rows(r[idx], cap)
    return (round(float(np.percentile(stars, 10)), 3),
            round(float(np.percentile(stars, 50)), 3),
            round(float((stars == 0).mean()), 3))


def ann_stats(r):
    r = np.asarray(r, float)
    sd = r.std(ddof=1)
    return {"mean_bp_bar": float(r.mean() * 1e4),
            "ann_sd_pct": float(sd * np.sqrt(BARS_PER_YEAR) * 100),
            "ann_SR": float(r.mean() / sd * np.sqrt(BARS_PER_YEAR)) if sd > 0 else 0.0}
