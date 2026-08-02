"""EWM Monte Carlo valuation fan — scenario-toggle engine.

Answers the board's core question distributionally: sell for less now vs
gamble to 2027-07-31. Per path: draw scenario weights (split-concentration
Dirichlet, weight uncertainty), draw a scenario, draw a within-cell quantile
(shared across months — one common driver, perfect within-path correlation),
apply the toggled shocks, then value every candidate close month.

Toggles (all optional):
  force_hikes: -1..4     pin the rate path to one row (-1 = benign-easing cut)
  crash: none|moderate|severe   equity drawdown mapped to revenue-multiple
         compression with the report's 1-2 quarter transmission lag.
         Calibration anchor: 2022-23 revenue-priced deals compressed 60%+
         peak-to-trough on SPX -25% PLUS 525bp of hikes; standalone-crash
         effect uses roughly half that gradient (judgment-tagged):
         moderate (-20% SPX) -> multiple x0.85; severe (-35%) -> x0.70,
         severe also adds +10pp stall hazard to rows >=2.
  regime_50bp: true      the report's off-cohort branch — 50bp increments,
         values gap to the $145-170M band (at the $105M basis) and stall
         hazard jumps to 40%. A different model, not a sixth weighted row.
  extra_stall_pp: 0..30  additional hawk-row stall hazard (breakeven probe)
  pin_report: true       pin revenue at $105M (report-fidelity mode)

Fan = valuation conditional on closing that month; stalled paths take the
recut haircut, dead paths count in p_no_deal (excluded from percentiles).
Deterministic seed -> gate-testable.
"""
from __future__ import annotations

import numpy as np

from .core import (HIKES, IDX, MONTHS, NS, PARAMS, REV_BASIS, SCEN, TARGET_M,
                   _mi, multiple_range, revenue_ramp, stall_exposure,
                   weight_draws)

CRASH_FACTOR = {"none": 1.0, "moderate": 0.85, "severe": 0.70}
REGIME_BAND = (145.0, 170.0)                              # report, at $105M basis


def _tri_ppf(u: np.ndarray, lo: float, mid: float, hi: float) -> np.ndarray:
    """Inverse CDF of Triangular(lo, mid, hi) for shared-quantile draws."""
    if hi - lo < 1e-9:
        return np.full_like(u, mid)
    fc = (mid - lo) / (hi - lo)
    left = lo + np.sqrt(u * (hi - lo) * (mid - lo))
    right = hi - np.sqrt((1 - u) * (hi - lo) * (hi - mid))
    return np.where(u < fc, left, right)


def simulate(p: dict, inputs: dict, toggles: dict, n_paths: int = 4000) -> dict:
    tg = {"force_hikes": None, "crash": "none", "regime_50bp": False,
          "extra_stall_pp": 0.0, "pin_report": False, **(toggles or {})}
    rng = np.random.default_rng(p["seed"] + 7)
    ramp = revenue_ramp(p)
    pin = bool(tg["pin_report"])
    dissent = bool(inputs.get("dissent_cluster"))
    today = inputs.get("today_month", "2026-09")
    ti = _mi(today) if today in MONTHS else 0
    extra_stall = min(max(float(tg["extra_stall_pp"] or 0) / 100, 0.0), 0.30)
    crash = tg["crash"] if tg["crash"] in CRASH_FACTOR else "none"

    # per-path draws
    w = weight_draws(p, dissent, n_paths, rng)            # (n, 5)
    if tg["force_hikes"] is not None and int(tg["force_hikes"]) in IDX:
        s_idx = np.full(n_paths, IDX[int(tg["force_hikes"])])
    else:
        cum = np.cumsum(w, axis=1)
        s_idx = (rng.uniform(size=(n_paths, 1)) < cum).argmax(axis=1)
    u_cell = rng.uniform(size=n_paths)                    # shared cell quantile
    z_stall = rng.uniform(size=n_paths)                   # stall event draw
    z_death = rng.uniform(size=n_paths)
    u_regime = rng.uniform(size=n_paths)                  # 50bp-branch value draw

    stall_base = np.array([SCEN[s]["stall_p"] for s in range(NS)])[s_idx]
    hk = np.array(HIKES)[s_idx]                           # hike count per path
    stall_base = stall_base + extra_stall * (hk >= 3)     # hawk rows, matching h*
    if crash == "severe":
        stall_base = stall_base + 0.10 * (hk >= 2)
    if tg["regime_50bp"]:
        stall_base = np.maximum(stall_base, 0.40)
    stall_base = np.clip(stall_base, 0.0, 0.95)

    recut = 1 + p["stall_value_pct"] / 100                # -6.5% on stall
    fan = []
    for m in MONTHS:
        rev = REV_BASIS if pin else ramp["revenue"][m]
        # crash transmission: no effect first month, full by today+4 (1-2q lag)
        phase = min(max((_mi(m) - ti - 1) / 3.0, 0.0), 1.0)
        cf = 1 - (1 - CRASH_FACTOR[crash]) * phase
        if tg["regime_50bp"]:
            # off-cohort branch: value band gapped, shaped by the row-4 decay
            shape = (multiple_range(IDX[4], m, p)[1]
                     / multiple_range(IDX[4], "2027-03", p)[1])
            lo, hi = REGIME_BAND
            base = (lo + u_regime * (hi - lo)) * (rev / REV_BASIS) * shape
        else:
            base = np.empty(n_paths)
            for s in range(NS):
                mask = s_idx == s
                if mask.any():
                    mlo, mmid, mhi = multiple_range(s, m, p)
                    base[mask] = _tri_ppf(u_cell[mask], mlo, mmid, mhi) * rev
        val = base * cf
        hz = stall_base * stall_exposure(m, p)
        stalled = z_stall < hz
        dead = stalled & (z_death < p["stall_death_tail"])
        val = np.where(stalled & ~dead, val * recut, val)
        ok = ~dead
        pct = np.percentile(val[ok], [10, 25, 50, 75, 90]) if ok.any() else [0] * 5
        fan.append({"month": m,
                    "p10": round(float(pct[0]), 1), "p25": round(float(pct[1]), 1),
                    "p50": round(float(pct[2]), 1), "p75": round(float(pct[3]), 1),
                    "p90": round(float(pct[4]), 1),
                    "ev": round(float(val[ok].mean()), 1) if ok.any() else 0.0,
                    "p_no_deal": round(float(dead.mean()), 3)})

    on_pace = [{"month": m,
                "value": round(multiple_range(p["ramp_scenario"], m, p)[1]
                               * (REV_BASIS if pin else ramp["revenue"][m]), 1)}
               for m in MONTHS]
    return {"months": MONTHS, "fan": fan, "on_pace": on_pace,
            "target_band": p["target_value"], "target_month": TARGET_M,
            "toggles": tg, "n_paths": n_paths,
            "assumptions": [
                "cells: report-v6 revenue-multiple ranges, triangular within-cell, "
                "one shared quantile per path (single common driver)",
                "weights: split-concentration Dirichlet (head kappa 60, tail kappa 15), "
                "mean-preserving",
                "crash mapping: half the 2022-23 revenue-deal gradient — moderate "
                "x0.85, severe x0.70 multiple, phased in over the report's 1-2q "
                "transmission lag (judgment-tagged)",
                "50bp regime: report's off-cohort branch, $145-170M band at the "
                "$105M basis, 40% stall hazard — a different model, not a weighted row",
                "stall: -6.5% recut, 13% death tail; dead paths excluded from the "
                "fan and counted in p_no_deal",
            ]}
