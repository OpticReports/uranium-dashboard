"""Stage 1 — rate paths and surprise vectors (spec §4.1, amended A1/A7e).

Monthly grid Aug-2026..Jun-2027 (11 steps, month-end). The market-implied path
is manual-config through params (implied_prob_*); scenarios place ±25bp moves
at consecutive FOMC meetings starting Oct-2026. Span −2..+4 per amendment A7e
(cut scenarios — all Stage-1 formulas are linear in S).
"""
from __future__ import annotations

import numpy as np

N_MONTHS = 11
MONTHS = ["2026-08", "2026-09", "2026-10", "2026-11", "2026-12", "2027-01",
          "2027-02", "2027-03", "2027-04", "2027-05", "2027-06"]

# FOMC decision dates -> index of the monthly step they land in
MEETINGS = [
    {"date": "2026-09-16", "idx": 1},
    {"date": "2026-10-28", "idx": 2},
    {"date": "2026-12-09", "idx": 4},
    {"date": "2027-01-27", "idx": 5},
    {"date": "2027-03-17", "idx": 7},
    {"date": "2027-04-28", "idx": 8},
]
# scenario moves start at Oct-2026, consecutive meetings (spec 4.1)
SCENARIO_MEETING_IDXS = [2, 4, 5, 7, 8]
HIKE_BP = 25.0
SCENARIO_SPAN = (-2, 4)


def build_paths(hikes: int, params: dict[str, float]) -> dict[str, np.ndarray]:
    """Per-month implied/scenario steps (bp), surprise S, cumulative CS,
    priced-hike and surprise-hike counts (fractional, signed)."""
    if not SCENARIO_SPAN[0] <= hikes <= SCENARIO_SPAN[1]:
        raise ValueError(f"hikes must be in {SCENARIO_SPAN}")
    implied = np.zeros(N_MONTHS)
    implied[2] = params["implied_prob_oct"] * HIKE_BP
    implied[4] = params["implied_prob_dec"] * HIKE_BP
    scn = np.zeros(N_MONTHS)
    n = abs(hikes)
    sign = 1.0 if hikes >= 0 else -1.0
    for k in range(min(n, len(SCENARIO_MEETING_IDXS))):
        scn[SCENARIO_MEETING_IDXS[k]] += sign * HIKE_BP
    surprise = scn - implied
    return {
        "implied_bp": implied,
        "scenario_bp": scn,
        "surprise_bp": surprise,
        "cum_surprise_bp": np.cumsum(surprise),
        "priced_hikes": implied / HIKE_BP,          # fractional
        "surprise_hikes": surprise / HIKE_BP,       # signed
    }


def kappa_live(kappa_base: float, tp_coeff: float,
               d_acm_tp_6m_pp: float | None) -> float:
    """Amendment A1: kappa_t = clip(base + coeff * 6m ACM TP change, .25, .65)."""
    if d_acm_tp_6m_pp is None:
        return kappa_base
    return float(np.clip(kappa_base + tp_coeff * d_acm_tp_6m_pp, 0.25, 0.65))


def rate_legs(surprise_bp: np.ndarray, kappa: float, rho_real: float
              ) -> tuple[np.ndarray, np.ndarray]:
    """Monthly Δ10y and Δreal (both pp) from front-end surprise steps."""
    dy10_pp = kappa * surprise_bp / 100.0
    return dy10_pp, rho_real * dy10_pp
