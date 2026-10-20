"""Business-cycle tracker (Zeberg-style 'where are we in the cycle').

Two composites, validated against every NBER recession 1960-2026 before
shipping (validation stats recomputed from live data by the gates):

  COINCIDENT — mean expanding-window z of 6m annualized growth of the four
  series the NBER dating committee uses: payrolls (PAYEMS), industrial
  production (INDPRO), real income ex transfers (W875RX1), real mfg &
  trade sales (CMRMTSPL). Below -0.75 is the recession-consistent zone
  (~65% precision full-sample but ~58% post-1990 / ~93% recall on monthly
  NBER labels; every recession since 1970 bottomed below -1.5 [2001:
  -1.69 - the -1.65 version was knife-edged, QA 2026-08-07]).

  LEADING — mean expanding z of: yield curve (T10Y3M; GS10-TB3MS before
  1982), permits 6m growth, -claims 6m growth, factory hours, sentiment
  change, -Baa spread. Crossing -0.5 was STRICTLY EARLY on 4 of 7
  recessions (median 3m outside the early-80s pair; 1990/2020 crossed AT
  onset, 2008 one month after); 3 of 15 spells false, TWO of them recent
  (2023-04/05, 2024-07) - counter-agent recount, 2026-08-07.

Phases: CONTRACTION coin<-0.75 · SLOWDOWN coin<0 & lead<-0.3 · STALL
coin<0 · LATE CYCLE lead<-0.5 · EXPANSION otherwise.

Also serves the payrolls-momentum view (12m MA of monthly payroll change,
the Zeberg chart) so the panel can toggle between framings.

Honesty: monthly cadence with ~1-month publication lag. Real-time
reliability MEASURED on ALFRED vintages (160 as-of dates 2000-2026,
study 2026-08-11): latest-month phase label matches the revised label
82% overall — CONTRACTION 98% (recall 41/42, precision 41/46, the 5
false alarms all knife-edge), SLOWDOWN 89%, STALL 81%, EXPANSION 64%;
disagreements are almost all EXPANSION<->STALL sign flips at
|coin| < ~0.5, so that boundary renders as PROVISIONAL. Edge-month
coincident z MAE 0.24 sigma (p90 0.46; bias -0.05, not exploitable).
Recession entries 2001/2008/2020 were all labeled at the
publication-limited minimum (2008: Jan-08 CONTRACTION on the Feb-08
vintage, ~9 months before NBER announced). Worst real-time failure:
2022 printed EXPANSION live all year but is a 10-month STALL after
benchmark revisions - the optimistic direction. Pre-2010 income/sales/
claims vintages are spliced approximations (lower-bound degradation).
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
SLOWDOWN_LEAD = -0.3
# member labels, in composite order (the panel's "what is driving it" strip)
COIN_MEMBERS = [("PAYEMS", "payrolls"), ("INDPRO", "industrial output"),
                ("W875RX1", "real income ex transfers"),
                ("CMRMTSPL", "real mfg & trade sales")]
LEAD_MEMBERS = ["yield curve", "building permits", "jobless claims (inv.)",
                "factory hours", "sentiment change", "Baa spread (inv.)"]
# ALFRED-vintage study 2026-08-11 (160 as-of dates 2000-2026): frozen numbers
RT_AGREEMENT_PCT = 82.5
RT_BY_PHASE = {"CONTRACTION": 98, "SLOWDOWN": 89, "STALL": 81, "EXPANSION": 64}
RT_EDGE_MAE, RT_EDGE_P90 = 0.24, 0.46


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
    missing = [s for s in SERIES if not out.get(s)]
    if missing:
        # fetch_series degrades to empty on FRED failure; a partial board would
        # silently recompute composites from fewer members (and can flip the
        # phase). Refuse instead - the route serves its stale cache / 503s.
        raise RuntimeError(f"cycle: no data for {missing}; refusing partial board")
    return out


def compute(raw_override: dict | None = None) -> dict:
    M = _fetch_all(raw_override)
    months = sorted(set(M["PAYEMS"]) & set(M["INDPRO"]))
    months = [m for m in months if m >= "1960-01"]

    def arr(name):
        return [M[name].get(m) for m in months]

    coin_z = {label: _zs(_g6(arr(s))) for s, label in COIN_MEMBERS}
    coin = _mean_rows(list(coin_z.values()))
    curve = [(a if a is not None else
              ((g - t) if g is not None and t is not None else None))
             for a, g, t in zip(arr("T10Y3M"), arr("GS10"), arr("TB3MS"))]
    sent = arr("UMCSENT")
    dsent = [None] + [(b - a) if a is not None and b is not None else None
                      for a, b in zip(sent, sent[1:])]
    lead_z = dict(zip(LEAD_MEMBERS, [
        _zs(curve),
        _zs(_g6(arr("PERMIT"))),
        _zs([-x if x is not None else None for x in _g6(arr("ICSA"))]),
        _zs(arr("AWHMAN")),
        _zs(dsent),
        _zs([-x if x is not None else None for x in arr("BAA10YM")]),
    ]))
    lead_raw = _mean_rows(list(lead_z.values()))
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

    # validation stats (recomputed live so drift is visible); the post-1990
    # precision is the era the QA panel flagged as the honest one (~58%)
    tp = fp = fn = tp90 = fp90 = 0
    for m, c, r in zip(months, coin, rec):
        if c is None or r is None:
            continue
        s = c < COIN_RECESSION
        tp += s and r == 1
        fp += s and r == 0
        fn += (not s) and r == 1
        if m >= "1990-01":
            tp90 += s and r == 1
            fp90 += s and r == 0
    stats = {"precision": round(tp / (tp + fp), 3) if tp + fp else None,
             "precision_post1990": round(tp90 / (tp90 + fp90), 3) if tp90 + fp90 else None,
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
    # ALFRED vintage study 2026-08-11: the EXPANSION<->STALL boundary flips
    # ~1-in-3 on revision when |coin| < 0.5, and the p90 edge error (0.46)
    # exceeds a sub-0.5 gap to the -0.75 contraction line - render such
    # labels as provisional.
    cur_coin, cur_phase = coin[-1], phases[-1]
    provisional = bool(cur_coin is not None and cur_phase in
                       ("EXPANSION", "STALL") and abs(cur_coin) < 0.5)
    realtime = {"study": "ALFRED vintages, 160 as-of dates 2000-2026 "
                         "(2026-08-11)",
                "label_agreement_pct": 82.5,
                "by_phase_pct": {"CONTRACTION": 98, "SLOWDOWN": 89,
                                 "STALL": 81, "EXPANSION": 64},
                "edge_mae_z": 0.24, "edge_p90_z": 0.46,
                "provisional": provisional,
                "provisional_note": ("EXPANSION vs STALL flips ~1-in-3 on "
                                     "revision at |coin|<0.5; a CONTRACTION "
                                     "print could appear or vanish on "
                                     "revision alone when the gap to -0.75 "
                                     "is under ~0.46") if provisional
                else None}
    components = _components(months, coin_z, lead_z)
    members_in_latest = sum(1 for c in components["coincident"] if c["in_latest"])
    current = {"month": months[-1], "coincident": rnd(coin[-1]),
               "leading": rnd(lead[-1]), "phase": phases[-1],
               "members_in_latest": members_in_latest}
    return {"months": months,
            "nowcast": nc,
            "components": components,
            "read": build_read(current, provisional, components, stats, nc),
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
            "current": current,
            "realtime": realtime,
            "basis": ("monthly FRED, ~1m publication lag; expanding-window "
                      "z (no full-sample lookahead). Real-time reliability "
                      "measured on ALFRED vintages (2026-08-11): labels "
                      "match revised 82% (CONTRACTION 98%, EXPANSION 64%); "
                      "nowcast phase 7/7 correct under vintages incl. "
                      "2020-04 CONTRACTION while realized data still read "
                      "-0.22")}


# ---------- the plain-English read (panel summary; numbers are live) ----------

def _components(months, coin_z: dict, lead_z: dict) -> dict:
    """Latest z per member with the month it belongs to. A coincident member
    that has not published for the latest month is still shown (at its own
    last month) and flagged in_latest=False, so the panel can say how many
    of the four the headline coincident reading actually rests on."""
    def latest(zs):
        for i in range(len(zs) - 1, -1, -1):
            if zs[i] is not None:
                return {"z": round(zs[i], 2), "month": months[i],
                        "in_latest": i == len(zs) - 1}
        return {"z": None, "month": None, "in_latest": False}
    return {"coincident": [{"label": k, **latest(v)} for k, v in coin_z.items()],
            "leading": [{"label": k, **latest(v)} for k, v in lead_z.items()]}


def _sz(z) -> str:
    return "n/a" if z is None else f"{z:+.2f}σ"


def build_read(current: dict, provisional: bool, components: dict,
               stats: dict, nc: dict | None) -> dict:
    """Six short strings the panel shows above the chart. Every number comes
    from the board itself; the frozen reliability figures are the ALFRED
    study's (module docstring). Wording is 'watch', never 'alert'."""
    coin, lead, phase = current["coincident"], current["leading"], current["phase"]
    k, month = current["members_in_latest"], current["month"]
    prov = " (provisional)" if provisional else ""
    if coin is None or lead is None or phase is None:
        return {"headline": "No phase: the composites are not computable for the latest month.",
                "drivers": "", "calculation": "", "reliability": "", "next": "", "nowcast": ""}
    lead_dir = ("pointing up" if lead > 0 else
                f"soft but above the {SLOWDOWN_LEAD} slowdown line" if lead > SLOWDOWN_LEAD
                else "falling")
    if phase == "CONTRACTION":
        head = (f"CONTRACTION: coincident growth is {_sz(coin)}, below the {COIN_RECESSION} line "
                f"that has coincided with NBER recession months "
                f"{round(100 * (stats.get('precision') or 0))}% of the time; the leading composite is "
                f"{_sz(lead)}.")
    elif phase == "SLOWDOWN":
        head = (f"SLOWDOWN: growth is below its long-run average ({_sz(coin)}) AND the leading "
                f"composite is falling ({_sz(lead)}, under {SLOWDOWN_LEAD}); historically this "
                f"combination has rarely stayed a false alarm for long.")
    elif phase == "STALL":
        size = "a hair" if abs(coin) < 0.1 else "modestly" if abs(coin) < 0.35 else "clearly"
        gap = coin - COIN_RECESSION
        dist = ("well above" if gap >= RT_EDGE_P90 else "above" if gap >= RT_EDGE_MAE
                else "within revision noise of")
        head = (f"STALL{prov}: coincident growth is {size} below its long-run average "
                f"({_sz(coin)}) and {dist} the recession line ({COIN_RECESSION}); the leading "
                f"composite is {_sz(lead)} and {lead_dir}.")
    elif phase == "LATE_CYCLE":
        head = (f"LATE CYCLE: growth is still above average ({_sz(coin)}) but the leading "
                f"composite has rolled over ({_sz(lead)}, below {LEAD_WARN}); this crossing "
                f"came strictly early on 4 of 7 recessions, and 3 of 15 such spells were false.")
    else:
        head = (f"EXPANSION{prov}: coincident growth is above its long-run average ({_sz(coin)}) "
                f"and the leading composite is {_sz(lead)}.")
    if k < 4:
        head += (f" The {month} reading rests on {k} of 4 coincident members; the others "
                 f"publish later and will move it.")
    cm = "; ".join(f"{c['label']} {_sz(c['z'])}" + ("" if c["in_latest"] else f" ({c['month']})")
                   for c in components["coincident"])
    lm = "; ".join(f"{c['label']} {_sz(c['z'])}" for c in components["leading"])
    drivers = (f"Coincident members (6-month annualized growth vs each series' own history): {cm}. "
               f"Leading members: {lm}.")
    calculation = (
        "Each member is standardized against its own history up to that month (expanding "
        "z-score, minimum 10 years, so no look-ahead): 6-month annualized growth for the four "
        "activity series, permits and claims; levels for the yield curve and factory hours; a "
        "1-month change for sentiment; claims and the Baa spread are inverted so that up = better. "
        "Coincident = plain average of its 4 member z's; leading = average of its 6, then a 3-month "
        f"moving average. Phase rules: CONTRACTION if coincident < {COIN_RECESSION}; SLOWDOWN if "
        f"< 0 with leading < {SLOWDOWN_LEAD}; STALL if < 0; LATE CYCLE if leading < {LEAD_WARN}; "
        "otherwise EXPANSION.")
    p, p90, r = stats.get("precision"), stats.get("precision_post1990"), stats.get("recall")
    reliability = (
        f"Scored against NBER monthly labels since 1960: coincident < {COIN_RECESSION} has "
        f"{round(100 * (p or 0))}% precision ({round(100 * (p90 or 0))}% since 1990) and "
        f"{round(100 * (r or 0))}% recall; every recession since 1970 bottomed below -1.5. In real "
        f"time (ALFRED vintages, 160 as-of dates 2000-2026) the live label matched the later revised "
        f"label {RT_AGREEMENT_PCT:.0f}% of the time - CONTRACTION {RT_BY_PHASE['CONTRACTION']}%, "
        f"SLOWDOWN {RT_BY_PHASE['SLOWDOWN']}%, STALL {RT_BY_PHASE['STALL']}%, EXPANSION "
        f"{RT_BY_PHASE['EXPANSION']}%; a typical revision moves the latest coincident reading by "
        f"{RT_EDGE_MAE}σ (p90 {RT_EDGE_P90}), which is why labels within 0.5 of zero are marked "
        "provisional.")
    steps = []
    if phase != "CONTRACTION":
        gap = coin - COIN_RECESSION
        scale = ("inside revision noise" if gap < RT_EDGE_P90
                 else f"about {gap / RT_EDGE_MAE:.0f}x a typical revision")
        steps.append(f"CONTRACTION needs the coincident line to fall {gap:.2f}σ ({scale})")
    if phase in ("STALL", "SLOWDOWN"):
        steps.append(f"EXPANSION needs +{-coin:.2f}σ"
                     f"{' (within revision noise)' if -coin < RT_EDGE_MAE else ''}")
    if phase == "STALL":
        steps.append(f"SLOWDOWN needs the leading line to fall {lead - SLOWDOWN_LEAD:.2f}σ "
                     f"to {SLOWDOWN_LEAD}")
    if phase in ("EXPANSION", "LATE_CYCLE"):
        steps.append(f"STALL needs the coincident line to fall {coin:.2f}σ below zero")
    if phase == "EXPANSION":
        steps.append(f"LATE CYCLE needs the leading line to fall {lead - LEAD_WARN:.2f}σ "
                     f"to {LEAD_WARN}")
    nxt = ("From here: " + "; ".join(steps) + ". A phase change raises a canary event only after "
           "an 8-hour confirmation on fresh data.")
    if nc:
        now = (f"Nowcast for {nc['month']} (payrolls, claims and rates for that month are already "
               f"published; the composite is not): {nc['value']:+.2f}σ -> {nc['phase']} "
               f"(bridge {nc['bridge']:+.2f}, claims member {nc['claims']:+.2f}"
               f"{'; claims member below -0.75' if nc.get('claims_trigger') else ''}). Walk-forward "
               f"1972-2026: RMSE {nc['stats']['rmse_vs_persistence_pct']}% vs persistence.")
    else:
        now = ("No nowcast at the moment: the one-month-ahead model only runs between the payrolls "
               "release and the industrial-production release each month (its bridge is fitted at "
               "fixed publication lags), so for most of the month the chart ends at the last "
               "published composite.")
    return {"headline": head, "drivers": drivers, "calculation": calculation,
            "reliability": reliability, "next": nxt, "nowcast": now}


# ---------- phase-change detection (called from the refresh job) ----------

PHASE_CONFIRM_S = 8 * 3600   # > the 6h route cache TTL: a change only alerts
                             # once a FRESH recompute (not the cached board)
                             # still shows it - kills data-glitch flapping.


def phase_change(board: dict) -> str | None:
    """Compare current phase vs the persisted last-seen phase; persist and
    return a change message the caller can event/alert on (None = no change).
    A change must persist for PHASE_CONFIRM_S before it fires; a None phase
    (degenerate board) never touches state."""
    cur = board["current"]["phase"]
    if cur is None:
        return None
    path = os.path.join(settings.cache_dir, "cycle_phase.json")
    state: dict = {}
    try:
        state = json.load(open(path))
    except Exception:  # noqa: BLE001
        pass
    prev = state.get("phase")
    now = int(time.time())
    fire = False
    if prev is None:
        state = {"phase": cur}                      # first sight: adopt quietly
    elif cur == prev:
        state.pop("candidate", None)                # back to baseline: reset
        state.pop("candidate_ts", None)
    elif state.get("candidate") == cur:
        if now - int(state.get("candidate_ts", now)) >= PHASE_CONFIRM_S:
            fire = True
            state = {"phase": cur}
    else:                                           # new candidate: start clock
        state["candidate"] = cur
        state["candidate_ts"] = now
    state.update({"month": board["current"]["month"], "ts": now})
    try:
        os.makedirs(settings.cache_dir, exist_ok=True)
        json.dump(state, open(path, "w"))
    except Exception:  # noqa: BLE001
        pass
    if fire:
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

        def mdiff(a, b):                          # calendar months a - b
            return (int(a[:4]) - int(b[:4])) * 12 + int(a[5:7]) - int(b[5:7])

        if mdiff(tgt, months[last_realized]) != 1:
            return None   # one-step model; a wider gap was never validated

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
            if mdiff(tgt, ms[-1]) != lag:
                return None   # series staler than the trained bridge lag:
                              # gl_t below would no longer mean g6(tgt-lag)
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
                "inputs_asof": {"PAYEMS": tgt,
                                "INDPRO": sorted(M["INDPRO"])[-1],
                                "W875RX1": sorted(M["W875RX1"])[-1],
                                "CMRMTSPL": sorted(M["CMRMTSPL"])[-1]},
                # honest numbers for THIS estimator (ENS_BC_S: COIN(M-1)
                # = available 3-component mean), from the timing audit's
                # walk-forward re-run - NOT the study baseline's headline,
                # which used a regressor unavailable at issue time
                "stats": {"rmse_vs_persistence_pct": -24.2,
                          "rmse_ex2020_pct": -7.0,
                          "dm_ex2020": -2.76,
                          "transitions_called_early_pct": "~25 (CI 18-34)",
                          "onsets_earlier": "5/7 earlier, 1 tie, 1 later "
                                            "(calendar basis; never missed)"},
                "basis": ("ENS_BC_S walk-forward, QA-corrected 2026-08-07; "
                          "edge = publication-timing (payrolls/claims/rates "
                          "print ~1m before the composite); final-vintage "
                          "validation - live vintages noisier; upgrade path "
                          "ENS_BC_HH in CYCLE_NOWCAST.md")}
    except Exception:  # noqa: BLE001
        return None
