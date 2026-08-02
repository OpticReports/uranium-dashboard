"""EWM engine — EV surface, indices, window scores, prescriptive rules.

Implements exit_window_monitor_spec.md AS AMENDED (ewm/SPEC_AMENDMENTS.md):
tail-only dissent bump, three-term month shape anchored at Q1'27, static
window weights + SPIKE-x-POS deny-Green override, frozen-input cost-of-delay,
tilt-dependent signing gap, stage-based remaining lead time, delay-not-death
stall modeling. The cohort surface is SEEDED from the spec's anchors
(source tag seeded-from-spec) pending the report-v6 table import.
"""
from __future__ import annotations

from datetime import date

MONTHS = [f"{y}-{m:02d}" for y, ms in ((2026, range(9, 13)), (2027, range(1, 13)))
          for m in ms]                                    # 2026-09 .. 2027-12
ANCHOR = "2027-01"                                        # Q1'27 anchor month
FOMC = ["2026-09", "2026-10", "2026-12", "2027-01", "2027-03", "2027-04",
        "2027-06", "2027-07", "2027-09", "2027-10", "2027-12"]
CPI = MONTHS                                              # monthly release

PARAMS = {
    "hike_weights": [0.30, 0.35, 0.25, 0.07, 0.03],       # market; live-updatable
    "multiples": [14.5, 14.0, 13.4, 11.8, 11.2],          # seeded-from-spec; hike-3 cliff
    "ebitda_run_rate": 14.0,                              # $M; company input overrides
    "ebitda_growth_mo": 0.0,                              # amended default 0
    "exec_noise_pct": 6.0,                                # 10/90 half-width per scenario
    "hawk_shape_qtr": -0.15, "hawk_shape_floor": -0.6,    # turns per quarter past anchor
    "dove_shape_qtr": 0.10, "dove_shape_cap": 0.3,
    "rush_discount": 0.0,                                 # 2% when frontier-adjacent; 0 in G1
    "dissent_bump_pp": 3.0,                               # tail-only, from doves
    "w_rate": 0.35, "w_fcix": 0.25, "w_dmhi": 0.20, "w_canary": 0.20,
    "green_min": 70.0, "amber_min": 45.0,
    "gap_months_dovish": 2.5, "gap_months_hawkish": 4.5,
    "event_w_fomc": 1.0, "event_w_cpi": 0.4,
    "lead_by_stage": {"not_started": 7, "prep": 6, "in_market": 4,
                      "loi": 2, "exclusivity": 1, "close": 0},
    "stall_delay_q": 1.5, "stall_value_pct": -6.5, "stall_death_tail": 0.13,
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


def month_shape(s: int, m: str, p: dict) -> float:
    """Multiple adjustment (turns) vs the Q1'27 anchor — amended A5: identical
    to 0 at the anchor so the G1 anchors are exact."""
    dq = (_mi(m) - _mi(ANCHOR)) / 3.0
    if dq <= 0:
        return -p["rush_discount"] * 0 if dq == 0 else 0.0  # pre-anchor: flat (rush handled in gate)
    if s >= 3:
        return max(p["hawk_shape_qtr"] * dq, p["hawk_shape_floor"])
    if s == 0:
        return min(p["dove_shape_qtr"] * dq, p["dove_shape_cap"])
    return 0.0


def ev_surface(p: dict, ebitda: float, dissent_cluster: bool) -> dict:
    w = scenario_weights(p, dissent_cluster)
    out = []
    for m in MONTHS:
        vals = [(p["multiples"][s] + month_shape(s, m, p)) * ebitda
                for s in range(5)]
        ev = sum(wi * v for wi, v in zip(w, vals))
        # 10/90: scenario dispersion + execution noise (half-width per scenario)
        lo = sorted(vals)[0] * (1 - p["exec_noise_pct"] / 100)
        hi = sorted(vals)[-1] * (1 + p["exec_noise_pct"] / 100)
        modal = [v for v, wi in zip(vals, w) if wi == max(w)][0]
        out.append({"month": m, "ev": round(ev, 1), "p10": round(lo, 1),
                    "p90": round(hi, 1), "modal": round(modal, 1),
                    "by_scenario": [round(v, 1) for v in vals]})
    return {"months": MONTHS, "surface": out, "weights": w,
            "ebitda_used": ebitda,
            "source": "seeded-from-spec (replace via report-v6 import)"}


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
    WAITING k months to launch, holding today's information fixed: you lose
    feasible months from the front of the window and keep exposure to the
    hawk-scenario shape decay at the back."""
    feas = [s["month"] for s in scores if s["feasible"]]
    if not feas:
        return {"curve": [], "note": "no feasible months"}
    ev_by = {r["month"]: r["ev"] for r in surface}
    best_now = max(ev_by[m] for m in feas)
    curve = []
    for k in range(0, 7):
        remaining = feas[k:]
        if not remaining:
            break
        best_k = max(ev_by[m] for m in remaining)
        curve.append({"delay_months": k, "best_ev": round(best_k, 1),
                      "cost_vs_now": round(best_now - best_k, 2),
                      "cost_per_week": round((best_now - best_k) / max(k * 4.33, 1), 3)})
    return {"curve": curve, "best_feasible_ev": round(best_now, 1)}


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
    if ctx.get("ebitda_delta", 0) > 0:
        d = ctx["ebitda_delta"]
        cards.append({"rank": 4, "action": f"Re-anchor ask: +${d:.1f}M run-rate EBITDA "
                      f"~ +${13*d:.0f}-{15*d:.0f}M value",
                      "trigger": f"ebitda_raised+{d}",
                      "rationale": "Margin trajectory offsets multiple compression",
                      "confidence": "high"})
    if ctx.get("stress_prob", 0) > 0.25:
        cards.append({"rank": 5, "action": "Treat Q1'27 close as hard deadline",
                      "trigger": f"stress_prob={ctx['stress_prob']:.2f}>0.25",
                      "rationale": "Q2'27 window degrading under simulator stress odds",
                      "confidence": "medium"})
    return cards
