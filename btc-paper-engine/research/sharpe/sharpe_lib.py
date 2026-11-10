"""Sharpe study library (PREREG.md). Every directional trade comes from the
CAGR study's harness (engine code path, gate-tested against run_replay);
this module adds the three registered levers and the account-level metric.

  baseline   live engine 2026-09-30: S3 + S4 resting-stop trail, w_trend
             0.30, lev 1.5, KELLY_M 0.30, fixed $100k base, 4.32 bp/side
  H1         vol-targeted entry size, m = clip(sigma_ref/sigma_now, .5, 1.33)
  H2         pullback signal vetoed against the 200-DAY (1,200-bar) SMA
  H3a/H3b    $30k funding-carry sleeve, static / gated 8% ARM, 5% DISARM

Metric: Sharpe of DAILY account P&L on the fixed $100k base, sqrt(365).
"""
import calendar
import csv
import math
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "cagr"))
import harness as H                                                 # noqa: E402

BASE = 100_000.0
K = 0.30
W_TREND, LEV = 0.30, 1.5
W_P, W_T = (1 - W_TREND) * LEV, W_TREND * LEV      # 1.05 / 0.45 at k = 1
DAY = 86400

VOL_WIN, VOL_REF, M_LO, M_HI = 180, H.BARS_PER_YEAR, 0.5, 1.33
GATE_BARS = 1200                                     # 200 days of 4h bars

CARRY_NOTIONAL = 30_000.0
SPOT_BPS, PERP_BPS = 7.0, H.LIVE_TAKER_BPS
RESIZE_DRIFT = 0.25
ARM, DISARM, GATE_DAYS = 0.08, 0.05, 30

DATA = os.path.join(HERE, "data")


def ts_of(d):
    return calendar.timegm(time.strptime(d, "%Y-%m-%d"))


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
class World:
    def __init__(self):
        self.bars = H.load_bars("btcusd")
        self.ts = np.array([b.ts for b in self.bars], dtype=np.int64)
        self.close = np.array([b.close for b in self.bars])
        self.closes = {"btcusd": H.closes_of(self.bars)}
        self.inds = H.compute_indicators(self.bars, 20)
        self.idx = {int(t): i for i, t in enumerate(self.ts)}
        self.sma_gate = pd.Series(self.close).rolling(GATE_BARS).mean().to_numpy()
        lr = np.full(len(self.close), np.nan)
        lr[1:] = np.diff(np.log(self.close))
        s_now = pd.Series(lr).rolling(VOL_WIN).std(ddof=0)
        s_ref = s_now.rolling(VOL_REF).median()
        self.sigma_now = s_now.to_numpy()
        self.sigma_ref = s_ref.to_numpy()
        self.funding = load_funding("funding_bitmex_xbtusd.csv")

    # ---- H1 -------------------------------------------------------------
    def vol_mult(self, T):
        """m for an entry on bar T: sigmas over bars ending at T-1 (known
        when bar T opens). 1.0 where the history is too short."""
        j = self.idx.get(int(T) - H.BAR_S)
        if j is None:
            return 1.0
        a, b = self.sigma_ref[j], self.sigma_now[j]
        if not (a == a and b == b and b > 0):
            return 1.0
        return float(min(M_HI, max(M_LO, a / b)))

    # ---- H2 -------------------------------------------------------------
    def gate_fn(self, i, bar, ind, sig):
        if sig is None:
            return None
        sma = self.sma_gate[i]
        if sma != sma:
            return sig
        if sig == "L" and not bar.close > sma:
            return None
        if sig == "S" and not bar.close < sma:
            return None
        return sig

    # ---- legs -------------------------------------------------------------
    def legs(self, t0, t1, vol=False, gate=False):
        pull = H.leg_trades(self.bars, "pullback", start_ts=t0, end_ts=t1,
                            inds=self.inds, leg="pullback",
                            signal_fn=self.gate_fn if gate else None)
        trend = H.leg_trades(self.bars, "donchian", start_ts=t0, end_ts=t1,
                             inds=self.inds, leg="trend",
                             donchian_fn=H.process_donchian_resting_stop)
        wf_p = (lambda T: W_P * self.vol_mult(T)) if vol else None
        wf_t = (lambda T: W_T * self.vol_mult(T)) if vol else None
        return [H.LegSpec(pull, W_P, weight_fn=wf_p),
                H.LegSpec(trend, W_T, weight_fn=wf_t)]


def load_funding(name):
    """(ts_seconds, rate per stamp). Hyperliquid's file is in MILLISECONDS
    (header ts_ms); read as seconds it silently yields zero funding (audit
    2026-10-01, finding 1)."""
    rows = list(csv.reader(open(os.path.join(DATA, name))))
    hdr, rows = rows[0], rows[1:]
    ts = np.array([int(float(r[0])) for r in rows], dtype=np.int64)
    if hdr[0].endswith("_ms") or ts.max() > 10 ** 11:
        ts = ts // 1000
    assert ts.max() < 10 ** 11
    order = np.argsort(ts, kind="stable")
    return ts[order], np.array([float(r[1]) for r in rows])[order]


# --------------------------------------------------------------------------
# directional book -> per-bar P&L on the fixed base
# --------------------------------------------------------------------------
def directional(W, t0, t1, vol=False, gate=False):
    """(ts, pnl_cum) per 4h bar: MTM account P&L, fixed $100k base."""
    r = H.simulate(W.legs(t0, t1, vol, gate), W.closes, k=K, start_ts=t0,
                   end_ts=t1, fixed_base=BASE, start_equity=BASE)
    assert not r.ruined
    return r.ts, r.equity - BASE, r


# --------------------------------------------------------------------------
# H3 carry sleeve -> per-bar P&L
# --------------------------------------------------------------------------
def carry(grid_ts, close_by_ts, fund_ts, fund_rate, gated, *,
          notional=CARRY_NOTIONAL, spot_bps=SPOT_BPS, perp_bps=PERP_BPS):
    """Cumulative sleeve P&L at each bar's close, over `grid_ts` (bar opens).

    Long spot qty q, short perp qty q, both marked at the same close, so
    price P&L is identically zero (basis NOT modelled). At each bar OPEN:
    decide (gate at UTC day start; resize at UTC month start), trading at
    the last known close. Over the bar: accrue every funding stamp s with
    open < s <= close at +rate * q * close (rate > 0: short receives).
    Fees: (spot+perp) bp on |dq| * price for every change of q."""
    f = (spot_bps + perp_bps) / 1e4
    q, on, cum, last_px = 0.0, False, 0.0, None
    out = np.empty(len(grid_ts))
    fees = funding = 0.0
    n_switch = 0
    k = int(np.searchsorted(fund_ts, grid_ts[0], side="right")) if len(grid_ts) else 0
    first = True
    for j, ts in enumerate(grid_ts):
        ts = int(ts)
        px = last_px
        if px is not None:
            want_on = on
            if not gated:
                want_on = True
            elif first or ts % DAY == 0:
                lo = int(np.searchsorted(fund_ts, ts - GATE_DAYS * DAY, side="left"))
                hi = int(np.searchsorted(fund_ts, ts, side="left"))   # s < ts
                full = len(fund_ts) and fund_ts[0] <= ts - GATE_DAYS * DAY
                if full and hi > lo:
                    ann = fund_rate[lo:hi].sum() * 365.0 / GATE_DAYS
                    if ann >= ARM:
                        want_on = True
                    elif ann < DISARM:
                        want_on = False
                else:
                    want_on = False
            first = False
            target = q
            if want_on and not on:
                target = notional / px
            elif not want_on and on:
                target = 0.0
            elif on and _is_month_start(ts) and \
                    abs(q * px / notional - 1.0) > RESIZE_DRIFT:
                target = notional / px
            if target != q:
                fee = f * abs(target - q) * px
                cum -= fee
                fees += fee
                if (target > 0) != (q > 0):
                    n_switch += 1
                q = target
            on = q > 0
        c = close_by_ts[ts]
        end = ts + H.BAR_S
        while k < len(fund_ts) and fund_ts[k] <= end:
            if fund_ts[k] > ts and q > 0:
                g = fund_rate[k] * q * c
                cum += g
                funding += g
            k += 1
        last_px = c
        out[j] = cum
    last_stamp = int(fund_ts[-1]) if len(fund_ts) else None
    return out, dict(fees=fees, funding=funding, switches=n_switch,
                     funding_ends=last_stamp,
                     uncovered_days=max(0.0, (int(grid_ts[-1]) + H.BAR_S
                                              - (last_stamp or 0)) / DAY - 1)
                     if len(grid_ts) else 0.0)


def _is_month_start(ts):
    return ts % DAY == 0 and time.gmtime(ts).tm_mday == 1


# --------------------------------------------------------------------------
# account metric
# --------------------------------------------------------------------------
def daily_pnl(ts, pnl_cum):
    """Daily P&L from a per-bar cumulative series; day = UTC date of the
    bar OPEN (a bar opening 20:00 closes at 24:00, the day's last close)."""
    day = np.asarray(ts) // DAY
    s = pd.Series(np.asarray(pnl_cum), index=day)
    last = s.groupby(level=0).last()
    return last.index.to_numpy(), np.diff(np.concatenate([[0.0], last.to_numpy()]))


def sharpe(d):
    d = np.asarray(d, dtype=float)
    sd = d.std()
    return float(d.mean() / sd * math.sqrt(365)) if sd > 0 else float("nan")


def max_dd_usd(pnl_cum):
    path = np.concatenate([[0.0], np.asarray(pnl_cum)])
    return float((path - np.maximum.accumulate(path)).min())


def boot_delta(a, b, n=2000, block=30.0, seed=7):
    """Paired stationary bootstrap of Sharpe(b) - Sharpe(a) on daily P&L."""
    a, b = np.asarray(a), np.asarray(b)
    assert len(a) == len(b)
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    for i in range(n):
        idx = H._stationary_bootstrap_idx(len(a), len(a), block, rng)
        out[i] = sharpe(b[idx]) - sharpe(a[idx])
    return float(np.percentile(out, 5)), float(np.percentile(out, 95))


def dsr(d, n_trials, sd_trials=0.469):
    """Deflated Sharpe (Bailey & Lopez de Prado 2014) of daily series d,
    benchmark = expected max of n_trials Sharpes with cross-trial sd
    `sd_trials` (annualised, RESEARCH_PROTOCOL.md section 2)."""
    G = 0.5772156649015329
    nd = _norm_cdf
    d = np.asarray(d, dtype=float)
    T = len(d)
    s = d.mean() / d.std()
    sd = sd_trials / math.sqrt(365)
    sr0 = sd * ((1 - G) * _norm_ppf(1 - 1 / n_trials)
                + G * _norm_ppf(1 - 1 / (n_trials * math.e)))
    z = (d - d.mean()) / d.std()
    sk, ku = float((z ** 3).mean()), float((z ** 4).mean())
    den = 1 - sk * s + (ku - 1) / 4 * s * s
    return nd((s - sr0) * math.sqrt(T - 1) / math.sqrt(den))


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p):
    lo, hi = -40.0, 40.0
    for _ in range(200):
        m = (lo + hi) / 2
        if _norm_cdf(m) < p:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2
