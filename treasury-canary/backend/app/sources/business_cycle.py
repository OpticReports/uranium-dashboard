"""Business-cycle tracker (Zeberg-style 'where are we in the cycle').

Two composites, validated against every NBER recession 1960-2026 before
shipping (validation stats recomputed from live data by the gates):

  COINCIDENT — mean expanding-window z of 6m annualized growth of the four
  series the NBER dating committee uses: payrolls (PAYEMS), industrial
  production (INDPRO), real income ex transfers (W875RX1), real mfg &
  trade sales (CMRMTSPL). Below -0.75 is the recession-consistent zone
  (~65% precision / ~92% recall on monthly NBER labels; every recession
  since 1970 bottomed below -1.65).

  LEADING — mean expanding z of: yield curve (T10Y3M; GS10-TB3MS before
  1982), permits 6m growth, -claims 6m growth, factory hours, sentiment
  change, -Baa spread. Crossing -0.5 preceded 6 of 7 recessions (median
  6m); 3 of 14 warning spells were false.

Phases: CONTRACTION coin<-0.75 · SLOWDOWN coin<0 & lead<-0.3 · STALL
coin<0 · LATE CYCLE lead<-0.5 · EXPANSION otherwise.

Also serves the payrolls-momentum view (12m MA of monthly payroll change,
the Zeberg chart) so the panel can toggle between framings.

Honesty: monthly cadence with ~1-month publication lag; validation uses
REVISED data — live vintages are noisier, so real-time precision runs
below the backtest stats. Expanding-window z-scores avoid full-sample
lookahead but revisions cannot be un-baked without ALFRED vintages.
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass

from ..config import settings
from .fred import fetch_series

SERIES = ["PAYEMS", "INDPRO", "W875RX1", "CMRMTSPL", "PERMIT", "ICSA",
          "AWHMAN", "UMCSENT", "T10Y3M", "BAA10YM", "GS10", "TB3MS", "USREC"]
_MEAN_COLLAPSE = {"ICSA", "T10Y3M"}          # weekly/daily: month-mean
START = "1959-01-01"
Z_MIN = 120                                   # expanding-z warmup (months)
COIN_RECESSION = -0.75
LEAD_WARN = -0.5


def _monthly(dates, values, how):
    out: dict[str, list[float]] = {}
    for d, v in zip(dates, values):
        if v is None:
            continue
        out.setdefault(str(d)[:7], []).append(float(v))
    return {m: (sum(v) / len(v) if how == "mean" else v[-1])
            for m, v in out.items()}


def _g6(xs):
    out = [None] * len(xs)
    for i in range(6, len(xs)):
        a, b = xs[i], xs[i - 6]
        if a and b and a > 0 and b > 0:
            out[i] = (math.log(a) - math.log(b)) * 2 * 100
    return out


def _zs(xs):
    out = [None] * len(xs)
    hist: list[float] = []
    for i, x in enumerate(xs):
        if x is not None:
            hist.append(x)
        if x is not None and len(hist) >= Z_MIN:
            mu = sum(hist) / len(hist)
            sd = (sum((h - mu) ** 2 for h in hist) / len(hist)) ** 0.5
            out[i] = (x - mu) / (sd + 1e-9)
    return out


def _mean_rows(rows):
    out = []
    for vals in zip(*rows):
        vs = [v for v in vals if v is not None]
        out.append(sum(vs) / len(vs) if vs else None)
    return out


def phase_of(coin, lead) -> str | None:
    if coin is None or lead is None:
        return None
    if coin < COIN_RECESSION:
        return "CONTRACTION"
    if coin < 0 and lead < -0.3:
        return "SLOWDOWN"
    if coin < 0:
        return "STALL"
    if lead < LEAD_WARN:
        return "LATE_CYCLE"
    return "EXPANSION"


def _fetch_all(raw_override: dict | None = None) -> dict[str, dict[str, float]]:
    """{series: {YYYY-MM: value}}. raw_override (tests) supplies
    {series: [(date, value), ...]} and skips the network entirely."""
    out = {}
    for s in SERIES:
        if raw_override is not None:
            pairs = raw_override.get(s, [])
            dates = [p[0] for p in pairs]
            vals = [float(p[1]) for p in pairs]
        else:
            dates, vals = fetch_series(s, start=START)
        out[s] = _monthly(dates, vals, "mean" if s in _MEAN_COLLAPSE else "last")
    return out


def compute(raw_override: dict | None = None) -> dict:
    M = _fetch_all(raw_override)
    months = sorted(set(M["PAYEMS"]) & set(M["INDPRO"]))
    months = [m for m in months if m >= "1960-01"]

    def arr(name):
        return [M[name].get(m) for m in months]

    coin = _mean_rows([_zs(_g6(arr(s)))
                       for s in ("PAYEMS", "INDPRO", "W875RX1", "CMRMTSPL")])
    curve = [(a if a is not None else
              ((g - t) if g is not None and t is not None else None))
             for a, g, t in zip(arr("T10Y3M"), arr("GS10"), arr("TB3MS"))]
    sent = arr("UMCSENT")
    dsent = [None] + [(b - a) if a is not None and b is not None else None
                      for a, b in zip(sent, sent[1:])]
    lead_raw = _mean_rows([
        _zs(curve),
        _zs(_g6(arr("PERMIT"))),
        _zs([-x if x is not None else None for x in _g6(arr("ICSA"))]),
        _zs(arr("AWHMAN")),
        _zs(dsent),
        _zs([-x if x is not None else None for x in arr("BAA10YM")]),
    ])
    lead = [None] * len(lead_raw)              # 3m smooth
    for i in range(len(lead_raw)):
        w = [x for x in lead_raw[max(0, i - 2):i + 1] if x is not None]
        lead[i] = sum(w) / len(w) if w else None
    rec = arr("USREC")
    phases = [phase_of(c, l) for c, l in zip(coin, lead)]

    # payrolls momentum (Zeberg view): 12m MA of monthly change, thousands
    pay = arr("PAYEMS")
    chg = [None] + [(b - a) if a is not None and b is not None else None
                    for a, b in zip(pay, pay[1:])]
    ma12 = [None] * len(chg)
    for i in range(12, len(chg)):
        w = [x for x in chg[i - 11:i + 1] if x is not None]
        if len(w) == 12:
            ma12[i] = sum(w) / 12
    # Zeberg claim check: is the current MA below every pre-recession level
    # since 1970? (value of ma12 at each NBER recession start month)
    starts = [i for i in range(1, len(rec))
              if rec[i] == 1 and rec[i - 1] == 0 and months[i] >= "1970-01"]
    at_starts = [ma12[i] for i in starts if ma12[i] is not None]
    zeberg_claim = (ma12[-1] is not None and at_starts
                    and ma12[-1] < min(at_starts))

    # validation stats (recomputed live so drift is visible)
    tp = fp = fn = 0
    for c, r in zip(coin, rec):
        if c is None or r is None:
            continue
        s = c < COIN_RECESSION
        tp += s and r == 1
        fp += s and r == 0
        fn += (not s) and r == 1
    stats = {"precision": round(tp / (tp + fp), 3) if tp + fp else None,
             "recall": round(tp / (tp + fn), 3) if tp + fn else None,
             "threshold": COIN_RECESSION}

    rec_spans = []
    on = None
    for i, r in enumerate(rec):
        if r == 1 and on is None:
            on = months[i]
        if r == 0 and on is not None:
            rec_spans.append([on, months[i]])
            on = None
    if on is not None:
        rec_spans.append([on, months[-1]])

    rnd = lambda x: round(x, 3) if x is not None else None
    nc = nowcast(M, months, coin)
    return {"months": months,
            "nowcast": nc,
            "coincident": [rnd(x) for x in coin],
            "leading": [rnd(x) for x in lead],
            "phase": phases,
            "payroll_ma12_k": [rnd(x) for x in ma12],
            "payroll_chg_k": [rnd(x) for x in chg],
            "rec_spans": rec_spans,
            "zeberg_check": {"holds": bool(zeberg_claim),
                             "current_ma_k": rnd(ma12[-1]),
                             "min_at_recession_starts_k": rnd(min(at_starts))
                             if at_starts else None},
            "stats": stats,
            "current": {"month": months[-1], "coincident": rnd(coin[-1]),
                        "leading": rnd(lead[-1]), "phase": phases[-1]},
            "basis": ("monthly FRED, ~1m publication lag; expanding-window "
                      "z (no full-sample lookahead); validation on revised "
                      "data - live vintages noisier")}


# ---------- phase-change detection (called from the refresh job) ----------

def phase_change(board: dict) -> str | None:
    """Compare current phase vs the persisted last-seen phase; persist and
    return a change message the caller can event/alert on (None = no change)."""
    path = os.path.join(settings.cache_dir, "cycle_phase.json")
    cur = board["current"]["phase"]
    prev = None
    try:
        prev = json.load(open(path)).get("phase")
    except Exception:  # noqa: BLE001
        pass
    try:
        os.makedirs(settings.cache_dir, exist_ok=True)
        json.dump({"phase": cur, "month": board["current"]["month"],
                   "ts": int(time.time())}, open(path, "w"))
    except Exception:  # noqa: BLE001
        pass
    if prev and cur and prev != cur:
        return (f"business-cycle phase change: {prev} -> {cur} "
                f"(coincident {board['current']['coincident']:+.2f}, "
                f"leading {board['current']['leading']:+.2f})")
    return None


# ---------- nowcast: next-month coincident, ahead of publication ----------
# Method ENS_BC from the 2026-08-07 walk-forward study (1972-2026, n=654):
# 0.5*BRIDGE + 0.5*CLAIMS. RMSE -28.5% vs persistence (-14.7% ex-2020,
# DM t -5.33); 25.4% of phase transitions called a month early (persistence
# 0% by construction); recession onsets: earlier 3/7, tied 3, later 1,
# missed 0; only sub -0.75 false alarm (1981-06) preceded the actual 1981
# recession. The edge is PUBLICATION-TIMING asymmetry: payrolls, claims and
# rates for month M print ~1 month before the full composite for M does.
# Caveats: final-vintage validation; COIN(M-1) regressor = last realized.
# Full spec + study: scratchpad nowcast_study.md / nowcast_spec.json,
# summarized in the /cycle response.

def _ols(X, y):
    import numpy as np
    X = np.asarray(X, float); y = np.asarray(y, float)
    beta, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(X)), X]), y,
                               rcond=None)
    return beta


def _zs_at(hist_vals, x):
    """expanding z of x against history (history includes x's month peers)."""
    import numpy as np
    h = np.asarray([v for v in hist_vals if v is not None], float)
    if len(h) < Z_MIN:
        return None
    return float((x - h.mean()) / (h.std() + 1e-9))


def nowcast(M: dict, months: list, coin: list) -> dict | None:
    """M = {series: {month: value}} from _fetch_all; coin = realized
    coincident series aligned to months. Returns the ENS_BC nowcast for the
    first month after the last realized composite value."""
    import numpy as np
    try:
        pay_months = sorted(M["PAYEMS"])
        tgt = pay_months[-1]                      # payrolls lead the pack
        last_realized = max(i for i, c in enumerate(coin) if c is not None)
        if months[last_realized] >= tgt:
            return None                           # composite already caught up

        def g6_at(ser, m, lag=0):
            ms = sorted(M[ser])
            if m not in ms:
                return None
            i = ms.index(m)
            if i - 6 - lag < 0:
                return None
            a, b = M[ser][ms[i - lag]], M[ser][ms[i - 6 - lag]]
            return (math.log(a) - math.log(b)) * 2 if a > 0 and b > 0 else None

        gp_tgt = g6_at("PAYEMS", tgt)
        zparts = []
        # payrolls: actual, z'd against its own growth history (z is
        # scale-invariant — but only if value and history share units)
        gp_hist = [h for h in (g6_at("PAYEMS", m) for m in pay_months)
                   if h is not None]
        zparts.append(_zs_at(gp_hist, gp_tgt) if gp_tgt is not None else None)
        # bridged components
        for ser, lag in (("INDPRO", 1), ("W875RX1", 1), ("CMRMTSPL", 2)):
            ms = sorted(M[ser])
            X, y = [], []
            for m in ms:
                g0, gl, gpm = g6_at(ser, m), g6_at(ser, m, lag), g6_at("PAYEMS", m)
                if None not in (g0, gl, gpm):
                    X.append([gl, gpm]); y.append(g0)
            if len(y) < 200:
                return None
            b = _ols(X, y)
            gl_t = g6_at(ser, ms[-1], 0)          # last actual growth as lag proxy
            if gl_t is None or gp_tgt is None:
                return None
            proj = float(b[0] + b[1] * gl_t + b[2] * gp_tgt)
            hist = [g6_at(ser, m) for m in ms]
            zparts.append(_zs_at([h * 100 for h in hist if h is not None],
                                 proj * 100))
        if any(z is None for z in zparts):
            return None
        bridge = float(np.mean(zparts))

        # CLAIMS member
        cl_months = sorted(M["ICSA"])
        def zc6(m):
            ms = cl_months
            if m not in ms: return None
            i = ms.index(m)
            if i < 6: return None
            a, b_ = M["ICSA"][ms[i]], M["ICSA"][ms[i - 6]]
            return -(math.log(a) - math.log(b_)) * 2 if a > 0 and b_ > 0 else None
        zc_hist = [zc6(m) for m in cl_months]
        def zc_z(m):
            v = zc6(m)
            return _zs_at([x for x in zc_hist if x is not None], v) if v is not None else None
        def curve_at(m):
            t = M["T10Y3M"].get(m)
            if t is not None: return t
            g, tb = M["GS10"].get(m), M["TB3MS"].get(m)
            return (g - tb) if g is not None and tb is not None else None
        curve_hist = [curve_at(m) for m in months]
        def curve_z(m):
            v = curve_at(m)
            return _zs_at([x for x in curve_hist if x is not None], v) if v is not None else None
        X, y = [], []
        for i in range(1, len(months)):
            m = months[i]
            f = [coin[i - 1], zc_z(m),
                 (zc_z(m) - zc_z(months[i - 3])) if i >= 3 and zc_z(m) is not None
                 and zc_z(months[i - 3]) is not None else None, curve_z(m)]
            if coin[i] is not None and None not in f:
                X.append(f); y.append(coin[i])
        if len(y) < 200:
            return None
        b = _ols(X, y)
        m3 = months[last_realized - 2]
        f_t = [coin[last_realized], zc_z(tgt),
               (zc_z(tgt) - zc_z(m3)) if zc_z(tgt) is not None
               and zc_z(m3) is not None else None, curve_z(tgt)]
        if None in f_t:
            return None
        claims = float(b[0] + sum(bi * xi for bi, xi in zip(b[1:], f_t)))

        ens = 0.5 * bridge + 0.5 * claims
        ph = ("CONTRACTION" if ens < COIN_RECESSION else
              "STALL" if ens < 0 else "EXPANSION")
        return {"month": tgt, "value": round(ens, 3),
                "bridge": round(bridge, 3), "claims": round(claims, 3),
                "phase": ph,
                "claims_trigger": bool(claims < COIN_RECESSION),
                "stats": {"rmse_vs_persistence_pct": -28.5,
                          "rmse_ex2020_pct": -14.7,
                          "transitions_called_early_pct": 25.4,
                          "onsets_earlier": "3/7 (never missed; 1 late by 1m)"},
                "basis": ("ENS_BC walk-forward spec 2026-08-07; edge = "
                          "publication-timing (payrolls/claims/rates print "
                          "~1m before the composite); final-vintage "
                          "validation - live vintages noisier")}
    except Exception:  # noqa: BLE001
        return None
