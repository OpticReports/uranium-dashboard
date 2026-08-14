"""Transparency endpoint content: where every parameter came from.

Served at /shock-sim/calibration so the UI (and any reviewer) can see the
estimation windows and the counter-agent's amendment verdicts without reading
the repo. Full detail: rate_shock_simulator_spec.md + SPEC_AMENDMENTS.md.
"""
from __future__ import annotations

from .params import registry

AMENDMENTS_SUMMARY = [
    "kappa 0.45 ACCEPTED as central value; made term-premium-dependent: "
    "kappa_t = clip(0.45 + 0.40*dACM_TP_6m, 0.25, 0.65) (5 episodes, R2=0.58)",
    "OAS priced-hike tightening sign VERIFIED on 2015-18 (BaaAaa proxy); "
    "magnitude halved -8 -> -4bp with late-cycle taper",
    "2-state Markov KEPT: 2022 grind is reproduced by the +15bp/surprise-hike "
    "drift (18x15=270bp ~ realized); stress state = 2020-style gap regime",
    "beta_dur AMENDED UP to SPX 8 / QQQ 11 / SOXX 14 per 100bp (2020-26 "
    "estimates; spec defaults failed gate G1 by ~15x)",
    "SOXX ACCEPTED as AI-capex proxy (1.3-1.6x QQQ's rate beta, single symbol)",
    "t-copula (shared chi2 mixing) ADOPTED: Gaussian understated joint "
    "5th-pct co-crash by 29% at rho=0.6 (> spec's 20% switch rule)",
    "stress-entry logistic RECALIBRATED to the spec's own targets: a=-4.65, "
    "b=2.6 (spec defaults gave P(stress)=89% for 4 hikes vs target 35-50%)",
    "real share rho 0.7 -> 0.9 (2022 realized real/nominal share = 1.00)",
    "VIX haircut 0.9 -> 0.8 (realized/VIX median 0.75)",
    "scenario span widened to -2..+4 (cut scenarios; Stage 1 linear in S)",
    "SPEC GAP filled: stress_exit_monthly=0.25 (spec defined no exit prob)",
    "QA ROUND (P4): crack + OAS entry jump now fire ONCE per path (re-entry "
    "re-firing made softer stress deepen the median and inflated G1; "
    "post-fix G1 medians SPX 81.1 / HYG 90.7 — in-band honestly)",
    "QA ROUND: HYG idio vol made per-path (cross-path mean starved "
    "normal-state paths of 39% of vol at high stress share)",
    "QA ROUND: stress attractor floored at theta_normal_path + "
    "oas_stress_premium (stress could otherwise be spread-tightening after "
    "a big grind); oas_theta_normal marked fallback-only (live oas0 anchors "
    "the attractor); 14 params flagged high_sensitivity from the tornado",
    "REALISM ROUND: HYG stress made crisis-capable (theta 750/jump 180); "
    "one-sided dovish stress channel b_cut=1.5 (cut scenarios now carry MORE "
    "tail risk than baseline, matching 2001/2007/2020); vol scales with "
    "|surprise| capped at 2022's 1.6x; fans are TOTAL-RETURN indices; "
    "drawdown chips are daily-touch estimates from the month-end grid; "
    "delta baseline = pure implied path; per-path kappa/beta uncertainty",
]

ESTIMATION_WINDOWS = {
    "kappa": "episode-total d10y/d2y over 1994-95, 1999-00, 2004-06, 2015-18, "
             "2022-23 (FRED DGS2/DGS10)",
    "beta_dur": "monthly log returns on dDFII10, 2020-2026 (FMP prices), "
                "rounded down for the 2022 multiple-compression confound",
    "oas_dtheta_priced": "2015-18 cycle via Baa-Aaa (FRED, uncapped) scaled to "
                         "HY OAS: HY ~ 149 + 2.43*BaaAaa (R2=0.71 on 2023-26)",
    "oas_theta_normal": "HY OAS 2023-08..2026-07 median (FRED cap limits the "
                        "window to ~3y; full-history HY median ~430 — "
                        "regime-conditional)",
    "vix_haircut": "21d realized vol / VIX, 2010-2026, n=198 non-overlapping",
    "logistic": "calibrated to spec 4.2 targets: P(stress by Q2'27) 8-12% at "
                "0-1 hikes, 35-50% at 3-4 hikes",
}


def calibration_payload() -> dict:
    return {
        "params": registry(),
        "amendments": AMENDMENTS_SUMMARY,
        "estimation_windows": ESTIMATION_WINDOWS,
        "epistemic_note": (
            "Conditional betas are estimated on ~5 hiking cycles; regime-"
            "switch probabilities are judgment encoded as parameters. This "
            "is scenario visualization, not prediction."),
    }
