"""Round 9 — exit-rule ablation: which executor knob carries the gap to the
paper R2-A? Contract: docs/VARIANTS_PREREGISTRATION_R9_EXIT_ABLATION.md
(committed before this file existed). Everything is IMPORTED from the
executor mirror; no engine is re-implemented here.

Arms: P (paper, R2A_MODE), F_k (P with one knob at the executor value),
B_k (E with one knob at the paper value), G_stop / G_time / G_size (knob
groups on P), E (executor mechanics only: no costs, no carry, lag 1).
Metrics per the contract: full-window and sub-period stats, gap share,
recovery share, paired stationary block bootstrap of the Sharpe delta vs
the arm's base, the four-part "carries the gap" rule and the action bar.

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
    BOOT_MEAN_BLOCK, CAP, DATA, EXEC_T1, R2A_MODE, ExecCfg, _round, build_exec_rows,
    gate_rows, load_inputs, run_executor_book, select_capped_exec, write_results,
)
from scripts.backtest_variants_10y import SUB_PERIODS, seg_stats  # noqa: E402

RESULTS = DATA / "backtest_exit_ablation_results.json"
ABL_SEED = 20261004
ABL_DRAWS = 2000
TRADING_DAYS = 252

# knob, paper value, executor value — the contract's table, in its order
KNOBS: list[tuple[str, object, object]] = [
    ("peak_seed", "entry_close", "fire_close"),
    ("ratchet", False, True),
    ("day_zero_stop", False, True),
    ("risk_cap", 0.5, None),
    ("time_stop_anchor", "entry", "fire"),
    ("time_stop_fill", "deadline_close", "next_open"),
    ("integer_shares", False, True),
    ("cash_clip", False, True),
    ("paper_arith", True, False),
]
GROUPS = {"G_stop": ("peak_seed", "ratchet", "day_zero_stop"),
          "G_time": ("time_stop_anchor", "time_stop_fill"),
          "G_size": ("risk_cap", "integer_shares", "cash_clip", "paper_arith")}
CARRY_SHARE = 0.50          # contract: forward gap share and backward recovery share
ACTION_MAXDD_SLACK = 0.02   # contract: backward flip's max DD no more than 2 pp worse than E

P_CFG = R2A_MODE
E_CFG = replace(EXEC_T1, commission_model="none", bil_order_cost=False, carry=False)


def _flip(cfg: ExecCfg, knob: str, to_executor: bool) -> ExecCfg:
    _, pv, ev = next(k for k in KNOBS if k[0] == knob)
    return replace(cfg, **{knob: ev if to_executor else pv})


def arms() -> list[tuple[str, ExecCfg, str]]:
    """(name, cfg, base_name). The base is what the arm's delta is measured against."""
    out: list[tuple[str, ExecCfg, str]] = [("P", P_CFG, "P")]
    for knob, _, _ in KNOBS:
        out.append((f"F_{knob}", _flip(P_CFG, knob, True), "P"))
    for knob, _, _ in KNOBS:
        out.append((f"B_{knob}", _flip(E_CFG, knob, False), "E"))
    for g, knobs in GROUPS.items():
        cfg = P_CFG
        for knob in knobs:
            cfg = _flip(cfg, knob, True)
        out.append((g, cfg, "P"))
    out.append(("E", E_CFG, "E"))
    return out


def all_flipped_is_executor() -> bool:
    cfg = P_CFG
    for knob, _, _ in KNOBS:
        cfg = _flip(cfg, knob, True)
    return cfg == E_CFG


def run_arm(cfg: ExecCfg, fire_rows: list[dict], mkt: dict, tiers: dict) -> tuple[list, int]:
    rows, _ = build_exec_rows(fire_rows, mkt, tiers, cfg)
    taken, _ = select_capped_exec(gate_rows(rows, mkt["xbi_above_prior"][200]), CAP)
    book = run_executor_book(taken, mkt, cfg)
    return book["curve"], len(taken)


def daily_rets(curve: list, lo: date, hi: date) -> list[float]:
    seg = [v for d, v in curve if lo <= d <= hi]
    return [seg[i] / seg[i - 1] - 1 for i in range(1, len(seg))]


def _sharpe(r: list[float]) -> float:
    if len(r) < 2:
        return float("nan")
    mu = sum(r) / len(r)
    var = sum((x - mu) ** 2 for x in r) / (len(r) - 1)
    sd = math.sqrt(var)
    return (mu / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else float("nan")


def paired_sharpe_bootstrap(ra: list[float], rb: list[float], draws: int = ABL_DRAWS,
                            mean_block: int = BOOT_MEAN_BLOCK, seed: int = ABL_SEED) -> dict:
    """Stationary block bootstrap (same construction as the mirror's) of the
    Sharpe DIFFERENCE a − b, with IDENTICAL block draws for both series so the
    interval is on the paired delta, not on two independent resamples."""
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

    lo, hi = pct(2.5), pct(97.5)
    return {"draws": draws, "mean_block_days": mean_block, "seed": seed, "n_days": N,
            "p2_5": lo, "p50": pct(50), "p97_5": hi,
            "excludes_zero": (lo > 0) or (hi < 0)}


def _share(num: float, den: float) -> float | None:
    return (num / den) if abs(den) > 1e-12 else None


def run_ablation(fire_rows: list[dict], mkt: dict, tiers: dict, *, draws: int = ABL_DRAWS,
                 seed: int = ABL_SEED, bars_info: dict | None = None,
                 cache_basis: dict | None = None) -> dict:
    if not all_flipped_is_executor():
        raise SystemExit("KNOBS do not span P -> E: the contract's knob table is incomplete")
    calendar = mkt["calendar"]
    lo_full, hi_full = calendar[0], calendar[-1]
    windows = {"full": (lo_full, hi_full)}
    for name, lo, hi in SUB_PERIODS:
        windows[name] = (max(lo, lo_full), min(hi, hi_full))

    curves: dict[str, list] = {}
    stats: dict[str, dict] = {}
    n_taken: dict[str, int] = {}
    for name, cfg, _base in arms():
        cv, n = run_arm(cfg, fire_rows, mkt, tiers)
        curves[name] = cv
        n_taken[name] = n
        stats[name] = {w: seg_stats(cv, lo, hi) for w, (lo, hi) in windows.items()}

    cagr = {n: stats[n]["full"].get("cagr", float("nan")) for n in stats}
    gap = cagr["E"] - cagr["P"]
    results: dict[str, dict] = {}
    for name, cfg, base in arms():
        d_full = {k: stats[name]["full"].get(k, float("nan")) - stats[base]["full"].get(k, float("nan"))
                  for k in ("cagr", "max_dd", "sharpe", "end_value")}
        sub = {w: stats[name][w].get("cagr", float("nan")) - stats[base][w].get("cagr", float("nan"))
               for w in windows if w != "full"}
        boot = (paired_sharpe_bootstrap(daily_rets(curves[name], lo_full, hi_full),
                                        daily_rets(curves[base], lo_full, hi_full),
                                        draws, BOOT_MEAN_BLOCK, seed)
                if name != base else {})
        entry = {"base": base, "cfg": cfg.label, "n_taken": n_taken[name],
                 "stats": stats[name], "delta_vs_base": d_full,
                 "subperiod_cagr_delta": sub, "sharpe_delta_bootstrap": boot}
        if name.startswith("F_"):
            entry["gap_share"] = _share(d_full["cagr"], gap)
        elif name.startswith("B_"):
            entry["recovery_share"] = _share(d_full["cagr"], -gap)
        elif name in GROUPS:
            entry["gap_share"] = _share(d_full["cagr"], gap)
        results[name] = entry

    # the contract's four-part rule, per knob
    verdicts: dict[str, dict] = {}
    for knob, _, _ in KNOBS:
        f, b = results[f"F_{knob}"], results[f"B_{knob}"]
        sign_f = -1 if gap < 0 else 1          # forward moves TOWARD E: expected sign of the CAGR delta
        f_sub_ok = sum(1 for v in f["subperiod_cagr_delta"].values()
                       if not math.isnan(v) and (v * sign_f) > 0) >= 2
        b_sub_ok = sum(1 for v in b["subperiod_cagr_delta"].values()
                       if not math.isnan(v) and (v * -sign_f) > 0) >= 2
        tests = {
            "forward_gap_share_ge_0.5": (f["gap_share"] is not None and f["gap_share"] >= CARRY_SHARE),
            "backward_recovery_share_ge_0.5": (b["recovery_share"] is not None
                                               and b["recovery_share"] >= CARRY_SHARE),
            "sharpe_ci_excludes_zero_both": bool(f["sharpe_delta_bootstrap"].get("excludes_zero")
                                                 and b["sharpe_delta_bootstrap"].get("excludes_zero")),
            "subperiod_sign_2_of_3_both": bool(f_sub_ok and b_sub_ok),
        }
        carries = all(tests.values())
        dd_ok = (stats[f"B_{knob}"]["full"].get("max_dd", 9) <= stats["E"]["full"].get("max_dd", 0)
                 + ACTION_MAXDD_SLACK)
        verdicts[knob] = {"tests": tests, "carries_the_gap": carries,
                          "backward_max_dd_within_slack": dd_ok,
                          "proposal": bool(carries and dd_ok),
                          "forward_gap_share": f["gap_share"], "backward_recovery_share": b["recovery_share"]}

    return {
        "generated": date.today().isoformat(),
        "contract": "docs/VARIANTS_PREREGISTRATION_R9_EXIT_ABLATION.md",
        "script": "scripts/backtest_exit_ablation.py",
        "windows": {w: [lo.isoformat(), hi.isoformat()] for w, (lo, hi) in windows.items()},
        "knobs": [{"knob": k, "paper": pv, "executor": ev} for k, pv, ev in KNOBS],
        "groups": {g: list(ks) for g, ks in GROUPS.items()},
        "protocol": {"costs": "none", "carry": False, "entry_lag": 1, "sleeve_target": 1.0,
                     "cap": CAP, "gate": "XBI > 200dma prior close, slot held from the gate date",
                     "bootstrap": {"kind": "paired stationary block on the Sharpe delta vs the arm's base",
                                   "draws": draws, "mean_block_days": BOOT_MEAN_BLOCK, "seed": seed},
                     "carry_share": CARRY_SHARE, "action_max_dd_slack": ACTION_MAXDD_SLACK,
                     "bars": bars_info or {}, "cache_basis": cache_basis or {}},
        "mechanics_gap": {"cagr_P": cagr["P"], "cagr_E": cagr["E"], "gap_cagr": gap,
                          "sharpe_P": stats["P"]["full"].get("sharpe"), "sharpe_E": stats["E"]["full"].get("sharpe"),
                          "max_dd_P": stats["P"]["full"].get("max_dd"), "max_dd_E": stats["E"]["full"].get("max_dd")},
        "arms": results,
        "verdicts": verdicts,
        "honesty": [
            "IN-SAMPLE SELECTION OF AN EXIT RULE on the history the engine was selected on; R3-F: the trail x time-stop map is not a plateau. A winner is a hypothesis for the live shadow record, not a result.",
            "BARS = FMP dividend-adjusted lane, not the August campaign cache (R2-A +9% end value, one cap flip); all arms share the lane: deltas internally consistent, absolute levels not the R2/R3 docs'.",
            "Deltas below the lane-drift noise floor (~0.8 pp CAGR) are not robust.",
            "Survivor universe, hindsight tiers; costs and carry OFF by design (rules, not economics).",
            "Shares of the gap need not sum to one (interactions); the group arms show them.",
            "Never present these in-sample CAGRs as a forecast.",
        ],
    }


def print_table(res: dict) -> None:
    g = res["mechanics_gap"]
    print(f"\nmechanics gap (E - P), full window: CAGR {g['gap_cagr']:+.2%}  "
          f"(P {g['cagr_P']:.2%} -> E {g['cagr_E']:.2%}); Sharpe {g['sharpe_P']:.3f} -> {g['sharpe_E']:.3f}; "
          f"maxDD {g['max_dd_P']:.1%} -> {g['max_dd_E']:.1%}")
    print(f"\n{'arm':22s} {'base':4s} {'CAGR':>8s} {'maxDD':>7s} {'Sharpe':>7s} {'dCAGR':>8s} {'dSharpe':>8s} "
          f"{'share':>7s} {'CI95 dSharpe':>22s} {'sub +':>5s} {'taken':>6s}")
    for name, a in res["arms"].items():
        s = a["stats"]["full"]
        d = a["delta_vs_base"]
        share = a.get("gap_share", a.get("recovery_share"))
        b = a["sharpe_delta_bootstrap"]
        ci = f"[{b['p2_5']:+.3f}, {b['p97_5']:+.3f}]{'*' if b.get('excludes_zero') else ' '}" if b else ""
        subs = sum(1 for v in a["subperiod_cagr_delta"].values() if v * (1 if d["cagr"] >= 0 else -1) > 0)
        print(f"{name:22s} {a['base']:4s} {s.get('cagr', float('nan')):8.2%} {s.get('max_dd', float('nan')):7.1%} "
              f"{s.get('sharpe', float('nan')):7.3f} {d['cagr']:+8.2%} {d['sharpe']:+8.3f} "
              f"{(share if share is not None else float('nan')):7.2f} {ci:>22s} {subs:>5d} {a['n_taken']:>6d}")
    print("\nverdicts (contract: forward share >= 0.5, backward recovery >= 0.5, CI excludes 0 both ways, sub-period sign 2/3 both ways):")
    for knob, v in res["verdicts"].items():
        t = v["tests"]
        print(f"  {knob:18s} fwd {v['forward_gap_share'] if v['forward_gap_share'] is None else round(v['forward_gap_share'], 2)!s:>6} "
              f"bwd {v['backward_recovery_share'] if v['backward_recovery_share'] is None else round(v['backward_recovery_share'], 2)!s:>6} "
              f"CI {'y' if t['sharpe_ci_excludes_zero_both'] else 'n'} sub {'y' if t['subperiod_sign_2_of_3_both'] else 'n'} "
              f"-> {'CARRIES' if v['carries_the_gap'] else 'no'}{' (proposal)' if v['proposal'] else ''}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=RESULTS)
    ap.add_argument("--draws", type=int, default=ABL_DRAWS)
    ap.add_argument("--seed", type=int, default=ABL_SEED)
    args = ap.parse_args(argv)
    inp = load_inputs(refresh_bars_if_missing=True)
    res = run_ablation(inp["fire_rows"], inp["mkt"], inp["tiers"], draws=args.draws, seed=args.seed,
                       bars_info=inp.get("bars_info"), cache_basis=inp.get("cache_basis"))
    write_results(res, args.out)
    print_table(res)
    print(f"\nResults written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
