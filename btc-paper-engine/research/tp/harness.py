"""Take-profit study harness (RESEARCH_TP.md, research/tp/PREREG.md).

Research only - the live engine is untouched. The S4 path below is a
variant-aware copy of core._process_donchian. With the BASE variant it must
reproduce run_replay's S4 trade list field for field (test_harness.py G1);
every take-profit rule is a hook added around that verbatim core.

Conventions (fixed in PREREG.md before any variant ran):
- Resting orders (trail, take-profit limits, breakeven and channel stops) are
  tested from the bar AFTER the fill, as the engine does for the trail.
- Same bar touches a stop and a take-profit: the STOP fills (pessimistic).
- A bar that opens through a resting level fills at the open.
- Close-based rules (overextension, RSI, time, climax, ER fade, volume
  climax, placebo) are judged at a bar's close and fill at the NEXT open.
- Take-profit distances use ATR known when the order is placed: the signal
  bar's ATR (Pending.atr_signal), never the fill bar's.
- Fees: the registered research basis, 6 bps/side on entry notional, charged
  at each close (partials pro rata).
"""
from __future__ import annotations

import calendar
import csv
import gzip
import math
import os
import random
import sys
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))

from app.config import (LIVE_LEV, LIVE_W_TREND, RESEARCH_BOOKS,  # noqa: E402
                        RESEARCH_SIGNAL, RESEARCH_TRADE)
from app.engine.core import (BAR_SECONDS, Bar, Book, ClosedTrade,  # noqa: E402
                             Ind, Pending, Position, _close_position,
                             _mark_to_market, _size, eval_donchian,
                             eval_signal, process_closed_bar,
                             resolve_open_exit)
from app.engine.replay import compute_indicators  # noqa: E402

S3_CFG = next(b for b in RESEARCH_BOOKS if b.name == "S3")
S4_CFG = next(b for b in RESEARCH_BOOKS if b.name == "S4")
WARMUP = 210                      # run_replay default
BARS_PER_YEAR = 2190


def ts(y, m, d, h=0):
    return calendar.timegm((y, m, d, h, 0, 0))


T_2013 = ts(2013, 1, 1)
T_2022 = ts(2022, 1, 1)
T_IS_END = ts(2026, 7, 31, 20)    # last 4h bar of the in-sample period
T_FWD = ts(2026, 9, 1)            # forward window (reported, not gating)


# --------------------------------------------------------------------- data
def load_bars(path: str) -> list[Bar]:
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt") as f:
        return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                    high=float(r["high"]), low=float(r["low"]),
                    close=float(r["close"]), volume=float(r["volume"]))
                for r in csv.DictReader(f)]


@dataclass
class Asset:
    name: str
    bars: list
    inds: list
    hi10: list
    lo10: list
    er20: list
    atr_prev: list


def prepare(name: str, bars: list[Bar]) -> Asset:
    inds = compute_indicators(bars)
    n = len(bars)
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    hi10, lo10 = [None] * n, [None] * n
    for i in range(10, n):                     # prior 10 bars, as hi20/lo20
        hi10[i] = max(highs[i - 10:i])
        lo10[i] = min(lows[i - 10:i])
    er20 = [None] * n
    for i in range(20, n):
        den = sum(abs(closes[k] - closes[k - 1]) for k in range(i - 19, i + 1))
        er20[i] = abs(closes[i] - closes[i - 20]) / den if den > 0 else None
    atr_prev = [None] + [inds[i - 1].atr14 for i in range(1, n)]
    return Asset(name, bars, inds, hi10, lo10, er20, atr_prev)


DATA = os.path.join(HERE, "data")


def load_asset(sym: str) -> Asset:
    return prepare(sym, load_bars(os.path.join(DATA, f"{sym}usd_4h.csv.gz")))


# ------------------------------------------------------------------ variants
@dataclass(frozen=True)
class V:
    name: str = "BASE"
    tp_k: float | None = None        # full TP: resting limit at entry -/+ k*atr0
    ptp_k: float | None = None       # partial TP level (k*atr0)
    ptp_f: float = 0.0               # fraction of the ORIGINAL qty taken there
    lock_k: float | None = None      # once close-MFE >= k*atr0 ...
    lock_m: float = 5.0              # ... the trail multiple drops to m
    be_k: float | None = None        # once close-MFE >= k*atr0: stop at entry
    ext_z: float | None = None       # favorable |close - SMA50| / ATR >= z
    rsi_l: float | None = None       # RSI14 <= l (short) / >= 100 - l (long)
    time_n: int | None = None        # bars held >= n
    chan_n: int | None = None        # resting stop at prior n-bar high/low
    climax_k: float | None = None    # favorable open->close >= k*ATR(prev bar)
    er_k: float | None = None        # close-MFE >= k*atr0 AND ER20 < er_x
    er_x: float | None = None
    volx_v: float | None = None      # favorable bar >= 1.5*ATR(prev) and volume >= v*SMA20(vol)
    placebo_q: float | None = None   # null: per-bar hazard of a random exit
    placebo_f: float = 1.0           # fraction closed by a placebo exit
    seed: int = 0
    cool_n: int | None = None        # AMENDMENT 1: after a profit-taking full exit,
    #                                  block same-side entries for n bars ("stand aside")


BASE = V()
# Full exits that take profit (AMENDMENT 1). Stop-type exits - the trail,
# breakeven and channel stops - re-arm entries at once, exactly as today.
PROFIT_EXITS = {"TP", "EXT", "RSI", "TIME", "CLIMAX", "ER", "VOLX", "PLACEBO"}


# --------------------------------------------------------------- accounting
def _close_part(book: Book, pos: Position, qty: float, exit_ts: int,
                exit_price: float, reason: str) -> None:
    """Close `qty` of `pos` with the engine's accounting, pro rata. The halt
    check stays with the final full close (_close_position), as in the
    engine, which only checks dd there."""
    sgn = 1.0 if pos.side == "L" else -1.0
    notional = qty * pos.entry_price
    fees = notional * pos.fee_bps / 10_000.0
    pnl = qty * (exit_price - pos.entry_price) * sgn - fees
    eq_before = book.equity
    book.equity += pnl
    book.peak_equity = max(book.peak_equity, book.equity)
    book.trades.append(ClosedTrade(
        book=book.cfg.name, side=pos.side, signal_ts=pos.signal_ts,
        entry_ts=pos.entry_ts, entry_price=pos.entry_price, qty=qty,
        notional=notional, stop_price=pos.stop_price,
        atr_at_entry=pos.atr_at_entry, exit_ts=exit_ts, exit_price=exit_price,
        exit_reason=reason, bars_held=(exit_ts - pos.entry_ts) // BAR_SECONDS,
        fees_usd=fees, pnl_usd=pnl,
        pnl_pct=pnl / notional * 100 if notional else 0.0,
        equity_before=eq_before, equity_after=book.equity))
    pos.qty = round(pos.qty - qty, 6)
    pos.notional = pos.qty * pos.entry_price


def _close_full(book: Book, pos: Position, exit_ts: int, exit_price: float,
                reason: str, tcfg) -> None:
    _close_position(book, pos, exit_ts, exit_price, reason, tcfg)
    if reason in PROFIT_EXITS:
        book._cool = (pos.side, exit_ts)


# ------------------------------------------------------------------ S4 step
def _fresh_state(atr0: float, entry: float) -> dict:
    return dict(atr0=atr0, best=entry, lock_on=False, be_on=False,
                ptp_done=False, flag=None, flag_f=1.0, placebo_done=False,
                mfe_px=entry)


def s4_step(book: Book, bar: Bar, ind: Ind, i: int, A: Asset, tcfg,
            signal, v: V, rng: random.Random) -> None:
    st = book._st
    pos = book.position
    # (0) a close-based exit flagged at the previous close fills at this open
    if pos is not None and st.get("flag"):
        f = st["flag_f"]
        if f >= 1.0:
            _close_full(book, pos, bar.ts, bar.open, st["flag"], tcfg)
            pos = None
        else:
            q = round(pos.qty * f, 6)
            if 0 < q < pos.qty:
                _close_part(book, pos, q, bar.ts, bar.open, st["flag"])
            st["flag"], st["flag_f"] = None, 1.0
    # (1) pending entry - engine verbatim
    if book.pending is not None:
        p = book.pending
        book.pending = None
        if ind.atr14 is not None:
            qty, notional = _size(book, p.side, bar.open, ind.atr14, tcfg)
            if qty > 0:
                book.position = Position(
                    side=p.side, entry_ts=bar.ts, entry_price=bar.open,
                    qty=qty, notional=notional, stop_price=0.0,
                    atr_at_entry=ind.atr14, signal_ts=p.signal_ts,
                    fee_bps=2 * tcfg.taker_fee_bps)
                book._st = st = _fresh_state(p.atr_signal, bar.open)
    pos = book.position
    if pos is None:
        pass
    else:
        L = pos.side == "L"
        st["mfe_px"] = max(st["mfe_px"], bar.high) if L else min(st["mfe_px"], bar.low)
        atr0 = st["atr0"] if st["atr0"] and st["atr0"] > 0 else None
        after_fill = bar.ts > pos.entry_ts
        # (2) resting stops: engine trail, plus breakeven and channel stops;
        #     the tightest one is the order that would fill first.
        if after_fill:
            cands = []
            if pos.trail is not None:
                cands.append((pos.trail, "STOP"))
            if v.be_k is not None and st["be_on"]:
                cands.append((pos.entry_price, "BE"))
            if v.chan_n is not None:
                lvl = (A.lo10[i] if v.chan_n == 10 else ind.lo20) if L else \
                      (A.hi10[i] if v.chan_n == 10 else ind.hi20)
                if lvl is not None:
                    cands.append((lvl, "CHAN"))
            if cands:
                lvl, why = (max(cands) if L else min(cands))
                hit = bar.low <= lvl if L else bar.high >= lvl
                if hit:
                    fill = min(lvl, bar.open) if L else max(lvl, bar.open)
                    _close_full(book, pos, bar.ts, fill, why, tcfg)
                    pos = None
            # resting take-profit limits (only if no stop filled this bar)
            if pos is not None and atr0 is not None:
                for k, frac, tag in ((v.ptp_k, v.ptp_f, "TP_PART"),
                                     (v.tp_k, 1.0, "TP")):
                    if pos is None or k is None:
                        continue
                    if tag == "TP_PART" and (st["ptp_done"] or frac <= 0):
                        continue
                    lvl = pos.entry_price + k * atr0 if L else pos.entry_price - k * atr0
                    hit = bar.high >= lvl if L else bar.low <= lvl
                    if not hit:
                        continue
                    fill = max(lvl, bar.open) if L else min(lvl, bar.open)
                    if tag == "TP":
                        _close_full(book, pos, bar.ts, fill, "TP", tcfg)
                        pos = None
                    else:
                        q = round(pos.qty * frac, 6) if not st["ptp_done"] else 0
                        # frac is of the ORIGINAL qty; nothing was taken before
                        if 0 < q < pos.qty:
                            _close_part(book, pos, q, bar.ts, fill, "TP_PART")
                        st["ptp_done"] = True
        # (3) survivors ratchet the trail from this close (engine, with the
        #     profit-lock multiple once it is on)
        if pos is not None and ind.atr14 is not None:
            mult = v.lock_m if (v.lock_k is not None and st["lock_on"]) else book.cfg.trail_atr
            lvl = (bar.close - mult * ind.atr14 if L else bar.close + mult * ind.atr14)
            pos.trail = (lvl if pos.trail is None else
                         (max(pos.trail, lvl) if L else min(pos.trail, lvl)))
            pos.stop_price = pos.trail
        # (4) close-based state and exit flags, judged after the fill bar
        if pos is not None and after_fill:
            c = bar.close
            st["best"] = max(st["best"], c) if L else min(st["best"], c)
            mfe_atr = None
            if atr0 is not None:
                mfe_atr = ((st["best"] - pos.entry_price) if L else
                           (pos.entry_price - st["best"])) / atr0
                if v.lock_k is not None and mfe_atr >= v.lock_k:
                    st["lock_on"] = True
                if v.be_k is not None and mfe_atr >= v.be_k:
                    st["be_on"] = True
            flag = None
            a = ind.atr14
            ap = A.atr_prev[i]
            held = (bar.ts - pos.entry_ts) // BAR_SECONDS
            if v.ext_z is not None and ind.sma50 is not None and a:
                d = ((c - ind.sma50) if L else (ind.sma50 - c)) / a
                if d >= v.ext_z:
                    flag = "EXT"
            if flag is None and v.rsi_l is not None and ind.rsi14 is not None:
                if (ind.rsi14 >= 100 - v.rsi_l) if L else (ind.rsi14 <= v.rsi_l):
                    flag = "RSI"
            if flag is None and v.time_n is not None and held >= v.time_n:
                flag = "TIME"
            if flag is None and v.climax_k is not None and ap:
                mv = (c - bar.open) if L else (bar.open - c)
                if mv >= v.climax_k * ap:
                    flag = "CLIMAX"
            if (flag is None and v.er_k is not None and mfe_atr is not None
                    and A.er20[i] is not None):
                if mfe_atr >= v.er_k and A.er20[i] < v.er_x:
                    flag = "ER"
            if flag is None and v.volx_v is not None and ap and ind.vol_sma20:
                mv = (c - bar.open) if L else (bar.open - c)
                if mv >= 1.5 * ap and bar.volume >= v.volx_v * ind.vol_sma20:
                    flag = "VOLX"
            if flag is not None:
                st["flag"], st["flag_f"] = flag, 1.0
            elif v.placebo_q is not None and not st["placebo_done"]:
                if rng.random() < v.placebo_q:
                    st["flag"], st["flag_f"] = "PLACEBO", v.placebo_f
                    st["placebo_done"] = True
    # (5) new entry - engine verbatim, plus AMENDMENT 1's stand-aside
    cool = getattr(book, "_cool", None)
    if (v.cool_n and cool is not None and signal == cool[0]
            and bar.ts - cool[1] < v.cool_n * BAR_SECONDS):
        signal = None
    if (book.position is None and book.pending is None and not book.halted
            and signal is not None):
        book.pending = Pending(side=signal, limit=-1.0, signal_ts=bar.ts,
                               atr_signal=ind.atr14 or 0.0)


def _attach_mfe(book: Book, n_before: int, st: dict) -> None:
    for t in book.trades[n_before:]:
        t.mfe_px = st.get("mfe_px")


def run_s4(A: Asset, v: V = BASE, start_ts=None, end_ts=None,
           tcfg=RESEARCH_TRADE, cfg=S4_CFG):
    """S4 alone, gated exactly as run_replay gates every book. Returns the
    book and its per-bar MTM series [(bar_ts, mtm_equity)]."""
    book = Book(cfg=cfg)
    book._st = {}
    rng = random.Random(v.seed)
    mtm = []
    for i, bar in enumerate(A.bars):
        if i < WARMUP:
            continue
        if start_ts is not None and bar.ts < start_ts:
            continue
        if end_ts is not None and bar.ts > end_ts:
            break
        ind = A.inds[i]
        n0 = len(book.trades)
        st_before = book._st
        s4_step(book, bar, ind, i, A, tcfg, eval_donchian(bar, ind), v, rng)
        if len(book.trades) > n0:
            _attach_mfe(book, n0, st_before if st_before else book._st)
        _mark_to_market(book, bar.close)
        mtm.append((bar.ts, book.mtm_equity))
    return book, mtm


def run_s3(A: Asset, start_ts=None, end_ts=None, scfg=RESEARCH_SIGNAL,
           tcfg=RESEARCH_TRADE):
    """S3 through the engine's own code path (unmodified)."""
    book = Book(cfg=S3_CFG)
    mtm = []
    for i, bar in enumerate(A.bars):
        if i < WARMUP:
            continue
        if start_ts is not None and bar.ts < start_ts:
            continue
        if end_ts is not None and bar.ts > end_ts:
            break
        ind = A.inds[i]
        resolve_open_exit(book, bar, tcfg)
        process_closed_bar(book, bar, ind, scfg, tcfg, eval_signal(bar, ind, scfg))
        mtm.append((bar.ts, book.mtm_equity))
    return book, mtm


# ------------------------------------------------------------------- blends
def blend_exit_step(b3: Book, b4: Book, w: float, lev: float, t0: int, t1: int):
    """bench_blend.blend_curve's arithmetic, with the window's starting point
    (t0, 1.0) kept - the bench version drops the first trade's P&L
    (RESEARCH_PROTOCOL.md §9 item 6). Same-ts events: pullback first, as the
    bench's string sort does; a sequence number breaks remaining ties."""
    evs = sorted([(t.exit_ts, "P", k, t) for k, t in enumerate(b3.trades)]
                 + [(t.exit_ts, "T", k, t) for k, t in enumerate(b4.trades)],
                 key=lambda e: (e[0], e[1], e[2]))
    p3 = p4 = 1.0
    eq = 1.0
    out = [(t0, 1.0)]
    for ts_, which, _, t in evs:
        ratio = t.equity_after / (b3 if which == "P" else b4).cfg.start_equity
        r = (ratio / p3 - 1) * (1 - w) if which == "P" else (ratio / p4 - 1) * w
        if which == "P":
            p3 = ratio
        else:
            p4 = ratio
        if t0 <= ts_ <= t1:
            eq *= 1 + lev * r
            out.append((ts_, eq))
    return out


def blend_mtm(m3, m4, w: float, lev: float):
    """Bar-rebalanced constant-weight blend of the two books' MTM returns."""
    assert len(m3) == len(m4) and all(a[0] == b[0] for a, b in zip(m3, m4))
    out = [(m3[0][0], 1.0)]
    nav = 1.0
    for k in range(1, len(m3)):
        r3 = m3[k][1] / m3[k - 1][1] - 1
        r4 = m4[k][1] / m4[k - 1][1] - 1
        nav *= 1 + lev * (w * r4 + (1 - w) * r3)
        out.append((m3[k][0], nav))
    return out


def curve_stats(curve, bar_returns: bool = False) -> dict:
    t0, t1 = curve[0][0], curve[-1][0]
    yrs = max((t1 - t0) / (365.25 * 86400), 1e-9)
    nav = [c[1] for c in curve]
    tot = nav[-1] / nav[0] - 1
    cagr = (nav[-1] / nav[0]) ** (1 / yrs) - 1 if nav[-1] > 0 else -1.0
    peak, mdd = nav[0], 0.0
    for x in nav:
        peak = max(peak, x)
        mdd = min(mdd, x / peak - 1)
    out = dict(total=tot, cagr=cagr, maxdd=mdd,
               mar=cagr / abs(mdd) if mdd < -0.005 else None, years=yrs)
    if bar_returns and len(nav) > 3:
        r = [nav[k] / nav[k - 1] - 1 for k in range(1, len(nav))]
        mu = sum(r) / len(r)
        sd = math.sqrt(sum((x - mu) ** 2 for x in r) / (len(r) - 1))
        out["sharpe"] = mu / sd * math.sqrt(BARS_PER_YEAR) if sd > 0 else None
    return out


def trade_stats(book: Book) -> dict:
    """Per TRADE (partials grouped by entry_ts)."""
    by = {}
    for t in book.trades:
        g = by.setdefault(t.entry_ts, dict(pnl=0.0, notional=0.0, t=t, parts=[]))
        g["pnl"] += t.pnl_usd
        g["notional"] = max(g["notional"], t.qty * t.entry_price + sum(p.qty * p.entry_price for p in g["parts"]))
        g["parts"].append(t)
    pcts, wins, losses, caps = [], 0.0, 0.0, []
    for g in by.values():
        t0 = g["parts"][0]
        notional0 = sum(p.qty for p in g["parts"]) * t0.entry_price
        pct = g["pnl"] / notional0 if notional0 else 0.0
        pcts.append(pct)
        if g["pnl"] > 0:
            wins += g["pnl"]
        else:
            losses += -g["pnl"]
        mfe = getattr(g["parts"][-1], "mfe_px", None)
        if mfe is not None:
            sgn = 1 if t0.side == "L" else -1
            best = (mfe - t0.entry_price) * sgn
            if best > 0:
                gross = sum(p.qty * (p.exit_price - p.entry_price) * sgn for p in g["parts"])
                caps.append(gross / (best * sum(p.qty for p in g["parts"])))
    n = len(pcts)
    w = [p for p in pcts if p > 0]
    lo = [p for p in pcts if p <= 0]
    return dict(n=n, win_rate=len(w) / n if n else None,
                avg_win=sum(w) / len(w) if w else None,
                avg_loss=sum(lo) / len(lo) if lo else None,
                pf=wins / losses if losses > 0 else None,
                capture=sorted(caps)[len(caps) // 2] if caps else None)
