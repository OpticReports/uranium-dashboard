"""EXIT2 harness (research/exit2/PREREG.md). Research only; the live engine
and the take-profit study's harness are untouched (this module imports the
TP harness's engine-verbatim pieces and adds exit hooks around a copy of its
S4 step).

With variant BASE, run_s4x must reproduce run_replay's S4 trade list field
for field (test_exit2.py G1). Conventions are the TP study's (PREREG §7
there): resting stops are live from the bar after the fill; a bar touching
a stop fills at the level, or at the open if it opened through it;
close-based rules are judged at a bar's close (never the fill bar's) and
fill at the NEXT open; 6 bps/side on entry notional at each close, partials
pro rata.
"""
from __future__ import annotations

import math
import os
import random
import sys
import time
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tp"))

from harness import (BAR_SECONDS, LIVE_LEV, LIVE_W_TREND,  # noqa: E402,F401
                     RESEARCH_TRADE, S4_CFG, T_2013, T_2022, T_FWD, T_IS_END,
                     WARMUP, Book, Pending, Position, _close_full, _close_part,
                     _fresh_state, _mark_to_market, _size, blend_exit_step,
                     blend_mtm, curve_stats, eval_donchian, load_asset,
                     load_bars, prepare, run_s3, trade_stats)

DATA_H = os.path.join(HERE, "data_h")
INSAMPLE = ("btc", "eth", "ltc", "xrp", "bch")
HOLDOUT = ("sol", "link", "ada", "xlm", "doge", "avax", "dot", "uni", "aave",
           "algo", "near", "shib")
T_HORIZONS = (30, 90, 270, 810)


def load_holdout(sym):
    return prepare(sym, load_bars(os.path.join(DATA_H, f"{sym}usd_4h.csv.gz")))


# ----------------------------------------------------------- extra arrays
@dataclass
class Ext:
    rv42: list
    tstat: dict
    atr_mean: list
    sma1200: list
    er60: list
    ret20z: list


def extend(A) -> Ext:
    c = [b.close for b in A.bars]
    n = len(c)
    r = [0.0] + [math.log(c[k] / c[k - 1]) for k in range(1, n)]
    s1 = [0.0] * (n + 1)
    s2 = [0.0] * (n + 1)
    for k in range(n):
        s1[k + 1] = s1[k] + r[k]
        s2[k + 1] = s2[k] + r[k] * r[k]

    def mean_sd(i, L):                       # returns r[i-L+1..i]
        if i - L + 1 < 1:
            return None, None
        m = (s1[i + 1] - s1[i - L + 1]) / L
        v = max((s2[i + 1] - s2[i - L + 1]) / L - m * m, 0.0) * L / (L - 1)
        return m, math.sqrt(v)

    rv42 = [None] * n
    for i in range(n):
        _, sd = mean_sd(i, 42)
        rv42[i] = sd
    tstat = {}
    for L in T_HORIZONS:
        t = [None] * n
        for i in range(n):
            m, sd = mean_sd(i, L)
            if m is not None and sd and sd > 0:
                t[i] = m / (sd / math.sqrt(L))
        tstat[L] = t
    atr = [ind.atr14 for ind in A.inds]
    from collections import deque
    atr_mean = [None] * n
    acc, q = 0.0, deque()
    for i in range(n):                       # mean ATR over the prior 2190 bars
        if len(q) >= 2190:
            atr_mean[i] = acc / len(q)
        if atr[i] is not None:
            q.append(atr[i])
            acc += atr[i]
            if len(q) > 2190:
                acc -= q.popleft()
    sma1200 = [None] * n
    cs = [0.0] * (n + 1)
    for k in range(n):
        cs[k + 1] = cs[k] + c[k]
    for i in range(1199, n):
        sma1200[i] = (cs[i + 1] - cs[i - 1199]) / 1200
    er60 = [None] * n
    for i in range(60, n):
        den = sum(abs(c[k] - c[k - 1]) for k in range(i - 59, i + 1))
        er60[i] = abs(c[i] - c[i - 60]) / den if den > 0 else None
    ret20z = [None] * n
    for i in range(20, n):
        if rv42[i]:
            ret20z[i] = math.log(c[i] / c[i - 20]) / (rv42[i] * math.sqrt(20))
    return Ext(rv42, tstat, atr_mean, sma1200, er60, ret20z)


# ---------------------------------------------------------------- variants
@dataclass(frozen=True)
class X:
    name: str = "BASE"
    vs_band: float | None = None      # V1 in-trade vol scaling (down-only)
    vs_kind: str = "atr"              # "atr": ATR14 / signal-bar ATR; "rv": rv42 / at signal bar
    ts_set: tuple = ()                # V2 trend-strength horizons (bars)
    ts_div: float = 2.0               # signal = mean(clip(t / div, -1, 1))
    ts_mode: str = "scale"            # "scale" (down-only) | "flip" (exit when it turns against)
    rg_map: str | None = None         # V3 regime-conditional trail multiple
    acc_alpha: float | None = None    # V4 time acceleration of the multiple
    acc_min: float = 3.0
    accp_beta: float | None = None    # V4 profit acceleration of the multiple
    psar_max: float | None = None     # V4 Parabolic SAR stop (step 0.02, max AF)
    lr_theta: float | None = None     # V5 walk-forward logistic exit threshold


BASE = X()


def _rg(name, vr, aligned, er):
    if name == "flat":                       # test-only no-op mapping (G6)
        return 5.0
    if name == "lowvol_tight":
        return 3.5 if vr < 0.8 else 5.0
    if name == "highvol_wide":
        return 6.5 if vr > 1.25 else 5.0
    if name == "vol_both":
        return 3.5 if vr < 0.8 else (6.5 if vr > 1.25 else 5.0)
    if name == "vol_inverse":
        return 6.5 if vr < 0.8 else (3.5 if vr > 1.25 else 5.0)
    if name == "align":
        return 6.0 if aligned else 4.0
    if name == "er":
        return 6.0 if (er is not None and er > 0.3) else 4.0
    if name == "vol_both_align":
        return _rg("vol_both", vr, aligned, er) * (1.15 if aligned else 0.85)
    raise ValueError(name)


def trail_mult(x, st, E, i, bar, ind, pos) -> float:
    m = 5.0
    L = pos.side == "L"
    if x.rg_map is not None:
        vr = ind.atr14 / E.atr_mean[i] if E.atr_mean[i] else 1.0
        sma = E.sma1200[i]
        aligned = sma is not None and ((bar.close > sma) if L else (bar.close < sma))
        m = _rg(x.rg_map, vr, aligned, E.er60[i])
    if x.acc_alpha is not None:
        held = (bar.ts - pos.entry_ts) // BAR_SECONDS
        m = max(x.acc_min, m - x.acc_alpha * held / 42)
    if x.accp_beta is not None and st.get("atr0"):
        mfe = ((st["best"] - pos.entry_price) if L else (pos.entry_price - st["best"])) / st["atr0"]
        m = max(3.0, m - x.accp_beta * max(mfe, 0.0) / 10)
    return m


# -------------------------------------------------------- V5: logistic exit
MODELS: dict = {}                      # year -> (mu, sd, w, b); trained by train_models


def lr_feats(st, pos, bar, ind, A, E, i):
    d = 1.0 if pos.side == "L" else -1.0
    a0, a = st["atr0"], ind.atr14
    if not a0 or not a or ind.sma50 is None or ind.sma200 is None or ind.rsi14 is None:
        return None
    if E.atr_mean[i] is None or E.er60[i] is None or A.er20[i] is None or E.ret20z[i] is None:
        return None
    mfe = d * (st["best"] - pos.entry_price) / a0
    opn = d * (bar.close - pos.entry_price) / a0
    held = (bar.ts - pos.entry_ts) / BAR_SECONDS / 42
    return [mfe, opn, mfe - opn, held, A.er20[i], E.er60[i], a / E.atr_mean[i],
            d * (ind.rsi14 - 50) / 50, d * (bar.close - ind.sma50) / a,
            d * (bar.close - ind.sma200) / a, d * E.ret20z[i]]


def lr_prob(f, year):
    mdl = MODELS.get(year)
    if mdl is None or f is None:
        return None
    mu, sd, w, b = mdl
    z = b + sum(wk * (fk - mk) / sk for wk, fk, mk, sk in zip(w, f, mu, sd))
    return 1 / (1 + math.exp(-max(min(z, 50), -50)))


def year_of(t):
    return time.gmtime(t).tm_year


def year_start(y):
    import calendar
    return calendar.timegm((y, 1, 1, 0, 0, 0))


# ----------------------------------------------------------------- S4 step
def s4_step_x(book, bar, ind, i, A, E, tcfg, signal, x: X, rec=None):
    st = book._st
    pos = book.position
    # (0) a close-based exit (full or partial) flagged at the previous close
    if pos is not None and st.get("flag"):
        f = st["flag_f"]
        if f >= 1.0:
            _close_full(book, pos, bar.ts, bar.open, st["flag"], tcfg)
            pos = None
        else:
            q = round(pos.qty * f, 6)
            if 0 < q < pos.qty:
                _close_part(book, pos, q, bar.ts, bar.open, st["flag"])
            st["frac"] = pos.qty / st["qty0"]
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
                st = _fresh_state(p.atr_signal, bar.open)
                st.update(qty0=qty, frac=1.0, vol0=E.rv42[i - 1] if i > 0 else None,
                          sar=None, ep=None, af=None)
                book._st = st
    pos = book.position
    if pos is not None:
        L = pos.side == "L"
        st["mfe_px"] = max(st["mfe_px"], bar.high) if L else min(st["mfe_px"], bar.low)
        after_fill = bar.ts > pos.entry_ts
        # (2) resting stops: the engine trail, plus the Parabolic SAR
        if after_fill:
            cands = []
            if pos.trail is not None:
                cands.append((pos.trail, "STOP"))
            if x.psar_max is not None and st.get("sar") is not None:
                cands.append((st["sar"], "SAR"))
            if cands:
                lvl = max(c[0] for c in cands) if L else min(c[0] for c in cands)
                # a tie with the engine's trail is the engine's stop (label too)
                why = ("STOP" if pos.trail is not None and pos.trail == lvl
                       else next(w for l_, w in cands if l_ == lvl))
                hit = bar.low <= lvl if L else bar.high >= lvl
                if hit:
                    fill = min(lvl, bar.open) if L else max(lvl, bar.open)
                    _close_full(book, pos, bar.ts, fill, why, tcfg)
                    pos = None
        # (3) survivors ratchet the trail from this close (variant multiple)
        if pos is not None and ind.atr14 is not None:
            mult = trail_mult(x, st, E, i, bar, ind, pos)
            lvl = (bar.close - mult * ind.atr14 if L else bar.close + mult * ind.atr14)
            pos.trail = (lvl if pos.trail is None else
                         (max(pos.trail, lvl) if L else min(pos.trail, lvl)))
            pos.stop_price = pos.trail
            if x.psar_max is not None and st.get("sar") is None:
                st["sar"] = pos.trail
                st["ep"] = bar.high if L else bar.low
                st["af"] = min(0.02, x.psar_max)
        # (4) close-based state and flags, after the fill bar
        if pos is not None and after_fill:
            c = bar.close
            st["best"] = max(st["best"], c) if L else min(st["best"], c)
            if x.psar_max is not None and st.get("sar") is not None:
                if (bar.high > st["ep"]) if L else (bar.low < st["ep"]):
                    st["ep"] = bar.high if L else bar.low
                    st["af"] = min(st["af"] + 0.02, x.psar_max)
                sar = st["sar"] + st["af"] * (st["ep"] - st["sar"])
                prev = A.bars[i - 1]
                st["sar"] = (min(sar, bar.low, prev.low) if L else max(sar, bar.high, prev.high))
            if rec is not None:
                f = lr_feats(st, pos, bar, ind, A, E, i)
                if f is not None:
                    rec.append((pos.entry_ts, i, f))
            full, tgt = None, None
            if x.ts_set:
                vals = [E.tstat[Lh][i] for Lh in x.ts_set]
                if all(v is not None for v in vals):
                    s = sum(max(-1.0, min(1.0, v / x.ts_div)) for v in vals) / len(vals)
                    al = s if L else -s
                    if x.ts_mode == "flip":
                        if al < 0:
                            full = "TREND"
                    else:
                        if al <= 0:
                            full = "TREND"
                        else:
                            tgt = min(al, st["frac"])
                            if st["frac"] - tgt < 0.25 - 1e-12:
                                tgt = None
            if full is None and x.vs_band is not None:
                if x.vs_kind == "atr":
                    r = (ind.atr14 / st["atr0"]) if (st["atr0"] and ind.atr14) else None
                else:
                    r = (E.rv42[i] / st["vol0"]) if (st["vol0"] and E.rv42[i]) else None
                if r:
                    t = max(0.25, min(1.0, 1 / r))
                    t = min(t, st["frac"])
                    if st["frac"] - t >= x.vs_band - 1e-12:
                        tgt = t
            if full is None and x.lr_theta is not None:
                p = lr_prob(lr_feats(st, pos, bar, ind, A, E, i), year_of(bar.ts))
                if p is not None and p > x.lr_theta:
                    full = "LR"
            if full is not None:
                st["flag"], st["flag_f"] = full, 1.0
            elif tgt is not None and tgt < st["frac"]:
                st["flag"], st["flag_f"] = "SCALE", 1 - tgt / st["frac"]
    # (5) new entry - engine verbatim
    if (book.position is None and book.pending is None and not book.halted
            and signal is not None):
        book.pending = Pending(side=signal, limit=-1.0, signal_ts=bar.ts,
                               atr_signal=ind.atr14 or 0.0)


def run_s4x(A, E, x: X = BASE, start_ts=None, end_ts=None, tcfg=RESEARCH_TRADE,
            cfg=S4_CFG, rec=None):
    book = Book(cfg=cfg)
    book._st = {}
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
        st0 = book._st
        s4_step_x(book, bar, ind, i, A, E, tcfg, eval_donchian(bar, ind), x, rec)
        for t in book.trades[n0:]:
            t.mfe_px = (st0 or book._st).get("mfe_px")
        _mark_to_market(book, bar.close)
        mtm.append((bar.ts, book.mtm_equity))
    return book, mtm


# ----------------------------------------------------- V5 model training
def collect_samples(A, E, cfg, start_ts=None, end_ts=None):
    """Per-bar features of BASE trades with the label 'exiting at the next
    open beats this trade's eventual exit' and the trade's exit time."""
    rec = []
    book, _ = run_s4x(A, E, BASE, start_ts, end_ts, cfg=cfg, rec=rec)
    final = {}
    for t in book.trades:
        final[t.entry_ts] = (t.exit_ts, t.exit_price, t.side)
    out = []
    for entry_ts, i, f in rec:
        if entry_ts not in final or i + 1 >= len(A.bars):
            continue
        ex_ts, ex_px, side = final[entry_ts]
        nxt = A.bars[i + 1].open
        d = 1.0 if side == "L" else -1.0
        out.append((ex_ts, f, 1.0 if d * (nxt - ex_px) > 0 else 0.0))
    return out


def _fit_logistic(Xs, ys, lam=1.0, iters=30):
    import numpy as np
    Xa = np.asarray(Xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    mu = Xa.mean(0)
    sd = Xa.std(0)
    sd[sd == 0] = 1.0
    Z = (Xa - mu) / sd
    Z1 = np.hstack([Z, np.ones((len(Z), 1))])
    w = np.zeros(Z1.shape[1])
    reg = lam * np.eye(Z1.shape[1])
    reg[-1, -1] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Z1 @ w, -50, 50)))
        g = Z1.T @ (p - y) + reg @ w
        H = (Z1 * (p * (1 - p))[:, None]).T @ Z1 + reg
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return list(mu), list(sd), list(w[:-1]), float(w[-1])


def train_models(samples, years=range(2014, 2027), min_n=500):
    """MODELS[y]: fitted only on samples whose trade closed before Jan 1 of y."""
    MODELS.clear()
    for y in years:
        cut = year_start(y)
        tr = [(f, lab) for ex_ts, f, lab in samples if ex_ts < cut]
        if len(tr) >= min_n and 0 < sum(l for _, l in tr) < len(tr):
            MODELS[y] = _fit_logistic([f for f, _ in tr], [l for _, l in tr])
    return MODELS
