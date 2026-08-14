"""EWM engine v2 — report-v6 cohort surface on a REVENUE-multiple basis.

v2 replaces the seeded EBITDA-multiple surface with the operator's own
Rate Cycle Scenario Cohort table (cohort_v6.json, extracted 2026-08-02):
per-scenario VALUE RANGES at the two report close windows (end Q1'27, end
Q2'27), priced as revenue multiples on the report's $105M revenue basis.

Additions per ewm/METHODOLOGY_RESEARCH.md shortlist:
  1. dynamic revenue ramp — $105M run-rate at end-Dec-2026 (editable), evenly
     scaling to the $200-225M valuation target by 2027-07-31; today's implied
     run-rate is extrapolated back along the same line
  2. closed-form breakeven row (Q1 vs Q2 flip conditions: weight shifts in pp,
     extra stall hazard h*)
  3. hawk-skewed cell ranges propagated end-to-end (perfect-correlation
     EV_lo/EV_hi bounds) — replaces the flat 6% exec-noise band
  4. split-concentration Dirichlet weight-uncertainty band (mean-preserving:
     Beta on the tail mass at kappa_lo, Dirichlet on the head at kappa_hi)
  5. stall-adjusted EV + hold-to-target premium per month
Window scores, rate risk, cost-of-delay and action cards carry over from v1
(amendments A1-A6 unchanged); the report-fidelity gate pins revenue at $105M
so the report cells are reproduced exactly.
"""
from __future__ import annotations

import json
import os

import numpy as np

_COHORT = json.load(open(os.path.join(os.path.dirname(__file__), "cohort_v6.json")))
_PLAN = json.load(open(os.path.join(os.path.dirname(__file__), "plan_aug2026.json")))

MONTHS = [f"{y}-{m:02d}" for y, ms in ((2026, range(9, 13)), (2027, range(1, 13)))
          for m in ms]                                    # 2026-09 .. 2027-12
Q1END, Q2END = "2027-03", "2027-06"                       # report close windows
TARGET_M = "2027-07"                                      # scale target 2027-07-31
ANCHOR = Q1END                                            # report-fidelity anchor
FOMC = ["2026-09", "2026-10", "2026-12", "2027-01", "2027-03", "2027-04",
        "2027-06", "2027-07", "2027-09", "2027-10", "2027-12"]
CPI = MONTHS                                              # monthly release

REV_BASIS = float(_COHORT["deal_profile"]["revenue_m"])   # 105 — report's basis

# v2.1 EXTENSION row (NOT in the report): benign-easing cut scenario. The
# report's futures context prices ~30-35% odds of NO hike by December; cuts
# are a small slice of that mass, so 5pp is carved from the holds row
# (judgment-tagged). Values reverse the report's debt-capacity anchor
# (~$10M per 50bp) for a 25-50bp easing, with the same +5M Q1->Q2 dove
# drift as the holds row. A recession-FORCED cut is NOT this row — that is
# the crash / 50bp-regime stress machinery (shock-sim finding: cut
# scenarios carry MORE tail risk, but through the deterioration that
# forces them, which the cohort conditions away).
EXT_CUT = {"hike_path": "1+ cuts (benign easing)", "probability": 0.05,
           "id": -1, "fed_funds_q1_2027_pct": [3.25, 3.50],
           "value_close_end_q1_2027_m": [205, 218],
           "value_close_end_q2_2027_m": [210, 223]}
CUT_CARVE = EXT_CUT["probability"]                        # funded from the holds row

# per-scenario multiple ranges = value cells / report revenue basis
SCEN = []
for _src, _s in [("extension-v2", EXT_CUT)] + [("report-v6", s)
                                               for s in _COHORT["scenarios"]]:
    SCEN.append({
        "label": _s["hike_path"],
        "hikes": _s["id"],
        "source": _src,
        "modal": bool(_s.get("modal", False)),
        "q1": tuple(v / REV_BASIS for v in _s["value_close_end_q1_2027_m"]),
        "q2": tuple(v / REV_BASIS for v in _s["value_close_end_q2_2027_m"]),
        "stall_p": (sum(_s["process_stall_probability"]) / 2
                    if "process_stall_probability" in _s else 0.0),
        "fed_funds": _s["fed_funds_q1_2027_pct"],
    })
MODAL_S = next(i for i, s in enumerate(SCEN) if s["modal"])
HIKES = [s["hikes"] for s in SCEN]                        # [-1, 0, 1, 2, 3, 4]
IDX = {h: i for i, h in enumerate(HIKES)}
NS = len(SCEN)

PARAMS = {
    "hike_weights": [CUT_CARVE] + [
        s["probability"] - (CUT_CARVE if s["id"] == 0 else 0.0)
        for s in _COHORT["scenarios"]],                   # [.05,.25,.35,.25,.07,.03]
    # --- dynamic ramp (operator premise: evenly scaling, on pace) ---
    "revenue_dec2026": REV_BASIS,                         # editable run-rate waypoint
    # valuation target = the company plan's Q2'27 -> Q3'27 EV band (Ray,
    # Aug 2026; was [200, 225] from the operator report). The Jul-31-27
    # scale target sits inside this window on the plan's own interpolation.
    "target_value": [226.7, 241.6],                       # editable valuation target
    # --- company-plan anchoring (Casey: the plan quarters ARE the actual
    # values at those close dates — the central line, with the cohort grid
    # supplying scenario dispersion AROUND it). False here keeps the pure
    # engine on the legacy ramp; the live board flips it on via inputs.
    "anchor_plan": False, "plan_margins": {}, "plan_multiples": {},
    "ramp_scenario": MODAL_S,                             # 'on pace' priced on the modal path (judgment)
    # --- multiple extrapolation guards beyond the report's two windows ---
    "mult_floor": 1.20, "mult_cap": 2.10,
    # --- stall model (delay-not-death, amendment A6d calibration) ---
    "stall_value_pct": -6.5, "stall_death_tail": 0.13,
    "stall_death_recovery": 0.65,                         # judgment: dead process re-run later recovers ~65%
    "stall_exposure_q1": 0.5,                             # Q1 close dodges half the hawk-row stall window
    # --- Dirichlet weight-uncertainty (memo e1: split concentration) ---
    "kappa_hi": 60.0, "kappa_lo": 15.0,
    "dirichlet_draws": 4000, "seed": 20260802,
    # --- v1 carryover: dissent bump, window scoring, stages, cards ---
    "dissent_bump_pp": 3.0,                               # tail-only, from doves (A1)
    "w_rate": 0.35, "w_fcix": 0.25, "w_dmhi": 0.20, "w_canary": 0.20,
    "green_min": 70.0, "amber_min": 45.0,
    "gap_months_dovish": 2.5, "gap_months_hawkish": 4.5,
    "event_w_fomc": 1.0, "event_w_cpi": 0.4,
    "lead_by_stage": {"not_started": 7, "prep": 6, "in_market": 4,
                      "loi": 2, "exclusivity": 1, "close": 0},
}


def _mi(m: str) -> int:
    return MONTHS.index(m)


def scenario_weights(p: dict, dissent_cluster: bool) -> list[float]:
    w = list(p["hike_weights"])
    if dissent_cluster:                                   # tail-only bump (A1)
        bump = p["dissent_bump_pp"] / 100.0
        w[IDX[3]] += bump * 0.7
        w[IDX[4]] += bump * 0.3
        w[IDX[-1]] -= bump * 0.2                          # funded from the dove rows
        w[IDX[0]] -= bump * 0.5
        w[IDX[1]] -= bump * 0.3
    s = sum(w)
    return [max(x, 0.0) / s for x in w]


def multiple_range(s: int, m: str, p: dict = PARAMS) -> tuple[float, float, float]:
    """(lo, mid, hi) revenue multiple for scenario s at close month m.
    Exact report cells at Q1END/Q2END; linear between; flat before Q1END
    (transmission lag: pre-window closes still get Q1 pricing — conservative);
    linear extrapolation past Q2END clipped to [mult_floor, mult_cap]."""
    i, i1, i2 = _mi(m), _mi(Q1END), _mi(Q2END)
    f = max(0.0, (i - i1) / (i2 - i1))
    lo1, hi1 = SCEN[s]["q1"]
    lo2, hi2 = SCEN[s]["q2"]
    lo = min(max(lo1 + f * (lo2 - lo1), p["mult_floor"]), p["mult_cap"])
    hi = min(max(hi1 + f * (hi2 - hi1), p["mult_floor"]), p["mult_cap"])
    if hi < lo:
        lo, hi = hi, lo
    return lo, (lo + hi) / 2, hi


def revenue_ramp(p: dict) -> dict:
    """Monthly revenue line feeding the whole surface (cells, breakeven,
    Dirichlet band, MC fan all read this — one source of level truth).

    anchor_plan mode (the live default): the company plan's EV track is the
    CENTRAL line. Effective revenue r(m) = plan_EV(m) / base-weighted mid
    multiple, so the base-weighted EV reproduces the plan by construction
    and the cohort grid contributes scenario DISPERSION around it. The
    anchor uses the frozen cohort base weights — dissent, tilt and stall
    still move value around the plan rather than being absorbed into it.

    Legacy mode: linear line through the editable Dec-2026 run-rate
    waypoint and the revenue back-solved to hit the valuation target at
    2027-07-31 under the modal path."""
    if p.get("anchor_plan"):
        plan = company_plan(p.get("plan_margins"), p.get("plan_multiples"))
        bw = [max(x, 0.0) for x in PARAMS["hike_weights"]]
        bw = [x / sum(bw) for x in bw]
        rev = {}
        for m in MONTHS:
            wm = sum(wi * multiple_range(s, m, p)[1] for s, wi in enumerate(bw))
            rev[m] = round(plan["ev_by_month"][m] / wm, 2)
        return {"revenue": rev, "target_revenue": rev[TARGET_M],
                "slope_per_month": round((rev[MONTHS[-1]] - rev[MONTHS[0]])
                                         / (len(MONTHS) - 1), 4),
                "today_implied": rev[MONTHS[0]], "anchored": True,
                "basis_note": "surface anchored to the company plan EV track "
                              "(EV = TTM EBITDA x multiple); base-weighted EV "
                              "reproduces the plan by construction — weights, "
                              "dissent and stall move value AROUND it"}
    mult_t = multiple_range(p["ramp_scenario"], TARGET_M, p)[1]
    r_target = (sum(p["target_value"]) / 2) / mult_t
    r0, i0, it = p["revenue_dec2026"], _mi("2026-12"), _mi(TARGET_M)
    slope = (r_target - r0) / (it - i0)
    return {"revenue": {m: round(r0 + slope * (_mi(m) - i0), 2) for m in MONTHS},
            "target_revenue": round(r_target, 2),
            "slope_per_month": round(slope, 4),
            "today_implied": round(r0 + slope * (0 - i0), 2),
            "anchored": False,
            "basis_note": f"on-pace target priced at the modal-path multiple "
                          f"{mult_t:.2f}x at {TARGET_M} (judgment)"}


def company_plan(margin_overrides: dict | None = None,
                 multiple_overrides: dict | None = None) -> dict:
    """The banker plan track (Ray, Aug 2026): EV = TTM EBITDA x EBITDA
    multiple per quarter. Margin %% and multiple are editable per quarter
    (keyed by period label, e.g. "Q1 2027"); a margin edit recomputes EBITDA
    off the plan's TTM revenue, so revenue stays the fixed premise and
    margin/multiple are the two levers. This is a SEPARATE LENS from the
    cohort surface (rate scenarios on the report's revenue basis) — shown
    side by side, never blended into the scenario math."""
    mo = margin_overrides or {}
    xo = multiple_overrides or {}
    rows = []
    for q in _PLAN["quarters"]:
        rev = float(q["ttm_revenue"])
        base_margin = 100.0 * q["ttm_ebitda"] / rev
        try:
            margin = float(mo.get(q["period"], base_margin))
        except (TypeError, ValueError):
            margin = base_margin
        margin = min(max(margin, 0.0), 60.0)
        try:
            mult = float(xo.get(q["period"], q["ebitda_multiple"]))
        except (TypeError, ValueError):
            mult = float(q["ebitda_multiple"])
        mult = min(max(mult, 0.0), 30.0)
        ebitda = rev * margin / 100.0
        rows.append({"period": q["period"], "month": q["month"],
                     "revenue_m": round(rev / 1e6, 2),
                     "margin_pct": round(margin, 2),
                     "margin_default_pct": round(base_margin, 2),
                     "margin_overridden": q["period"] in mo,
                     "ebitda_m": round(ebitda / 1e6, 2),
                     "multiple_x": round(mult, 2),
                     "multiple_default_x": float(q["ebitda_multiple"]),
                     "multiple_overridden": q["period"] in xo,
                     "ev_m": round(ebitda * mult / 1e6, 1)})
    # monthly EV line for chart overlays: linear between quarter-end months,
    # clamped flat outside the plan's span (no extrapolation beyond Ray's table)
    pts = [(_mi(r["month"]), r["ev_m"]) for r in rows]
    ev_by_month = {}
    for m in MONTHS:
        i = _mi(m)
        if i <= pts[0][0]:
            v = pts[0][1]
        elif i >= pts[-1][0]:
            v = pts[-1][1]
        else:
            v = pts[-1][1]
            for (a, va), (b, vb) in zip(pts, pts[1:]):
                if a <= i <= b:
                    v = va + (vb - va) * (i - a) / (b - a)
                    break
        ev_by_month[m] = round(v, 1)
    return {"rows": rows, "ev_by_month": ev_by_month,
            "source": _PLAN["source_tag"], "received": _PLAN["received"],
            "basis": _PLAN["basis"]}


def stall_exposure(m: str, p: dict = PARAMS) -> float:
    """Share of a hawk row's stall risk a close at m is exposed to: closing by
    Q1-end dodges half the hike-transmission window; Q2-end and later carry
    it all; linear between."""
    i, i1, i2 = _mi(m), _mi(Q1END), _mi(Q2END)
    if i <= i1:
        return p["stall_exposure_q1"]
    if i >= i2:
        return 1.0
    return p["stall_exposure_q1"] + (1 - p["stall_exposure_q1"]) * (i - i1) / (i2 - i1)


def _stall_cost_frac(s: int, m: str, p: dict) -> float:
    """Expected fractional value cost of stall risk for scenario s closing at
    m: P(stall)·exposure·(recut haircut + death tail · unrecovered value).
    stall_mult scales the hawk-row hazard from the live HY financing state
    (BENIGN x1 / TIGHT x1.33 / SHUT x1.67 — CANARY_COUPLING memo §3)."""
    sp = min(0.95, SCEN[s]["stall_p"] * p.get("stall_mult", 1.0))
    if sp == 0.0:
        return 0.0
    per_event = abs(p["stall_value_pct"]) / 100 + p["stall_death_tail"] * (1 - p["stall_death_recovery"])
    return sp * stall_exposure(m, p) * per_event


def apply_weight_tilt(p: dict, tilt: dict | None) -> dict:
    """Bounded market-nowcast tilt: move `pp` (capped ±5pp) of weight toward
    the hikes-row `toward`, funded proportionally from the other rows. Only
    ever applied via the operator's Apply button — never silently."""
    if not tilt or not tilt.get("pp"):
        return p
    toward = int(tilt.get("toward", 1))
    if toward not in IDX:
        return p
    pp = max(0.0, min(0.05, float(tilt["pp"])))
    w = list(p["hike_weights"])
    ti = IDX[toward]
    others = sum(x for i, x in enumerate(w) if i != ti)
    if others <= 0:
        return p
    w = [x - pp * x / others if i != ti else x + pp for i, x in enumerate(w)]
    s = sum(w)
    return {**p, "hike_weights": [max(x, 0.0) / s for x in w]}


def cohort_surface(p: dict, dissent_cluster: bool = False,
                   pin_report: bool = False) -> dict:
    """V(s, m) = multiple(s, m) x revenue(m). pin_report=True pins revenue at
    the report's $105M basis so the report cells reproduce exactly (gate G1);
    live mode applies the ramp — the report held performance constant, the
    ramp is the operator's stated scaling premise layered on top."""
    w = scenario_weights(p, dissent_cluster)
    ramp = revenue_ramp(p)
    rows = []
    for m in MONTHS:
        rev = REV_BASIS if pin_report else ramp["revenue"][m]
        cells = []
        for s in range(NS):
            lo, mid, hi = (x * rev for x in multiple_range(s, m, p))
            cells.append({"lo": round(lo, 1), "mid": round(mid, 1),
                          "hi": round(hi, 1),
                          "stall_p": SCEN[s]["stall_p"]})
        ev = sum(wi * c["mid"] for wi, c in zip(w, cells))
        ev_lo = sum(wi * c["lo"] for wi, c in zip(w, cells))   # perfect-corr bounds
        ev_hi = sum(wi * c["hi"] for wi, c in zip(w, cells))
        ev_adj = sum(wi * c["mid"] * (1 - _stall_cost_frac(s, m, p))
                     for s, (wi, c) in enumerate(zip(w, cells)))
        hawk_i = [i for i, h in enumerate(HIKES) if h >= 2]
        hawk_mass = sum(w[i] for i in hawk_i)
        ev_hawk = (sum(w[s] * cells[s]["mid"] * (1 - _stall_cost_frac(s, m, p))
                       for s in hawk_i) / hawk_mass) if hawk_mass > 0 else 0.0
        rows.append({"month": m, "revenue": round(rev, 1),
                     "ev": round(ev, 1), "ev_lo": round(ev_lo, 1),
                     "ev_hi": round(ev_hi, 1), "ev_stall_adj": round(ev_adj, 1),
                     "ev_hawk_adj": round(ev_hawk, 1),
                     "modal": cells[MODAL_S]["mid"],
                     "cells": cells,
                     "tag": ("report" if m in (Q1END, Q2END) else
                             "interpolated" if _mi(Q1END) < _mi(m) < _mi(Q2END) else
                             "extrapolated")})
    return {"months": MONTHS, "surface": rows, "weights": w, "ramp": ramp,
            "pin_report": pin_report,
            "scenarios": [{"label": s["label"], "modal": s["modal"],
                           "hikes": s["hikes"], "source": s["source"],
                           "stall_p": s["stall_p"], "fed_funds": s["fed_funds"],
                           "weight": round(wi, 3)}
                          for s, wi in zip(SCEN, w)],
            "source": _COHORT["source_tag"]}


def breakeven(p: dict, dissent_cluster: bool = False,
              pin_report: bool = False) -> dict:
    """Closed-form Q1-end vs Q2-end flip conditions (memo e2). EV is linear in
    the weights, so every flip has an exact expression:
      - dEV = EV(Q1) - EV(Q2) on midpoint cells (negative => Q2 ahead)
      - weight shifts (pp) that zero dEV for the two canonical pairs
      - extra hawk-row stall hazard h* at which waiting to Q2 forfeits the
        hawk-row close and Q1 wins: h* = -dEV / sum_{s>=3} w_s V(s, Q1)."""
    w = scenario_weights(p, dissent_cluster)
    ramp = revenue_ramp(p)
    r1 = REV_BASIS if pin_report else ramp["revenue"][Q1END]
    r2 = REV_BASIS if pin_report else ramp["revenue"][Q2END]
    q1 = [multiple_range(s, Q1END, p)[1] * r1 for s in range(NS)]
    q2 = [multiple_range(s, Q2END, p)[1] * r2 for s in range(NS)]
    d = [a - b for a, b in zip(q1, q2)]
    dev = sum(wi * di for wi, di in zip(w, d))
    hawk_q1 = sum(w[s] * q1[s] for s in (IDX[3], IDX[4]))

    def _shift(frm: int, to: int) -> float | None:
        denom = d[to] - d[frm]
        if abs(denom) < 1e-9:
            return None
        x = -dev / denom
        return round(x, 4) if 0 < x <= min(w[frm], 1.0) + 0.25 else None

    stall_h = round(-dev / hawk_q1, 4) if dev < 0 and hawk_q1 > 0 else 0.0
    flips = {"shift_s1_to_s2_pp": _shift(IDX[1], IDX[2]),
             "shift_s0_to_s3_pp": _shift(IDX[0], IDX[3]),
             "extra_stall_pp": stall_h if dev < 0 else None}
    dists = [v for v in (flips["shift_s1_to_s2_pp"], flips["shift_s0_to_s3_pp"],
                         flips["extra_stall_pp"]) if v]
    return {"dev_q1_minus_q2": round(dev, 2),
            "preferred": "Q1" if dev > 0 else "Q2",
            "per_scenario_delta": [round(x, 1) for x in d],
            "flips": flips,
            "within_5pp_of_flip": bool(dists) and min(dists) <= 0.05,
            "sentence": _breakeven_sentence(dev, flips)}


def _breakeven_sentence(dev: float, flips: dict) -> str:
    pref, alt = ("Q1", "Q2") if dev > 0 else ("Q2", "Q1")
    parts = [f"{pref}-end close ahead by ${abs(dev):.1f}M pure EV"]
    if flips["extra_stall_pp"]:
        parts.append(f"flips to {alt} if hawk-row stall hazard rises "
                     f"+{flips['extra_stall_pp']*100:.0f}pp")
    if flips["shift_s1_to_s2_pp"]:
        parts.append(f"or if {flips['shift_s1_to_s2_pp']*100:.0f}pp of weight "
                     f"moves 1-hike -> 2-hikes")
    if flips["shift_s0_to_s3_pp"]:
        parts.append(f"or {flips['shift_s0_to_s3_pp']*100:.0f}pp moves "
                     f"0-hikes -> 3-hikes")
    return "; ".join(parts) + "."


def weight_draws(p: dict, dissent_cluster: bool, n: int,
                 rng: np.random.Generator) -> np.ndarray:
    """Mean-preserving split-concentration draws (memo e1): tail mass ~
    Beta(kappa_lo*t, kappa_lo*(1-t)); head split ~ Dirichlet(kappa_hi*head);
    tail split ~ Dirichlet(kappa_lo*tailsplit). E[w] = base weights, but the
    futures-identified head is tight and the judged tail is loose."""
    base = np.asarray(scenario_weights(p, dissent_cluster))
    # judged block = extension rows + the >=3-hike tail; identified block =
    # the futures-priced 0-2 hike region
    J = np.array([i for i, s in enumerate(SCEN)
                  if s["hikes"] >= 3 or s["source"] != "report-v6"])
    K = np.array([i for i in range(NS) if i not in set(J.tolist())])
    jm = base[J].sum()
    t = rng.beta(p["kappa_lo"] * jm, p["kappa_lo"] * (1 - jm), n)
    h = rng.dirichlet(p["kappa_hi"] * base[K] / base[K].sum(), n)
    j = rng.dirichlet(np.maximum(p["kappa_lo"] * base[J] / jm, 0.05), n)
    w = np.empty((n, NS))
    w[:, K] = h * (1 - t)[:, None]
    w[:, J] = j * t[:, None]
    return w


def dirichlet_band(p: dict, dissent_cluster: bool = False,
                   pin_report: bool = False) -> dict:
    """10-90 band of EV(m) across weight draws — weight uncertainty ONLY
    (midpoint cells), layered distinctly from within-scenario value ranges."""
    rng = np.random.default_rng(p["seed"])
    w = weight_draws(p, dissent_cluster, p["dirichlet_draws"], rng)
    ramp = revenue_ramp(p)
    out = []
    for m in MONTHS:
        rev = REV_BASIS if pin_report else ramp["revenue"][m]
        mids = np.array([multiple_range(s, m, p)[1] * rev for s in range(NS)])
        ev = w @ mids
        out.append({"month": m, "p10": round(float(np.percentile(ev, 10)), 1),
                    "p90": round(float(np.percentile(ev, 90)), 1)})
    return {"band": out, "draws": p["dirichlet_draws"],
            "kappa": {"head": p["kappa_hi"], "tail": p["kappa_lo"]},
            "note": "weight uncertainty only (midpoint cells); "
                    "cell ranges are a separate layer"}


def hold_premium(surface_rows: list[dict]) -> list[dict]:
    """Stall-adjusted EV(2027-07 target month) minus stall-adjusted EV(m):
    what holding to the scale target is worth vs closing at m — the direct
    render of 'sell for less now vs gamble to July 31 2027'."""
    tgt = next(r["ev_stall_adj"] for r in surface_rows if r["month"] == TARGET_M)
    return [{"month": r["month"],
             "premium": round(tgt - r["ev_stall_adj"], 1)}
            for r in surface_rows]


def rate_risk(m: str, p: dict, hike_w: list[float]) -> float:
    """0..1 risk: prob-weighted surprise hikes landing by m + event density in
    the (tilt-dependent) signing-to-close gap ending at m. Higher = worse."""
    hawk_tilt = sum(wi for wi, h in zip(hike_w, HIKES) if h >= 2)
    gap = p["gap_months_hawkish"] if hawk_tilt > 0.3 else p["gap_months_dovish"]
    gi = max(0, _mi(m) - int(round(gap)))
    window = MONTHS[gi:_mi(m) + 1]
    ev_density = (sum(p["event_w_fomc"] for x in FOMC if x in window)
                  + sum(p["event_w_cpi"] for x in CPI if x in window))
    ev_density /= (len(window) * 1.4)                     # normalize ~0..1
    exp_hikes = sum(wi * max(h, 0) for wi, h in zip(hike_w, HIKES))
    # hikes land Oct'26..Apr'27: exposure share of that span occurring <= m
    span = [x for x in MONTHS if "2026-10" <= x <= "2027-04"]
    landed = len([x for x in span if x <= m]) / len(span)
    return min(1.0, 0.5 * (exp_hikes / 2.0) * landed + 0.5 * ev_density)


def window_scores(p: dict, hike_w: list[float], fcix_z: float, dmhi01: float,
                  canary01: float, stage: str, today_month: str,
                  spike_pos_override: bool = False) -> list[dict]:
    """Score(m) 0-100. Components mapped to 0..1 'goodness'; feasibility gate
    strikes months inside remaining lead time (stage-based, amended A6c)."""
    lead = p["lead_by_stage"].get(stage, 6)
    out = []
    fci01 = max(0.0, min(1.0, 1 - (fcix_z + 0.5) / 1.75))  # easy=1, tight=0
    for m in MONTHS:
        feasible = _mi(m) >= _mi(today_month) + lead if today_month in MONTHS else True
        rr = rate_risk(m, p, hike_w)
        score = 100 * (p["w_rate"] * (1 - rr) + p["w_fcix"] * fci01
                       + p["w_dmhi"] * dmhi01 + p["w_canary"] * (1 - canary01))
        if spike_pos_override:                            # A2: deny Green
            score = min(score, 69.0)
        band = ("GREEN" if score >= p["green_min"] else
                "AMBER" if score >= p["amber_min"] else "RED")
        out.append({"month": m, "score": round(score, 1),
                    "band": band, "feasible": feasible,
                    "events": {"fomc": m in FOMC}})
    return out


def slip_costs(p: dict, surface_rows: list[dict], stage: str,
               today_month: str, hike_w: list[float]) -> dict:
    """Cost of PROCESS SLIPPAGE — replaces the frozen-input cost-of-delay
    table, whose answer was ~$0 by construction under the ramp. The real,
    non-zero costs of slipping are calendar-mechanical:
      1. the Q1-option cliff: with the current stage's lead time, slipping
         k* months pushes the earliest feasible close past Q1-end 2027 and
         forfeits the early-close option outright;
      2. unsigned event exposure: every month of slip is another FOMC/CPI
         faced without locked terms (stall and repricing risk live in the
         unsigned phase);
      3. the hawk-conditional cost: what the forfeited early close was worth
         if the >=2-hike world materializes (stall-adjusted).
    """
    lead = p["lead_by_stage"].get(stage, 6)
    ti = _mi(today_month) if today_month in MONTHS else 0
    hawk_tilt = sum(wi for wi, h in zip(hike_w, HIKES) if h >= 2)
    gap = p["gap_months_hawkish"] if hawk_tilt > 0.3 else p["gap_months_dovish"]
    adj = {r["month"]: r["ev_stall_adj"] for r in surface_rows}
    hawk = {r["month"]: r["ev_hawk_adj"] for r in surface_rows}
    horizon = [m for m in MONTHS if _mi(m) <= _mi(TARGET_M)]

    def _sign_by(close_m: str) -> str:
        return MONTHS[max(ti, _mi(close_m) - int(round(gap)))]

    def _events(a: str, b: str, cal: list[str]) -> int:
        return len([m for m in cal if a <= m <= b])

    rows, cliff = [], None
    base_hawk = None
    for k in range(0, 7):
        ei = ti + lead + k
        if ei >= len(MONTHS):
            break
        earliest = MONTHS[ei]
        feas = [m for m in horizon if _mi(m) >= ei]
        if not feas:
            break
        q1_open = _mi(earliest) <= _mi(Q1END)
        if not q1_open and cliff is None:
            cliff = k
        sign_by = _sign_by(earliest)
        hawk_best = max(hawk[m] for m in feas)
        if base_hawk is None:
            base_hawk = hawk_best
        rows.append({
            "slip_months": k, "earliest_close": earliest,
            "q1_open": q1_open, "sign_by": sign_by,
            "fomc_unsigned": _events(today_month, sign_by, FOMC),
            "hawk_cost": round(base_hawk - hawk_best, 2)})
    # what the cliff forfeits, valued in the hawk-conditional world
    later = [m for m in horizon if _mi(m) > _mi(Q1END)]
    forfeit = (round(max(0.0, hawk.get(Q1END, 0.0)
                         - max(hawk[m] for m in later)), 2) if later else 0.0)
    q1_sign, q2_sign = _sign_by(Q1END), _sign_by(Q2END)
    return {"rows": rows, "cliff_months": cliff,
            "gap_months": gap,
            "q1": {"close": Q1END, "sign_by": q1_sign,
                   "fomc_to_sign": _events(today_month, q1_sign, FOMC),
                   "stall_exposure_pct": int(p["stall_exposure_q1"] * 100)},
            "q2": {"close": Q2END, "sign_by": q2_sign,
                   "fomc_to_sign": _events(today_month, q2_sign, FOMC),
                   "stall_exposure_pct": 100},
            "forfeit_hawk_value": forfeit,
            "note": "slippage costs are calendar-mechanical: the Q1-option "
                    "cliff, unsigned event exposure, and the hawk-conditional "
                    "value of the early close"}


def action_cards(p: dict, ctx: dict) -> list[dict]:
    """Rule table. Every card carries the full argued case: rationale (the
    mechanism), evidence (numbered facts from the frozen studies and the
    coupling research), and a concrete playbook — plus the machine-checkable
    trigger that fired it. Hysteresis is applied by the caller via trigger
    persistence."""
    cards = []
    hw = ctx["hike_weights"]
    if ctx.get("dissent_cluster"):
        cards.append({
            "rank": 1,
            "action": "Accelerate: compress prep; target a signed LOI with "
                      "committed financing before the December FOMC",
            "trigger": "dissent_cluster>=3",
            "confidence": "medium",
            "rationale": (
                "The Jul 29 2026 hold passed 9-3 with Hammack, Kashkari and "
                "Logan dissenting for an immediate hike — the first unified "
                "three-way directional dissent since September 2016, and that "
                "one resolved with a hike two meetings later (Dec 2016). "
                "Clustered dissents are evidence the committee's center is "
                "shifting before futures fully price it, so the 3-4-hike tail "
                "(~10% in the cohort) is likely understated. Those tail rows "
                "price this deal at $150-177M with 25-35% odds the process "
                "stalls entirely — and hikes hit private-market pricing with "
                "a 1-2 quarter lag, so terms locked before December close on "
                "pre-hike pricing even if the hikes come."),
            "evidence": [
                "Sept 2016 precedent: three-way dissent -> hike within two "
                "meetings; the Fed historically moves in the dissent "
                "direction within 1-2 meetings",
                "model mechanics: this trigger shifts +3pp of probability "
                "into the 3-4 hike rows (funded from the dove rows)",
                "report transmission lag: Q4 hikes land on private deal "
                "pricing in Q1-Q2 2027 — the target close window",
                "Sept CPI and the Sept 16 dot plot are the last cheap "
                "information events before the December meeting"],
            "playbook": [
                "compress diligence/QofE now; run buyer meetings in parallel "
                "rather than sequence",
                "target LOI + committed financing before the Dec 9 FOMC",
                "reassess at Sept CPI and the Sept 16 dot plot — further "
                "hawkish dot migration or a fourth dissenter = accelerate "
                "harder"]})
    if ctx.get("fcix_z", 0) > 0.75:
        cards.append({
            "rank": 2,
            "action": "Prioritize committed-capital buyers; expect financing "
                      "outs in LOIs; weigh strategics",
            "trigger": f"fcix_z={ctx['fcix_z']:.2f}>0.75",
            "confidence": "medium",
            "rationale": (
                "Financing conditions are tighter than average (NFCI z above "
                "+0.75). Sponsor leverage is the first casualty: the buyout "
                "literature's most robust result is that credit conditions — "
                "not deal quality — set LBO leverage and price. A buyer who "
                "must raise debt at close is a buyer whose bid can shrink "
                "between LOI and signing."),
            "evidence": [
                "Axelson et al. (J. Finance): each 100bp of HY widening cuts "
                "LBO leverage ~5.9% and purchase price ~4.8% — and private "
                "deals are MORE credit-sensitive than public comps",
                "2022: LBO equity checks exceeded 50% for the first time on "
                "record as debt became scarce",
                "direct lenders funded 54-59% of LBO volume in 2023 — a "
                "~$200M deal prices in that market, so committed private "
                "credit or cash buyers dodge the syndication window entirely"],
            "playbook": [
                "rank the buyer list by certainty of funds, not headline bid",
                "push for reverse termination fees where financing outs "
                "appear in LOIs",
                "keep at least one strategic (no leverage needed) warm as "
                "the pricing floor"]})
    p2 = sum(wi for wi, h in zip(hw, HIKES) if h >= 2)
    if p2 > 0.40:
        cards.append({
            "rank": 3,
            "action": "Negotiate a rate-contingent collar / earnout now",
            "trigger": f"P(>=2 hikes)={p2:.2f}>0.40",
            "confidence": "medium",
            "rationale": (
                f"With P(>=2 hikes) at {p2:.0%}, buyer and seller are "
                "pricing different worlds: the cohort spans roughly $211M "
                "(holds continue) down to $154M (4 hikes) for the same "
                "Q1-end close — a spread no single fixed price can bridge "
                "honestly. A rate-contingent structure converts disagreement "
                "about the Fed into a shared instrument instead of a "
                "negotiation stalemate, and pre-agreeing the adjustment "
                "beats being retraded after an adverse FOMC."),
            "evidence": [
                "Denis-Macias (JFQA): material-adverse-event disputes drive "
                "80% of renegotiations; the average renegotiated cut is -15%",
                "SRS Acquiom: >90% of private deals already carry "
                "purchase-price-adjustment mechanisms — this adds a rate leg",
                "~30-40% of lower-middle-market deals get retraded between "
                "LOI and close in normal times (~7% typical haircut); "
                "pre-agreed formulas remove the retrade pretext"],
            "playbook": [
                "propose a collar keyed to an observable (fed funds target "
                "or BSL spread at close), symmetric so the buyer shares "
                "upside if hikes don't land",
                "cap the collar's width near the report's per-scenario "
                "range (~$8-22M) so it prices the disagreement, not the deal"]})
    if ctx.get("revenue_delta", 0) > 0:
        d = ctx["revenue_delta"]
        lo, hi = SCEN[IDX[4]]["q1"][0], SCEN[IDX[0]]["q1"][1]  # report rows: 1.38-2.00x
        cards.append({
            "rank": 4,
            "action": f"Re-anchor the ask: +${d:.1f}M revenue run-rate "
                      f"~ +${lo*d:.1f}-{hi*d:.1f}M of value (1.38-2.00x revenue)",
            "trigger": f"revenue_raised+{d}",
            "confidence": "high",
            "rationale": (
                "This deal prices on a revenue multiple, so every dollar of "
                "run-rate flows straight through the 1.38-2.00x grid. Growth "
                "is the seller's compounding asset in this process: staying "
                "on the ramp adds roughly $0.9M of revenue (~$1.8M of value "
                "at the modal multiple) every month, which is what funds the "
                "hold-vs-sell tension in the first place. A raised run-rate "
                "is the one input that lifts every scenario row at once — "
                "including the hawk rows."),
            "evidence": [
                f"report multiples: +$1M revenue = +$1.38M value even in the "
                f"4-hike row, +$2.00M in the holds row",
                "the ramp premise: evenly scaling toward $200-225M by "
                "Jul 31 2027 — beating the ramp re-rates the whole table"],
            "playbook": [
                "refresh the CIM and management case with the new run-rate "
                "before the next buyer touchpoint",
                "re-anchor the ask off the updated table, not the old one"]})
    fin = ctx.get("financing") or {}
    if fin.get("state") in ("TIGHT", "SHUT"):
        sev = fin["state"]
        cards.append({
            "rank": 3,
            "action": (
                "Financing window " + ("SHUT — assume syndicated debt is "
                "unavailable; committed-capital or all-equity buyers only; "
                "expect retrades" if sev == "SHUT" else
                "tightening — lock committed financing early; expect retrade "
                "attempts and +1-2 quarters of process risk")),
            "trigger": f"hy_state={sev} hy={fin.get('hy_bp')}bp "
                       f"d90={fin.get('d90_bp')}bp",
            "confidence": "high" if sev == "SHUT" else "medium",
            "rationale": (
                "High-yield spreads are the strongest evidence-backed "
                "predictor of whether this deal can be financed. The state "
                "machine has crossed into " + sev + " on level and/or speed "
                "of widening — historically the point where lenders resize, "
                "ICs pause, and LOIs grow financing outs. The engine has "
                f"already scaled the hawk-row stall odds x{fin.get('stall_mult')} "
                "to reflect it; the breakeven row above shows how much of "
                "that risk flips the Q1-vs-Q2 call."),
            "evidence": [
                "2022 episode: HY 310->583bp shut the market — leveraged-loan "
                "issuance -63%, HY issuance -76%, LBO count 147->51",
                "the shutdown happened at only ~500-600bp because the MOVE "
                "was fast — level AND speed both trigger this state",
                "2022-23 stress stalled processes (fewer launches, longer "
                "timelines) rather than killing signed deals — being SIGNED "
                "is the protection"],
            "playbook": [
                "lock rate/spread terms with lenders now; committed paper "
                "over best-efforts syndication",
                "advance any buyer who does not need the debt market",
                "expect and pre-empt the retrade conversation"]})
    if ctx.get("stress_prob", 0) > 0.25:
        cards.append({
            "rank": 5,
            "action": "Treat the Q1'27 close as a hard deadline",
            "trigger": f"stress_prob={ctx['stress_prob']:.2f}>0.25",
            "confidence": "medium",
            "rationale": (
                f"The rate-shock simulator, run across the cohort scenarios "
                f"and weighted by their probabilities, puts "
                f"{ctx['stress_prob']:.0%} odds on the market entering a "
                "stress regime inside the window — above the 25% line where "
                "the Q2 option stops being cheap. A Q2-end close carries "
                "the FULL hawk-row stall exposure; closing by Q1-end dodges "
                "half of it. The evidence says stress mainly stalls and "
                "delays processes rather than breaking signed deals, so the "
                "protection is to be signed and closed before the stress "
                "window, not to hope it misses."),
            "evidence": [
                "stall exposure model: Q1-end close carries 50% of hawk-row "
                "stall risk, Q2-end carries 100%",
                "2022-23: deal terminations stayed ~3% by count even in "
                "stress — but launches fell and timelines stretched; "
                "unsigned processes bore the damage",
                "the simulator figure understates cumulative risk (it is "
                "max monthly stress occupancy and its horizon ends Jun-27)"],
            "playbook": [
                "build the calendar backwards from Mar 31 2027: exclusivity "
                "by January, LOI by early December, management meetings "
                "Oct-Nov",
                "treat any slip past those gates as a decision point, not a "
                "drift"]})
    be = ctx.get("breakeven")
    if be and be.get("within_5pp_of_flip"):
        cards.append({
            "rank": 6,
            "action": "Window choice is LIVE: Q1-vs-Q2 is within 5pp of "
                      "flipping — decide on stall risk, not headline EV",
            "trigger": f"breakeven_margin<=5pp (dEV={be['dev_q1_minus_q2']})",
            "confidence": "high",
            "rationale": (
                "Expected value is linear in the scenario probabilities, so "
                "the Q1-vs-Q2 preference has an exact flipping point — and "
                "the current margin is inside 5 percentage points of it. At "
                "this distance the headline EV difference is noise relative "
                "to the uncertainty in the stall odds and the tail weights; "
                "the honest basis for the window choice is your read on "
                "process-stall risk, which the table cannot settle for you."),
            "evidence": [
                f"current margin: dEV = {be['dev_q1_minus_q2']}M between "
                "the two report windows",
                "the Dirichlet weight-uncertainty band (table above) is "
                "wider than the EV gap at this margin"],
            "playbook": [
                "fix the decision criterion now (e.g. 'close Q1 unless "
                "financing stays BENIGN through the Dec FOMC') so the call "
                "is not re-litigated weekly",
                "watch the HY financing state — it moves the stall odds "
                "that decide this"]})
    return cards
