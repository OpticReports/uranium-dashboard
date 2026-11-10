"""Crash stress harness - BTC book + executor guards (PREREG.md, 2026-10-07).

Implements PREREG sections "Splice method" and "Portfolio emulation" for the
BTC half of the account. The carry sleeve enters through `carry_value`, a
per-bar array of the sleeve's value that is ADDED to BTC-book equity before
every halt check (the executor's halts measure the whole account).

Layers (per bar, in this order):

  0. UTC rollover (00:00 bar): DAILY_LOSS re-arms (or is relabelled DRAWDOWN
     when equity is also below the drawdown line, mirror._roll_day);
     day_start = equity at the open; variant-B DRAWDOWN resume after 7 days.
  1. exits of held legs whose engine trade exits on this bar: STOP intrabar
     at the stop level, or at the open if the bar gapped through; SIGNAL /
     TIME at the open (the engine's own exit price).
  2. entries (not while halted): engine trades entering on this bar at the
     engine's entry price; after a re-arm/resume (and at t0) every engine
     position still open is re-mirrored at this bar's open (market). Size =
     K x 1.5 x w x 100,000 x size_mult (volsize.size_mult at the SIGNAL bar,
     down-only), clamped so gross across both legs <= min(130k, 2.0 x base),
     pullback first then trend (mirror.LEGS order); 4.32 bp taker fee.
  3. intrabar halt check on the WORST equity of the bar (every held position
     at the bar's adverse extreme, same-bar entries included): a breach
     flattens every leg at the breach level (the price where equity crosses
     the line), or at the open if the bar opened through it.
  4. BTC perp funding on every position still held at the bar's close when
     an 8h funding stamp falls on that close (rate x qty x close; a long
     PAYS a positive rate, a short receives it; BitMEX XBTUSD of the
     analogue window shifted onto today's grid is the proxy for HL BTC -
     review finding, 2026-10-07); then mark to market at the close; close
     check (catches a breach the intrabar test cannot see: a net-flat book,
     or the close-only variant); HW ratchet.

Seam variants (`seam_variant`, review finding on the S3 seam): "csv" runs
the engine on the CSV as is (S3 LONG from 84,121.28, filled on the 04:00Z
bar whose low 84,010.77 sits under the limit); "pending_live" continues the
production Book from the LIVE snapshot (S3 flat, a long limit resting at
the 08:00Z close 83,706.22); "drop_seam" removes the seam trade from the
CSV list and keeps every later trade (a counterfactual, not an engine
path - the verifier's CF1). The trend leg is identical in all three (its
seam state equals the live one).

Halt labels. The executor's `_breach_for` tests DRAWDOWN before DAILY_LOSS
at the poll-time equity. Polling every 20 s, the line it meets FIRST as the
price moves is the HIGHER of the two in equity terms, so the default rule
(`halt_rule="first_cross"`) fills at max(dd_line, daily_line) and labels it
DRAWDOWN only when the drawdown line is the higher one. The literal reading
of the registration (`"dd_first"`: test the worst-intrabar equity against
the drawdown line first, fill at THAT line) is kept as a sensitivity
switch; the two differ only on a bar whose adverse extreme crosses both
lines (a > $30k-from-HW move inside one bar).

Nothing here touches production code or live config. Engine trades come
from research/cagr/harness.leg_trades (the production code path).
"""
from __future__ import annotations

import calendar
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CAGR = os.path.abspath(os.path.join(HERE, "..", "cagr"))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
for _p in (CAGR, BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import harness                                                     # noqa: E402
from harness import Trade, leg_trades, compute_indicators, ts_of    # noqa: E402
from app import volsize                                            # noqa: E402
from app.engine import core                                        # noqa: E402
from app.engine.core import (Bar, Book, BookCfg, Pending, SignalCfg,  # noqa: E402
                             TradeCfg, eval_signal, process_closed_bar,
                             resolve_open_exit)

BAR = 14_400
DAY = 86_400
RUNS_DIR = os.path.join(HERE, "runs")

# ---- the book as deployed 2026-10-07 (PREREG table; frozen here) -----------
BASE = 100_000.0                 # SIZING_BASE_USD
LEV = 1.5                        # LIVE_LEV
W_TREND = 0.30                   # LIVE_W_TREND
W_PULL = 1.0 - W_TREND
KELLY_M_CAP = 0.75
MAX_NOTIONAL = 130_000.0
MAX_ACCOUNT_LEV = 2.0
DD_HALT_PCT = 0.30
DAILY_LOSS_PCT = 0.06
DAILY_LOSS_REF_K = 0.30
FEE_BPS = 4.32                   # measured live, per side, every fill
PAPER_FEE_BPS_SIDE = 6.0         # the live engine's TradeCfg() default: no
#                                  STRATEGY_FILE on the service (render.yaml)
START_EQUITY = 100_000.0
CARRY_START = 30_000.0
HW_SEED = 100_000.0
RESUME_DAYS_B = 7
LEGS = ("pullback", "trend")     # mirror.LEGS order: pullback sized first
WEIGHTS = {"pullback": W_PULL, "trend": W_TREND}
PAPER_SEED = {                   # the engine's own paper books at the seam
    "pullback": dict(equity=104_840.0, peak=107_860.0, dd_halt=0.30),
    "trend": dict(equity=109_343.0, peak=115_992.0, dd_halt=0.50),
}
PAPER_SEED_ERA = {
    "pullback": dict(equity=100_000.0, peak=100_000.0, dd_halt=0.30),
    "trend": dict(equity=100_000.0, peak=100_000.0, dd_halt=0.50),
}
SEED_NOW = 1_791_383_077         # the as-of instant of the seed run
#                                  (2026-10-07 14:24Z -> last closed bar 08:00Z)
LOAD_NOW = time.time()           # "use time.time() once at load" (spec)
SEED_LAST_CLOSED_TS = 1_791_360_000   # 2026-10-07 08:00Z, the seed's seam
SEED_TREND_ENTRY = 80_702.77
SEED_TREND_TRAIL = 83_274.67
SEED_S3_LIVE_LIMIT_TS = SEED_LAST_CLOSED_TS   # live S3: PENDING long limit at
#                                               the 08:00Z close (signal 08:00Z)
BALANCE_DAYS = (91, 182, 273, 365)
SEAM_VARIANTS = ("csv", "pending_live", "drop_seam")

# ---- improvement candidates (CANDIDATES.md, 2026-10-07): OPTIONS, default
# OFF; parameters fixed before any run; production untouched ---------------
FAST_BRAKE_FLOOR = 0.25          # C1: pullback fast vol brake floor
FAST_BRAKE_REF_BARS = 2_190      # C1: reference window (= volsize.VOL_REF)
FAST_BRAKE_MIN_VALID = 0.9       # C1: same fallback convention as volsize
DAMP_DAYS = 5                    # C2: post-stop damper window (days)
DAMP_MULTS = (0.5, 0.25)         # C2: after 1 stop / after >= 2 consecutive stops


@dataclass(frozen=True)
class Options:
    """Candidate logic changes, each an independent switch (default off).

    fast_brake (C1): the pullback leg's entry size is also scaled by
      clip(v_ref / v_now, FAST_BRAKE_FLOOR, 1.0), v_now = ATR14/close at the
      SIGNAL bar, v_ref = median of ATR14/close over the 2,190 bars ending
      at the signal bar (>= 90% valid, else 1.0); m_pull = min(m_live, m_fast).
      The trend leg is untouched.
    post_stop_damper (C2): after a pullback exit by the engine's STOP, a
      pullback entry within DAMP_DAYS of that stop is sized x0.5 (one stop)
      or x0.25 (two or more consecutive stops); a SIGNAL/TIME exit, or an
      entry later than DAMP_DAYS after the last stop, resets the streak.
      The trend leg is untouched."""
    fast_brake: bool = False
    post_stop_damper: bool = False

    def any(self) -> bool:
        return self.fast_brake or self.post_stop_damper

    def tag(self) -> str:
        parts = []
        if self.fast_brake:
            parts.append("C1")
        if self.post_stop_damper:
            parts.append("C2")
        return "+".join(parts) if parts else "base"

ANCHORS = {                      # PREREG scenarios: analogue anchor dates
    "COVID": "2020-02-13",
    "2008": "2021-11-09",
    "1999": "2017-12-17",
}


def _date(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(int(ts)))


def _day(ts: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(int(ts)))


# --------------------------------------------------------------------------
# splice builder
# --------------------------------------------------------------------------
class SplicedBars(list):
    """list[Bar] with the splice bookkeeping attached.

    seam: index of the first PATH bar (bars[:seam] are real closed bars);
    t0: its timestamp; scale: today_close / anchor_close (1.0 in historical
    mode); anchor_ts: the first analogue bar's real timestamp."""
    seam: int = 0
    t0: int = 0
    scale: float = 1.0
    anchor_ts: int = 0
    anchor_close: float = 0.0
    today_close: float = 0.0
    last_real_ts: int = 0
    now_used: float = 0.0
    pair: str = ""
    mode: str = ""
    key: tuple = ()

    @property
    def path(self) -> list[Bar]:
        return self[self.seam:]


def load_closed_bars(pair: str = "btcusd", now: float | None = None) -> list[Bar]:
    """Real bars whose 4h window has closed (ts + 14400 <= now)."""
    now = LOAD_NOW if now is None else now
    return [b for b in harness.load_bars(pair) if b.ts + BAR <= now]


def add_months(date: str, months: int) -> str:
    y, m, d = (int(x) for x in date.split("-"))
    m2 = m - 1 + months
    y2, m2 = y + m2 // 12, m2 % 12 + 1
    last = calendar.monthrange(y2, m2)[1]
    return f"{y2:04d}-{m2:02d}-{min(d, last):02d}"


def build_spliced(pair: str, anchor_date: str, months: int = 12,
                  offset_days: int = 0, now: float | None = None,
                  min_history: int = 2_400) -> SplicedBars:
    """Real closed bars, then the analogue window (anchor + offset, `months`
    calendar months) with O/H/L/C scaled by today_close / anchor_close,
    volume unscaled, timestamps continuing today's 4h grid."""
    real = load_closed_bars(pair, now)
    if len(real) < min_history:
        raise ValueError(f"only {len(real)} closed bars; need {min_history}")
    full = harness.load_bars(pair)
    a_ts = ts_of(anchor_date) + offset_days * DAY
    e_ts = ts_of(add_months(anchor_date, months)) + offset_days * DAY
    win = [b for b in full if a_ts <= b.ts < e_ts]
    if not win or win[0].ts != a_ts:
        raise ValueError(f"no {pair} bar at anchor {_date(a_ts)}")
    for j, b in enumerate(win):
        if b.ts != a_ts + j * BAR:
            raise ValueError(f"gap in analogue window at {_date(b.ts)}")
    today_close = real[-1].close
    scale = today_close / win[0].close
    t0 = real[-1].ts + BAR
    if e_ts > real[-1].ts:
        raise ValueError("analogue window overlaps the live history")
    out = SplicedBars(real)
    out.extend(Bar(ts=t0 + j * BAR, open=b.open * scale, high=b.high * scale,
                   low=b.low * scale, close=b.close * scale, volume=b.volume)
               for j, b in enumerate(win))
    out.seam, out.t0, out.scale = len(real), t0, scale
    out.anchor_ts, out.anchor_close = a_ts, win[0].close
    out.today_close, out.last_real_ts = today_close, real[-1].ts
    out.now_used, out.pair, out.mode = (LOAD_NOW if now is None else now), pair, "splice"
    out.key = ("splice", pair, anchor_date, months, offset_days, real[-1].ts)
    return out


def historical_window(pair: str, start_date: str, end_date: str,
                      now: float | None = None,
                      min_history: int = 2_400) -> SplicedBars:
    """Plain historical mode (no splice): the path is the real bars in
    [start, end), with all earlier real bars as history (seam = start)."""
    real = load_closed_bars(pair, now)
    s_ts, e_ts = ts_of(start_date), ts_of(end_date)
    bars = [b for b in real if b.ts < e_ts]
    seam = next((i for i, b in enumerate(bars) if b.ts >= s_ts), None)
    if seam is None or seam < min_history:
        raise ValueError(f"window {start_date}..{end_date}: seam {seam} needs "
                         f">= {min_history} bars of history")
    out = SplicedBars(bars)
    out.seam, out.t0, out.scale = seam, bars[seam].ts, 1.0
    out.anchor_ts, out.anchor_close = bars[seam].ts, bars[seam].close
    out.today_close, out.last_real_ts = bars[seam - 1].close, bars[seam - 1].ts
    out.now_used, out.pair, out.mode = (LOAD_NOW if now is None else now), pair, "history"
    out.key = ("history", pair, start_date, end_date, bars[-1].ts)
    return out


def synthetic_path(closes: list[float], now: float | None = None,
                   pair: str = "btcusd", ohlc_fn=None) -> SplicedBars:
    """Real history + a synthetic path of closes (tests). Each bar opens at
    the previous close; high/low span open..close unless `ohlc_fn(j, prev,
    close) -> (o, h, l, c)` is given."""
    real = load_closed_bars(pair, now)
    out = SplicedBars(real)
    prev = real[-1].close
    t0 = real[-1].ts + BAR
    for j, c in enumerate(closes):
        if ohlc_fn is not None:
            o, h, l, c = ohlc_fn(j, prev, c)
        else:
            o, h, l = prev, max(prev, c), min(prev, c)
        out.append(Bar(ts=t0 + j * BAR, open=o, high=h, low=l, close=c,
                       volume=real[-1].volume))
        prev = c
    out.seam, out.t0, out.scale = len(real), t0, 1.0
    out.anchor_ts, out.anchor_close = t0, closes[0]
    out.today_close, out.last_real_ts = real[-1].close, real[-1].ts
    out.now_used, out.pair, out.mode = (LOAD_NOW if now is None else now), pair, "synthetic"
    out.key = ("synthetic", pair, real[-1].ts, tuple(closes))
    return out


# --------------------------------------------------------------------------
# engine layer
# --------------------------------------------------------------------------
_ENGINE_CACHE: dict[tuple, dict[str, list[Trade]]] = {}


def engine_trades(bars: SplicedBars, seam_variant: str = "csv") -> dict[str, list[Trade]]:
    """Both legs EXACTLY as the live engine, via harness.leg_trades:
    pullback SignalCfg() / TradeCfg(taker_fee_bps=4.32); trend donchian-20,
    trail 5.0. Cached per path (trades do not depend on K, carry, variant).
    `seam_variant` (module docstring) changes only the pullback leg's seam."""
    if seam_variant not in SEAM_VARIANTS:
        raise ValueError(f"seam_variant must be one of {SEAM_VARIANTS}")
    key = bars.key + (seam_variant,)
    if key not in _ENGINE_CACHE:
        tc = TradeCfg(taker_fee_bps=FEE_BPS)
        base = _ENGINE_CACHE.get(bars.key + ("csv",))
        if base is None:
            base = {
                "pullback": leg_trades(bars, "pullback", scfg=SignalCfg(), tcfg=tc,
                                       leg="pullback"),
                "trend": leg_trades(bars, "donchian", trail_atr=5.0, tcfg=tc,
                                    leg="trend"),
            }
            _ENGINE_CACHE[bars.key + ("csv",)] = base
        if seam_variant == "csv":
            out = base
        elif seam_variant == "drop_seam":
            t0 = bars.t0
            out = dict(base)
            out["pullback"] = [t for t in base["pullback"]
                               if not (t.entry_ts < t0 and
                                       (t.exit_ts is None or t.exit_ts >= t0))]
        else:
            out = dict(base)
            out["pullback"] = pullback_trades_pending_live(bars)
        _ENGINE_CACHE[key] = out
    return _ENGINE_CACHE[key]


def pullback_trades_pending_live(bars: SplicedBars, warmup_bars: int = 210) -> list[Trade]:
    """The pullback leg continued from the LIVE seam snapshot: at the seam
    the production Book is set to the state the live engine reported at
    2026-10-07 08:00Z (no position; a long limit at the last closed bar's
    close, signal_ts = that bar, ATR of that bar) and then run forward with
    the same loop as harness.leg_trades. Everything before the seam is the
    CSV path (its trades are history, priced into the paper-book seed)."""
    tc = TradeCfg(taker_fee_bps=FEE_BPS)
    scfg = SignalCfg()
    inds = compute_indicators(bars, 20)
    cfg = BookCfg(name="pullback", sizing="fixed", strategy="pullback",
                  trail_atr=5.0, leverage=1.0, cap=1.0, start_equity=1.0,
                  dd_halt=1e9)
    book = Book(cfg=cfg)
    for i in range(warmup_bars, len(bars)):
        if i == bars.seam:
            last, ind_last = bars[i - 1], inds[i - 1]
            book.position = None
            book.pending = Pending(side="L", limit=last.close, signal_ts=last.ts,
                                   atr_signal=ind_last.atr14 or 0.0)
        bar, ind = bars[i], inds[i]
        resolve_open_exit(book, bar, tc)
        process_closed_bar(book, bar, ind, scfg, tc, eval_signal(bar, ind, scfg))
    out = [Trade("pullback", t.side, t.entry_ts, t.entry_price, t.exit_ts,
                 t.exit_price, t.exit_reason) for t in book.trades]
    if book.position is not None:
        p = book.position
        out.append(Trade("pullback", p.side, p.entry_ts, p.entry_price, None, None, "OPEN"))
    return out


def engine_state_at(bars: list[Bar], strategy: str, upto: int | None = None,
                    warmup_bars: int = 210) -> Book:
    """The engine Book after processing bars[:upto] - the same loop as
    harness.leg_trades (resolve_open_exit -> signal -> process_closed_bar),
    returned whole so the open position's trail / the pending limit can be
    checked against the live engine. Verification only; trades always come
    from leg_trades."""
    upto = len(bars) if upto is None else upto
    tc = TradeCfg(taker_fee_bps=FEE_BPS)
    scfg = SignalCfg()
    inds = compute_indicators(bars[:upto], 20)
    cfg = BookCfg(name=strategy, sizing="fixed", strategy=strategy,
                  trail_atr=5.0, leverage=1.0, cap=1.0, start_equity=1.0,
                  dd_halt=1e9)
    book = Book(cfg=cfg)
    for i in range(warmup_bars, upto):
        bar, ind = bars[i], inds[i]
        resolve_open_exit(book, bar, tc)
        sig = (core.eval_donchian(bar, ind) if strategy == "donchian"
               else eval_signal(bar, ind, scfg))
        process_closed_bar(book, bar, ind, scfg, tc, sig)
    return book


def paper_book(trades: list[Trade], t0: int, seed: dict, enabled: bool = True,
               fee_bps_side: float = PAPER_FEE_BPS_SIDE) -> tuple[list[Trade], dict]:
    """Emulate the engine's own paper book for one leg from the seam.

    Fixed sizing, leverage 1.0, cap 1.0 (core._size: notional = equity,
    qty rounded to 6 dp), round-trip fee 2 x fee_bps_side on entry notional
    (core._close_position), equity compounding on closed trades only, halt
    when equity / peak - 1 <= -dd_halt at a close (one-way: every later
    entry of this leg is dropped). Returns (published trades, info)."""
    eq, peak, dd_halt = seed["equity"], seed["peak"], seed["dd_halt"]
    rt = 2.0 * fee_bps_side / 10_000.0
    halt_ts, halt_eq, dropped = None, None, 0
    path = []
    out = []
    # margin to the book's own halt line (equity - peak x (1 - dd_halt)):
    # how close the leg came to halting, or by how much it crossed (review
    # finding: the COVID S3 halt is a knife-edge and must be reported as one)
    line = peak * (1.0 - dd_halt)
    min_margin, min_margin_ts, min_eq = eq - line, None, eq
    line_at_halt, margin_at_halt = None, None
    for t in trades:
        if t.exit_ts is not None and t.exit_ts < t0:
            continue                                  # history: priced in the seed
        if halt_ts is not None and t.entry_ts > halt_ts:
            dropped += 1
            continue
        out.append(t)
        if t.exit_ts is None:
            continue                                  # open at the end of data
        qty = round(eq / t.entry_price, 6)
        notional = qty * t.entry_price
        sgn = 1.0 if t.side == "L" else -1.0
        pnl = qty * (t.exit_price - t.entry_price) * sgn - notional * rt
        eq += pnl
        peak = max(peak, eq)
        dd = eq / peak - 1.0
        line = peak * (1.0 - dd_halt)
        path.append((t.exit_ts, round(eq, 2), round(dd, 4)))
        if halt_ts is None and eq - line < min_margin:
            min_margin, min_margin_ts = eq - line, t.exit_ts
        min_eq = min(min_eq, eq)
        if enabled and halt_ts is None and dd <= -dd_halt:
            halt_ts, halt_eq = t.exit_ts, eq
            line_at_halt, margin_at_halt = line, eq - line
    info = dict(halted=halt_ts is not None, halt_ts=halt_ts,
                halt_date=_date(halt_ts) if halt_ts else None,
                equity_at_halt=halt_eq, dropped=dropped, equity_end=eq,
                peak_end=peak, seed=dict(seed), path=path, enabled=enabled,
                line_seed=round(seed["peak"] * (1.0 - dd_halt), 2),
                line_at_halt=(round(line_at_halt, 2) if line_at_halt is not None else None),
                margin_at_halt=(round(margin_at_halt, 2) if margin_at_halt is not None else None),
                min_margin=round(min_margin, 2),
                min_margin_date=(_date(min_margin_ts) if min_margin_ts else None),
                min_equity=round(min_eq, 2))
    return out, info


# --------------------------------------------------------------------------
# executor layer
# --------------------------------------------------------------------------
def daily_loss_pct(K: float) -> float:
    return DAILY_LOSS_PCT * max(1.0, K / DAILY_LOSS_REF_K)


def leg_notional(K: float, leg: str, mult: float) -> float:
    """mirror._leg_frac x base x mult: K x lev x w x 100,000 x size_mult."""
    return min(K, KELLY_M_CAP) * LEV * WEIGHTS[leg] * BASE * mult


def cap_qty(leg: str, want_qty: float, px: float, other_qty: float) -> float:
    """mirror._leg_qty's clamp: this leg may add at most
    min(MAX_NOTIONAL, MAX_ACCOUNT_LEV x base) / px - |other legs' qty|."""
    cap_notional = min(MAX_NOTIONAL, MAX_ACCOUNT_LEV * BASE)
    room = max(0.0, cap_notional / px - other_qty)
    return min(want_qty, room)


@dataclass
class _Pos:
    leg: str
    side: str
    sgn: float
    qty: float
    entry_px: float
    entry_ts: int
    notional: float
    efee: float
    mult: float
    trade: Trade
    kind: str                     # "engine" | "remirror"
    funding: float = 0.0          # net perp funding on this position (+ received)
    mult_live: float = 1.0        # the live size_mult (volsize) before any option
    mult_fast: float = 1.0        # C1 factor (1.0 when off / not binding)
    damp: float = 1.0             # C2 factor (1.0 when off / not damped)
    streak: int = 0               # C2 stop streak in force at this entry


def funding_by_close(btc_funding: dict[int, float] | None) -> dict[int, list[float]]:
    """{bar close ts: [rate_8h, ...]} from {stamp ts (s): rate_8h}: a stamp
    is paid at the first 4h close at or after it (BitMEX 04/12/20Z stamps
    sit on closes; the shift onto today's grid keeps them on it)."""
    out: dict[int, list[float]] = {}
    for s, rate in (btc_funding or {}).items():
        c = -(-int(s) // BAR) * BAR
        out.setdefault(c, []).append(float(rate))
    return out


_ATR_FRAC_CACHE: dict[tuple, np.ndarray] = {}


def atr_frac_series(bars: SplicedBars) -> np.ndarray:
    """ATR14 / close for every bar (the engine's own app.indicators.atr; NaN
    where the ATR is not yet defined). Cached per path."""
    key = bars.key
    if key not in _ATR_FRAC_CACHE:
        from app.indicators import atr as _atr
        a = _atr([b.high for b in bars], [b.low for b in bars], [b.close for b in bars], 14)
        _ATR_FRAC_CACHE[key] = np.array([(x / b.close) if x is not None else np.nan
                                         for x, b in zip(a, bars)], dtype=float)
    return _ATR_FRAC_CACHE[key]


def fast_brake_mult(atr_frac: np.ndarray, i: int | None) -> dict:
    """C1 at signal-bar index i: {'m', 'basis', 'v_now', 'v_ref'}; m = 1.0
    with basis 'insufficient_history' when the window is not >= 90% valid
    (volsize's convention)."""
    if i is None or i < 0:
        return dict(m=1.0, basis="insufficient_history", v_now=None, v_ref=None)
    now = float(atr_frac[i])
    win = atr_frac[max(0, i - FAST_BRAKE_REF_BARS + 1):i + 1]
    valid = win[~np.isnan(win)]
    if now != now or now <= 0 or len(valid) < FAST_BRAKE_MIN_VALID * FAST_BRAKE_REF_BARS:
        return dict(m=1.0, basis="insufficient_history",
                    v_now=(None if now != now else now), v_ref=None)
    ref = float(np.median(valid))
    m = min(1.0, max(FAST_BRAKE_FLOOR, ref / now))
    return dict(m=round(float(m), 4), basis="fast_brake", v_now=now, v_ref=ref)


class Executor:
    """One run of the executor emulation over a path. Use run_executor()."""

    def __init__(self, bars: SplicedBars, published: dict[str, list[Trade]],
                 K: float, carry_value=None, dd_variant: str = "A",
                 intrabar: bool = True, halt_rule: str = "first_cross",
                 start_equity: float = START_EQUITY,
                 carry_start: float = CARRY_START, hw_seed: float = HW_SEED,
                 day_start_seed: float | None = None,
                 btc_funding: dict[int, float] | None = None,
                 options: Options | None = None):
        if dd_variant not in ("A", "B"):
            raise ValueError("dd_variant must be 'A' or 'B'")
        if halt_rule not in ("first_cross", "dd_first"):
            raise ValueError("halt_rule must be 'first_cross' or 'dd_first'")
        self.bars, self.published = bars, published
        self.K = min(float(K), KELLY_M_CAP)
        self.K_raw = float(K)
        self.dpct = daily_loss_pct(self.K)
        self.variant, self.intrabar, self.halt_rule = dd_variant, intrabar, halt_rule
        n = len(bars) - bars.seam
        if carry_value is None:
            self.carry = np.full(n, carry_start, dtype=float)
        else:
            self.carry = np.asarray(carry_value, dtype=float)
            if self.carry.shape != (n,):
                raise ValueError(f"carry_value must have {n} entries (path bars), "
                                 f"got {self.carry.shape}")
        self.carry_start = carry_start
        self.cash = start_equity - carry_start
        self.pos: dict[str, _Pos] = {}
        self.halted: str | None = None
        self.halt_ts: int | None = None
        self.hw = hw_seed
        self.day_start = start_equity if day_start_seed is None else day_start_seed
        self.fees = 0.0
        self.btc_funding_modelled = btc_funding is not None
        self._fund_by_close = funding_by_close(btc_funding)
        self.funding = 0.0                       # net BTC perp funding (+ received)
        self.funding_by_leg = {leg: 0.0 for leg in LEGS}
        self.funding_stamps = 0                  # position-stamps paid/received
        self.events: list[tuple] = []
        self.trades: list[dict] = []
        self.halts: list[dict] = []
        self.ts_out, self.eq_btc_out, self.eq_tot_out = [], [], []
        self.worst_intrabar_out = []
        self.funding_cum_out = []
        # the rails as the executor would have read them on each bar: the
        # day_start in force, the worst equity's margin to each line, and
        # whether the rails were armed (review finding: report the intrabar
        # worst day and the daily-rail consumption)
        self.day_start_out, self.margin_day_out, self.margin_dd_out = [], [], []
        self.armed_out = []
        self.n_entries = 0
        self.closes = harness.closes_of(bars)       # for size_mult (all bars)
        self._by_entry: dict[str, dict[int, Trade]] = {
            leg: {t.entry_ts: t for t in published[leg]} for leg in LEGS}
        self._carry_now = carry_start
        # attribution: realised P&L per leg (net of fees and funding) and the
        # per-bar per-leg mark-to-market (realised + open position) so that
        # eq_btc - 70k == sum over legs at every bar
        self.realised = {leg: 0.0 for leg in LEGS}
        self.leg_mtm_out = {leg: [] for leg in LEGS}
        # candidate options (default off): C1 fast brake, C2 post-stop damper
        self.opt = options or Options()
        self._bar_index = {b.ts: i for i, b in enumerate(bars)} if self.opt.fast_brake else {}
        self._atr_frac = atr_frac_series(bars) if self.opt.fast_brake else None
        self._pb_stop_streak = 0
        self._pb_last_stop_ts: int | None = None
        self.brake_counts = dict(fast_binding=0, damped=0)

    # ---- bookkeeping -----------------------------------------------------
    def _unreal(self, px: float) -> float:
        return sum(p.qty * (px - p.entry_px) * p.sgn for p in self.pos.values())

    def _net_qty(self) -> float:
        return sum(p.qty * p.sgn for p in self.pos.values())

    def _equity(self, px: float) -> float:
        return self.cash + self._unreal(px) + self._carry_now

    def _event(self, ts: int, kind: str, detail: str, equity: float) -> None:
        self.events.append((int(ts), kind, detail, round(float(equity), 2)))

    def _lines(self) -> tuple[float, float]:
        return self.hw - DD_HALT_PCT * BASE, self.day_start - self.dpct * BASE

    def _breach_literal(self, equity: float) -> tuple[str, float] | None:
        """mirror._breach_for at a KNOWN equity level (a poll reading):
        DRAWDOWN first, then DAILY_LOSS. Used at the close and at an open
        that gapped through a line."""
        l_dd, l_day = self._lines()
        if equity < l_dd:
            return "DRAWDOWN", l_dd
        if equity < l_day:
            return "DAILY_LOSS", l_day
        return None

    def _breach_path(self, eq_open: float, eq_worst: float) -> tuple[str, float] | None:
        """(kind, line) for a bar whose equity moves CONTINUOUSLY from
        `eq_open` to `eq_worst` (positions linear in price). The executor,
        polling every 20 s, meets the HIGHER line first, so that is the one
        it halts on (`first_cross`); `dd_first` tests the worst equity
        against the drawdown line first (the registration's literal order).
        A bar that already opened below a line is a jump: literal order at
        the open."""
        l_dd, l_day = self._lines()
        if self.halt_rule == "dd_first":
            if eq_worst < l_dd:
                return "DRAWDOWN", l_dd
            if eq_worst < l_day:
                return "DAILY_LOSS", l_day
            return None
        line = max(l_dd, l_day)
        if eq_open < line:
            return self._breach_literal(eq_open)
        if eq_worst < line:
            return ("DRAWDOWN" if l_dd >= l_day else "DAILY_LOSS"), line
        return None

    # ---- fills -----------------------------------------------------------
    def _open(self, leg: str, t: Trade, px: float, ts: int, kind: str) -> None:
        mult_info = volsize.size_mult(self.closes, t.entry_ts - BAR)
        mult = mult_info["m"]
        mult_live, mult_fast, damp, streak = mult, 1.0, 1.0, 0
        if leg == "pullback" and self.opt.fast_brake:
            fb = fast_brake_mult(self._atr_frac, self._bar_index.get(t.entry_ts - BAR))
            mult_fast = fb["m"]
            if mult_fast < mult:
                self.brake_counts["fast_binding"] += 1
                self._event(ts, "FAST_BRAKE", f"pullback size_mult {mult:.2f} -> {mult_fast:.2f} "
                            f"(ATR/close {fb['v_now']:.4f} vs ref {fb['v_ref']:.4f})",
                            self._equity(px))
            mult = min(mult, mult_fast)
        if leg == "pullback" and self.opt.post_stop_damper:
            if (self._pb_last_stop_ts is not None
                    and ts - self._pb_last_stop_ts <= DAMP_DAYS * DAY and self._pb_stop_streak > 0):
                streak = self._pb_stop_streak
                damp = DAMP_MULTS[min(streak, len(DAMP_MULTS)) - 1]
                self.brake_counts["damped"] += 1
                self._event(ts, "POST_STOP_DAMP", f"pullback x{damp:g} ({streak} consecutive "
                            f"stop{'s' if streak > 1 else ''}, last {_date(self._pb_last_stop_ts)})",
                            self._equity(px))
            else:
                self._pb_stop_streak = 0          # > DAMP_DAYS since the last stop: reset
            mult *= damp
        want_n = leg_notional(self.K, leg, mult)
        want_q = want_n / px
        other = sum(abs(p.qty) for n, p in self.pos.items() if n != leg)
        qty = cap_qty(leg, want_q, px, other)
        if qty < want_q - 1e-12:
            self._event(ts, "CAP_CLAMP",
                        f"{leg} {want_q:.5f}->{qty:.5f} BTC (gross cap "
                        f"{min(MAX_NOTIONAL, MAX_ACCOUNT_LEV * BASE):.0f})",
                        self._equity(px))
        if qty <= 0:
            self._event(ts, "ENTRY_SKIPPED", f"{leg}: no cap room", self._equity(px))
            return
        notional = qty * px
        fee = FEE_BPS / 10_000.0 * notional
        self.cash -= fee
        self.fees += fee
        self.n_entries += 1
        self.pos[leg] = _Pos(leg=leg, side=t.side, sgn=1.0 if t.side == "L" else -1.0,
                             qty=qty, entry_px=px, entry_ts=ts, notional=notional,
                             efee=fee, mult=mult, trade=t, kind=kind,
                             mult_live=mult_live, mult_fast=mult_fast, damp=damp, streak=streak)

    def _close(self, leg: str, px: float, ts: int, reason: str) -> dict:
        p = self.pos.pop(leg)
        gross = p.qty * (px - p.entry_px) * p.sgn
        fee = FEE_BPS / 10_000.0 * p.qty * px
        self.cash += gross - fee
        self.fees += fee
        self.realised[leg] += gross - fee - p.efee + p.funding
        if leg == "pullback" and self.opt.post_stop_damper:
            if reason == "STOP":
                self._pb_stop_streak += 1
                self._pb_last_stop_ts = int(ts)
            elif reason in ("SIGNAL", "TIME"):
                self._pb_stop_streak, self._pb_last_stop_ts = 0, None
            # a HALT_* flatten is the executor's doing, not the engine's verdict
        rec = dict(leg=leg, side=p.side, entry_ts=p.entry_ts, entry_date=_date(p.entry_ts),
                   entry_px=round(p.entry_px, 2), exit_ts=int(ts), exit_date=_date(ts),
                   exit_px=round(px, 2), qty=round(p.qty, 8),
                   notional=round(p.notional, 2), size_mult=p.mult,
                   gross=round(gross, 2), fees=round(fee + p.efee, 2),
                   funding=round(p.funding, 2),
                   pnl=round(gross - fee - p.efee + p.funding, 2), reason=reason, kind=p.kind,
                   engine_entry_ts=p.trade.entry_ts, engine_exit_ts=p.trade.exit_ts,
                   engine_reason=p.trade.reason,
                   mult_live=p.mult_live, mult_fast=p.mult_fast, damp=p.damp, streak=p.streak)
        self.trades.append(rec)
        return rec

    def _pay_funding(self, b: Bar) -> None:
        """BTC perp funding at this bar's close for every position still
        held: a long pays qty x close x rate (positive rate), a short
        receives it. Entered-this-bar positions pay; exited-this-bar ones do
        not (they are gone by the close)."""
        rates = self._fund_by_close.get(b.ts + BAR)
        if not rates or not self.pos:
            return
        for rate in rates:
            for p in self.pos.values():
                pay = -p.sgn * p.qty * b.close * rate
                self.cash += pay
                p.funding += pay
                self.funding += pay
                self.funding_by_leg[p.leg] += pay
                self.funding_stamps += 1

    def _flatten(self, px: float, ts: int, kind: str, line: float, how: str) -> None:
        for leg in list(self.pos):
            self._close(leg, px, ts, f"HALT_{kind}")
        self.halted, self.halt_ts = kind, int(ts)
        eq = self._equity(px)
        self.halts.append(dict(ts=int(ts), date=_date(ts), kind=kind, line=round(line, 2),
                               fill_px=round(px, 2), how=how, equity_after=round(eq, 2),
                               hw=round(self.hw, 2), day_start=round(self.day_start, 2)))
        self._event(ts, f"HALT_{kind}", f"line {line:.0f} ({how}), flattened at {px:.0f}; "
                    f"HW {self.hw:.0f} day_start {self.day_start:.0f}", eq)
        if kind == "DAILY_LOSS":
            # mirror._check_halts: a DAILY flatten that lands below the
            # drawdown line is relabelled so it cannot auto-rearm
            l_dd, _ = self._lines()
            if eq < l_dd:
                self.halted = "DRAWDOWN"
                self.halts[-1]["relabelled"] = "DRAWDOWN"
                self._event(ts, "HALT_RELABEL", "DAILY_LOSS upgraded to DRAWDOWN "
                            f"(equity {eq:.0f} < {l_dd:.0f})", eq)

    def _breach_fill_px(self, line: float, b: Bar) -> float | None:
        """Price at which equity crosses `line` (positions linear in price);
        the open if the bar opened through it. None if the book is net flat."""
        net = self._net_qty()
        if abs(net) < 1e-12:
            return None
        p_star = (line - self.cash - self._carry_now
                  + sum(p.qty * p.entry_px * p.sgn for p in self.pos.values())) / net
        return min(p_star, b.open) if net > 0 else max(p_star, b.open)

    # ---- the bar loop ----------------------------------------------------
    def _remirror(self, b: Bar, why: str) -> None:
        """Enter at the open every engine position still open at this bar
        (the executor re-mirrors the engine's book on t0 / re-arm / resume)."""
        for leg in LEGS:
            if leg in self.pos:
                continue
            for t in self.published[leg]:
                if t.entry_ts < b.ts and (t.exit_ts is None or t.exit_ts >= b.ts):
                    if t.exit_ts == b.ts and t.reason != "STOP":
                        self._event(b.ts, "REMIRROR_SKIP", f"{leg}: engine exits at "
                                    f"this open ({t.reason})", self._equity(b.open))
                        break
                    self._open(leg, t, b.open, b.ts, "remirror")
                    if leg in self.pos:
                        self._event(b.ts, "REMIRROR", f"{leg} {t.side} {self.pos[leg].qty:.5f} "
                                    f"BTC at open {b.open:.0f} ({why})", self._equity(b.open))
                    if t.exit_ts == b.ts and leg in self.pos:
                        # the resting stop is already through: round trip at once
                        fill = (min(t.exit_price, b.open) if t.side == "L"
                                else max(t.exit_price, b.open))
                        self._close(leg, fill, b.ts, "STOP")
                    break

    def run(self) -> None:
        bars, seam = self.bars, self.bars.seam
        remirror = "t0"
        for j in range(len(bars) - seam):
            b = bars[seam + j]
            self._carry_now = float(self.carry[j])
            eq_open = self._equity(b.open)
            # 0) UTC rollover: re-arm DAILY_LOSS (or relabel), reset day_start
            if j > 0 and b.ts % DAY == 0:
                if self.halted == "DAILY_LOSS":
                    l_dd, _ = self._lines()
                    if eq_open < l_dd:
                        self.halted = "DRAWDOWN"
                        self._event(b.ts, "HALT_RELABEL", "DRAWDOWN at rollover: equity "
                                    f"{eq_open:.0f} < HW {self.hw:.0f} - 30% of base; "
                                    "DAILY_LOSS not re-armed", eq_open)
                    else:
                        self.halted = None
                        self.halts[-1]["rearm_ts"] = int(b.ts)
                        self._event(b.ts, "REARM", "DAILY_LOSS cleared at UTC rollover",
                                    eq_open)
                        remirror = "rearm"
                self.day_start = eq_open
            # variant B: Casey resumes a DRAWDOWN halt after 7 days
            if (self.halted == "DRAWDOWN" and self.variant == "B"
                    and b.ts >= self.halt_ts + RESUME_DAYS_B * DAY):
                l_dd, _ = self._lines()
                if eq_open < l_dd:
                    # a plain /resume is refused while the breach is live;
                    # /resume?reanchor=1 moves HW and day_start to equity
                    self.hw = self.day_start = eq_open
                    self._event(b.ts, "RESUME_REANCHOR", f"DRAWDOWN resumed after "
                                f"{RESUME_DAYS_B}d with marks moved to {eq_open:.0f}",
                                eq_open)
                else:
                    self._event(b.ts, "RESUME", f"DRAWDOWN resumed after {RESUME_DAYS_B}d "
                                f"(equity {eq_open:.0f} back above {l_dd:.0f})", eq_open)
                self.halts[-1]["rearm_ts"] = int(b.ts)
                self.halted = None
                remirror = "resume"
            self.hw = max(self.hw, eq_open)
            armed_bar = self.halted is None          # rails live on this bar
            # 1) exits
            for leg in list(self.pos):
                p = self.pos[leg]
                t = p.trade
                if t.exit_ts is not None and t.exit_ts <= b.ts:
                    if t.reason == "STOP":
                        fill = (min(t.exit_price, b.open) if p.sgn > 0
                                else max(t.exit_price, b.open))
                    else:
                        fill = t.exit_price          # SIGNAL / TIME: this open
                    self._close(leg, fill, b.ts, t.reason)
            # 2) entries
            if self.halted is None:
                if remirror:
                    self._remirror(b, remirror)
                    remirror = None
                for leg in LEGS:
                    if leg in self.pos:
                        continue
                    t = self._by_entry[leg].get(b.ts)
                    if t is not None:
                        self._open(leg, t, t.entry_price, b.ts, "engine")
            # 3) intrabar halt check at the bar's adverse extreme
            worst = None
            if self.pos:
                net = self._net_qty()
                if abs(net) >= 1e-12:
                    adverse = b.low if net > 0 else b.high
                    favour = b.high if net > 0 else b.low
                    worst = self._equity(adverse)
                    if self.intrabar:
                        self.hw = max(self.hw, self._equity(favour))
                        br = self._breach_path(self._equity(b.open), worst)
                        if br is not None and self.halted is None:
                            kind, line = br
                            px = self._breach_fill_px(line, b)
                            how = "gap at open" if px == b.open else "at the line"
                            self._flatten(px, b.ts, kind, line, how)
            # 4) BTC perp funding on what is still held at the close; mark to
            #    market at the close; close check; HW ratchet
            self._pay_funding(b)
            eq_close = self._equity(b.close)
            l_dd_test, l_day_test = self._lines()       # lines the bar was tested on
            if self.halted is None:
                # the executor halts on ACCOUNT equity whether or not the
                # BTC book holds anything (a carry-sleeve loss alone trips
                # it and blocks BTC entries); with no positions the flatten
                # is a no-op and only the flag is set
                br = self._breach_literal(eq_close)
                if br is not None:
                    kind, line = br
                    self._flatten(b.close, b.ts, kind, line, "at the close")
                    eq_close = self._equity(b.close)
            self.hw = max(self.hw, eq_close)
            w = eq_close if worst is None else min(worst, eq_close)
            self.ts_out.append(int(b.ts))
            for leg in LEGS:
                p = self.pos.get(leg)
                open_mtm = (p.qty * (b.close - p.entry_px) * p.sgn - p.efee + p.funding) if p else 0.0
                self.leg_mtm_out[leg].append(self.realised[leg] + open_mtm)
            self.eq_btc_out.append(eq_close - self._carry_now)
            self.eq_tot_out.append(eq_close)
            self.worst_intrabar_out.append(w)
            self.funding_cum_out.append(self.funding)
            self.day_start_out.append(self.day_start)
            self.margin_day_out.append(w - l_day_test)
            self.margin_dd_out.append(w - l_dd_test)
            self.armed_out.append(armed_bar)

    def open_positions(self) -> list[dict]:
        if not self.bars:
            return []
        b = self.bars[-1]
        out = []
        for leg, p in self.pos.items():
            gross = p.qty * (b.close - p.entry_px) * p.sgn
            out.append(dict(leg=leg, side=p.side, entry_ts=p.entry_ts,
                            entry_date=_date(p.entry_ts), entry_px=round(p.entry_px, 2),
                            exit_ts=None, exit_date=None, exit_px=None,
                            qty=round(p.qty, 8), notional=round(p.notional, 2),
                            size_mult=p.mult, gross=round(gross, 2), fees=round(p.efee, 2),
                            funding=round(p.funding, 2),
                            pnl=round(gross - p.efee + p.funding, 2), reason="OPEN", kind=p.kind,
                            engine_entry_ts=p.trade.entry_ts, engine_exit_ts=None,
                            engine_reason="OPEN", mtm_px=round(b.close, 2),
                            mult_live=p.mult_live, mult_fast=p.mult_fast, damp=p.damp,
                            streak=p.streak))
        return out


def run_executor(bars: SplicedBars, published: dict[str, list[Trade]], K: float,
                 **kw) -> Executor:
    ex = Executor(bars, published, K, **kw)
    ex.run()
    return ex


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def max_dd(path: np.ndarray) -> float:
    return harness.max_dd(np.asarray(path, dtype=float))


def max_dd_intrabar(start: float, eq_close: list[float], eq_worst: list[float]) -> float:
    """Drawdown of each bar's WORST intrabar equity from the running peak of
    close equity (the drawdown the executor's 20 s polls would have seen)."""
    peak, mdd = start, 0.0
    for c, w in zip(eq_close, eq_worst):
        mdd = min(mdd, w / peak - 1.0)
        peak = max(peak, c)
    return float(mdd)


def worst_day(ts: list[int], eq: list[float], start: float) -> dict:
    """Worst UTC day on close-to-close equity (first day vs `start`)."""
    days: dict[str, float] = {}
    for t, e in zip(ts, eq):
        days[_day(t)] = e                      # last close of the day wins
    prev, worst = start, None
    for d, e in days.items():
        r = e / prev - 1.0
        if worst is None or r < worst["pct"]:
            worst = dict(date=d, pct=r, usd=e - prev, from_equity=prev, to_equity=e)
        prev = e
    return worst or dict(date=None, pct=0.0, usd=0.0)


def worst_day_intrabar(ts: list[int], worst: list[float], day_start: list[float],
                       armed: list[bool] | None = None) -> dict:
    """Worst UTC day on the executor's own reading (mirror._breach_for at a
    20 s poll): each bar's worst intrabar equity against the day_start in
    force on that bar (equity at the day's 00:00 open; the start equity on
    the first partial day). Bars with the rails disarmed are skipped."""
    armed = [True] * len(ts) if armed is None else armed
    days: dict[str, tuple[float, float]] = {}
    for t, w, ds, a in zip(ts, worst, day_start, armed):
        if not a:
            continue
        d = _day(t)
        cur = days.get(d)
        if cur is None or w < cur[0]:
            days[d] = (float(w), float(ds))
    out = None
    for d, (w, ds) in days.items():
        usd = w - ds
        if out is None or usd < out["usd"]:
            out = dict(date=d, pct=usd / ds, usd=usd, from_equity=ds, to_equity=w)
    return out or dict(date=None, pct=0.0, usd=0.0)


def rail_use(ts: list[int], margin_day: list[float], margin_dd: list[float],
             armed: list[bool], dpct: float) -> dict:
    """How much of each executor rail the worst intrabar equity consumed:
    budget = the line's distance from its anchor (dpct x base for the daily
    rail, 30% x base for the drawdown rail); used = budget - min margin."""
    out = {}
    for name, margins, budget in (("daily_loss", margin_day, dpct * BASE),
                                  ("drawdown", margin_dd, DD_HALT_PCT * BASE)):
        best, best_ts = None, None
        for t, m, a in zip(ts, margins, armed):
            if a and (best is None or m < best):
                best, best_ts = float(m), int(t)
        out[name] = dict(budget=round(budget, 2),
                         min_margin=(round(best, 2) if best is not None else None),
                         date=(_date(best_ts) if best_ts is not None else None),
                         used_pct=(round((budget - best) / budget, 4) if best is not None else None))
    return out


def balances_at(ts: list[int], eq: list[float], t0: int,
                days=BALANCE_DAYS) -> dict:
    """Equity at the close of the last bar OPENING <= t0 + d days. `exact`
    is judged on the bar's CLOSE timestamp (ts + BAR == target): True when
    that close sits on the instant. `shortfall_s` = target - close: a
    NEGATIVE value means the close is that far AFTER the instant (the bar
    opening on it), a positive one that the path ended before it. On the
    365-day analogue windows (2,190 bars) the day-365 balance is the last
    path bar, which closes exactly on day 365; the COVID window (leap year,
    2,196 bars) and every 91/182/273-day balance are the close 4h after the
    instant (re-verification finding, 2026-10-07: the first reading judged
    exactness on the bar's open and had it the wrong way round)."""
    out = {}
    ts_a = np.asarray(ts)
    for d in days:
        target = t0 + d * DAY
        idx = np.searchsorted(ts_a, target, side="right") - 1
        if idx < 0:
            out[str(d)] = None
        else:
            close_ts = int(ts_a[idx]) + BAR
            out[str(d)] = dict(equity=round(float(eq[idx]), 2), ts=int(ts_a[idx]),
                               date=_date(ts_a[idx]), close_date=_date(close_ts),
                               exact=bool(close_ts == target),
                               shortfall_s=int(target - close_ts))
    return out


# --------------------------------------------------------------------------
# scenario runner
# --------------------------------------------------------------------------
def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")


def _trade_dict(t: Trade) -> dict:
    return dict(leg=t.leg, side=t.side, entry_ts=t.entry_ts, entry_date=_date(t.entry_ts),
                entry_price=t.entry_price, exit_ts=t.exit_ts,
                exit_date=_date(t.exit_ts) if t.exit_ts else None,
                exit_price=t.exit_price, reason=t.reason)


def run_path(name: str, bars: SplicedBars, K: float, carry_value=None,
             dd_variant: str = "A", intrabar: bool = True,
             engine_halts: bool = True, halt_rule: str = "first_cross",
             paper_seed: dict | None = None, start_equity: float = START_EQUITY,
             carry_start: float = CARRY_START, save: bool = True,
             extra: dict | None = None, btc_funding: dict[int, float] | None = None,
             seam_variant: str = "csv", options: Options | None = None) -> dict:
    """Engine (leg_trades) -> paper-book halts -> executor over `bars`.
    btc_funding: {stamp ts (s, on today's grid): rate_8h} paid on the BTC
    book's own positions (None = not modelled); seam_variant: module
    docstring; options: candidate switches (Options; None = the book as
    deployed)."""
    options = options or Options()
    paper_seed = PAPER_SEED if paper_seed is None else paper_seed
    raw = engine_trades(bars, seam_variant)
    published, eh = {}, {}
    for leg in LEGS:
        published[leg], eh[leg] = paper_book(raw[leg], bars.t0, paper_seed[leg],
                                             enabled=engine_halts)
    ex = run_executor(bars, published, K, carry_value=carry_value,
                      dd_variant=dd_variant, intrabar=intrabar,
                      halt_rule=halt_rule, start_equity=start_equity,
                      carry_start=carry_start, btc_funding=btc_funding, options=options)
    eq_tot = np.asarray(ex.eq_tot_out)
    eq_btc = np.asarray(ex.eq_btc_out)
    ts = ex.ts_out
    closes = [b.close for b in bars.path]
    c0 = closes[0]
    bench = [start_equity * c / c0 for c in closes]
    path = np.concatenate([[start_equity], eq_tot])
    btc_path = np.concatenate([[start_equity - carry_start], eq_btc])
    bench_path = np.concatenate([[start_equity], bench])
    wd = worst_day(ts, list(eq_tot), start_equity)
    wdi = worst_day_intrabar(ts, ex.worst_intrabar_out, ex.day_start_out, ex.armed_out)
    rails = rail_use(ts, ex.margin_day_out, ex.margin_dd_out, ex.armed_out, ex.dpct)
    trades = ex.trades + ex.open_positions()
    res = dict(
        name=name, mode=bars.mode, pair=bars.pair, K=ex.K, K_raw=ex.K_raw,
        dd_variant=dd_variant, intrabar=intrabar, engine_halts=engine_halts,
        halt_rule=halt_rule, daily_loss_pct=ex.dpct, seam_variant=seam_variant,
        options=dict(fast_brake=options.fast_brake, post_stop_damper=options.post_stop_damper,
                     tag=options.tag()),
        brake_counts=dict(ex.brake_counts),
        leg_mtm={leg: [round(float(x), 2) for x in ex.leg_mtm_out[leg]] for leg in LEGS},
        realised_by_leg={leg: round(ex.realised[leg], 2) for leg in LEGS},
        years=len(closes) * BAR / (365.25 * DAY),
        carry_modelled=carry_value is not None,
        btc_funding_modelled=ex.btc_funding_modelled,
        btc_funding_total=round(ex.funding, 2),
        btc_funding_by_leg={leg: round(v, 2) for leg, v in ex.funding_by_leg.items()},
        btc_funding_stamps=ex.funding_stamps,
        btc_funding_cum=[round(float(x), 2) for x in ex.funding_cum_out],
        worst_day_intrabar=wdi, rail_use=rails,
        day_start=[round(float(x), 2) for x in ex.day_start_out],
        margin_daily=[round(float(x), 2) for x in ex.margin_day_out],
        margin_drawdown=[round(float(x), 2) for x in ex.margin_dd_out],
        rails_armed=list(ex.armed_out),
        t0=bars.t0, t0_date=_date(bars.t0), seam=bars.seam, scale=bars.scale,
        anchor_ts=bars.anchor_ts, anchor_date=_date(bars.anchor_ts),
        anchor_close=bars.anchor_close, today_close=bars.today_close,
        last_real_ts=bars.last_real_ts, last_real_date=_date(bars.last_real_ts),
        now_used=bars.now_used, n_path_bars=len(closes),
        ts=ts, equity_total=[round(float(x), 2) for x in eq_tot],
        equity_btc=[round(float(x), 2) for x in eq_btc],
        bench_hold_btc=[round(float(x), 2) for x in bench],
        carry_value=[round(float(x), 2) for x in ex.carry],
        worst_intrabar_equity=[round(float(x), 2) for x in ex.worst_intrabar_out],
        events=ex.events, trades=trades, halts=ex.halts, engine_halts_info=eh,
        balances=balances_at(ts, list(eq_tot), bars.t0),
        balances_btc=balances_at(ts, list(eq_btc), bars.t0),
        balances_bench=balances_at(ts, bench, bars.t0),
        final_equity=round(float(eq_tot[-1]), 2),
        max_dd=round(float(max_dd(path)), 4),
        max_dd_btc_book=round(float(max_dd(btc_path)), 4),
        max_dd_bench=round(float(max_dd(bench_path)), 4),
        max_dd_intrabar=round(max_dd_intrabar(start_equity, list(eq_tot),
                                              ex.worst_intrabar_out), 4),
        worst_day=wd, fees=round(ex.fees, 2), n_trades=len(ex.trades),
        n_entries=ex.n_entries, n_open=len(ex.pos),
        halts_count=len(ex.halts), hw_end=round(ex.hw, 2),
        engine_trades={leg: [_trade_dict(t) for t in raw[leg]
                             if t.exit_ts is None or t.exit_ts >= bars.t0]
                       for leg in LEGS},
        published_trades={leg: [_trade_dict(t) for t in published[leg]] for leg in LEGS},
        spliced_closes=[(int(b.ts), round(b.close, 4)) for b in bars.path],
        history_tail_closes=[(int(b.ts), b.close) for b in
                             bars[max(0, bars.seam - volsize.NEED_BARS - 10):bars.seam]],
        constants=dict(BASE=BASE, LEV=LEV, W_TREND=W_TREND, KELLY_M_CAP=KELLY_M_CAP,
                       MAX_NOTIONAL=MAX_NOTIONAL, MAX_ACCOUNT_LEV=MAX_ACCOUNT_LEV,
                       DD_HALT_PCT=DD_HALT_PCT, DAILY_LOSS_PCT=DAILY_LOSS_PCT,
                       DAILY_LOSS_REF_K=DAILY_LOSS_REF_K, FEE_BPS=FEE_BPS,
                       PAPER_FEE_BPS_SIDE=PAPER_FEE_BPS_SIDE, START_EQUITY=start_equity,
                       CARRY_START=carry_start, HW_SEED=HW_SEED,
                       RESUME_DAYS_B=RESUME_DAYS_B, paper_seed=paper_seed),
    )
    if extra:
        res.update(extra)
    if save:
        os.makedirs(RUNS_DIR, exist_ok=True)
        carry_tag = ("carry" + (res.get("carry_funding_source") or "")
                     if carry_value is not None else "nocarry")
        fn = _slug(f"{name}_K{ex.K:g}_off{res.get('offset_days', 0):+d}_{dd_variant}_"
                   f"{'intra' if intrabar else 'close'}_{'eh' if engine_halts else 'noeh'}_"
                   f"{halt_rule}_{carry_tag}_"
                   f"{'bfund' if btc_funding is not None else 'nobfund'}_{seam_variant}"
                   + (f"_opt{options.tag()}" if options.any() else ""))
        res["file"] = os.path.join(RUNS_DIR, fn + ".json")
        with open(res["file"], "w") as fh:
            json.dump(res, fh)
    return res


def run_scenario(name: str, anchor: str, K: float, offset_days: int = 0,
                 carry_value=None, dd_variant: str = "A", intrabar: bool = True,
                 engine_halts: bool = True, halt_rule: str = "first_cross",
                 months: int = 12, pair: str = "btcusd", now: float | None = None,
                 save: bool = True, btc_funding: dict[int, float] | None = None,
                 seam_variant: str = "csv", options: Options | None = None) -> dict:
    """Spliced crash scenario for the BTC book + executor guards.

    name: label ("COVID"/"2008"/"1999" or anything); anchor: the analogue's
    pre-crash peak date (YYYY-MM-DD) or a key of ANCHORS; K: KELLY_M (clamped
    to KELLY_M_CAP 0.75); offset_days: shift of the analogue window (PREREG
    -28..+28); carry_value: per-path-bar value of the carry sleeve (None =
    a flat 30,000); dd_variant 'A' (DRAWDOWN stays flat) / 'B' (resumes after
    7 days); intrabar: test the halts on the bar's worst intrabar equity
    (False = close only, for the sensitivity table); engine_halts: emulate
    the engine's own paper-book halts; halt_rule: see module docstring;
    now: as-of instant for "last closed bar" (None = module load time)."""
    anchor_date = ANCHORS.get(anchor, anchor)
    bars = build_spliced(pair, anchor_date, months=months, offset_days=offset_days,
                         now=now)
    return run_path(name, bars, K, carry_value=carry_value, dd_variant=dd_variant,
                    intrabar=intrabar, engine_halts=engine_halts, halt_rule=halt_rule,
                    paper_seed=PAPER_SEED, save=save, btc_funding=btc_funding,
                    seam_variant=seam_variant, options=options,
                    extra=dict(offset_days=offset_days, anchor_input=anchor,
                               anchor_date_input=anchor_date, months=months))


def run_era(name: str, start_date: str, end_date: str, K: float,
            carry_value=None, dd_variant: str = "A", intrabar: bool = True,
            engine_halts: bool = True, halt_rule: str = "first_cross",
            pair: str = "btcusd", now: float | None = None, save: bool = True,
            btc_funding: dict[int, float] | None = None,
            options: Options | None = None) -> dict:
    """Plain historical window (no splice): paper books seeded 100k/100k,
    account 100k, HW 100k; any engine position open at the era start is
    re-mirrored at the first bar's open, as at t0 of a splice."""
    bars = historical_window(pair, start_date, end_date, now=now)
    return run_path(name, bars, K, carry_value=carry_value, dd_variant=dd_variant,
                    intrabar=intrabar, engine_halts=engine_halts, halt_rule=halt_rule,
                    paper_seed=PAPER_SEED_ERA, save=save, btc_funding=btc_funding,
                    options=options,
                    extra=dict(offset_days=0, start_date=start_date, end_date=end_date))


def summary_lines(r: dict) -> list[str]:
    bal = r["balances"]
    L = [f"{r['name']}  K={r['K']:g} off={r.get('offset_days', 0):+d} var={r['dd_variant']} "
         f"intrabar={r['intrabar']} engine_halts={r['engine_halts']} rule={r['halt_rule']} "
         f"carry={'yes' if r['carry_modelled'] else 'flat 30k'}",
         f"  t0 {r['t0_date']}  seam bar {r['seam']}  last real {r['last_real_date']} "
         f"close {r['today_close']:.2f}  anchor {r['anchor_date']} close {r['anchor_close']:.2f} "
         f"scale {r['scale']:.5f}  path bars {r['n_path_bars']}",
         "  balances (total):  " + "  ".join(
             f"{d}d {bal[d]['equity']:,.0f}" if bal[d] else f"{d}d n/a" for d in bal),
         "  balances (BTC book, from 70k):  " + "  ".join(
             f"{d}d {r['balances_btc'][d]['equity']:,.0f}" for d in r['balances_btc']
             if r['balances_btc'][d]),
         "  hold-BTC bench:  " + "  ".join(
             f"{d}d {r['balances_bench'][d]['equity']:,.0f}" for d in r['balances_bench']
             if r['balances_bench'][d]),
         f"  final {r['final_equity']:,.0f}  maxDD(MTM close) {r['max_dd']:.2%}  "
         f"maxDD(intrabar worst) {r['max_dd_intrabar']:.2%}  BTC-book maxDD {r['max_dd_btc_book']:.2%}  "
         f"bench maxDD {r['max_dd_bench']:.2%}",
         f"  worst day close-to-close {r['worst_day']['date']} {r['worst_day']['pct']:.2%} "
         f"({r['worst_day']['usd']:+,.0f})  intrabar vs day_start {r['worst_day_intrabar']['date']} "
         f"{r['worst_day_intrabar']['pct']:.2%} ({r['worst_day_intrabar']['usd']:+,.0f})",
         f"  rails: daily-loss used {r['rail_use']['daily_loss']['used_pct']:.0%} of "
         f"{r['rail_use']['daily_loss']['budget']:,.0f} ({r['rail_use']['daily_loss']['date']})  "
         f"drawdown used {r['rail_use']['drawdown']['used_pct']:.0%} of "
         f"{r['rail_use']['drawdown']['budget']:,.0f} ({r['rail_use']['drawdown']['date']})",
         f"  fees {r['fees']:,.0f}  BTC perp funding "
         + (f"{r['btc_funding_total']:+,.0f} (pullback {r['btc_funding_by_leg']['pullback']:+,.0f}, "
            f"trend {r['btc_funding_by_leg']['trend']:+,.0f}; {r['btc_funding_stamps']} position-stamps)"
            if r["btc_funding_modelled"] else "NOT modelled")
         + f"  trades {r['n_trades']} (+{r['n_open']} open)  halts {r['halts_count']}  "
         f"HW end {r['hw_end']:,.0f}  seam {r['seam_variant']}"]
    for leg in LEGS:
        e = r["engine_halts_info"][leg]
        L.append(f"  engine book {leg}: " + (
            f"HALTED {e['halt_date']} at paper equity {e['equity_at_halt']:,.0f} "
            f"(line {e['line_at_halt']:,.0f}, margin {e['margin_at_halt']:+,.0f}; "
            f"dropped {e['dropped']} later trades)" if e["halted"] else
            f"no halt (paper equity end {e['equity_end']:,.0f}, peak {e['peak_end']:,.0f}; "
            f"closest to its line {e['min_margin']:+,.0f} on {e['min_margin_date']})"))
    for ev in r["events"]:
        L.append(f"  event {_date(ev[0])} {ev[1]:16s} eq {ev[3]:>10,.0f}  {ev[2]}")
    return L


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="COVID")
    ap.add_argument("--anchor", default=None)
    ap.add_argument("--K", type=float, default=0.75)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--variant", default="A")
    ap.add_argument("--close-only", action="store_true")
    ap.add_argument("--no-engine-halts", action="store_true")
    ap.add_argument("--halt-rule", default="first_cross")
    ap.add_argument("--now", type=float, default=None)
    ap.add_argument("--seam", default="csv", choices=SEAM_VARIANTS)
    a = ap.parse_args()
    r = run_scenario(a.name, a.anchor or a.name, a.K, a.offset, None, a.variant,
                     not a.close_only, not a.no_engine_halts, a.halt_rule, now=a.now,
                     seam_variant=a.seam)
    print("\n".join(summary_lines(r)))
    print("  saved", r["file"])
