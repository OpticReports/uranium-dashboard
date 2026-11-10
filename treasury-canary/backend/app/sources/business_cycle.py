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

Nowcast and completed coincident (2026-10-28): the pre-registered study
studies/cycle-nowcast-v2.md (ONE scored run, two independent verifiers)
replaced the fixed-lag ENS_BC_S form with the lag-aware ENS_HH engine
(cycle_engine.py, vendored byte-for-byte from the study) and added the
bridge-COMPLETED coincident with completion bands (cycle_bands.json). The
frozen numbers are in NOWCAST_STATS; the comments above `nowcast` carry
the decisions and the honesty caveats (final-vintage bands; the real-time
edge over persistence-in-hand is small and rests on one recession).
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
             "threshold": COIN_RECESSION,
             "scored_from": next((m for m, c in zip(months, coin) if c is not None), None)}

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
    completed = completed_headline(nc, months[-1])
    piger = piger_line(raw_override)
    flags = member_flags(M, months[-1])
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
               "members_in_latest": members_in_latest,
               "coincident_completed": completed["value"] if completed else None,
               "completed_band": completed["band"] if completed else None,
               "leading_3m_change": (rnd(lead[-1] - lead[-4])
                                     if len(lead) > 3 and lead[-1] is not None
                                     and lead[-4] is not None else None)}
    return {"months": months,
            "nowcast": nc,
            "completed": completed,
            "piger": piger,
            "flags": flags,
            "components": components,
            "read": build_read(current, provisional, components, stats, nc,
                               completed, piger, flags),
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
    return "n/a" if z is None else f"{z + 0.0:+.2f}\u03c3"     # + 0.0 kills "-0.00"


def _dir(d) -> str:
    """3-month direction of the leading composite (level says where, this says
    which way): counter-agent 2026-10-20 - direction words were computed from
    the level before."""
    if d is None:
        return ""
    return ("rising over 3 months" if d > 0.05 else "falling over 3 months" if d < -0.05
            else "flat over 3 months")


def build_read(current: dict, provisional: bool, components: dict,
               stats: dict, nc: dict | None, completed: dict | None = None,
               piger: dict | None = None, flags: dict | None = None) -> dict:
    """Six short strings the panel shows above the chart. Every number comes
    from the board itself; the frozen reliability figures are the ALFRED
    study's (module docstring). Wording is 'watch', never 'alert'. The
    revision-noise tiers use the vintage study's p90 edge error so the
    headline and the 'from here' gaps agree with the provisional band."""
    coin, lead, phase = current["coincident"], current["leading"], current["phase"]
    k, month = current["members_in_latest"], current["month"]
    ldir = _dir(current.get("leading_3m_change"))
    prov = " (provisional)" if provisional else ""
    if coin is None or lead is None or phase is None:
        return {"headline": "No phase: the composites are not computable for the latest month.",
                "drivers": "", "calculation": "", "reliability": "", "next": "", "nowcast": ""}
    p, p90, r = stats.get("precision"), stats.get("precision_post1990"), stats.get("recall")
    pct = lambda x: f"{round(100 * x)}%" if x is not None else "n/a"
    lead_level = ("above zero" if lead >= 0 else
                  f"below zero but above the {SLOWDOWN_LEAD} slowdown line" if lead >= SLOWDOWN_LEAD
                  else f"below the {SLOWDOWN_LEAD} slowdown line")
    lead_txt = f"{_sz(lead)} ({lead_level}{', ' + ldir if ldir else ''})"
    if phase == "CONTRACTION":
        head = (f"CONTRACTION: coincident growth is {_sz(coin)}, below the {COIN_RECESSION} line, "
                f"which has coincided with NBER recession months {pct(p90)} of the time since 1990 "
                f"({pct(p)} over the full sample); the leading composite is {lead_txt}.")
    elif phase == "SLOWDOWN":
        head = (f"SLOWDOWN: growth is below its long-run average ({_sz(coin)}) AND the leading "
                f"composite is {lead_txt}; in real time this label matched the later revised label "
                f"{RT_BY_PHASE['SLOWDOWN']}% of the time.")
    elif phase == "STALL":
        size = "a hair" if abs(coin) < 0.1 else "modestly" if abs(coin) < 0.5 else "clearly"
        gap = coin - COIN_RECESSION
        dist = ("well above" if gap >= 2 * RT_EDGE_P90 else "above" if gap >= RT_EDGE_P90
                else "within revision noise of")
        head = (f"STALL{prov}: coincident growth is {size} below its long-run average "
                f"({_sz(coin)}) and {dist} the recession line ({COIN_RECESSION}); the leading "
                f"composite is {lead_txt}.")
    elif phase == "LATE_CYCLE":
        head = (f"LATE CYCLE: growth is still above average ({_sz(coin)}) but the leading "
                f"composite is {lead_txt}, under {LEAD_WARN}; this crossing came strictly early "
                f"on 4 of 7 recessions, and about 3 of 15 such spells were false (two knife-edge).")
    else:
        head = (f"EXPANSION{prov}: coincident growth is above its long-run average ({_sz(coin)}) "
                f"and the leading composite is {lead_txt}.")
    if k < 4:
        head += (f" The {month} reading rests on {k} of 4 coincident members; the others "
                 f"publish later and will move it.")
        if completed and completed.get("value") is not None:
            lo, hi = (completed.get("band") or [None, None])
            band = f" (80% band {lo:+.2f} to {hi:+.2f})" if lo is not None and hi is not None else ""
            head += (f" Bridging the lagging member{'s' if len(completed.get('pattern') or {}) != 1 else ''} "
                     f"gives {_sz(completed['value'])}{band}: the completed value in the header; the "
                     f"partial mean is the phase/alert quantity.")
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
    since = stats.get("scored_from") or "1970"
    reliability = (
        f"Scored against NBER monthly labels from {since} (the z-scores need a 10-year warm-up): "
        f"coincident < {COIN_RECESSION} has {pct(p)} precision ({pct(p90)} since 1990) and "
        f"{pct(r)} recall; every recession since 1970 bottomed below -1.5. In real time (ALFRED "
        f"vintages, 160 as-of dates 2000-2026) the live label matched the later revised label "
        f"{RT_AGREEMENT_PCT:.0f}% of the time - CONTRACTION {RT_BY_PHASE['CONTRACTION']}%, "
        f"SLOWDOWN {RT_BY_PHASE['SLOWDOWN']}%, STALL {RT_BY_PHASE['STALL']}%, EXPANSION "
        f"{RT_BY_PHASE['EXPANSION']}%; a typical revision moves the latest coincident reading by "
        f"{RT_EDGE_MAE}\u03c3 (p90 {RT_EDGE_P90}), which is why EXPANSION/STALL labels within 0.5 "
        "of zero are marked provisional.")
    # the 'from here' gaps: each names the phase phase_of() actually returns
    # when only that variable crosses its line
    steps = []
    noise = lambda g: ("inside revision noise" if g < RT_EDGE_P90
                       else f"about {g / RT_EDGE_MAE:.0f}x a typical revision")
    below_zero_phase = "SLOWDOWN" if lead < SLOWDOWN_LEAD else "STALL"
    if phase == "CONTRACTION":
        g = COIN_RECESSION - coin
        steps.append(f"exit to {below_zero_phase} needs the coincident line to rise {abs(g):.2f}\u03c3 "
                     f"to {COIN_RECESSION} ({noise(g)})")
    else:
        g = coin - COIN_RECESSION
        steps.append(f"CONTRACTION needs the coincident line to fall {abs(g):.2f}\u03c3 ({noise(g)})")
    if phase in ("STALL", "SLOWDOWN"):
        steps.append(f"EXPANSION needs the coincident line to rise {abs(coin):.2f}\u03c3 to zero"
                     f"{' (inside revision noise)' if abs(coin) < RT_EDGE_P90 else ''}")
    if phase == "STALL":
        steps.append(f"SLOWDOWN needs the leading line to fall {abs(lead - SLOWDOWN_LEAD):.2f}\u03c3 "
                     f"to {SLOWDOWN_LEAD}")
    if phase == "SLOWDOWN":
        steps.append(f"STALL needs the leading line to rise {abs(SLOWDOWN_LEAD - lead):.2f}\u03c3 "
                     f"to {SLOWDOWN_LEAD}")
    if phase in ("EXPANSION", "LATE_CYCLE"):
        steps.append(f"{below_zero_phase} needs the coincident line to fall {abs(coin):.2f}\u03c3 "
                     f"below zero")
    if phase == "EXPANSION":
        steps.append(f"LATE CYCLE needs the leading line to fall {abs(lead - LEAD_WARN):.2f}\u03c3 "
                     f"to {LEAD_WARN}")
    if phase == "LATE_CYCLE":
        steps.append(f"EXPANSION needs the leading line to rise {abs(LEAD_WARN - lead):.2f}\u03c3 "
                     f"to {LEAD_WARN}")
    nxt = ("From here: " + "; ".join(steps) + ". A phase change raises a canary event only after "
           "an 8-hour confirmation on fresh data.")
    now = _nowcast_read(nc, completed)
    return {"headline": head, "drivers": drivers, "calculation": calculation,
            "reliability": reliability, "next": nxt, "nowcast": now,
            "completed": _completed_read(current, completed),
            "piger": _piger_read(piger), "flags": _flags_read(flags)}


def _nowcast_read(nc: dict | None, completed: dict | None) -> str:
    """v2 nowcast sentence: value, information set and lags, or the reason
    there is none (v1 §2.4: every None carries a reason)."""
    if not nc:
        return "No nowcast: the engine did not run."
    lags = nc.get("lags") or {}
    lag_txt = ", ".join(f"{c} {L}" for c, L in lags.items() if L) or "all four members published"
    dropped = nc.get("dropped") or []
    if nc.get("value") is None:
        return (f"No nowcast for {nc.get('month')}: {nc.get('reason')}. Members lagging the payrolls "
                f"month: {lag_txt}.")
    st = nc.get("stats", {})
    return (f"Nowcast for {nc['month']} (information set {nc.get('info_set')}: payrolls for that month "
            f"are published; members lagging it by months: {lag_txt}"
            f"{'; dropped (lag >= 4, re-meaned): ' + ', '.join(dropped) if dropped else ''}): "
            f"{nc['value']:+.2f}\u03c3 -> {nc['phase']} (bridge {nc['bridge']:+.2f}, claims member "
            f"{nc['claims']:+.2f}{'; claims member below -0.75' if nc.get('claims_trigger') else ''}). "
            f"Pre-registered v2 (scored 2026-10-28): RMSE {st.get('lagsim_rmse_vs_pers_pct_full')}% vs "
            f"persistence 1972-2026 ({st.get('lagsim_rmse_vs_pers_pct_ex2020')}% ex-2020; the edge is "
            f"thin since 2013, ratio {st.get('lagsim_ratio_2013plus_ex2020')}); in true real time 2013+ "
            f"RMSE {st.get('realtime_rmse_ex2020')} vs {st.get('realtime_pers_in_hand_rmse_ex2020')} for "
            f"the best persistence actually in hand.")


def _completed_read(current: dict, completed: dict | None) -> str:
    k, month = current.get("members_in_latest"), current.get("month")
    partial = current.get("coincident")
    if not completed or completed.get("value") is None:
        why = (completed or {}).get("reason") or "no completion available"
        return (f"Headline coincident {partial:+.2f}\u03c3 is the mean of {k} of 4 members for {month}; "
                f"no bridge-completed value ({why}).") if partial is not None else ""
    lo, hi = (completed.get("band") or [None, None])
    band = f" (80% band {lo:+.2f} to {hi:+.2f})" if lo is not None and hi is not None else " (band pending)"
    pat = completed.get("pattern") or {}
    pat_txt = ", ".join(f"{c} bridged {L}m" for c, L in pat.items()) or "all members published"
    return (f"Completed coincident for {month}: {completed['value']:+.2f}\u03c3{band}; {pat_txt}. The "
            f"{k}-of-4 partial mean reads {partial:+.2f}\u03c3 and stays the phase/alert quantity "
            f"(completed RMSE 0.133 vs 0.168 partial, 1977-2026; bands are completion error only).")


def _piger_read(piger: dict | None) -> str:
    if not piger:
        return "Chauvet-Piger probability unavailable."
    return (f"Chauvet-Piger recession probability (FRED, smoothed): {piger['pct']:.1f}% for "
            f"{piger['month']}; 3x80% rule {piger['state_3x80'].replace('-', ' ')}. Real-time record "
            f"2006-2026: declared 2008 on 2009-01-01 (13 months after the peak), never declared 2020 "
            f"by 3x80%. Same four inputs as our composite - a cross-check, not independent evidence.")


def _flags_read(flags: dict | None) -> str:
    if not flags:
        return ""
    if flags.get("umcsent_delayed"):
        return (f"Sentiment (UMCSENT) is {flags['umcsent_lag_months']} months behind the headline month "
                f"on FRED (last {flags['umcsent_month']}); the leading composite uses its last print.")
    return ""


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
    coin_now = board["current"].get("coincident")
    quiet = (prev is not None and cur != prev and {prev, cur} == {"EXPANSION", "STALL"}
             and coin_now is not None and abs(coin_now) < RT_EDGE_P90)
    if prev is None:
        state = {"phase": cur}                      # first sight: adopt quietly
    elif quiet:
        # EXPANSION<->STALL inside the revision band (|coin| < p90 edge error
        # 0.46): the label flips ~1-in-3 on revision there, so re-baseline
        # quietly - no event, no alert (backlog item 9, 2026-10-28)
        state = {"phase": cur, "quiet_rebaseline": prev}
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


# ---------- nowcast v2: lag-aware, issued every day (cycle-nowcast-v2) ----------
# Pre-registered study studies/cycle-nowcast-v2.md, ONE scored run 2026-10-28
# (results.json, verified). The engine is the study's own, vendored byte-for-
# byte as cycle_engine.py (gate test). Decisions as frozen:
#   D-1 PASS    ENS_HH at the information set in force is the one-month-ahead
#               reading: RMSE vs realized persistence -29.9% full / -12.5%
#               ex-2020 (bars -25 / -8), DM NW-6 t = -4.69 (bar -1.645); final-
#               vintage replay 1972-01..2026-07, n = 655. Thin recently: the
#               2013+ ex-2020 ratio is 0.94 (whole sample 0.875).
#   D-2 PASS    the bridge-COMPLETED coincident is the headline value with its
#               band (RMSE 0.133 vs 0.168 for the partial mean; the partial
#               stays the gate/alert quantity, Q6 default).
#   D-3 SUCCESS calibrated ENS_HH / calibrated ADS RMSE ratio 0.71 on 120
#               real-time rows 2015-07+ ex-2020 (SUCCESS <= 1.10).
# True real time (ALFRED vintages, 2013-06+, one recession, descriptive): ex-2020
# RMSE 0.234 vs 0.253 (completed-persistence in hand) and 0.279 (available-
# members persistence) - but 0.194 for the HINDSIGHT final-vintage persistence
# nobody has on the day. Availability: a reading on 100% of calendar days vs
# 33% for the retired fixed-lag form (11% in the 2025-10..2026-04 shutdown).
# Bands: completion error only, final-vintage; first-print revision excluded.

from . import cycle_engine as CE

_BANDS_PATH = os.path.join(os.path.dirname(__file__), "cycle_bands.json")
PIGER_SERIES = "RECPROUSM156N"        # FRED smoothed Chauvet-Piger, PERCENT
PIGER_HI, PIGER_LO = 80.0, 20.0        # Piger's 3-month declaration rule

NOWCAST_STATS = {
    # frozen numbers of the ONE scored run (studies/cycle_nowcast_v2/results.json)
    "study": "cycle-nowcast-v2, scored 2026-10-28 (pre-registered; verified)",
    "lagsim_rmse_vs_pers_pct_full": -29.9, "lagsim_rmse_vs_pers_pct_ex2020": -12.5,
    "lagsim_dm_t_ex2020": -4.69, "lagsim_n": 655, "lagsim_window": "1972-01..2026-07",
    "lagsim_ratio_2013plus_ex2020": 0.94,
    "realtime_rmse_ex2020": 0.234, "realtime_pers_in_hand_rmse_ex2020": 0.253,
    "realtime_pers_available_rmse_ex2020": 0.279, "realtime_pers_hindsight_rmse_ex2020": 0.194,
    "realtime_n_ex2020": 145, "realtime_window": "2013-06..2026-09 (one recession)",
    "comparator_r_ens_over_ads_ex2020": 0.713, "comparator_n": 120,
    "completed_rmse": 0.133, "partial_rmse": 0.168,
    "availability_share_days_v2": 1.0, "availability_share_days_fixed_lag": 0.33,
}


def _load_bands() -> dict:
    try:
        return json.load(open(_BANDS_PATH))["bands"]
    except Exception:  # noqa: BLE001
        return {}


BANDS = _load_bands()


def _rnd(x, k=3):
    return None if x is None else round(float(x), k)


def nowcast(M: dict, months: list, coin: list, today: str | None = None) -> dict | None:
    """v2 reading from the series in hand (any lags): cycle_engine.issue on the
    monthly dicts the board already holds. Always returns a dict for the target
    month (the last PAYEMS month); `value` is None only with a `reason`
    (v1 §2.4). The old fixed-lag form returned None ~2/3 of the days."""
    try:
        state = {k: {m: v for m, v in d.items() if v is not None} for k, d in M.items()}
        out = CE.issue(state, d=today, mode="scoring", bands=BANDS)
    except Exception as exc:  # noqa: BLE001
        return {"month": max(M["PAYEMS"]) if M.get("PAYEMS") else None, "value": None,
                "reason": f"engine error: {type(exc).__name__}: {exc}", "stats": NOWCAST_STATS}
    ens = out.get("ens_hh")
    ct, cp = out.get("completed_target"), out.get("completed_prev")
    claims = out.get("claims_hh")
    return {"month": out["target_month"], "value": _rnd(ens),
            "bridge": _rnd(out.get("bridge_hh")), "claims": _rnd(claims),
            "phase": out.get("phase"),
            "claims_trigger": bool(claims is not None and claims < COIN_RECESSION),
            "info_set": out.get("info_set"), "lags": out.get("lags"), "K": out.get("K"),
            "dropped": out.get("dropped") or [], "members_bridged": out.get("members_bridged") or {},
            "members_skipped": out.get("members_skipped") or [],
            "flags": out.get("flags") or {},
            "reason": out.get("reason"),
            "last_complete_coin": out.get("last_complete_coin"),
            "completed_target": ({"month": ct["month"], "value": _rnd(ct["value"]),
                                  "band": [_rnd(b) for b in ct["band"]] if ct.get("band") else None,
                                  "pattern": ct["pattern"], "dropped": ct["dropped"],
                                  "pattern_key": ct["pattern_key"], "band_basis": ct["band_basis"]}
                                 if ct else None),
            "completed_prev": ({"month": cp["month"], "value": _rnd(cp["value"]),
                                "band": [_rnd(b) for b in cp["band"]] if cp.get("band") else None,
                                "pattern": cp["pattern"], "dropped": cp["dropped"],
                                "pattern_key": cp["pattern_key"], "band_basis": cp["band_basis"],
                                "nonstandard_pattern": cp.get("nonstandard_pattern")}
                               if cp else None),
            "persistence": {k: _rnd(v) for k, v in (out.get("persistence") or {}).items()},
            "inputs_asof": {c: (max(M[c]) if M.get(c) else None)
                            for c in ("PAYEMS", "INDPRO", "W875RX1", "CMRMTSPL", "ICSA")},
            "stats": NOWCAST_STATS,
            "basis": ("ENS_HH = 0.5*BRIDGE_HH + 0.5*CLAIMS_HH at the information set in force "
                      "(lag-aware bridges per member, claims/curve regression on bridge-"
                      "completed history; rows admitted only through K = M - max lag). "
                      "Pre-registered cycle-nowcast-v2, one scored run 2026-10-28; final-"
                      "vintage replay 1972-2026 plus a true real-time replay on ALFRED "
                      "vintages 2013-06+ (one recession). Bands = completion error only.")}


def completed_headline(nc: dict | None, month: str) -> dict | None:
    """The bridge-COMPLETED coincident for the board's headline month (D-2):
    completed_target when the axis already holds the PAYEMS month, else
    completed_prev; None (with reason) otherwise."""
    if not nc:
        return None
    for key in ("completed_target", "completed_prev"):
        c = nc.get(key)
        if c and c.get("month") == month and c.get("value") is not None:
            return {"month": month, "value": c["value"], "band": c.get("band"),
                    "pattern": c.get("pattern"), "dropped": c.get("dropped") or [],
                    "band_basis": c.get("band_basis"), "source": key}
    return {"month": month, "value": None, "band": None, "pattern": None, "dropped": [],
            "band_basis": None, "source": None,
            "reason": nc.get("reason") or "no completion for the headline month"}


def piger_line(raw_override: dict | None = None) -> dict | None:
    """Chauvet-Piger smoothed recession probability (FRED RECPROUSM156N, PERCENT)
    as a cross-check line: latest print, the last three months, and the state
    of Piger's 3x80% / 3x20% rule on the CURRENT vintage. Descriptive: in the
    pre-registered study the real-time record (240 releases 2006-08..2026-09)
    declared 2008 on 2009-01-01 (13 months after the NBER peak month, 31 days
    after NBER's own announcement) and never declared 2020 by 3x80% (the 100%
    print of 2020-04-30 was followed by re-based months). Same four inputs as
    our composite: a different model, not independent data. Optional: None when
    the series is unavailable."""
    try:
        if raw_override is not None:
            pairs = raw_override.get(PIGER_SERIES)
            if not pairs:
                return None
            dates, vals = [p[0] for p in pairs], [float(p[1]) for p in pairs]
        else:
            dates, vals = fetch_series(PIGER_SERIES, start="1967-06-01")
        ser = _monthly(dates, vals, "last")
        if not ser:
            return None
        ms = sorted(ser)
        last3 = [(m, ser[m]) for m in ms[-3:]]
        pcts = [v for _, v in last3]
        state = ("recession-declared" if len(pcts) == 3 and all(v > PIGER_HI for v in pcts) else
                 "expansion-declared" if len(pcts) == 3 and all(v < PIGER_LO for v in pcts) else
                 "undeclared")
        return {"series": PIGER_SERIES, "month": ms[-1], "pct": round(ser[ms[-1]], 2),
                "last3": [{"month": m, "pct": round(v, 2)} for m, v in last3],
                "state_3x80": state, "fires_1m50": bool(ser[ms[-1]] >= 50.0),
                "rule": "three consecutive months > 80% = recession start; < 20% = end (Piger)",
                "basis": ("smoothed (two-sided) probabilities: the back-history overstates "
                          "real-time skill; the latest print IS the real-time reading for its "
                          "month. Real-time record 2006-2026: 2008 declared 2009-01-01, 2020 "
                          "never declared by 3x80%. Same four inputs as the composite.")}
    except Exception:  # noqa: BLE001
        return None


def member_flags(M: dict, headline_month: str) -> dict:
    """Publication-delay flags for the read box (Q11: UMCSENT's one-month FRED
    delay since September 2026)."""
    um = max(M["UMCSENT"]) if M.get("UMCSENT") else None
    lag = (mdiff_months(headline_month, um) if um else None)
    return {"umcsent_month": um, "umcsent_lag_months": lag,
            "umcsent_delayed": bool(lag is not None and lag >= 2)}


def mdiff_months(a: str, b: str) -> int:
    return (int(a[:4]) - int(b[:4])) * 12 + int(a[5:7]) - int(b[5:7])
