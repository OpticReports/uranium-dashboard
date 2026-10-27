"""Round 10 — sleeve sizing: does the 30% sleeve sit idle, and does sizing
by occupancy help? Contract: docs/VARIANTS_PREREGISTRATION_R10_SIZING.md,
committed before this code. Everything is IMPORTED from the executor mirror
and the round-9 ablation; no engine is re-implemented here.

Arms (all on the executor path: T+2 fill, IBKR costs, BIL carry, cap 10,
XBI gate, 30/70 with the 5pp band — the mirror's blend3070_t2_carry book):
S0 risk 1% (anchor = the live rule), S1 1.5%, S2 2%, S3 3%, D1 slot_fill,
D2 inverse_occupancy. Two capital bases: $100,000 (the replay) and $120,000
(the live book after the deposit). The TAKEN set is identical across arms
(cap selection precedes sizing); only the book differs.

Metrics per arm and base: book-level and sleeve-level seg_stats over the
mirror's full / 5y / 2y windows, longest underwater, the sleeve's deployed
fraction (daily mean, p10/p50/p90, and the mean on days with >= 1 open),
share of days at >= 9 open / AT the 10-cap / at 0 open, the BIL carry in
dollars, entries, skipped_zero_qty, worst single trade as % of sleeve
equity at entry. H15a is scored in two halves (deployment within the 20-40%
prior; cap reached on a 'small minority' = under CAP_MINORITY of days).
Primary statistic: the paired stationary block bootstrap of the book-level
Sharpe delta vs S0 (identical block draws, mean block 21, seed 20261005,
Bonferroni family 5), plus the 63-day block sensitivity at 2,000 draws and
the 5y-window Sharpe-delta sign. Decision rule per the contract.

Usage:  python -m scripts.backtest_sizing_study [--out PATH] [--draws N] [--seed S]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backtest_executor_mirror import (  # noqa: E402
    BOOT_MEAN_BLOCK, CAP, DATA, EXEC_T2, ExecCfg, build_exec_rows, gate_rows, load_inputs,
    longest_underwater, run_executor_book, select_capped_exec, window_bounds, write_results,
)
from scripts.backtest_exit_ablation import (  # noqa: E402
    daily_rets, paired_sharpe_bootstrap, stored_mirror_end,
)
from scripts.backtest_variants_10y import START_EQUITY, seg_stats  # noqa: E402

RESULTS = DATA / "backtest_sizing_study_results.json"
SCRIPT = "scripts/backtest_sizing_study.py"
STUDY_SEED = 20261005
STUDY_DRAWS = 10000
SENS_DRAWS = 2000
SENS_BLOCK = 63
FAMILY = 5                       # Bonferroni family: the five non-anchor arms
MAXDD_SLACK = 0.02               # contract: book max DD no more than 2 pp worse than S0
ANCHOR = "S0"
MIRROR_VARIANT = "blend3070_t2_carry"
REDUCTION_TOL_USD = 1.0
LIVE_BASE = 120_000.0
BASES = (START_EQUITY, LIVE_BASE)
NEAR_CAP = 9
H15A_PRIOR = (0.20, 0.40)        # contract: mean deployed fraction prior
CAP_MINORITY = 0.10              # 'cap reached on a small minority of days' operationalised as < 10% of days

BLEND = replace(EXEC_T2, sleeve_target=0.30)

ARMS: list[tuple[str, dict, str]] = [
    ("S0", {"risk_frac": 0.01}, "risk 1.0% of sleeve equity (anchor; the live rule)"),
    ("S1", {"risk_frac": 0.015}, "risk 1.5%"),
    ("S2", {"risk_frac": 0.02}, "risk 2.0%"),
    ("S3", {"risk_frac": 0.03}, "risk 3.0%"),
    ("D1", {"sizing": "slot_fill"}, "slot-fill: notional = spendable sleeve cash / (10 - open)"),
    ("D2", {"sizing": "inverse_occupancy", "risk_frac": 0.01, "risk_frac_max": 0.03},
     "inverse-occupancy: risk = clamp(1% x 10 / (open + 1), 1%, 3%)"),
]

HONESTY = [
    # contract, "What this cannot tell us", carried verbatim in substance
    "In-sample over the same 10.6 years as every prior round; a sizing winner here is a hypothesis, "
    "not a result.",
    "The fire set is the tracker's (survivor-shaped universe); the fire rate (~9/month live) is taken "
    "as given, so an arm that would change which calls fire is out of scope.",
    "Costs are the IBKR fixed schedule, slippage by tier; BIL carry is the realised BIL total return, "
    "not a forecast.",
    "A dynamic arm (D1/D2) changes the executor's sizing contract and would need an executor build "
    "plus a tracker publication to go live.",
    "MEASUREMENT BASIS: daily mark-to-market on adjusted closes (trade-close MTM); max DD on the daily "
    "curve; CAGR calendar-day (365.25); Sharpe sqrt(252), rf = 0; trailing windows are SLICES of the "
    "full curve, not restarted books.",
    "The paired Sharpe-delta interval is CONDITIONAL on this single in-sample path and the fixed taken "
    "set (identical across arms here): it is an interval on these events, not on the strategy; "
    "percentile intervals, not bias-corrected; 21-day blocks understate multi-year regime persistence "
    "(see the 63-day sensitivity).",
    "Max DD carries no interval: the 2 pp bar is a single-path, single-episode point comparison.",
    "A positive CAGR delta with a wider drawdown is leverage, not improvement (contract decision rule).",
    "Deployed fraction = 1 - max(sleeve_cash, 0) / sleeve_eq at the close, so it counts open MTM "
    "notional, not cost basis; negative sleeve cash (the fill-vs-entry_ref gap) reads as 100%.",
    "Sizing proxy: lag-2 entries are sized on the sleeve equity at the fire-day close (the executor "
    "sizes at T+1 ~10:30 on live marks); slot_fill reads the spendable cash at that moment in the "
    "daily loop, after the day's exits.",
    "The sleeve-level curve is the 30/70 book's sleeve bucket INCLUDING band-rebalance transfers to and "
    "from the core, so its CAGR / DD are not a stand-alone sleeve strategy's (the mirror's exec_t2_carry "
    "is that); the sleeve columns are for deployment and sizing-size context, the decision rule is "
    "book-level.",
    "OCCUPANCY BASIS (D1/D2): the replay reads the open list and spendable cash on the T+2 fill day "
    "AFTER that day's exits (filled positions + earlier same-day entries); the executor reads "
    "open_count = positions - exiting + pending MOOs at T+1 ~10:30. Rows fired at T+1 close (slot held "
    "from their gate date in select_capped_exec) do not exist at the live sizing moment and are not "
    "counted; the T+2 exits ARE netted here and would not be live. protocol.occupancy_basis counts how "
    "many entries sit on such days. Neither direction can flip a NULL whose Bonferroni-5 lower bound is "
    "~-0.2 (D1/D2).",
    "THE BINDING CONSTRAINT on deployment is cap x notional-per-slot (10 x ~7-8% of the sleeve => ~74% "
    "deployed at a full cap) plus the 200dma gate (0% on gate-off days), not the 1% rule by itself; a "
    "cap arm is outside this contract's scope.",
    "Never present these in-sample CAGRs as a forecast.",
]


# --- arms ---------------------------------------------------------------------------

def arm_cfg(kwargs: dict, base: float) -> ExecCfg:
    return replace(BLEND, start_equity=base, **kwargs)


def taken_rows(fire_rows: list[dict], mkt: dict, tiers: dict) -> tuple[list[dict], dict]:
    """The mirror's lag-2 path: grade under EXEC_T2, gate on the gate date,
    live cap occupancy. Sizing knobs do not touch grading, so this is done
    once and shared by every arm."""
    rows, meta = build_exec_rows(fire_rows, mkt, tiers, EXEC_T2)
    gated = gate_rows(rows, mkt["xbi_above_prior"][200])
    taken, skipped = select_capped_exec(gated, CAP)
    g = {k: v for k, v in meta.items() if isinstance(v, (int, float))}
    g.update({"n_graded": len(rows), "n_gated": len(gated), "n_taken": len(taken),
              "skipped_at_cap": skipped})
    return taken, g


# --- sleeve statistics ---------------------------------------------------------------

def _pct(vals: list[float], p: float) -> float:
    """Nearest-rank percentile on the sorted list (the mirror's convention)."""
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))]


def deployment_stats(daily: dict[str, dict], lo: date, hi: date) -> dict:
    """From the book's per-day dict over [lo, hi]: deployed fraction
    = 1 - max(sleeve_cash, 0) / sleeve_eq per day (days with sleeve_eq <= 0
    are excluded), its mean and p10/p50/p90, and its mean on the days with
    >= 1 open; share of days with open_positions >= NEAR_CAP, == CAP, == 0;
    entries and skipped_zero_qty summed."""
    los, his = lo.isoformat(), hi.isoformat()
    ev = [e for ds, e in daily.items() if los <= ds <= his]
    dep = [1.0 - max(e["sleeve_cash"], 0.0) / e["sleeve_eq"] for e in ev if e["sleeve_eq"] > 0]
    dep_open = [1.0 - max(e["sleeve_cash"], 0.0) / e["sleeve_eq"] for e in ev
                if e["sleeve_eq"] > 0 and e["open_positions"] >= 1]
    n = len(ev)
    share = lambda pred: (sum(1 for e in ev if pred(e["open_positions"])) / n) if n else None  # noqa: E731
    return {
        "n_days": n,
        "deployed_mean": statistics.fmean(dep) if dep else None,
        "deployed_p10": _pct(dep, 10) if dep else None,
        "deployed_p50": _pct(dep, 50) if dep else None,
        "deployed_p90": _pct(dep, 90) if dep else None,
        "deployed_mean_when_open": statistics.fmean(dep_open) if dep_open else None,
        "share_days_ge9_open": share(lambda k: k >= NEAR_CAP),
        "share_days_at_cap": share(lambda k: k == CAP),
        "share_days_zero_open": share(lambda k: k == 0),
        "max_open": max((e["open_positions"] for e in ev), default=0),
        "entries": sum(e["entries"] for e in ev),
        "skipped_zero_qty": sum(e["skipped_zero_qty"] for e in ev),
    }


def occupancy_basis(taken: list[dict]) -> dict:
    """How often the replay's entry day differs from the executor's slot view:
    for every taken row, the number of OTHER taken rows whose cap slot is
    held (gate_date <= entry day) but which are not yet filled (entry_date >
    entry day). Reported, not corrected — see the OCCUPANCY BASIS honesty
    line."""
    pend = []
    for t in taken:
        ds = t["entry_date"]
        pend.append(sum(1 for u in taken if u is not t
                        and u.get("gate_date", u["entry_date"]) <= ds < u["entry_date"]))
    n = len(taken)
    return {
        "basis": "replay: open list + spendable cash read on the T+2 fill day after that day's exits; "
                 "executor: positions - exiting + pending MOOs at T+1 ~10:30",
        "n_entries": n,
        "entries_with_slot_held_unfilled": sum(1 for k in pend if k >= 1),
        "share_entries_with_slot_held_unfilled": (sum(1 for k in pend if k >= 1) / n) if n else None,
        "max_slot_held_unfilled": max(pend, default=0),
    }


def h15a_verdict(dep: dict) -> dict:
    """H15a in two halves on S0's full-window deployment stats: (i) mean
    deployed fraction inside the contract's 20-40% prior; (ii) the 10-cap
    reached on a small minority of days (< CAP_MINORITY). Each half is
    CONFIRMED / REFUTED on its own number."""
    m, at_cap = dep["deployed_mean"], dep["share_days_at_cap"]
    dep_ok = m is not None and H15A_PRIOR[0] <= m <= H15A_PRIOR[1]
    cap_ok = at_cap is not None and at_cap < CAP_MINORITY
    return {
        "deployment_mean": m, "prior": list(H15A_PRIOR), "deployment_within_prior": bool(dep_ok),
        "deployment_verdict": "CONFIRMED" if dep_ok else "REFUTED",
        "share_days_at_cap": at_cap, "cap_minority_threshold": CAP_MINORITY,
        "cap_minority_verdict": "CONFIRMED" if cap_ok else "REFUTED",
        "share_days_ge9_open": dep["share_days_ge9_open"],
        "share_days_zero_open": dep["share_days_zero_open"],
        "deployed_mean_when_open": dep["deployed_mean_when_open"],
        "deployed_p90": dep["deployed_p90"],
        "verdict": (f"deployment {'CONFIRMED' if dep_ok else 'REFUTED'} (mean "
                    f"{(m if m is not None else float('nan')):.1%} vs prior "
                    f"{H15A_PRIOR[0]:.0%}-{H15A_PRIOR[1]:.0%}); cap-minority "
                    f"{'CONFIRMED' if cap_ok else 'REFUTED'} (at the {CAP}-cap on "
                    f"{(at_cap if at_cap is not None else float('nan')):.1%} of days, threshold "
                    f"{CAP_MINORITY:.0%}); 0 open on {dep['share_days_zero_open']:.1%} of days (gate off); "
                    f"binding constraint = cap x notional-per-slot, not the 1% rule"),
    }


def worst_trade_pct(book: dict, lo: date, hi: date) -> dict:
    """Worst single trade as a fraction of sleeve equity at entry: for every
    trade entered in [lo, hi], pnl = qty * (exit - fill) (gross of
    commissions and the tiered slippage) divided by the book's sleeve_eq at
    the CLOSE of the entry date (daily[entry_date]['sleeve_eq']); the
    minimum (most negative) is reported with its trade."""
    los, his = lo.isoformat(), hi.isoformat()
    worst = None
    for t in book["trades"]:
        if not (los <= t["entry_date"] <= his):
            continue
        eq = book["daily"][t["entry_date"]]["sleeve_eq"]
        if eq <= 0:
            continue
        frac = t["qty"] * (t["exit"] - t["fill"]) / eq
        if worst is None or frac < worst["pct_of_sleeve_eq"]:
            worst = {"pct_of_sleeve_eq": frac, "symbol": t["symbol"], "entry_date": t["entry_date"],
                     "exit_date": t["exit_date"], "qty": t["qty"], "fill": t["fill"], "exit": t["exit"],
                     "sleeve_eq_at_entry": eq}
    return worst or {"pct_of_sleeve_eq": None}


def _uw_days(curve: list, lo: date, hi: date) -> int:
    seg = [(d, v) for d, v in curve if lo <= d <= hi]
    return int(longest_underwater(seg).get("days_calendar", 0)) if seg else 0


def arm_metrics(book: dict, windows: dict[str, tuple[date, date]]) -> dict:
    out = {"book": {}, "sleeve": {}, "deployment": {}, "worst_trade": {}}
    for w, (lo, hi) in windows.items():
        b = seg_stats(book["curve"], lo, hi)
        s = seg_stats(book["sleeve_curve"], lo, hi)
        if b:
            b["longest_underwater_days"] = _uw_days(book["curve"], lo, hi)
        if s:
            s["longest_underwater_days"] = _uw_days(book["sleeve_curve"], lo, hi)
        out["book"][w] = b
        out["sleeve"][w] = s
        out["deployment"][w] = deployment_stats(book["daily"], lo, hi)
        out["worst_trade"][w] = worst_trade_pct(book, lo, hi)
    return out


# --- decision rule --------------------------------------------------------------------

def decide(bonf_lo: float | None, max_dd_arm: float, max_dd_s0: float,
           sharpe_delta_5y: float | None, cagr_delta_full: float | None = None) -> dict:
    """The contract's three-clause rule on plain inputs: PROPOSE only when
    (1) the Bonferroni interval of the full-window book Sharpe delta vs S0
    lies entirely above zero, (2) the arm's book max DD is no more than
    MAXDD_SLACK worse than S0's, (3) the 5y-window Sharpe delta is positive.
    A positive CAGR delta with a wider drawdown is tagged leverage."""
    c1 = bonf_lo is not None and bonf_lo > 0
    c2 = max_dd_arm <= max_dd_s0 + MAXDD_SLACK
    c3 = sharpe_delta_5y is not None and not math.isnan(sharpe_delta_5y) and sharpe_delta_5y > 0
    reasons = {
        "bonferroni_interval_above_zero": bool(c1),
        "max_dd_within_2pp_of_s0": bool(c2),
        "sharpe_delta_sign_holds_5y": bool(c3),
    }
    leverage = bool(cagr_delta_full is not None and cagr_delta_full > 0 and max_dd_arm > max_dd_s0)
    return {"decision": "PROPOSE" if (c1 and c2 and c3) else "NULL", "reasons": reasons,
            "leverage_not_improvement": leverage}


# --- the study -----------------------------------------------------------------------

def run_study(fire_rows: list[dict], mkt: dict, tiers: dict, *, bil: dict[date, float],
              spy_px: dict[date, float | None], draws: int = STUDY_DRAWS, seed: int = STUDY_SEED,
              cache_basis: dict | None = None, bars_info: dict | None = None,
              mirror_stored_end: float | None = None, bases: tuple[float, ...] = BASES) -> dict:
    if bil is None or spy_px is None:
        raise SystemExit("the study needs the BIL yield series and SPY prices (the mirror's primary "
                         "blend3070_t2_carry inputs) — nothing written")
    calendar = mkt["calendar"]
    windows = window_bounds(calendar)
    t0 = time.time()
    print("sizing: grading the lag-2 taken set once ...", flush=True)
    taken, grading = taken_rows(fire_rows, mkt, tiers)
    print(f"sizing: taken {len(taken)} (graded {grading['n_graded']}, gated {grading['n_gated']}, "
          f"skipped at cap {grading['skipped_at_cap']})", flush=True)
    occ = occupancy_basis(taken)
    print(f"sizing: occupancy basis: {occ['entries_with_slot_held_unfilled']}/{occ['n_entries']} entries "
          f"({occ['share_entries_with_slot_held_unfilled']:.1%}) sit on a day with >= 1 slot held but "
          f"unfilled (max {occ['max_slot_held_unfilled']})", flush=True)

    arms_out: dict[str, dict] = {}
    for base in bases:
        bkey = f"{int(base)}"
        books: dict[str, dict] = {}
        per_arm: dict[str, dict] = {}
        for name, kw, desc in ARMS:
            cfg = arm_cfg(kw, base)
            bk = run_executor_book(taken, mkt, cfg, cash_yield=bil, spy_px=spy_px)
            books[name] = bk
            m = arm_metrics(bk, windows)
            m["cfg_label"] = cfg.label
            m["cfg"] = bk["meta"]["cfg"]
            m["desc"] = desc
            m["n_taken"] = bk["meta"]["n_taken"]
            m["skipped_zero_qty"] = bk["meta"]["skipped_zero_qty"]
            m["commissions_paid"] = bk["meta"]["commissions_paid"]
            m["carry_usd"] = bk["meta"]["carry_usd"]
            per_arm[name] = m
            f = m["book"]["full"]
            d = m["deployment"]["full"]
            print(f"sizing: base ${base:>9,.0f} arm {name} end ${f['end_value']:>12,.0f} "
                  f"CAGR {f['cagr']:+.2%} maxDD {f['max_dd']:.1%} Sharpe {f['sharpe']:.3f} "
                  f"deployed {d['deployed_mean']:.1%} at-cap {d['share_days_at_cap']:.1%} "
                  f"zero {d['share_days_zero_open']:.1%} carry ${m['carry_usd']:,.0f} entries {d['entries']} "
                  f"skipped0 {d['skipped_zero_qty']}  [{time.time() - t0:.0f}s]", flush=True)

        # primary statistic: paired bootstrap of book-level daily returns vs S0 (full window)
        lo, hi = windows["full"]
        r0 = daily_rets(books[ANCHOR]["curve"], lo, hi)
        s0 = per_arm[ANCHOR]
        for name, _kw, _desc in ARMS:
            m = per_arm[name]
            if name == ANCHOR:
                m["vs_s0"] = None
                m["decision"] = {"decision": "ANCHOR", "reasons": {}, "leverage_not_improvement": False}
                continue
            ra = daily_rets(books[name]["curve"], lo, hi)
            boot = paired_sharpe_bootstrap(ra, r0, draws=draws, mean_block=BOOT_MEAN_BLOCK,
                                           seed=seed, family=FAMILY)
            sens = paired_sharpe_bootstrap(ra, r0, draws=SENS_DRAWS, mean_block=SENS_BLOCK,
                                           seed=seed, family=FAMILY)
            deltas = {}
            for w in windows:
                a, b = m["book"].get(w) or {}, s0["book"].get(w) or {}
                deltas[w] = {k: (a[k] - b[k]) if (a and b) else None
                             for k in ("cagr", "max_dd", "sharpe", "end_value")}
            sd5 = deltas.get("5y", {}).get("sharpe")
            m["vs_s0"] = {"deltas": deltas, "sharpe_delta_bootstrap": boot,
                          "sharpe_delta_bootstrap_block63": sens,
                          "sharpe_delta_5y_sign": (None if sd5 is None else
                                                   ("+" if sd5 > 0 else "-" if sd5 < 0 else "0"))}
            m["decision"] = decide(boot.get("bonf_lo"), m["book"]["full"]["max_dd"],
                                   s0["book"]["full"]["max_dd"], sd5, deltas["full"]["cagr"])
            print(f"sizing: base ${base:>9,.0f} arm {name} vs S0: Sharpe delta p50 {boot['p50']:+.3f} "
                  f"95% [{boot['p2_5']:+.3f}, {boot['p97_5']:+.3f}] bonf5 [{boot['bonf_lo']:+.3f}, "
                  f"{boot['bonf_hi']:+.3f}] blk63 bonf5 lo {sens['bonf_lo']:+.3f}; 5y sign "
                  f"{m['vs_s0']['sharpe_delta_5y_sign']}; {m['decision']['decision']}  "
                  f"[{time.time() - t0:.0f}s]", flush=True)
        arms_out[bkey] = per_arm

    # reduction check: S0 at the replay base IS the mirror's primary blend book
    s0_end = arms_out[f"{int(START_EQUITY)}"][ANCHOR]["book"]["full"]["end_value"]
    reduction = {"variant": MIRROR_VARIANT, "stored_mirror_end": mirror_stored_end, "got": s0_end,
                 "abs_diff": (abs(s0_end - mirror_stored_end) if mirror_stored_end is not None else None),
                 "tolerance_usd": REDUCTION_TOL_USD,
                 "pass": (mirror_stored_end is not None and abs(s0_end - mirror_stored_end) <= REDUCTION_TOL_USD)}
    if mirror_stored_end is not None and not reduction["pass"]:
        raise SystemExit(f"REDUCTION FAILED: S0 at ${START_EQUITY:,.0f} ends ${s0_end:,.2f} vs the stored "
                         f"{MIRROR_VARIANT} ${mirror_stored_end:,.2f} — nothing written")

    decisions = {bkey: {name: per_arm[name]["decision"]["decision"] for name, _, _ in ARMS if name != ANCHOR}
                 for bkey, per_arm in arms_out.items()}
    hypotheses = {"H15a": {bkey: h15a_verdict(per_arm[ANCHOR]["deployment"]["full"])
                           for bkey, per_arm in arms_out.items()}}
    for bkey, h in hypotheses["H15a"].items():
        print(f"sizing: H15a @ ${int(bkey):,}: {h['verdict']}", flush=True)
    return {
        "generated": date.today().isoformat(),
        "script": SCRIPT,
        "contract": "docs/VARIANTS_PREREGISTRATION_R10_SIZING.md",
        "period": [calendar[0].isoformat(), calendar[-1].isoformat()],
        "windows": {w: [lo.isoformat(), hi.isoformat()] for w, (lo, hi) in windows.items()},
        "protocol": {
            "anchor": ANCHOR, "bases": list(bases), "cap": CAP, "near_cap_open": NEAR_CAP,
            "draws": draws, "seed": seed, "mean_block_days": BOOT_MEAN_BLOCK,
            "sensitivity": {"draws": SENS_DRAWS, "mean_block_days": SENS_BLOCK},
            "bonferroni_family": FAMILY, "max_dd_slack": MAXDD_SLACK,
            "decision_rule": "PROPOSE iff bonf_lo(full book Sharpe delta vs S0) > 0 AND book max DD <= "
                             "S0 + 2 pp AND 5y Sharpe delta > 0; else NULL",
            "arms": {name: {"kwargs": kw, "desc": desc} for name, kw, desc in ARMS},
            "cache_basis": cache_basis or {"lane": "unknown (no backtest_bars_basis.json sidecar)"},
            "bars": bars_info,
            "taken_set": grading,
            "occupancy_basis": occ,
            "h15a_scoring": {"prior": list(H15A_PRIOR), "cap_minority_threshold": CAP_MINORITY},
            "runtime_s": round(time.time() - t0, 1),
        },
        "reduction_check": reduction,
        "arms": arms_out,
        "decisions": decisions,
        "hypotheses": hypotheses,
        "honesty": HONESTY,
    }


def print_table(res: dict) -> None:
    for bkey, arms in res["arms"].items():
        print(f"\n== base ${int(bkey):,} | full {res['windows']['full'][0]} -> {res['windows']['full'][1]} ==")
        print(f"{'arm':4s} {'book end':>11s} {'CAGR':>7s} {'maxDD':>6s} {'Sharpe':>6s} {'uw d':>5s} | "
              f"{'slv CAGR':>8s} {'slv DD':>6s} {'slv Sh':>6s} {'dep':>6s} {'p10':>5s} {'p50':>5s} {'p90':>5s} "
              f"{'>=9':>5s} {'cap':>5s} {'zero':>5s} {'carry$':>7s} {'ent':>4s} {'sk0':>3s} {'worst':>6s} | "
              f"{'dSh p50':>7s} {'bonf5 lo':>8s} "
              f"{'b63 lo':>7s} {'5y':>2s} {'dDD':>6s} decision")
        for name, m in arms.items():
            b, s, d, w = m["book"]["full"], m["sleeve"]["full"], m["deployment"]["full"], m["worst_trade"]["full"]
            v = m["vs_s0"]
            if v:
                boot, sens = v["sharpe_delta_bootstrap"], v["sharpe_delta_bootstrap_block63"]
                tail = (f"{boot['p50']:>+7.3f} {boot['bonf_lo']:>+8.3f} {sens['bonf_lo']:>+7.3f} "
                        f"{v['sharpe_delta_5y_sign']:>2s} {v['deltas']['full']['max_dd']:>+6.1%} "
                        f"{m['decision']['decision']}"
                        + (" (leverage)" if m["decision"]["leverage_not_improvement"] else ""))
            else:
                tail = f"{'-':>7s} {'-':>8s} {'-':>7s} {'-':>2s} {'-':>6s} ANCHOR"
            wt = w.get("pct_of_sleeve_eq")
            print(f"{name:4s} ${b['end_value']:>10,.0f} {b['cagr']:>+7.2%} {b['max_dd']:>6.1%} {b['sharpe']:>6.3f} "
                  f"{b['longest_underwater_days']:>5d} | {s['cagr']:>+8.2%} {s['max_dd']:>6.1%} {s['sharpe']:>6.3f} "
                  f"{d['deployed_mean']:>6.1%} {d['deployed_p10']:>5.0%} {d['deployed_p50']:>5.0%} "
                  f"{d['deployed_p90']:>5.0%} {d['share_days_ge9_open']:>5.1%} {d['share_days_at_cap']:>5.1%} "
                  f"{d['share_days_zero_open']:>5.1%} {m['carry_usd']:>7,.0f} {d['entries']:>4d} "
                  f"{d['skipped_zero_qty']:>3d} {(wt if wt is not None else float('nan')):>+6.1%} | {tail}")
        for wname in ("5y", "2y"):
            print(f"  -- {wname}: " + "  ".join(
                f"{n}: Sh {m['book'][wname]['sharpe']:.3f} DD {m['book'][wname]['max_dd']:.1%}"
                for n, m in arms.items()))
    r = res["reduction_check"]
    print(f"\nreduction: S0 @ ${int(START_EQUITY):,} ends ${r['got']:,.2f} vs stored {r['variant']} "
          f"{r['stored_mirror_end']} (|diff| {r['abs_diff']}, pass={r['pass']})")
    print(f"decisions: {json.dumps(res['decisions'])}")
    for bkey, h in res.get("hypotheses", {}).get("H15a", {}).items():
        print(f"H15a @ ${int(bkey):,}: {h['verdict']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=RESULTS)
    ap.add_argument("--draws", type=int, default=STUDY_DRAWS)
    ap.add_argument("--seed", type=int, default=STUDY_SEED)
    args = ap.parse_args(argv)
    inp = load_inputs(refresh_bars_if_missing=True)
    res = run_study(inp["fire_rows"], inp["mkt"], inp["tiers"], bil=inp["bil"], spy_px=inp["spy_px"],
                    draws=args.draws, seed=args.seed, cache_basis=inp.get("cache_basis"),
                    bars_info=inp.get("bars_info"), mirror_stored_end=stored_mirror_end(MIRROR_VARIANT))
    write_results(res, args.out)
    print_table(res)
    print(f"\nResults written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
