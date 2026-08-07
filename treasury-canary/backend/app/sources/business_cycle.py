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
    return {"months": months,
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
