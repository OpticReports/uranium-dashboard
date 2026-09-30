"""Shared research harness for the CAGR study (RESEARCH_CAGR.md).

Design: the ENGINE decides trades, the PORTFOLIO layer sizes and marks them.

1. Engine layer - `leg_trades()` runs the production signal/entry/stop/exit
   code (app.engine.core) through a replay loop that is line-for-line
   `app.engine.replay.run_replay`, with two hooks a study can override:
   the donchian processing function and the channel lookback. With the
   hooks at their defaults it reproduces run_replay's trade list EXACTLY
   (test_harness.py enforces this). Books run with
   dd_halt disabled and unit size, so the trade list is a property of the
   RULES, not of any sizing or halt state - core.py's one-way book.halted
   (RESEARCH_SCALE.md defect table) cannot leak in.

2. Portfolio layer - `simulate()` replays those trades on the 4h bar grid
   against ONE shared equity, the way btc-executor actually trades:
   qty fixed at entry = weight * k * current MTM equity / entry price;
   marked to every bar's close; taker fee charged per side (entry notional
   at entry, exit notional at exit) at the rate measured on live
   Hyperliquid fills, 4.32 bps/side (8.64 round trip).

Metrics are MARK-TO-MARKET throughout - the drawdown the account actually
experiences, not the exit-step drawdown most published numbers in this
repo use (which runs 1-4pp shallower).

Nothing here touches production code or live state.
"""
from __future__ import annotations

import csv
import math
import os
import sys
from dataclasses import dataclass, field, replace
from typing import Callable

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.engine import core                                        # noqa: E402
from app.engine.core import (Bar, Book, BookCfg, Ind, SignalCfg,   # noqa: E402
                             TradeCfg, eval_signal, process_closed_bar,
                             resolve_open_exit)
from app.indicators import atr, rsi, sma                           # noqa: E402

BAR_S = 4 * 3600
BARS_PER_YEAR = 2190
LIVE_TAKER_BPS = 4.32          # measured on live HL fills, per side
DATA = os.path.join(HERE, "data")


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def load_bars(pair: str = "btcusd") -> list[Bar]:
    path = os.path.join(DATA, f"bars_4h_{pair}.csv")
    with open(path) as fh:
        return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                    high=float(r["high"]), low=float(r["low"]),
                    close=float(r["close"]), volume=float(r["volume"]))
                for r in csv.DictReader(fh)]


# --------------------------------------------------------------------------
# engine layer
# --------------------------------------------------------------------------
def compute_indicators(bars: list[Bar], channel: int = 20) -> list[Ind]:
    """app.engine.replay.compute_indicators with the Donchian lookback as a
    parameter. channel=20 is byte-identical to production."""
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    vols = [b.volume for b in bars]
    s50, s200 = sma(closes, 50), sma(closes, 200)
    r14 = rsi(closes, 14)
    a14 = atr(highs, lows, closes, 14)
    v20 = sma(vols, 20)
    n = len(bars)
    hi: list[float | None] = [None] * n
    lo: list[float | None] = [None] * n
    for i in range(channel, n):
        hi[i] = max(highs[i - channel:i])
        lo[i] = min(lows[i - channel:i])
    return [Ind(sma50=s50[i], sma200=s200[i], rsi14=r14[i], atr14=a14[i],
                vol_sma20=v20[i], hi20=hi[i], lo20=lo[i]) for i in range(n)]


@dataclass(frozen=True)
class Trade:
    """One round trip, as the ENGINE decided it. Size-free."""
    leg: str
    side: str                    # "L" | "S"
    entry_ts: int
    entry_price: float
    exit_ts: int | None          # None = still open at the end of data
    exit_price: float | None
    reason: str


def leg_trades(bars: list[Bar], strategy: str, *,
               start_ts: int | None = None, end_ts: int | None = None,
               scfg: SignalCfg | None = None, tcfg: TradeCfg | None = None,
               trail_atr: float = 5.0, channel: int = 20,
               donchian_fn: Callable | None = None,
               inds: list[Ind] | None = None,
               warmup_bars: int = 210, leg: str | None = None) -> list[Trade]:
    """Run ONE engine book over `bars` and return its round trips.

    Mirrors app.engine.replay.run_replay exactly (same bar gating, same
    resolve_open_exit -> signal -> process_closed_bar order). The book is
    unit-size with dd_halt disabled, so trades depend only on the rules.
    `donchian_fn` replaces core._process_donchian for the duration of the
    call (restored in `finally`) - the ONLY monkeypatch in this module, and
    it swaps a whole function, never a keyword default."""
    scfg = scfg or SignalCfg()
    tcfg = tcfg or TradeCfg(taker_fee_bps=LIVE_TAKER_BPS)
    if inds is not None and channel != 20:
        # a precomputed inds carries ITS OWN channel; passing channel=N with
        # someone else's inds silently tested channel 20 (audit a9). The
        # caller must hand in inds built for this channel - checked here.
        probe = compute_indicators(bars[:channel + 2], channel)[channel]
        if inds[channel].hi20 != probe.hi20:
            raise ValueError(f"inds were not built for channel={channel}")
    inds = inds if inds is not None else compute_indicators(bars, channel)
    cfg = BookCfg(name=leg or strategy, sizing="fixed", strategy=strategy,
                  trail_atr=trail_atr, leverage=1.0, cap=1.0,
                  start_equity=1.0, dd_halt=1e9)
    book = Book(cfg=cfg)
    orig = core._process_donchian
    if donchian_fn is not None:
        core._process_donchian = donchian_fn
    try:
        for i, bar in enumerate(bars):
            if i < warmup_bars:
                continue
            if start_ts is not None and bar.ts < start_ts:
                continue
            if end_ts is not None and bar.ts > end_ts:
                break
            ind = inds[i]
            resolve_open_exit(book, bar, tcfg)
            if strategy == "donchian":
                sig = core.eval_donchian(bar, ind)
            else:
                sig = eval_signal(bar, ind, scfg)
            process_closed_bar(book, bar, ind, scfg, tcfg, sig)
    finally:
        core._process_donchian = orig
    name = leg or strategy
    out = [Trade(name, t.side, t.entry_ts, t.entry_price, t.exit_ts,
                 t.exit_price, t.exit_reason) for t in book.trades]
    if book.position is not None:
        p = book.position
        out.append(Trade(name, p.side, p.entry_ts, p.entry_price, None, None,
                         "OPEN"))
    return out


def process_donchian_resting_stop(book: Book, bar: Bar, ind: Ind,
                                  tcfg: TradeCfg, signal) -> None:
    """Candidate A1. Identical to core._process_donchian except for ORDER:
    the stop that can be hit during bar t is the trail that was RESTING at
    the venue during bar t - i.e. the level set at close(t-1) - and only
    THEN is the trail ratcheted from close(t) for bar t+1.

    Production computes the new trail from close(t) first and tests bar t's
    own low against it. A real stop order cannot do that: on an up-bar with
    a deep lower wick the low printed before the close that created the
    level. btc-executor rests a venue stop at the PREVIOUS published trail,
    so this is what the venue actually does."""
    if book.pending is not None:
        p = book.pending
        book.pending = None
        if ind.atr14 is not None:
            qty, notional = core._size(book, p.side, bar.open, ind.atr14, tcfg)
            if qty > 0:
                book.position = core.Position(
                    side=p.side, entry_ts=bar.ts, entry_price=bar.open,
                    qty=qty, notional=notional, stop_price=0.0,
                    atr_at_entry=ind.atr14, signal_ts=p.signal_ts,
                    fee_bps=2 * tcfg.taker_fee_bps)
    pos = book.position
    if pos is not None:
        # 1) the RESTING stop (set at the previous close) is tested first
        if pos.trail is not None and bar.ts > pos.entry_ts:
            hit = (bar.low <= pos.trail if pos.side == "L"
                   else bar.high >= pos.trail)
            if hit:
                # a gap through the stop fills at the open, not at the level
                fill = (min(pos.trail, bar.open) if pos.side == "L"
                        else max(pos.trail, bar.open))
                core._close_position(book, pos, bar.ts, fill, "STOP", tcfg)
                pos = None
        # 2) survivors ratchet the trail from this close, for the NEXT bar
        if pos is not None and ind.atr14 is not None:
            lvl = (bar.close - book.cfg.trail_atr * ind.atr14 if pos.side == "L"
                   else bar.close + book.cfg.trail_atr * ind.atr14)
            pos.trail = (lvl if pos.trail is None else
                         (max(pos.trail, lvl) if pos.side == "L"
                          else min(pos.trail, lvl)))
            pos.stop_price = pos.trail
    if (book.position is None and book.pending is None and not book.halted
            and signal is not None):
        book.pending = core.Pending(side=signal, limit=-1.0, signal_ts=bar.ts,
                                    atr_signal=ind.atr14 or 0.0)


# --------------------------------------------------------------------------
# portfolio layer
# --------------------------------------------------------------------------
@dataclass
class LegSpec:
    trades: list[Trade]
    weight: float                # notional fraction of equity at k = 1
    asset: str = "btcusd"
    # Optional time-varying weight, evaluated at each ENTRY bar's open ts.
    # It must only use information from bars strictly before that ts; the
    # callers in candidates.py enforce this with a one-bar shift.
    weight_fn: Callable[[int], float] | None = None


@dataclass
class SimResult:
    ts: np.ndarray               # bar open timestamps
    equity: np.ndarray           # MTM equity at each bar's close
    gross_lev: np.ndarray        # gross notional / equity at each close
    n_trades: int
    fees: float
    ruined: bool = False
    trade_pnl: list = field(default_factory=list)
    start_equity: float = 100_000.0


def simulate(legs: list[LegSpec], closes: dict[str, dict[int, float]],
             k: float = 1.0, start_ts: int | None = None,
             end_ts: int | None = None, fee_bps: float = LIVE_TAKER_BPS,
             start_equity: float = 100_000.0,
             fixed_base: float | None = None) -> SimResult:
    """Replay engine trades against one shared MTM equity.

    Ordering within a bar: exits first (their P&L realised), then entries
    sized off the equity that results, then every open position is marked
    at the close. Within a leg the engine guarantees entry_ts > the prior
    trade's exit_ts, so a leg never holds two positions."""
    f = fee_bps / 10_000.0
    grid = sorted(set().union(*[set(c) for c in closes.values()]))
    if start_ts is not None:
        grid = [t for t in grid if t >= start_ts]
    if end_ts is not None:
        grid = [t for t in grid if t <= end_ts]
    entries: dict[int, list] = {}
    exits: dict[int, list] = {}
    for li, lg in enumerate(legs):
        for t in lg.trades:
            if start_ts is not None and t.entry_ts < start_ts:
                continue
            if end_ts is not None and t.entry_ts > end_ts:
                continue
            entries.setdefault(t.entry_ts, []).append((li, t))
            if t.exit_ts is not None and (end_ts is None or t.exit_ts <= end_ts):
                exits.setdefault(t.exit_ts, []).append((li, t))
    cash = start_equity
    open_pos: dict[tuple, dict] = {}      # (leg, entry_ts) -> position
    eq_out, lev_out = [], []
    fees = 0.0
    n = 0
    pnl_log = []
    # last_close holds each asset's most recent close KNOWN BEFORE this bar
    # opens; it is advanced to this bar's close only at the mark step. Entry
    # sizing therefore never sees the close of the bar it fills in (audit
    # 2026-09-29, a3: it used to, which was slightly pessimistic).
    last_close: dict[str, float] = {}
    ruined = False
    for ts in grid:
        # 1) exits
        for li, t in exits.get(ts, []):
            key = (li, t.entry_ts)
            p = open_pos.pop(key, None)
            if p is None:
                continue
            sgn = 1.0 if t.side == "L" else -1.0
            gross = p["qty"] * (t.exit_price - t.entry_price) * sgn
            fee = f * p["qty"] * t.exit_price
            cash += gross - fee
            fees += fee
            pnl_log.append((t.leg, t.entry_ts, t.exit_ts, gross - fee - p["efee"],
                            p["notional"]))
        # equity after exits, marked at the PREVIOUS close for still-open legs
        unreal = 0.0
        for (li, _), p in open_pos.items():
            px = last_close.get(legs[li].asset, p["entry_price"])
            unreal += p["qty"] * (px - p["entry_price"]) * p["sgn"]
        eq_now = cash + unreal
        # 2) entries, sized off current equity
        for li, t in entries.get(ts, []):
            if eq_now <= 0:
                break
            lg = legs[li]
            w = lg.weight_fn(t.entry_ts) if lg.weight_fn is not None else lg.weight
            # fixed_base = how btc-executor actually sizes (SIZING_BASE_USD,
            # no compounding); None = compound off current MTM equity.
            notional = w * k * (fixed_base if fixed_base else eq_now)
            if notional <= 0:
                continue
            qty = notional / t.entry_price
            fee = f * notional
            cash -= fee
            fees += fee
            n += 1
            open_pos[(li, t.entry_ts)] = dict(
                qty=qty, entry_price=t.entry_price, notional=notional,
                sgn=1.0 if t.side == "L" else -1.0, efee=fee)
        # 3) advance to this bar's closes, then mark to market
        for a, c in closes.items():
            if ts in c:
                last_close[a] = c[ts]
        unreal, gross_n = 0.0, 0.0
        for (li, _), p in open_pos.items():
            px = last_close.get(legs[li].asset, p["entry_price"])
            unreal += p["qty"] * (px - p["entry_price"]) * p["sgn"]
            gross_n += p["qty"] * px
        eq = cash + unreal
        eq_out.append(eq)
        lev_out.append(gross_n / eq if eq > 0 else float("inf"))
        if eq <= 0:
            ruined = True
            break
    ts_arr = np.array(grid[:len(eq_out)], dtype=np.int64)
    return SimResult(ts=ts_arr, equity=np.array(eq_out),
                     gross_lev=np.array(lev_out), n_trades=n, fees=fees,
                     ruined=ruined, trade_pnl=pnl_log,
                     start_equity=start_equity)


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def max_dd(eq: np.ndarray) -> float:
    if len(eq) == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    return float((eq / peak - 1.0).min())


def stats(r: SimResult) -> dict:
    eq = r.equity
    if len(eq) < 2 or r.ruined:
        return dict(cagr=-1.0, maxdd=-1.0, mar=None, sharpe=None,
                    n=r.n_trades, years=0.0, ruined=True)
    # Measured from START EQUITY, not from bar 0's close: a position that
    # loses on its first bar is a real drawdown (audit 2026-09-29, a5).
    e0 = r.start_equity
    path = np.concatenate([[e0], eq])
    yrs = (r.ts[-1] - r.ts[0] + BAR_S) / (365.25 * 86400)
    tot = eq[-1] / e0
    cagr = tot ** (1 / yrs) - 1 if yrs > 0 and tot > 0 else -1.0
    mdd = max_dd(path)
    ret = np.diff(path) / path[:-1]
    sd = ret.std()
    sharpe = float(ret.mean() / sd * math.sqrt(BARS_PER_YEAR)) if sd > 0 else None
    return dict(cagr=float(cagr), maxdd=float(mdd),
                mar=float(cagr / abs(mdd)) if mdd < -1e-4 else None,
                sharpe=sharpe, n=r.n_trades, years=float(yrs),
                max_gross_lev=float(np.nanmax(r.gross_lev)) if len(r.gross_lev) else 0.0,
                ruined=False)


def k_at_dd(legs, closes, target_dd: float = 0.30, lo: float = 0.01,
            hi: float = 25.0, iters: int = 40, **kw) -> float:
    """Largest k whose REALISED MTM max drawdown is <= target (bisection).

    NOT necessarily more or less conservative than k_safe - on the BTC
    2013+ sample it is the LOWER of the two (0.396 vs k_safe 0.434, whose
    realised DD is -32.3%). Anything that turns these into a live size must
    take min(k_at_dd, k_safe) (audit 2026-09-29, a8)."""
    def dd(k):
        r = simulate(legs, closes, k=k, **kw)
        return 1.0 if r.ruined else -max_dd(np.concatenate([[r.equity[0]], r.equity]))
    if dd(hi) <= target_dd:
        return hi
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if dd(mid) <= target_dd:
            lo = mid
        else:
            hi = mid
    return lo


def _stationary_bootstrap_idx(n: int, horizon: int, mean_block: float,
                              rng: np.random.Generator) -> np.ndarray:
    """Politis-Romano stationary bootstrap index path."""
    idx = np.empty(horizon, dtype=np.int64)
    p = 1.0 / mean_block
    i = rng.integers(n)
    for j in range(horizon):
        idx[j] = i
        i = rng.integers(n) if rng.random() < p else (i + 1) % n
    return idx


def k_safe(unit_ret: np.ndarray, target_dd: float = 0.30,
           prob: float = 0.10, horizon: int = 2 * BARS_PER_YEAR,
           mean_block: float = 180.0, n_paths: int = 1000,
           seed: int = 7) -> tuple[float, dict]:
    """Largest k with P(maxDD over `horizon` bars > target_dd) <= prob.

    Bootstraps the per-bar portfolio return series at k = 1 (stationary
    blocks, mean ~1 month so trade-length autocorrelation survives) and
    scales it by k. Constant-leverage scaling is an approximation to the
    fixed-qty-per-trade portfolio; the CAGR reported at k_safe always comes
    from an exact simulate(), never from this approximation.
    This is KELLY.md's own drawdown criterion - P(maxDD>30%) <= 10% - on a
    fixed 2-year horizon, matching RESEARCH_SCALE.md."""
    rng = np.random.default_rng(seed)
    n = len(unit_ret)
    paths = np.stack([unit_ret[_stationary_bootstrap_idx(n, horizon,
                                                         mean_block, rng)]
                      for _ in range(n_paths)])

    def p_breach(k):
        g = np.clip(1.0 + k * paths, 1e-12, None)
        eq = np.cumprod(g, axis=1)
        peak = np.maximum.accumulate(np.concatenate(
            [np.ones((n_paths, 1)), eq], axis=1), axis=1)[:, 1:]
        dd = (eq / peak - 1.0).min(axis=1)
        return float((dd < -target_dd).mean())

    lo, hi = 0.0, 1.0
    while p_breach(hi) <= prob and hi < 64:
        lo, hi = hi, hi * 2
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if p_breach(mid) <= prob:
            lo = mid
        else:
            hi = mid
    return lo, dict(p_at_k=p_breach(lo), horizon_bars=horizon,
                    mean_block=mean_block, n_paths=n_paths)


def closes_of(bars: list[Bar]) -> dict[int, float]:
    return {b.ts: b.close for b in bars}


def ts_of(date: str) -> int:
    import calendar
    import time
    return calendar.timegm(time.strptime(date, "%Y-%m-%d"))


# Non-overlapping eras. What each is out-of-sample FOR is recorded in
# RESEARCH_CAGR.md section 2 - no era is clean for both legs.
ERAS = {
    "E1 2013-16": ("2013-01-01", "2016-12-31"),
    "E2 2017-19": ("2017-01-01", "2019-12-31"),
    "E3 2020-21": ("2020-01-01", "2021-12-31"),
    "E4 2022-24H1": ("2022-01-01", "2024-06-30"),
    "E5 2024H2-26 (SPENT)": ("2024-07-01", "2026-07-31"),
    "E6 2026-08+ (fresh)": ("2026-08-01", "2026-12-31"),
}
FULL = ("2013-01-01", "2026-12-31")
