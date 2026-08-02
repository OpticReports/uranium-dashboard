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

MONTHS = [f"{y}-{m:02d}" for y, ms in ((2026, range(9, 13)), (2027, range(1, 13)))
          for m in ms]                                    # 2026-09 .. 2027-12
Q1END, Q2END = "2027-03", "2027-06"                       # report close windows
TARGET_M = "2027-07"                                      # scale target 2027-07-31
ANCHOR = Q1END                                            # report-fidelity anchor
FOMC = ["2026-09", "2026-10", "2026-12", "2027-01", "2027-03", "2027-04",
        "2027-06", "2027-07", "2027-09", "2027-10", "2027-12"]
CPI = MONTHS                                              # monthly release

REV_BASIS = float(_COHORT["deal_profile"]["revenue_m"])   # 105 — report's basis

# per-scenario multiple ranges = report value cells / report revenue basis
SCEN = []
for _s in _COHORT["scenarios"]:
    SCEN.append({
        "label": _s["hike_path"],
        "modal": bool(_s.get("modal", False)),
        "q1": tuple(v / REV_BASIS for v in _s["value_close_end_q1_2027_m"]),
        "q2": tuple(v / REV_BASIS for v in _s["value_close_end_q2_2027_m"]),
        "stall_p": (sum(_s["process_stall_probability"]) / 2
                    if "process_stall_probability" in _s else 0.0),
        "fed_funds": _s["fed_funds_q1_2027_pct"],
    })
MODAL_S = next(i for i, s in enumerate(SCEN) if s["modal"])

PARAMS = {
    "hike_weights": [s["probability"] for s in _COHORT["scenarios"]],
    # --- dynamic ramp (operator premise: evenly scaling, on pace) ---
    "revenue_dec2026": REV_BASIS,                         # editable run-rate waypoint
    "target_value": [200.0, 225.0],                       # editable valuation target
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
        w[3] += bump * 0.7
        w[4] += bump * 0.3
        w[0] -= bump * 0.6
        w[1] -= bump * 0.4
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
    """Linear revenue line through two waypoints: run-rate at end-Dec-2026
    (editable) and the back-solved revenue that puts value on target at
    2027-07-31 under the modal path. Extrapolated both directions —
    today's implied run-rate falls out of the same line."""
    mult_t = multiple_range(p["ramp_scenario"], TARGET_M, p)[1]
    r_target = (sum(p["target_value"]) / 2) / mult_t
    r0, i0, it = p["revenue_dec2026"], _mi("2026-12"), _mi(TARGET_M)
    slope = (r_target - r0) / (it - i0)
    return {"revenue": {m: round(r0 + slope * (_mi(m) - i0), 2) for m in MONTHS},
            "target_revenue": round(r_target, 2),
            "slope_per_month": round(slope, 4),
            "today_implied": round(r0 + slope * (0 - i0), 2),
            "basis_note": f"on-pace target priced at the modal-path multiple "
                          f"{mult_t:.2f}x at {TARGET_M} (judgment)"}


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
    m: P(stall)·exposure·(recut haircut + death tail · unrecovered value)."""
    sp = SCEN[s]["stall_p"]
    if sp == 0.0:
        return 0.0
    per_event = abs(p["stall_value_pct"]) / 100 + p["stall_death_tail"] * (1 - p["stall_death_recovery"])
    return sp * stall_exposure(m, p) * per_event


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
        for s in range(5):
            lo, mid, hi = (x * rev for x in multiple_range(s, m, p))
            cells.append({"lo": round(lo, 1), "mid": round(mid, 1),
                          "hi": round(hi, 1),
                          "stall_p": SCEN[s]["stall_p"]})
        ev = sum(wi * c["mid"] for wi, c in zip(w, cells))
        ev_lo = sum(wi * c["lo"] for wi, c in zip(w, cells))   # perfect-corr bounds
        ev_hi = sum(wi * c["hi"] for wi, c in zip(w, cells))
        ev_adj = sum(wi * c["mid"] * (1 - _stall_cost_frac(s, m, p))
                     for s, (wi, c) in enumerate(zip(w, cells)))
        hawk_mass = sum(w[2:])
        ev_hawk = (sum(w[s] * cells[s]["mid"] * (1 - _stall_cost_frac(s, m, p))
                       for s in (2, 3, 4)) / hawk_mass) if hawk_mass > 0 else 0.0
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
    q1 = [multiple_range(s, Q1END, p)[1] * r1 for s in range(5)]
    q2 = [multiple_range(s, Q2END, p)[1] * r2 for s in range(5)]
    d = [a - b for a, b in zip(q1, q2)]
    dev = sum(wi * di for wi, di in zip(w, d))
    hawk_q1 = sum(w[s] * q1[s] for s in (3, 4))

    def _shift(frm: int, to: int) -> float | None:
        denom = d[to] - d[frm]
        if abs(denom) < 1e-9:
            return None
        x = -dev / denom
        return round(x, 4) if 0 < x <= min(w[frm], 1.0) + 0.25 else None

    stall_h = round(-dev / hawk_q1, 4) if dev < 0 and hawk_q1 > 0 else 0.0
    flips = {"shift_s1_to_s2_pp": _shift(1, 2), "shift_s0_to_s3_pp": _shift(0, 3),
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
    tmass = base[3:].sum()
    head = base[:3] / base[:3].sum()
    tail = base[3:] / tmass
    t = rng.beta(p["kappa_lo"] * tmass, p["kappa_lo"] * (1 - tmass), n)
    h = rng.dirichlet(p["kappa_hi"] * head, n)
    tl = rng.dirichlet(np.maximum(p["kappa_lo"] * tail, 0.05), n)
    return np.hstack([h * (1 - t)[:, None], tl * t[:, None]])


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
        mids = np.array([multiple_range(s, m, p)[1] * rev for s in range(5)])
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
    hawk_tilt = sum(hike_w[2:])
    gap = p["gap_months_hawkish"] if hawk_tilt > 0.3 else p["gap_months_dovish"]
    gi = max(0, _mi(m) - int(round(gap)))
    window = MONTHS[gi:_mi(m) + 1]
    ev_density = (sum(p["event_w_fomc"] for x in FOMC if x in window)
                  + sum(p["event_w_cpi"] for x in CPI if x in window))
    ev_density /= (len(window) * 1.4)                     # normalize ~0..1
    exp_hikes = sum(wi * s for s, wi in enumerate(hike_w))
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


def cost_of_delay(surface: list[dict], scores: list[dict]) -> dict:
    """Amended A6a: frozen-input decision-delay counterfactual — the cost of
    WAITING k months to launch, holding today's information fixed. v2: values
    are STALL-ADJUSTED, the horizon is capped at the 2027-07-31 scale target
    (extrapolated months beyond the operator's stated horizon can't win
    'best EV'), and a hawk-conditional column (P-weighted on the >=2-hike
    rows) shows what the same delay costs if the hawkish world materializes —
    under the ramp the base-case delay cost is ~0 by construction; the risk
    lives in the hawk column."""
    feas = [s["month"] for s in scores
            if s["feasible"] and _mi(s["month"]) <= _mi(TARGET_M)]
    if not feas:
        return {"curve": [], "note": "no feasible months inside the horizon"}
    adj_by = {r["month"]: r["ev_stall_adj"] for r in surface}
    hawk_by = {r["month"]: r["ev_hawk_adj"] for r in surface}
    best_now = max(adj_by[m] for m in feas)
    hawk_now = max(hawk_by[m] for m in feas)
    curve = []
    for k in range(0, 7):
        remaining = feas[k:]
        if not remaining:
            break
        best_k = max(adj_by[m] for m in remaining)
        hawk_k = max(hawk_by[m] for m in remaining)
        curve.append({"delay_months": k, "best_ev": round(best_k, 1),
                      "cost_vs_now": round(best_now - best_k, 2),
                      "hawk_cost": round(hawk_now - hawk_k, 2),
                      "cost_per_week": round((best_now - best_k) / max(k * 4.33, 1), 3)})
    return {"curve": curve, "best_feasible_ev": round(best_now, 1),
            "note": "stall-adjusted, horizon capped at " + TARGET_M}


def action_cards(p: dict, ctx: dict) -> list[dict]:
    """Rule table (amended: every card logs its trigger values; hysteresis is
    applied by the caller via trigger persistence)."""
    cards = []
    hw = ctx["hike_weights"]
    if ctx.get("dissent_cluster"):
        cards.append({"rank": 1, "action": "Accelerate: compress prep; target LOI pre-Dec-FOMC",
                      "trigger": "dissent_cluster>=3",
                      "rationale": "Tail hike odds under-priced when dissents cluster; "
                                   "cost-of-delay curve applies", "confidence": "medium"})
    if ctx.get("fcix_z", 0) > 0.75:
        cards.append({"rank": 2, "action": "Prioritize committed-capital buyers; expect "
                      "financing outs in LOIs; weigh strategics",
                      "trigger": f"fcix_z={ctx['fcix_z']:.2f}>0.75",
                      "rationale": "Financing tight: sponsor leverage constrained",
                      "confidence": "medium"})
    if hw[2] + hw[3] + hw[4] > 0.40:
        cards.append({"rank": 3, "action": "Negotiate rate-contingent collar / earnout now",
                      "trigger": f"P(>=2 hikes)={hw[2]+hw[3]+hw[4]:.2f}>0.40",
                      "rationale": "Bridge bid-ask across rate scenarios",
                      "confidence": "medium"})
    if ctx.get("revenue_delta", 0) > 0:
        d = ctx["revenue_delta"]
        lo, hi = SCEN[4]["q1"][0], SCEN[0]["q1"][1]
        cards.append({"rank": 4, "action": f"Re-anchor ask: +${d:.1f}M revenue run-rate "
                      f"~ +${lo*d:.1f}-{hi*d:.1f}M value (1.38-2.00x revenue)",
                      "trigger": f"revenue_raised+{d}",
                      "rationale": "Growth trajectory offsets multiple compression",
                      "confidence": "high"})
    if ctx.get("stress_prob", 0) > 0.25:
        cards.append({"rank": 5, "action": "Treat Q1'27 close as hard deadline",
                      "trigger": f"stress_prob={ctx['stress_prob']:.2f}>0.25",
                      "rationale": "Q2'27 window degrading under simulator stress odds",
                      "confidence": "medium"})
    be = ctx.get("breakeven")
    if be and be.get("within_5pp_of_flip"):
        cards.append({"rank": 6, "action": "Window choice is LIVE: Q1-vs-Q2 within 5pp "
                      "of flipping — decide on stall risk, not headline EV",
                      "trigger": f"breakeven_margin<=5pp (dEV={be['dev_q1_minus_q2']})",
                      "rationale": "EV is linear in weights; the call rides on "
                                   "tail drift and stall hazard",
                      "confidence": "high"})
    return cards
