"""Round 9 — exit-rule ablation: which executor knob carries the gap to the
paper R2-A? Contract: docs/VARIANTS_PREREGISTRATION_R9_EXIT_ABLATION.md
(+ addendum 1), both committed before this code. Everything is IMPORTED
from the executor mirror; no engine is re-implemented here.

Arms: P (paper anchor, R2A_MODE, must reduce to run_call_book), P0 (the
ablation base: P on the ledger basis, paper_arith=False), F_k (P0 with one
knob at the executor value), B_k (E with one knob at the paper value),
G_stop / G_time / G_size (knob groups on P0), E (executor mechanics only:
no costs, no carry, lag 1). Metrics per the contract: full-window and
sub-period stats, gap share, recovery share, paired stationary block
bootstrap of the Sharpe delta vs the arm's base (sign-aware, with a
Bonferroni-8 interval), the four-part "carries the gap" rule, the action
bar, actionability tags, 63-day block sensitivity for knobs that carry.

Usage:  python -m scripts.backtest_exit_ablation [--out PATH] [--draws N] [--seed S]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backtest_executor_mirror import (  # noqa: E402
    BOOT_MEAN_BLOCK, CAP, DATA, EXEC_T1, R2A_MODE, REDUCTION_TOL, RESULTS as MIRROR_RESULTS,
    ExecCfg, _input, build_exec_rows, gate_rows, load_inputs, run_executor_book,
    select_capped_exec, write_results,
)
from scripts.backtest_variants_10y import SUB_PERIODS, run_call_book, seg_stats, select_capped  # noqa: E402
from scripts.backtest_variants_r2 import build_trailing_rows  # noqa: E402

RESULTS = DATA / "backtest_exit_ablation_results.json"
ABL_SEED = 20261004
ABL_DRAWS = 10000              # the Bonferroni-8 tail sits at p0.3125: 2,000 draws rest it on ~6 resamples
BASIS_CLEAN_CAGR = 0.008       # the contract's lane-drift noise floor: |CAGR(P0) - CAGR(P)| must sit under it
TRADING_DAYS = 252
BLOCK_SENSITIVITY = 63
N_EXPLORATORY = 8                  # Bonferroni family for the per-knob intervals
PRIMARY_KNOB = "ratchet"           # H14

# knob, paper value, executor value — addendum 1, item 3
KNOBS: list[tuple[str, object, object]] = [
    ("peak_seed", "entry_close", "fire_close"),
    ("ratchet", False, True),
    ("day_zero_stop", False, True),
    ("risk_cap", 0.5, None),
    ("time_stop_anchor", "entry", "fire"),
    ("time_stop_fill", "deadline_close", "next_open"),
    ("integer_shares", False, True),
    ("cash_clip", False, True),
]
WHERE = {"peak_seed": "tracker", "time_stop_anchor": "tracker", "time_stop_fill": "tracker",
         "ratchet": "tracker+executor", "day_zero_stop": "tracker+executor", "risk_cap": "executor",
         "integer_shares": "not_actionable", "cash_clip": "not_actionable"}
GROUPS = {"G_stop": ("peak_seed", "ratchet", "day_zero_stop"),
          "G_time": ("time_stop_anchor", "time_stop_fill"),
          "G_size": ("risk_cap", "integer_shares", "cash_clip")}
CARRY_SHARE = 0.50          # contract: forward gap share and backward recovery share
ACTION_MAXDD_SLACK = 0.02   # contract: backward flip's max DD no more than 2 pp worse than E

P_CFG = R2A_MODE
P0_CFG = replace(R2A_MODE, paper_arith=False)
E_CFG = replace(EXEC_T1, commission_model="none", bil_order_cost=False, carry=False)

HONESTY = [
    # contract, verbatim
    "In-sample: the exit rule is being selected on the same history the engine was selected on; "
    "R3-F showed the trail x time-stop map is not a plateau. A winner here is a hypothesis for the "
    "live shadow record, not a result.",
    "The bars are the FMP dividend-adjusted lane, not the August campaign cache (R2-A +9% end value "
    "on this lane, one cap flip); all arms share the lane, so the deltas are internally consistent, "
    "the absolute levels are not the R2/R3 docs'.",
    "Deltas below the lane-drift noise floor (~0.8 pp CAGR) are not robust.",
    "Survivor universe, hindsight tiers, costs and carry deliberately OFF (this measures rules, not "
    "economics).",
    "Never present these in-sample CAGRs as a forecast.",
    # addendum 1, item 9
    "The paired Sharpe-delta interval is CONDITIONAL on this single in-sample path and the fixed trade "
    "set: a few dozen divergent trades drive it, so it is an interval on these events, not on the "
    "strategy; 21-day blocks overstate the effective sample for trades that diverge over ~65 days "
    "(see the 63-day sensitivity); percentile intervals, not bias-corrected.",
    "Multiplicity: H14 (ratchet) is the single pre-registered primary at the uncorrected 95% level; "
    "the other seven knobs are exploratory and each reports whether it survives a Bonferroni-8 "
    "interval; the group arms are descriptive; shares of the gap need not sum to one (interactions).",
    "B_cash_clip (and P0 / the paper book) run negative cash with no margin cost: uncosted leverage.",
    "Uncapped risk (risk_cap None) uses the lane's 3xATR14; the campaign's uncapped ATR is not stored, "
    "so F_risk_cap / B_risk_cap carry a lane-vs-campaign ATR caveat.",
    "A proposal for ratchet or day_zero_stop is a change in BOTH the tracker's shadow grader "
    "(app/calls/shadow.py ratchets the published level up only) AND the executor "
    "(ibkr-executor/app/blend.py never applies a level below the working stop, which is also a "
    "data-bug safety).",
    "The day-zero floor is a WEAK RATCHET (the resting STP at L0 is only ever replaced by a higher "
    "level), so ratchet and day_zero_stop OVERLAP: F_ratchet has no floor while B_ratchet keeps one; "
    "the forward and backward ratchet arms are not mirror images, G_stop shows the joint.",
    "day_zero_stop's share INCLUDES the refusal of fires whose published level is <= 0 (L0 = "
    "close - 3xATR; the executor skips them as 'no sizing reference'); each arm's grading counts "
    "are in the JSON (arms.<name>.grading).",
    "A Sharpe-delta interval that excludes zero is not materiality: deterministic effects (whole "
    "shares) read as 'significant' at any size; the >= 0.5 share tests carry the materiality.",
]


def _flip(cfg: ExecCfg, knob: str, to_executor: bool) -> ExecCfg:
    _, pv, ev = next(k for k in KNOBS if k[0] == knob)
    return replace(cfg, **{knob: ev if to_executor else pv})


def arms() -> list[tuple[str, ExecCfg, str]]:
    """(name, cfg, base_name). The base is what the arm's delta is measured against."""
    out: list[tuple[str, ExecCfg, str]] = [("P", P_CFG, "P"), ("P0", P0_CFG, "P")]
    for knob, _, _ in KNOBS:
        out.append((f"F_{knob}", _flip(P0_CFG, knob, True), "P0"))
    for knob, _, _ in KNOBS:
        out.append((f"B_{knob}", _flip(E_CFG, knob, False), "E"))
    for g, knobs in GROUPS.items():
        cfg = P0_CFG
        for knob in knobs:
            cfg = _flip(cfg, knob, True)
        out.append((g, cfg, "P0"))
    out.append(("E", E_CFG, "E"))
    return out


def all_flipped_is_executor() -> bool:
    cfg = P0_CFG
    for knob, _, _ in KNOBS:
        cfg = _flip(cfg, knob, True)
    return cfg == E_CFG


def paper_anchor(fire_rows: list[dict], mkt: dict, tiers: dict) -> tuple[list, list, int]:
    """The mirror's r2a_ref path (paper grader, entry_date gate, select_capped)
    and the same rows through run_executor_book(R2A_MODE): (ref_curve, P_curve, n_taken)."""
    trail_rows, _ = build_trailing_rows(fire_rows, mkt, tiers)
    ta, _ = select_capped(gate_rows(trail_rows, mkt["xbi_above_prior"][200], key="entry_date"), CAP)
    return run_call_book(ta, mkt), run_executor_book(ta, mkt, P_CFG)["curve"], len(ta)


def run_arm(cfg: ExecCfg, fire_rows: list[dict], mkt: dict, tiers: dict) -> tuple[list, int, dict]:
    """Every non-anchor arm runs the executor path: lane grading under cfg,
    gate on the gate date, live cap occupancy, the ledger book. Returns the
    curve, the taken count and the grading counts (so a knob that REFUSES
    fires - day_zero_stop drops L0 <= 0 - is visible, counter-agent N1)."""
    rows, meta = build_exec_rows(fire_rows, mkt, tiers, cfg)
    gated = gate_rows(rows, mkt["xbi_above_prior"][200])
    taken, skipped = select_capped_exec(gated, CAP)
    book = run_executor_book(taken, mkt, cfg)
    grading = {k: v for k, v in meta.items() if isinstance(v, (int, float))}
    grading.update({"n_graded": len(rows), "n_gated": len(gated), "n_taken": len(taken),
                    "skipped_at_cap": skipped})
    return book["curve"], len(taken), grading


def daily_rets(curve: list, lo: date, hi: date) -> list[float]:
    seg = [v for d, v in curve if lo <= d <= hi]
    return [seg[i] / seg[i - 1] - 1 for i in range(1, len(seg))]


def _sharpe(r: list[float]) -> float:
    if len(r) < 2:
        return float("nan")
    mu = sum(r) / len(r)
    sd = math.sqrt(sum((x - mu) ** 2 for x in r) / (len(r) - 1))
    return (mu / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else float("nan")


def paired_sharpe_bootstrap(ra: list[float], rb: list[float], draws: int = ABL_DRAWS,
                            mean_block: int = BOOT_MEAN_BLOCK, seed: int = ABL_SEED,
                            family: int = N_EXPLORATORY) -> dict:
    """Stationary block bootstrap (the mirror's construction: seeded start,
    use-then-advance, p_new = 1/mean_block, wrap-around, horizon N) of the
    Sharpe DIFFERENCE a - b with IDENTICAL block draws for both series, so the
    interval is on the paired delta. Reports the 95% interval and the
    Bonferroni-`family` interval from the same draws."""
    N = min(len(ra), len(rb))
    if N < 3:
        return {}
    rng = random.Random(seed)
    p_new = 1.0 / mean_block
    diffs = []
    for _ in range(draws):
        i = rng.randrange(N)
        xa, xb = [], []
        for _step in range(N):
            xa.append(ra[i])
            xb.append(rb[i])
            i = rng.randrange(N) if rng.random() < p_new else (i + 1) % N
        diffs.append(_sharpe(xa) - _sharpe(xb))
    diffs.sort()

    def pct(p: float) -> float:
        return diffs[min(len(diffs) - 1, max(0, round(p / 100 * (len(diffs) - 1))))]

    tail = 100 * (0.05 / family) / 2
    return {"draws": draws, "mean_block_days": mean_block, "seed": seed, "n_days": N,
            "p2_5": pct(2.5), "p50": pct(50), "p97_5": pct(97.5),
            "bonf_family": family, "bonf_lo": pct(tail), "bonf_hi": pct(100 - tail),
            "excludes_zero": (pct(2.5) > 0) or (pct(97.5) < 0)}


def _share(num: float, den: float) -> float | None:
    return (num / den) if abs(den) > 1e-12 else None


def _on_side(ci: dict, sign: float, lo_key: str = "p2_5", hi_key: str = "p97_5") -> bool:
    """The interval lies entirely on the side of `sign` (negative: hi < 0)."""
    if not ci or sign == 0:
        return False
    return (ci[hi_key] < 0) if sign < 0 else (ci[lo_key] > 0)


def knob_verdict(knob: str, f: dict, b: dict, gap_cagr: float, gap_sharpe: float,
                 max_dd_B: float, max_dd_E: float) -> dict:
    """The contract's four-part rule (addendum 1 items 4-6), on plain inputs so
    it is unit-testable with fixed numbers."""
    sgn_c = -1.0 if gap_cagr < 0 else 1.0           # the direction a forward flip should move CAGR
    sgn_s = -1.0 if gap_sharpe < 0 else 1.0         # ... and Sharpe
    f_sub_ok = sum(1 for v in f["subperiod_cagr_delta"].values()
                   if not math.isnan(v) and v * sgn_c > 0) >= 2
    b_sub_ok = sum(1 for v in b["subperiod_cagr_delta"].values()
                   if not math.isnan(v) and v * -sgn_c > 0) >= 2
    fci, bci = f["sharpe_delta_bootstrap"], b["sharpe_delta_bootstrap"]
    tests = {
        "forward_gap_share_ge_0.5": (f.get("gap_share") is not None and f["gap_share"] >= CARRY_SHARE),
        "backward_recovery_share_ge_0.5": (b.get("recovery_share") is not None
                                           and b["recovery_share"] >= CARRY_SHARE),
        "sharpe_ci_on_gap_side_both": bool(_on_side(fci, sgn_s) and _on_side(bci, -sgn_s)),
        "subperiod_sign_2_of_3_both": bool(f_sub_ok and b_sub_ok),
    }
    carries = all(tests.values())
    bonf = bool(_on_side(fci, sgn_s, "bonf_lo", "bonf_hi") and _on_side(bci, -sgn_s, "bonf_lo", "bonf_hi"))
    dd_ok = max_dd_B <= max_dd_E + ACTION_MAXDD_SLACK
    where = WHERE[knob]
    return {"tests": tests, "carries_the_gap": carries,
            "survives_bonferroni_8": bool(carries and bonf),
            "primary": knob == PRIMARY_KNOB,
            "backward_max_dd_within_slack": dd_ok, "where_it_lives": where,
            "proposal": bool(carries and dd_ok and where != "not_actionable"),
            "forward_gap_share": f.get("gap_share"), "backward_recovery_share": b.get("recovery_share")}


def stored_mirror_end(name: str = "exec_t1_nocost_nocarry") -> float | None:
    path = _input(MIRROR_RESULTS)
    if not path.exists():
        print(f"WARNING: no mirror results at {path}: E cannot be checked against the published "
              f"mirror run (e_vs_mirror.stored_mirror_end = null). On the Render host the file is "
              f"present; locally run the mirror first for the guard to bite.", file=sys.stderr)
        return None
    try:
        return float(json.loads(path.read_text())["variants"][name]["windows"]["full"]["end_value"])
    except (KeyError, ValueError, TypeError):
        return None


def run_ablation(fire_rows: list[dict], mkt: dict, tiers: dict, *, draws: int = ABL_DRAWS,
                 seed: int = ABL_SEED, bars_info: dict | None = None,
                 cache_basis: dict | None = None, mirror_e_end: float | None = None,
                 reduction_tol: float = REDUCTION_TOL) -> dict:
    if not all_flipped_is_executor():
        raise SystemExit("KNOBS do not span P0 -> E: the contract's knob table is incomplete")
    calendar = mkt["calendar"]
    lo_full, hi_full = calendar[0], calendar[-1]
    windows = {"full": (lo_full, hi_full)}
    for name, lo, hi in SUB_PERIODS:
        if lo <= hi_full and hi >= lo_full:
            windows[name] = (max(lo, lo_full), min(hi, hi_full))

    # ---- machinery: P reduces to the mirror's r2a_ref; E matches the mirror's stored run
    ref_curve, p_curve, n_p = paper_anchor(fire_rows, mkt, tiers)
    red = max(abs(a[1] - b[1]) for a, b in zip(ref_curve, p_curve)) if ref_curve else 0.0
    if len(ref_curve) != len(p_curve) or red > reduction_tol:
        raise SystemExit(f"MACHINERY: P does not reduce to the mirror's r2a_ref (max|diff| {red:.3e} > "
                         f"{reduction_tol}) — nothing written")
    curves: dict[str, list] = {"P": p_curve}
    n_taken: dict[str, int] = {"P": n_p}
    grading: dict[str, dict] = {"P": {"n_taken": n_p, "path": "paper grader (build_trailing_rows)"}}
    for name, cfg, _base in arms():
        if name == "P":
            continue
        cv, n, g = run_arm(cfg, fire_rows, mkt, tiers)
        curves[name] = cv
        n_taken[name] = n
        grading[name] = g
    e_end = curves["E"][-1][1]
    e_check = {"stored_mirror_end": mirror_e_end, "got": e_end,
               "abs_diff": (abs(e_end - mirror_e_end) if mirror_e_end is not None else None)}
    if mirror_e_end is not None and abs(e_end - mirror_e_end) > 1.0:
        raise SystemExit(f"MACHINERY: E ends at ${e_end:,.2f} but the mirror results on disk say "
                         f"${mirror_e_end:,.2f} for exec_t1_nocost_nocarry — the bars changed under "
                         f"the study; re-run the mirror first. Nothing written")
    stats = {n: {w: seg_stats(cv, lo, hi) for w, (lo, hi) in windows.items()} for n, cv in curves.items()}

    cagr = {n: stats[n]["full"].get("cagr", float("nan")) for n in stats}
    sharpe = {n: stats[n]["full"].get("sharpe", float("nan")) for n in stats}
    gap = cagr["E"] - cagr["P0"]
    gap_sharpe = sharpe["E"] - sharpe["P0"]
    gap_vs_p = cagr["E"] - cagr["P"]
    basis_clean = abs(cagr["P0"] - cagr["P"]) <= BASIS_CLEAN_CAGR
    results: dict[str, dict] = {}
    for name, cfg, base in arms():
        d_full = {k: stats[name]["full"].get(k, float("nan")) - stats[base]["full"].get(k, float("nan"))
                  for k in ("cagr", "max_dd", "sharpe", "end_value")}
        sub = {w: stats[name][w].get("cagr", float("nan")) - stats[base][w].get("cagr", float("nan"))
               for w in windows if w != "full"}
        boot = (paired_sharpe_bootstrap(daily_rets(curves[name], lo_full, hi_full),
                                        daily_rets(curves[base], lo_full, hi_full), draws,
                                        BOOT_MEAN_BLOCK, seed)
                if name != base else {})
        entry = {"base": base, "cfg": cfg.label, "n_taken": n_taken[name], "grading": grading[name],
                 "stats": stats[name], "delta_vs_base": d_full,
                 "subperiod_cagr_delta": sub, "sharpe_delta_bootstrap": boot}
        if name.startswith("F_") or name in GROUPS:
            entry["gap_share"] = _share(d_full["cagr"], gap)
            # counter-agent N2: when the basis is not clean, the share against P too
            entry["gap_share_vs_P"] = _share(stats[name]["full"].get("cagr", float("nan")) - cagr["P"], gap_vs_p)
        elif name.startswith("B_"):
            entry["recovery_share"] = _share(d_full["cagr"], -gap)
            entry["recovery_share_vs_P"] = _share(d_full["cagr"], -gap_vs_p)
        results[name] = entry

    verdicts: dict[str, dict] = {}
    for knob, _, _ in KNOBS:
        f, b = results[f"F_{knob}"], results[f"B_{knob}"]
        v = knob_verdict(knob, f, b, gap, gap_sharpe,
                         stats[f"B_{knob}"]["full"].get("max_dd", 9.0), stats["E"]["full"].get("max_dd", 0.0))
        if v["carries_the_gap"]:
            # addendum 1, item 7: block-length sensitivity
            v["block63"] = {
                "forward": paired_sharpe_bootstrap(daily_rets(curves[f"F_{knob}"], lo_full, hi_full),
                                                   daily_rets(curves["P0"], lo_full, hi_full), draws,
                                                   BLOCK_SENSITIVITY, seed),
                "backward": paired_sharpe_bootstrap(daily_rets(curves[f"B_{knob}"], lo_full, hi_full),
                                                    daily_rets(curves["E"], lo_full, hi_full), draws,
                                                    BLOCK_SENSITIVITY, seed)}
            sgn = -1.0 if gap_sharpe < 0 else 1.0
            v["block63_holds"] = bool(_on_side(v["block63"]["forward"], sgn)
                                      and _on_side(v["block63"]["backward"], -sgn))
        verdicts[knob] = v

    return {
        "generated": date.today().isoformat(),
        "contract": "docs/VARIANTS_PREREGISTRATION_R9_EXIT_ABLATION.md (+ addendum 1)",
        "script": "scripts/backtest_exit_ablation.py",
        "windows": {w: [lo.isoformat(), hi.isoformat()] for w, (lo, hi) in windows.items()},
        "knobs": [{"knob": k, "paper": pv, "executor": ev, "where": WHERE[k]} for k, pv, ev in KNOBS],
        "groups": {g: list(ks) for g, ks in GROUPS.items()},
        "protocol": {"costs": "none", "carry": False, "entry_lag": 1, "sleeve_target": 1.0,
                     "cap": CAP, "gate": "XBI > 200dma prior close; slot held from the gate date",
                     "base": "P0 = R2A_MODE on the ledger basis (paper_arith=False)",
                     "bootstrap": {"kind": "paired stationary block on the Sharpe delta vs the arm's base",
                                   "draws": draws, "mean_block_days": BOOT_MEAN_BLOCK, "seed": seed,
                                   "bonferroni_family": N_EXPLORATORY, "block_sensitivity_days": BLOCK_SENSITIVITY},
                     "primary_knob": PRIMARY_KNOB,
                     "carry_share": CARRY_SHARE, "action_max_dd_slack": ACTION_MAXDD_SLACK,
                     "bars": bars_info or {}, "cache_basis": cache_basis or {}},
        "machinery": {"p_reduction_max_abs_diff": red, "p_n_taken": n_p, "e_vs_mirror": e_check},
        "basis_switch": {"P0_minus_P": {k: stats["P0"]["full"].get(k, float("nan")) - stats["P"]["full"].get(k, float("nan"))
                                       for k in ("cagr", "max_dd", "sharpe", "end_value")},
                         "clean": basis_clean, "clean_tolerance_cagr": BASIS_CLEAN_CAGR,
                         "note": ("basis switch inside the noise floor: shares are read against P0" if basis_clean else
                                  "BASIS NOT CLEAN: the ledger basis moves CAGR by more than the noise floor; "
                                  "read every share against BOTH bases (gap_share / gap_share_vs_P)")},
        "mechanics_gap": {"cagr_P": cagr["P"], "cagr_P0": cagr["P0"], "cagr_E": cagr["E"], "gap_cagr": gap,
                          "sharpe_P0": sharpe["P0"], "sharpe_E": sharpe["E"], "gap_sharpe": gap_sharpe,
                          "max_dd_P0": stats["P0"]["full"].get("max_dd"), "max_dd_E": stats["E"]["full"].get("max_dd")},
        "arms": results,
        "verdicts": verdicts,
        "honesty": list(HONESTY),
    }


def print_table(res: dict) -> None:
    g = res["mechanics_gap"]
    bs = res["basis_switch"]["P0_minus_P"]
    print(f"\nbasis switch P0 - P: CAGR {bs['cagr']:+.2%}  maxDD {bs['max_dd']:+.2%}  Sharpe {bs['sharpe']:+.3f}  "
          f"end ${bs['end_value']:+,.0f}  -> {'clean' if res['basis_switch']['clean'] else 'NOT CLEAN (read shares against both bases)'}")
    print(f"mechanics gap (E - P0), full window: CAGR {g['gap_cagr']:+.2%} (P0 {g['cagr_P0']:.2%} -> E {g['cagr_E']:.2%}); "
          f"Sharpe {g['sharpe_P0']:.3f} -> {g['sharpe_E']:.3f}; maxDD {g['max_dd_P0']:.1%} -> {g['max_dd_E']:.1%}")
    sgn_c = -1 if g["gap_cagr"] < 0 else 1
    print(f"\n{'arm':20s} {'base':4s} {'CAGR':>8s} {'maxDD':>7s} {'Sharpe':>7s} {'dCAGR':>8s} {'dSharpe':>8s} "
          f"{'share':>7s} {'CI95 dSharpe':>22s} {'sub':>4s} {'taken':>6s}")
    for name, a in res["arms"].items():
        s = a["stats"]["full"]
        d = a["delta_vs_base"]
        share = a.get("gap_share", a.get("recovery_share"))
        b = a["sharpe_delta_bootstrap"]
        ci = f"[{b['p2_5']:+.3f}, {b['p97_5']:+.3f}]{'*' if b.get('excludes_zero') else ' '}" if b else ""
        exp = sgn_c if (name.startswith("F_") or name in GROUPS) else -sgn_c
        subs = sum(1 for v in a["subperiod_cagr_delta"].values() if v * exp > 0)
        print(f"{name:20s} {a['base']:4s} {s.get('cagr', float('nan')):8.2%} {s.get('max_dd', float('nan')):7.1%} "
              f"{s.get('sharpe', float('nan')):7.3f} {d['cagr']:+8.2%} {d['sharpe']:+8.3f} "
              f"{(share if share is not None else float('nan')):7.2f} {ci:>22s} {subs:>4d} {a['n_taken']:>6d}")
    print("\nverdicts (fwd share >= 0.5, bwd recovery >= 0.5, Sharpe CI on the gap side both ways, sub-period sign 2/3 both ways):")
    for knob, v in res["verdicts"].items():
        t = v["tests"]
        fs = "   -  " if v["forward_gap_share"] is None else f"{v['forward_gap_share']:6.2f}"
        bs_ = "   -  " if v["backward_recovery_share"] is None else f"{v['backward_recovery_share']:6.2f}"
        print(f"  {knob:17s} fwd {fs} bwd {bs_} CI {'y' if t['sharpe_ci_on_gap_side_both'] else 'n'} "
              f"sub {'y' if t['subperiod_sign_2_of_3_both'] else 'n'} [{v['where_it_lives']}]"
              f"{' PRIMARY' if v['primary'] else ''} -> {'CARRIES' if v['carries_the_gap'] else 'no'}"
              f"{' bonf8-ok' if v['survives_bonferroni_8'] else ''}"
              f"{' block63-ok' if v.get('block63_holds') else (' block63-FAILS' if 'block63' in v else '')}"
              f"{' PROPOSAL' if v['proposal'] else ''}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=RESULTS)
    ap.add_argument("--draws", type=int, default=ABL_DRAWS)
    ap.add_argument("--seed", type=int, default=ABL_SEED)
    args = ap.parse_args(argv)
    inp = load_inputs(refresh_bars_if_missing=True)
    res = run_ablation(inp["fire_rows"], inp["mkt"], inp["tiers"], draws=args.draws, seed=args.seed,
                       bars_info=inp.get("bars_info"), cache_basis=inp.get("cache_basis"),
                       mirror_e_end=stored_mirror_end())
    write_results(res, args.out)
    print_table(res)
    print(f"\nResults written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
