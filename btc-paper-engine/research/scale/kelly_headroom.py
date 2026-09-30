"""How much bigger can THIS book be? Answered with the repo's own instrument.

lever_sweep.py measured only ONE of KELLY.md's four criteria (the DD budget).
KELLY.md's recommendation is min(half-Kelly, bootstrap p10, c*.m*, DD-budget m)
plus the >25% non-positive-resample kill rule. So the honest headroom number
has to come from `app.engine.kelly.analyze` itself, fed the per-step equity
returns of the book AS IT IS SIZED TODAY. Then `recommended_m` is literally
"how many times bigger the live book can be".

Two streams, both at the live size, so m is directly comparable:
  FIXED     - the live vol-blind rule at k_live = 0.0999
  VOLTARGET - same mean dollar risk, notional inverse to ATR
and a k=1.0 run as a pipe check against KELLY.md's published S5 row.

Usage: python3 kelly_headroom.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)

from scale_ladder import (EQUITY, LEV, MAX_NOTIONAL_USD, expo, _gross,  # noqa: E402
                          trades, KELLY_M_LIVE, SIZING_BASE_USD)
from app.engine.kelly import analyze                                    # noqa: E402

K_LIVE = KELLY_M_LIVE * LEV * SIZING_BASE_USD / (LEV * EQUITY)     # 0.09995
OUT: dict = {}


def main() -> None:
    ev, _ = trades()
    r = ev["r"].to_numpy()
    e1 = expo(ev, 1.0, "FIXED")
    risk1 = e1 * ev["s"].to_numpy()
    R_LEG = {lg: float(risk1[(ev.leg == lg).to_numpy()].mean())
             for lg in ("pullback", "trend")}

    t_end = ev["exit_ts"].iloc[-1]
    m2 = (ev["exit_ts"] >= t_end - int(2 * 365.25 * 86400)).to_numpy()

    cases = {}
    for win_lab, mask in (("full", np.ones(len(r), bool)), ("last_2y", m2)):
        for rule in ("FIXED", "VOLTARGET"):
            for k_lab, k in (("k_live_0.0999", K_LIVE), ("k_1.0_research_S5", 1.0)):
                e = expo(ev, k, rule, R_LEG)
                steps = (e * r)[mask]                 # per-step equity returns
                g = (_gross(ev, e) * EQUITY)[mask]
                a = analyze(steps.tolist(),
                            label=f"{win_lab}/{rule}/{k_lab}",
                            current_desc=f"gross median ${np.median(g):,.0f} "
                                         f"on ${EQUITY:,.0f} equity")
                cases[f"{win_lab}|{rule}|{k_lab}"] = {
                    "kelly": a,
                    "current_gross_usd": {
                        "median": float(np.median(g)), "max": float(g.max()),
                        "p99": float(np.percentile(g, 99))},
                    "gross_usd_at_recommended_m": {
                        "median": float(np.median(g)) * a.get("recommended_m", 0),
                        "p99": float(np.percentile(g, 99)) * a.get("recommended_m", 0),
                        "max": float(g.max()) * a.get("recommended_m", 0)},
                }
    OUT["cases"] = cases

    # ---- headline: the live book's own headroom ---------------------------
    live_f = cases["full|FIXED|k_live_0.0999"]
    live_v = cases["full|VOLTARGET|k_live_0.0999"]
    t2_f = cases["last_2y|FIXED|k_live_0.0999"]
    t2_v = cases["last_2y|VOLTARGET|k_live_0.0999"]
    OUT["headline_live_book_headroom"] = {
        "live_gross_usd": 15_000.0,
        "FIXED_recommended_m_full": live_f["kelly"]["recommended_m"],
        "FIXED_recommended_m_2y": t2_f["kelly"]["recommended_m"],
        "VOLTARGET_recommended_m_full": live_v["kelly"]["recommended_m"],
        "VOLTARGET_recommended_m_2y": t2_v["kelly"]["recommended_m"],
        "BINDING_recommended_m": min(live_f["kelly"]["recommended_m"],
                                     t2_f["kelly"]["recommended_m"]),
        "FIXED_authorised_gross_usd_binding": 15_000.0 * min(
            live_f["kelly"]["recommended_m"], t2_f["kelly"]["recommended_m"]),
        "VOLTARGET_binding_m": min(live_v["kelly"]["recommended_m"],
                                   t2_v["kelly"]["recommended_m"]),
        "VOLTARGET_authorised_gross_usd_binding": {
            "median": live_v["current_gross_usd"]["median"] * min(
                live_v["kelly"]["recommended_m"], t2_v["kelly"]["recommended_m"]),
            "p99": live_v["current_gross_usd"]["p99"] * min(
                live_v["kelly"]["recommended_m"], t2_v["kelly"]["recommended_m"]),
        },
        "which_criterion_binds": {
            k: _binding(v["kelly"]) for k, v in cases.items() if "k_live" in k},
        "MAX_NOTIONAL_USD_today": MAX_NOTIONAL_USD,
    }

    # pipe check against KELLY.md's published S5 row
    OUT["pipe_check_vs_KELLY_md_S5"] = {
        "KELLY_md_S5_published": {"m_star": 3.5, "boot_p10_p90": [1.0, 4.0],
                                  "half_K": 1.8, "c_star": 0.64,
                                  "m_at_DD30": 0.94, "P_dd_gt_20_at_current": 0.63,
                                  "recommended_m": 0.94, "n": 146,
                                  "window": "2y replay, cash_apy 4%, 6bp"},
        "mine_last_2y_FIXED_k1": {
            kk: cases["last_2y|FIXED|k_1.0_research_S5"]["kelly"].get(kk)
            for kk in ("n", "kelly_m", "half_kelly_m", "shrinkage_c_star",
                       "conservative_m", "dd_constrained", "dd_at_current",
                       "recommended_m", "verdict", "bootstrap")},
        "differences_that_explain_any_gap": [
            "my fee is the engine's 12bp round trip; KELLY.md's cell is 6bp",
            "my cash_apy is 0; KELLY.md's published S5 row is cash_apy 4%",
            "my bars are the repo fixture 2022-02..2026-07; KELLY.md's 2y "
            "replay window differs",
            "my stream is the exit-step BLEND; KELLY.md's S5 row is the same "
            "construction, so this is the closest available comparison",
        ],
    }

    with open(os.path.join(HERE, "kelly_headroom.json"), "w") as fh:
        json.dump(OUT, fh, indent=2, default=float)

    print("=" * 96)
    print(f"{'case':<42} {'n':>4} {'m*':>6} {'halfK':>6} {'p10':>6} "
          f"{'c*m*':>6} {'ddm30':>6} {'REC':>6} {'gross@REC med $':>16}")
    for k, v in cases.items():
        a = v["kelly"]
        print(f"{k:<42} {a['n']:>4} {a['kelly_m']:>6.2f} {a['half_kelly_m']:>6.2f} "
              f"{a['bootstrap']['p10']:>6.2f} "
              f"{a['shrinkage_c_star']*a['kelly_m']:>6.2f} "
              f"{a['dd_constrained']['p_maxdd30_le_10pct']:>6.2f} "
              f"{a['recommended_m']:>6.2f} "
              f"{v['gross_usd_at_recommended_m']['median']:>16,.0f}")
    print("=" * 96)
    print(json.dumps(OUT["headline_live_book_headroom"], indent=1, default=float))
    print("=" * 96)
    print(json.dumps(OUT["pipe_check_vs_KELLY_md_S5"], indent=1, default=float))


def _binding(a: dict) -> str:
    cands = {"half_kelly": a["half_kelly_m"], "bootstrap_p10": a["bootstrap"]["p10"],
             "c_star_x_m_star": round(a["shrinkage_c_star"] * a["kelly_m"], 2),
             "dd30_budget": a["dd_constrained"]["p_maxdd30_le_10pct"]}
    return min(cands, key=cands.get) + f" = {min(cands.values()):.2f}"


if __name__ == "__main__":
    main()
