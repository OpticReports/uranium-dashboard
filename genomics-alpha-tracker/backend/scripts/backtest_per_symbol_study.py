"""Round 11 — one open call per symbol: does refusing a repeat entry into a
name already held, and handing the cap slot to the next gated fire in a
different name, improve the book? Contract:
docs/VARIANTS_PREREGISTRATION_R11_PER_SYMBOL.md, committed before this code.
Everything is IMPORTED from the executor mirror, the round-9 ablation and the
round-10 sizing study; no engine is re-implemented here.

Arms (executor path: T+2 fill, IBKR costs, BIL carry, XBI gate, cap 10, risk
1%, 30/70 with the 5pp band, LIVE base $120,000): A0 no per-symbol limit (the
live rule = round-10 S0), U1 at most 1 open call per symbol, U2 at most 2.
"Open" = select_capped_exec's own slot occupancy (gate date .. exit date).
The $100,000 base runs A0 only, as the reduction check against the stored
mirror blend3070_t2_carry.

Metrics: book CAGR / Sharpe / max DD / longest underwater (full, 5y, 2y);
sleeve CAGR / max DD / Sharpe TIME-WEIGHTED (band transfers to/from the core
removed as external flows; the bucket incl. transfers is kept, relabelled) /
mean deployed / days at cap; largest single-name share
of sleeve equity per open day (median / p90 / max); entries taken, refused as
repeats, skipped at cap; mean distinct names per open day; mean r_net of the
taken trades. Primary statistic: paired stationary block bootstrap of the
full-window book Sharpe delta vs A0 (10,000 draws, mean block 21, seed
20261006, Bonferroni family 2) plus its p5 (one-sided 95%) and the 63-day
block sensitivity. Two-tier decision rule per the contract. Reported, not
decided on: the per-symbol exit-date boundary (refusals that live's same-cycle
release would have let in; U1/U2 re-run with that release) and same-gate-date
sibling refusals (the live port's entry_intents requirement).

Usage:  python -m scripts.backtest_per_symbol_study [--out PATH] [--draws N] [--seed S]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backtest_executor_mirror import (  # noqa: E402
    BOOT_MEAN_BLOCK, CAP, DATA, EXEC_T2, build_exec_rows, gate_rows, load_inputs, run_executor_book,
    select_capped_exec, window_bounds, write_results,
)
from scripts.backtest_exit_ablation import (  # noqa: E402
    daily_rets, paired_sharpe_bootstrap, stored_mirror_end,
)
from scripts.backtest_sizing_study import _pct, _uw_days, arm_cfg, arm_metrics, taken_rows  # noqa: E402
from scripts.backtest_variants_10y import START_EQUITY, seg_stats  # noqa: E402

RESULTS = DATA / "backtest_per_symbol_study_results.json"
SCRIPT = "scripts/backtest_per_symbol_study.py"
CONTRACT = "docs/VARIANTS_PREREGISTRATION_R11_PER_SYMBOL.md"
STUDY_SEED = 20261006
STUDY_DRAWS = 10000
SENS_BLOCK = 63
FAMILY = 2                        # Bonferroni family: U1, U2
ONE_SIDED_FAMILY = 0.5            # paired_sharpe_bootstrap tail = 100*(0.05/0.5)/2 = 5 -> bonf_lo IS the p5
ANCHOR = "A0"
MIRROR_VARIANT = "blend3070_t2_carry"
REDUCTION_TOL_USD = 1.0
LIVE_BASE = 120_000.0
TIE_TOL = 1e-12                   # point Sharpe deltas closer than this are a tie (float guard only)

# contract decision rule, fixed in the pre-registration
T1_MAXDD_SLACK = 0.02             # improvement: book max DD no more than 2 pp worse than A0
T2_P5_FLOOR = -0.10               # risk control: one-sided 95% lower bound of the Sharpe delta >= -0.10
T2_MAXDD_SLACK = 0.005            # risk control: book max DD no worse than A0 + 0.5 pp
T2_SH5Y_FLOOR = -0.05             # risk control: 5y Sharpe delta >= -0.05
T2_P90_SHARE_CUT = 0.10           # risk control: p90 largest-name share >= 10 pp below A0's

ARMS: list[tuple[str, int | None, str]] = [
    ("A0", None, "anchor: the live rule, no per-symbol limit (= round-10 S0)"),
    ("U1", 1, "at most 1 open call per symbol"),
    ("U2", 2, "at most 2 open calls per symbol"),
]

# the scratch measurement that motivated the round (contract 'Question'); A0 at $120k must reproduce it
MOTIVATING = {
    "share_open_days_name_held_2plus": (0.87, 0.005),
    "n_entries": (674, 0),
    "entries_with_same_name_held_on_entry_day": (258, 0),
    "largest_name_share_p50": (0.20, 0.005),
    "largest_name_share_p90": (0.40, 0.005),
    "largest_name_share_max": (0.64, 0.005),
    "first_entries_strict_n": (440, 0),
    "repeat_entries_strict_n": (234, 0),
    "first_entries_strict_mean_r_net": (0.20, 0.005),
    "repeat_entries_strict_mean_r_net": (0.20, 0.005),
}

HONESTY = [
    "In-sample over the same 10.6 years as every prior round (2016-01-04..2026-08-19); a per-symbol "
    "winner here is a hypothesis, not a result. Never present these in-sample CAGRs as a forecast.",
    "Survivor-shaped fire set (today's watchlist); the fire rate is taken as given; the tracker's "
    "repeat-fire behaviour is whatever it was historically.",
    "Costs: IBKR fixed schedule + tiered slippage; BIL carry is the realised BIL total return.",
    "A pass changes the executor's planner only (the tracker keeps publishing every gated fire); the "
    "shadow grader and H14 are unaffected.",
    "MEASUREMENT BASIS: daily mark-to-market on adjusted closes; max DD on the daily curve; CAGR "
    "calendar-day (365.25); Sharpe sqrt(252), rf = 0; 5y/2y are SLICES of the full curve, not restarted "
    "books.",
    "Paired Sharpe-delta intervals are CONDITIONAL on this single in-sample path: percentile, not "
    "bias-corrected; 21-day blocks understate regime persistence (63-day sensitivity reported). p5 is "
    "the 5th percentile of the SAME draws (one-sided 95% lower bound).",
    "Max DD and the concentration p90 carry no interval: single-path point comparisons.",
    "Per-symbol 'open' in the SELECTION uses the cap's occupancy (gate date .. exit date inclusive); "
    "the CONCENTRATION metrics use the book's held definition (entry_date <= d < exit_date) and the "
    "symbol's MTM notional / sleeve equity at the close, so a U1 name can still show one position.",
    "Selection counts: the cap is checked first; refused_repeat counts only repeats that would "
    "otherwise have taken a slot (a repeat arriving at a full cap is skipped_at_cap).",
    "Sleeve CAGR / max DD / Sharpe are TIME-WEIGHTED: each day's band transfer to/from the core "
    "(run_executor_book's sleeve_band_flow, incl. the BIL fee on a sleeve->core move) is an external "
    "flow, r_t = (sleeve_eq_t - flow_t) / sleeve_eq_{t-1} - 1. The sleeve BUCKET incl. transfers "
    "(round 10's convention) is kept as 'sleeve_bucket_incl_transfers' and is NOT a return. The "
    "decision rule is book-level.",
    "Sanity reproduction: the motivating '258 entries into an open name' counts same-day co-entries "
    "both ways (entry_date <= d < exit_date of ANY other trade); the first/repeat R split (440/234) "
    "uses strictly-earlier entries. Both definitions are recorded as the scratch computed them.",
    "Tie-break per contract: both arms qualifying -> higher full-window point Sharpe delta, tie -> U1; "
    "the comparison is across tiers too, as written.",
]


# --- selection ----------------------------------------------------------------------

def gated_rows(fire_rows: list[dict], mkt: dict, tiers: dict) -> tuple[list[dict], dict]:
    """The mirror's lag-2 path up to the cap: grade under EXEC_T2, gate on the
    gate date (round 10's taken_rows minus the cap step, done once)."""
    rows, meta = build_exec_rows(fire_rows, mkt, tiers, EXEC_T2)
    gated = gate_rows(rows, mkt["xbi_above_prior"][200])
    g = {k: v for k, v in meta.items() if isinstance(v, (int, float))}
    g.update({"n_graded": len(rows), "n_gated": len(gated)})
    return gated, g


def select_arm(gated: list[dict], k: int | None, release: str = "cap") -> tuple[list[dict], dict]:
    log: list = []
    taken, at_cap, refused = select_capped_exec(gated, CAP, per_symbol_max=k, return_detail=True,
                                                symbol_release=release, refusal_log=log)
    return taken, {"per_symbol_max": k, "symbol_release": release, "n_gated": len(gated),
                   "entries_taken": len(taken), "refused_repeat": refused, "skipped_at_cap": at_cap,
                   **refusal_breakdown(log, k)}


def refusal_breakdown(log: list, k: int | None) -> dict:
    """From select_capped_exec's refusal_log: refusals that hinge on the exit-date
    boundary (fewer than k blockers exit AFTER the row's gate date, so live's
    same-cycle release of an exiting / stop-filled call would have let the row in;
    counter-agent A1) and refusals where a blocker shares the row's gate date
    (a same-cycle sibling the live port must count via entry_intents; A2)."""
    if k is None:
        return {"refused_exit_date_boundary_only": 0, "refused_by_same_gate_date_sibling": 0}
    g = lambda r: r.get("gate_date", r["entry_date"])  # noqa: E731
    return {
        "refused_exit_date_boundary_only": sum(1 for r, bl in log if sum(1 for b in bl if b["exit_date"] > g(r)) < k),
        "refused_by_same_gate_date_sibling": sum(1 for r, bl in log if any(g(b) == g(r) for b in bl)),
    }


def same_gate_dup_groups(gated: list[dict]) -> int:
    """(symbol, gate_date) groups with more than one gated fire (multi-flag)."""
    c: dict[tuple[str, str], int] = {}
    for r in gated:
        key = (r["symbol"], r.get("gate_date", r["entry_date"]))
        c[key] = c.get(key, 0) + 1
    return sum(1 for v in c.values() if v > 1)


# --- sleeve, time-weighted --------------------------------------------------------------

def sleeve_twr_curve(book: dict) -> list[tuple[date, float]]:
    """The sleeve's time-weighted curve, in dollars from the sleeve's first
    close: v_t = v_{t-1} * (sleeve_eq_t - flow_t) / sleeve_eq_{t-1}, where
    flow_t is the day's band transfer into the sleeve (daily sleeve_band_flow).
    Band transfers are external flows, so this is the sleeve's own return path;
    with no transfers it equals sleeve_curve."""
    sc, daily = book["sleeve_curve"], book["daily"]
    out = [sc[0]]
    for i in range(1, len(sc)):
        d, post = sc[i]
        prev = sc[i - 1][1]
        pre = post - daily[d.isoformat()]["sleeve_band_flow"]
        out.append((d, out[-1][1] * (pre / prev if prev > 0 else 1.0)))
    return out


def sleeve_flow_summary(book: dict) -> dict:
    fl = [e["sleeve_band_flow"] for e in book["daily"].values() if abs(e["sleeve_band_flow"]) > 1e-9]
    return {"n_flow_days": len(fl), "n_rebalances": book["meta"]["rebalances"],
            "net_flow_into_sleeve_usd": sum(fl), "gross_in_usd": sum(f for f in fl if f > 0),
            "gross_out_usd": -sum(f for f in fl if f < 0)}


def sleeve_twr_metrics(twr: list, windows: dict) -> dict:
    out = {}
    for w, (lo, hi) in windows.items():
        st = seg_stats(twr, lo, hi)
        if st:
            st["longest_underwater_days"] = _uw_days(twr, lo, hi)
        out[w] = st
    return out


# --- concentration ------------------------------------------------------------------

def held_by_day(trades: list[dict], calendar: list[date]) -> dict[str, dict[str, list[dict]]]:
    """Per calendar day, the book's held trades by symbol: a trade is held on d
    when entry_date <= d < exit_date (the book's open list after the day's
    exits). Days with nothing held are omitted (open days only)."""
    out: dict[str, dict[str, list[dict]]] = {}
    for d in calendar:
        ds = d.isoformat()
        by: dict[str, list[dict]] = {}
        for t in trades:
            if t["entry_date"] <= ds < t["exit_date"]:
                by.setdefault(t["symbol"], []).append(t)
        if by:
            out[ds] = by
    return out


def largest_name_series(book: dict, px: dict, calendar: list[date],
                        held: dict | None = None) -> list[tuple[date, float, int]]:
    """Per open day: (date, largest single-name share of sleeve equity, distinct
    names held). Share = sum over the symbol's held trades of qty * adjusted
    close / the book's sleeve_eq at that close (days with sleeve_eq <= 0
    skipped)."""
    held = held if held is not None else held_by_day(book["trades"], calendar)
    out = []
    for d in calendar:
        by = held.get(d.isoformat())
        if not by:
            continue
        eq = book["daily"][d.isoformat()]["sleeve_eq"]
        if eq <= 0:
            continue
        top = max(sum(t["qty"] * px[s][d] for t in ts) for s, ts in by.items())
        out.append((d, top / eq, len(by)))
    return out


def concentration_stats(book: dict, px: dict, calendar: list[date]) -> dict:
    held = held_by_day(book["trades"], calendar)
    ser = largest_name_series(book, px, calendar, held)
    shares = [s for _, s, _ in ser]
    return {
        "basis": "book held (entry_date <= d < exit_date); share = symbol MTM / sleeve_eq at the close; "
                 "open days = >= 1 held",
        "n_open_days": len(ser),
        "largest_name_share_p50": _pct(shares, 50) if shares else None,
        "largest_name_share_p90": _pct(shares, 90) if shares else None,
        "largest_name_share_max": max(shares) if shares else None,
        "mean_distinct_names_per_open_day": statistics.fmean([n for _, _, n in ser]) if ser else None,
        "max_same_name_held": max((len(ts) for by in held.values() for ts in by.values()), default=0),
    }


def sanity_reproduction(book: dict, px: dict, calendar: list[date]) -> dict:
    """The contract's motivating scratch numbers, recomputed from A0's book
    trades at $120k, each against its stated value at its stated rounding."""
    tr = book["trades"]
    held = held_by_day(tr, calendar)
    conc = concentration_stats(book, px, calendar)
    multi = sum(1 for by in held.values() if any(len(ts) >= 2 for ts in by.values()))
    into_open = sum(1 for t in tr if any(u is not t and u["symbol"] == t["symbol"]
                                         and u["entry_date"] <= t["entry_date"] < u["exit_date"] for u in tr))
    rep = [t for t in tr if any(u["symbol"] == t["symbol"] and u["entry_date"] < t["entry_date"] < u["exit_date"]
                                for u in tr)]
    rep_ids = {id(t) for t in rep}
    first = [t for t in tr if id(t) not in rep_ids]
    got = {
        "share_open_days_name_held_2plus": multi / len(held) if held else None,
        "n_entries": len(tr),
        "entries_with_same_name_held_on_entry_day": into_open,
        "largest_name_share_p50": conc["largest_name_share_p50"],
        "largest_name_share_p90": conc["largest_name_share_p90"],
        "largest_name_share_max": conc["largest_name_share_max"],
        "first_entries_strict_n": len(first),
        "repeat_entries_strict_n": len(rep),
        "first_entries_strict_mean_r_net": statistics.fmean([t["r_net"] for t in first]) if first else None,
        "repeat_entries_strict_mean_r_net": statistics.fmean([t["r_net"] for t in rep]) if rep else None,
    }
    checks = {k: {"stated": v, "tol": tol, "got": got[k],
                  "pass": got[k] is not None and abs(got[k] - v) <= tol + 1e-12}
              for k, (v, tol) in MOTIVATING.items()}
    return {"base": LIVE_BASE, "checks": checks, "pass": all(c["pass"] for c in checks.values())}


# --- decision rule --------------------------------------------------------------------

def decide_arm(bonf_lo: float | None, p5: float | None, max_dd_arm: float, max_dd_a0: float,
               sharpe_delta_5y: float | None, p90_share_arm: float | None,
               p90_share_a0: float | None) -> dict:
    """The contract's two tiers on plain inputs; an arm is proposed under the
    FIRST tier it meets. (1) improvement: Bonferroni-2 lower bound of the
    Sharpe delta > 0, max DD <= A0 + 2 pp, 5y Sharpe delta > 0. (2) risk
    control: p5 of the Sharpe delta >= -0.10, max DD <= A0 + 0.5 pp, 5y Sharpe
    delta >= -0.05, p90 largest-name share <= A0's - 10 pp."""
    ok = lambda x: x is not None and x == x  # noqa: E731  (not None, not NaN)
    t1 = {
        "bonf2_lo_gt_0": bool(ok(bonf_lo) and bonf_lo > 0),
        "max_dd_within_2pp_of_a0": bool(max_dd_arm <= max_dd_a0 + T1_MAXDD_SLACK),
        "sharpe_delta_5y_gt_0": bool(ok(sharpe_delta_5y) and sharpe_delta_5y > 0),
    }
    t2 = {
        "p5_ge_minus_0.10": bool(ok(p5) and p5 >= T2_P5_FLOOR),
        "max_dd_within_0.5pp_of_a0": bool(max_dd_arm <= max_dd_a0 + T2_MAXDD_SLACK),
        "sharpe_delta_5y_ge_minus_0.05": bool(ok(sharpe_delta_5y) and sharpe_delta_5y >= T2_SH5Y_FLOOR),
        "p90_share_10pp_below_a0": bool(ok(p90_share_arm) and ok(p90_share_a0)
                                        and p90_share_arm <= p90_share_a0 - T2_P90_SHARE_CUT),
    }
    tier = "improvement" if all(t1.values()) else ("risk_control" if all(t2.values()) else None)
    return {"decision": "PROPOSE" if tier else "NULL", "tier": tier,
            "reasons": {"tier1_improvement": t1, "tier2_risk_control": t2}}


def choose(candidates: list[tuple[str, str, float | None]]) -> dict:
    """candidates in contract order (U1 first): (name, decision, full-window
    point Sharpe delta). None qualifying -> NULL; one -> it; several -> the
    higher point Sharpe delta, a tie -> the earlier (simpler) arm."""
    q = [(n, sd) for n, dec, sd in candidates if dec == "PROPOSE"]
    if not q:
        return {"proposal": None, "rule": "no arm met either tier -> NULL"}
    if len(q) == 1:
        return {"proposal": q[0][0], "rule": "single qualifying arm"}
    best_n, best_sd = q[0]
    rule = "both qualify: higher point Sharpe delta"
    for n, sd in q[1:]:
        if abs(sd - best_sd) <= TIE_TOL:
            rule = f"both qualify: point Sharpe delta tie -> {best_n} (simpler)"
        elif sd > best_sd:
            best_n, best_sd = n, sd
    return {"proposal": best_n, "rule": rule}


# --- the study -----------------------------------------------------------------------

def _boot(ra: list[float], r0: list[float], *, draws: int, block: int, seed: int) -> dict:
    """Bonferroni-2 interval plus the one-sided p5/p95 from IDENTICAL draws
    (same seed, block and N -> the same sorted diffs; ONE_SIDED_FAMILY puts
    paired_sharpe_bootstrap's bonf tails at exactly 5 / 95)."""
    b = paired_sharpe_bootstrap(ra, r0, draws=draws, mean_block=block, seed=seed, family=FAMILY)
    one = paired_sharpe_bootstrap(ra, r0, draws=draws, mean_block=block, seed=seed, family=ONE_SIDED_FAMILY)
    assert one["p50"] == b["p50"] and one["p2_5"] == b["p2_5"], "identical draws expected"
    b["p5"], b["p95"] = one["bonf_lo"], one["bonf_hi"]
    return b


LIVE_PORT_SPEC = (
    "ibkr-executor blend.py step(): held_by_symbol(sym) = positions in sym NOT in `exiting` + pending_entries "
    "in sym + entry_intents in sym ALREADY PLANNED THIS CYCLE; refuse an intent when held_by_symbol >= k, "
    "checked AFTER the cap check (a refusal consumes no slot), walking the payload in (gate_date, entry_date, "
    "symbol, flag) order. Required gate test: two same-symbol fires (different flags) in ONE payload -> k=1 "
    "plans the first only (the replay refuses same-gate-date siblings; counter-agent A2). Live frees an "
    "exiting / stop-filled call in the same cycle; the replay holds it through its exit date (see "
    "sensitivity_live_release) — pin one semantics in the port and its test.")


def live_release_sensitivity(gated: list[dict], k: int, mkt: dict, windows: dict, a0: dict, r0: list[float], *,
                             bil: dict, spy_px: dict, px: dict, draws: int, seed: int) -> dict:
    """The arm re-run with symbol_release='live' (a same-symbol call stops
    counting on its exit date), scored on the contract's clauses against the
    SAME A0. Reported only; the decision stays on the pre-registered rule."""
    taken, sel = select_arm(gated, k, release="live")
    bk = run_executor_book(taken, mkt, arm_cfg({}, LIVE_BASE), cash_yield=bil, spy_px=spy_px)
    full, y5 = seg_stats(bk["curve"], *windows["full"]), seg_stats(bk["curve"], *windows["5y"])
    conc = concentration_stats(bk, px, mkt["calendar"])
    boot = _boot(daily_rets(bk["curve"], *windows["full"]), r0, draws=draws, block=BOOT_MEAN_BLOCK, seed=seed)
    sd5 = y5["sharpe"] - a0["book"]["5y"]["sharpe"]
    return {
        "symbol_release": "live", "selection": sel, "book_full": full, "book_5y": y5,
        "point_sharpe_delta_full": full["sharpe"] - a0["book"]["full"]["sharpe"],
        "sharpe_delta_5y": sd5, "max_dd_delta": full["max_dd"] - a0["book"]["full"]["max_dd"],
        "largest_name_share_p90": conc["largest_name_share_p90"],
        "p90_share_delta": conc["largest_name_share_p90"] - a0["concentration"]["largest_name_share_p90"],
        "sharpe_delta_bootstrap": boot,
        "decision": decide_arm(boot.get("bonf_lo"), boot.get("p5"), full["max_dd"], a0["book"]["full"]["max_dd"],
                               sd5, conc["largest_name_share_p90"], a0["concentration"]["largest_name_share_p90"]),
    }


def computed_honesty(per_arm: dict, grading: dict) -> list[str]:
    """Honesty lines whose numbers come from THIS run (never hand-typed)."""
    out = []
    sv = {n: m["sleeve"]["full"] for n, m in per_arm.items()}
    bk = {n: m["sleeve_bucket_incl_transfers"]["full"] for n, m in per_arm.items()}
    out.append("Sleeve, time-weighted vs bucket incl. transfers (full window): " + "; ".join(
        f"{n} TWR CAGR {sv[n]['cagr']:.1%} / DD {sv[n]['max_dd']:.1%} / Sh {sv[n]['sharpe']:.3f} vs bucket "
        f"{bk[n]['cagr']:.1%} / {bk[n]['max_dd']:.1%} (net transfer in ${m['sleeve_flows']['net_flow_into_sleeve_usd']:+,.0f} "
        f"over {m['sleeve_flows']['n_flow_days']} days)" for n, m in per_arm.items())
        + ". The bucket figures are NOT returns (counter-agent B1).")
    for n, m in per_arm.items():
        if n == ANCHOR:
            continue
        sb = m["vs_a0"]["sleeve_twr_sharpe_delta_bootstrap"]
        out.append(f"{n} sleeve TWR CAGR {100 * (sv[n]['cagr'] - sv[ANCHOR]['cagr']):+.1f} pp/yr vs A0 "
                   f"({sv[n]['cagr']:.1%} vs {sv[ANCHOR]['cagr']:.1%}), sleeve TWR Sharpe delta point "
                   f"{sv[n]['sharpe'] - sv[ANCHOR]['sharpe']:+.3f} (paired p50 {sb['p50']:+.3f}, p5 {sb['p5']:+.3f}); "
                   f"book Sharpe delta {m['vs_a0']['point_sharpe_delta_full']:+.3f}, book CAGR delta "
                   f"{100 * (m['book']['full']['cagr'] - per_arm[ANCHOR]['book']['full']['cagr']):+.2f} pp/yr"
                   + (" — the book stays level through the band-rebalancing path."
                      if abs(m['book']['full']['cagr'] - per_arm[ANCHOR]['book']['full']['cagr']) < 0.0025
                      else " — the book does NOT stay level (re-review N1)."))
    for n, m in per_arm.items():
        if n == ANCHOR:
            continue
        sel, lv = m["selection"], m["sensitivity_live_release"]
        out.append(
            f"{n} per-symbol exit-date boundary: the replay holds a symbol THROUGH its exit date (the cap's "
            f"test), conservative by up to one day vs live, where an exiting or stop-filled call frees the "
            f"symbol in the same cycle: {sel['refused_exit_date_boundary_only']}/{sel['refused_repeat']} refusals "
            f"hinge on it. Re-run with live release: end ${lv['book_full']['end_value']:,.0f}, dSh "
            f"{lv['point_sharpe_delta_full']:+.3f} (vs {m['vs_a0']['point_sharpe_delta_full']:+.3f}), 5y dSh "
            f"{lv['sharpe_delta_5y']:+.3f} (vs {m['vs_a0']['deltas']['5y']['sharpe']:+.3f}), dDD "
            f"{100 * lv['max_dd_delta']:+.2f} pp (vs {100 * m['vs_a0']['deltas']['full']['max_dd']:+.2f} pp), p5 {lv['sharpe_delta_bootstrap']['p5']:+.3f}, p90 share "
            f"{lv['largest_name_share_p90']:.1%} -> {lv['decision']['decision']}"
            + (f" ({lv['decision']['tier']})" if lv['decision']['tier'] else "") + " (counter-agent A1).")
    out.append(
        f"Same-gate-date siblings: {grading['same_gate_date_dup_groups']} (symbol, gate_date) groups carry >1 "
        "gated fire; refusals blocked by a same-gate-date sibling: " + ", ".join(
            f"{n} {m['selection']['refused_by_same_gate_date_sibling']}" for n, m in per_arm.items() if n != ANCHOR)
        + ". A live port counting only positions + pending_entries would let these in; see "
          "proposal.live_port_spec (counter-agent A2).")
    return out


def run_study(fire_rows: list[dict], mkt: dict, tiers: dict, *, bil: dict[date, float],
              spy_px: dict[date, float | None], draws: int = STUDY_DRAWS, seed: int = STUDY_SEED,
              cache_basis: dict | None = None, bars_info: dict | None = None,
              mirror_stored_end: float | None = None) -> dict:
    if bil is None or spy_px is None:
        raise SystemExit("the study needs the BIL yield series and SPY prices — nothing written")
    calendar, px = mkt["calendar"], mkt["px"]
    windows = window_bounds(calendar)
    t0 = time.time()
    print("per-symbol: grading + gating the lag-2 rows once ...", flush=True)
    gated, grading = gated_rows(fire_rows, mkt, tiers)
    grading["same_gate_date_dup_groups"] = same_gate_dup_groups(gated)
    print(f"per-symbol: graded {grading['n_graded']}, gated {grading['n_gated']}, (symbol, gate_date) "
          f"groups with >1 fire {grading['same_gate_date_dup_groups']}", flush=True)

    # reduction check: A0 at $100k IS the mirror's blend3070_t2_carry (round 10's S0 path)
    a0_taken, _sel = select_arm(gated, None)
    r10_taken, _ = taken_rows(fire_rows, mkt, tiers)
    if a0_taken != r10_taken:
        raise SystemExit("REDUCTION FAILED: A0's taken set differs from round 10's taken_rows — nothing written")
    red_book = run_executor_book(a0_taken, mkt, arm_cfg({}, START_EQUITY), cash_yield=bil, spy_px=spy_px)
    red_end = red_book["curve"][-1][1]
    reduction = {"variant": MIRROR_VARIANT, "base": START_EQUITY, "stored_mirror_end": mirror_stored_end,
                 "got": red_end, "tolerance_usd": REDUCTION_TOL_USD,
                 "abs_diff": abs(red_end - mirror_stored_end) if mirror_stored_end is not None else None,
                 "pass": mirror_stored_end is not None and abs(red_end - mirror_stored_end) <= REDUCTION_TOL_USD}
    print(f"per-symbol: reduction A0 @ ${START_EQUITY:,.0f} ends ${red_end:,.2f} vs stored "
          f"{mirror_stored_end} pass={reduction['pass']}", flush=True)
    if mirror_stored_end is not None and not reduction["pass"]:
        raise SystemExit("REDUCTION FAILED — nothing written")

    books: dict[str, dict] = {}
    twrs: dict[str, list] = {}
    per_arm: dict[str, dict] = {}
    for name, k, desc in ARMS:
        taken, sel = select_arm(gated, k)
        bk = run_executor_book(taken, mkt, arm_cfg({}, LIVE_BASE), cash_yield=bil, spy_px=spy_px)
        books[name] = bk
        m = arm_metrics(bk, windows)
        m["sleeve_bucket_incl_transfers"] = m.pop("sleeve")          # round 10's bucket: NOT a return
        twrs[name] = sleeve_twr_curve(bk)
        m["sleeve"] = sleeve_twr_metrics(twrs[name], windows)       # the pre-registered sleeve metrics
        m["sleeve_basis"] = ("time-weighted: band transfers to/from the core are external flows "
                             "(sleeve_band_flow); end_value = the sleeve's start compounded at its own returns")
        m["sleeve_flows"] = sleeve_flow_summary(bk)
        dep = m["deployment"]["full"]
        sel.update({"book_entries": len(bk["trades"]), "skipped_zero_qty": bk["meta"]["skipped_zero_qty"],
                    "days_at_cap": sum(1 for e in bk["daily"].values() if e["open_positions"] == CAP)})
        m.update({"desc": desc, "per_symbol_max": k, "cfg_label": arm_cfg({}, LIVE_BASE).label,
                  "selection": sel, "concentration": concentration_stats(bk, px, calendar),
                  "mean_r_net_taken": (statistics.fmean([t["r_net"] for t in bk["trades"]])
                                       if bk["trades"] else None),
                  "carry_usd": bk["meta"]["carry_usd"], "commissions_paid": bk["meta"]["commissions_paid"]})
        per_arm[name] = m
        f, c = m["book"]["full"], m["concentration"]
        sv = m["sleeve"]["full"]
        print(f"per-symbol: {name} end ${f['end_value']:>11,.0f} CAGR {f['cagr']:+.2%} maxDD {f['max_dd']:.1%} "
              f"Sharpe {f['sharpe']:.3f} | sleeve TWR CAGR {sv['cagr']:+.2%} DD {sv['max_dd']:.1%} Sh "
              f"{sv['sharpe']:.3f} (flows {m['sleeve_flows']['n_flow_days']}d net "
              f"${m['sleeve_flows']['net_flow_into_sleeve_usd']:+,.0f}) | taken {sel['entries_taken']} refused {sel['refused_repeat']} "
              f"at-cap {sel['skipped_at_cap']} dep {dep['deployed_mean']:.1%} top-name p50/p90 "
              f"{c['largest_name_share_p50']:.1%}/{c['largest_name_share_p90']:.1%} names "
              f"{c['mean_distinct_names_per_open_day']:.2f}  [{time.time() - t0:.0f}s]", flush=True)

    sanity = sanity_reproduction(books[ANCHOR], px, calendar)
    print(f"per-symbol: A0 sanity reproduction pass={sanity['pass']}: " + ", ".join(
        f"{k}={v['got']:.4g}" for k, v in sanity["checks"].items()), flush=True)
    if not sanity["pass"]:
        raise SystemExit("SANITY FAILED: A0 does not reproduce the contract's motivating numbers — nothing written")

    lo, hi = windows["full"]
    r0 = daily_rets(books[ANCHOR]["curve"], lo, hi)
    a0 = per_arm[ANCHOR]
    for name, _k, _d in ARMS:
        m = per_arm[name]
        if name == ANCHOR:
            m["vs_a0"] = None
            m["decision"] = {"decision": "ANCHOR", "tier": None, "reasons": {}}
            continue
        ra = daily_rets(books[name]["curve"], lo, hi)
        boot = _boot(ra, r0, draws=draws, block=BOOT_MEAN_BLOCK, seed=seed)
        print(f"per-symbol: {name} block-{BOOT_MEAN_BLOCK} bootstrap done [{time.time() - t0:.0f}s]", flush=True)
        sens = _boot(ra, r0, draws=draws, block=SENS_BLOCK, seed=seed)
        deltas = {}
        for w in windows:
            a, b = m["book"].get(w) or {}, a0["book"].get(w) or {}
            deltas[w] = {kk: (a[kk] - b[kk]) if (a and b) else None
                         for kk in ("cagr", "max_dd", "sharpe", "end_value")}
            deltas[w]["longest_underwater_days"] = (a["longest_underwater_days"] - b["longest_underwater_days"]
                                                    if (a and b) else None)
        sd5 = deltas["5y"]["sharpe"]
        sleeve_deltas = {w: {kk: (m["sleeve"][w][kk] - a0["sleeve"][w][kk])
                             if (m["sleeve"].get(w) and a0["sleeve"].get(w)) else None
                             for kk in ("cagr", "max_dd", "sharpe")} for w in windows}
        sboot = _boot(daily_rets(twrs[name], lo, hi), daily_rets(twrs[ANCHOR], lo, hi),
                      draws=draws, block=BOOT_MEAN_BLOCK, seed=seed)
        m["vs_a0"] = {"deltas": deltas, "point_sharpe_delta_full": deltas["full"]["sharpe"],
                      "sharpe_delta_bootstrap": boot, "sharpe_delta_bootstrap_block63": sens,
                      "p90_share_delta": (m["concentration"]["largest_name_share_p90"]
                                          - a0["concentration"]["largest_name_share_p90"]),
                      "sleeve_twr_deltas": sleeve_deltas,
                      "sleeve_twr_sharpe_delta_bootstrap": sboot}
        m["decision"] = decide_arm(boot.get("bonf_lo"), boot.get("p5"), m["book"]["full"]["max_dd"],
                                   a0["book"]["full"]["max_dd"], sd5,
                                   m["concentration"]["largest_name_share_p90"],
                                   a0["concentration"]["largest_name_share_p90"])
        print(f"per-symbol: {name} vs A0: dSharpe point {deltas['full']['sharpe']:+.3f} p50 {boot['p50']:+.3f} "
              f"bonf2 [{boot['bonf_lo']:+.3f}, {boot['bonf_hi']:+.3f}] p5 {boot['p5']:+.3f} | blk63 bonf2 lo "
              f"{sens['bonf_lo']:+.3f} p5 {sens['p5']:+.3f} | 5y dSh {sd5:+.3f} | "
              f"{m['decision']['decision']} ({m['decision']['tier']})  [{time.time() - t0:.0f}s]", flush=True)
        m["sensitivity_live_release"] = live_release_sensitivity(
            gated, _k, mkt, windows, a0, r0, bil=bil, spy_px=spy_px, px=px, draws=draws, seed=seed)
        lv = m["sensitivity_live_release"]
        print(f"per-symbol: {name} live-release sensitivity: end ${lv['book_full']['end_value']:,.0f} dSh "
              f"{lv['point_sharpe_delta_full']:+.3f} p5 {lv['sharpe_delta_bootstrap']['p5']:+.3f} 5y dSh "
              f"{lv['sharpe_delta_5y']:+.3f} dDD {100 * lv['max_dd_delta']:+.2f}pp p90 share "
              f"{lv['largest_name_share_p90']:.1%} -> {lv['decision']['decision']} ({lv['decision']['tier']})  "
              f"[{time.time() - t0:.0f}s]", flush=True)

    proposal = choose([(n, per_arm[n]["decision"]["decision"], per_arm[n]["vs_a0"]["point_sharpe_delta_full"])
                       for n, _k, _d in ARMS if n != ANCHOR])
    proposal["live_port_spec"] = LIVE_PORT_SPEC
    print(f"per-symbol: proposal {proposal}", flush=True)
    return {
        "generated": date.today().isoformat(),
        "script": SCRIPT,
        "contract": CONTRACT,
        "period": [calendar[0].isoformat(), calendar[-1].isoformat()],
        "windows": {w: [a.isoformat(), b.isoformat()] for w, (a, b) in windows.items()},
        "protocol": {
            "anchor": ANCHOR, "base": LIVE_BASE, "reduction_base": START_EQUITY, "cap": CAP,
            "draws": draws, "seed": seed, "mean_block_days": BOOT_MEAN_BLOCK,
            "sensitivity": {"draws": draws, "mean_block_days": SENS_BLOCK},
            "bonferroni_family": FAMILY,
            "p5_basis": "5th percentile of the identical paired draws (one-sided 95% lower bound)",
            "decision_rule": {
                "tier1_improvement": "bonf2_lo > 0 AND book max DD <= A0 + 2 pp AND 5y Sharpe delta > 0",
                "tier2_risk_control": "p5 >= -0.10 AND book max DD <= A0 + 0.5 pp AND 5y Sharpe delta >= "
                                      "-0.05 AND p90 largest-name share <= A0's - 10 pp",
                "order": "an arm is proposed under the FIRST tier it meets; otherwise NULL",
                "tie_break": "both U1 and U2 qualify -> higher full-window point Sharpe delta; tie -> U1",
            },
            "arms": {n: {"per_symbol_max": k, "desc": d} for n, k, d in ARMS},
            "cache_basis": cache_basis or {"lane": "unknown (no backtest_bars_basis.json sidecar)"},
            "bars": bars_info,
            "grading": grading,
            "runtime_s": round(time.time() - t0, 1),
        },
        "reduction_check": reduction,
        "sanity_reproduction_a0": sanity,
        "arms": per_arm,
        "decisions": {n: {"decision": per_arm[n]["decision"]["decision"], "tier": per_arm[n]["decision"]["tier"]}
                      for n, _k, _d in ARMS if n != ANCHOR},
        "proposal": proposal,
        "honesty": HONESTY + computed_honesty(per_arm, grading),
    }


def print_table(res: dict) -> None:
    print(f"\n== R11 per-symbol | base ${int(res['protocol']['base']):,} | full {res['windows']['full'][0]} -> "
          f"{res['windows']['full'][1]} ==")
    print(f"{'arm':3s} {'book end':>10s} {'CAGR':>7s} {'maxDD':>6s} {'Sharpe':>6s} {'uw d':>5s} | "
          f"{'twrCAGR':>7s} {'twrDD':>6s} {'twrSh':>5s} {'dep':>6s} {'capD':>4s} | {'top p50':>7s} {'p90':>6s} {'max':>6s} "
          f"{'names':>5s} | {'taken':>5s} {'refus':>5s} {'@cap':>5s} {'rNet':>5s} | {'dSh':>6s} {'p50':>6s} "
          f"{'bonf2lo':>7s} {'p5':>6s} {'b63lo':>6s} {'b63p5':>6s} {'5y dSh':>6s} {'dDD':>6s} decision")
    for name, m in res["arms"].items():
        b, s, d, c, sel = (m["book"]["full"], m["sleeve"]["full"], m["deployment"]["full"], m["concentration"],
                           m["selection"])
        v = m["vs_a0"]
        if v:
            bt, sn = v["sharpe_delta_bootstrap"], v["sharpe_delta_bootstrap_block63"]
            tail = (f"{v['point_sharpe_delta_full']:>+6.3f} {bt['p50']:>+6.3f} {bt['bonf_lo']:>+7.3f} "
                    f"{bt['p5']:>+6.3f} {sn['bonf_lo']:>+6.3f} {sn['p5']:>+6.3f} {v['deltas']['5y']['sharpe']:>+6.3f} "
                    f"{v['deltas']['full']['max_dd']:>+6.1%} {m['decision']['decision']}"
                    + (f" ({m['decision']['tier']})" if m["decision"]["tier"] else ""))
        else:
            tail = f"{'-':>6s} {'-':>6s} {'-':>7s} {'-':>6s} {'-':>6s} {'-':>6s} {'-':>6s} {'-':>6s} ANCHOR"
        print(f"{name:3s} ${b['end_value']:>9,.0f} {b['cagr']:>+7.2%} {b['max_dd']:>6.1%} {b['sharpe']:>6.3f} "
              f"{b['longest_underwater_days']:>5d} | {s['cagr']:>+7.2%} {s['max_dd']:>6.1%} {s['sharpe']:>5.3f} {d['deployed_mean']:>6.1%} "
              f"{sel['days_at_cap']:>4d} | {c['largest_name_share_p50']:>7.1%} {c['largest_name_share_p90']:>6.1%} "
              f"{c['largest_name_share_max']:>6.1%} {c['mean_distinct_names_per_open_day']:>5.2f} | "
              f"{sel['entries_taken']:>5d} {sel['refused_repeat']:>5d} {sel['skipped_at_cap']:>5d} "
              f"{m['mean_r_net_taken']:>+5.2f} | {tail}")
    print("  (twr* = sleeve TIME-WEIGHTED, band transfers removed; sleeve bucket incl. transfers, NOT a return: "
          + "  ".join(f"{n} CAGR {m['sleeve_bucket_incl_transfers']['full']['cagr']:+.2%} DD "
                      f"{m['sleeve_bucket_incl_transfers']['full']['max_dd']:.1%}" for n, m in res["arms"].items())
          + ")")
    for w in ("5y", "2y"):
        print(f"  -- {w}: " + "  ".join(
            f"{n}: CAGR {m['book'][w]['cagr']:+.2%} Sh {m['book'][w]['sharpe']:.3f} DD {m['book'][w]['max_dd']:.1%} "
            f"uw {m['book'][w]['longest_underwater_days']}d" for n, m in res["arms"].items()))
    for name, m in res["arms"].items():
        if m["vs_a0"]:
            r = m["decision"]["reasons"]
            print(f"  {name} tier1 {r['tier1_improvement']}\n  {name} tier2 {r['tier2_risk_control']}")
            sel, lv = m["selection"], m["sensitivity_live_release"]
            print(f"  {name} refusals: exit-date-boundary-only {sel['refused_exit_date_boundary_only']}/"
                  f"{sel['refused_repeat']}, same-gate-date sibling {sel['refused_by_same_gate_date_sibling']}; "
                  f"live-release re-run: dSh {lv['point_sharpe_delta_full']:+.3f} p5 "
                  f"{lv['sharpe_delta_bootstrap']['p5']:+.3f} 5y {lv['sharpe_delta_5y']:+.3f} dDD "
                  f"{100 * lv['max_dd_delta']:+.2f}pp p90 {lv['largest_name_share_p90']:.1%} -> {lv['decision']['decision']}")
    r = res["reduction_check"]
    print(f"\nreduction: A0 @ ${int(START_EQUITY):,} ends ${r['got']:,.2f} vs stored {r['variant']} "
          f"{r['stored_mirror_end']} (|diff| {r['abs_diff']}, pass={r['pass']})")
    sa = res["sanity_reproduction_a0"]
    print(f"A0 sanity (motivating numbers) pass={sa['pass']}: " + "; ".join(
        f"{k} {v['got']:.4g} (stated {v['stated']})" for k, v in sa["checks"].items()))
    print(f"decisions: {json.dumps(res['decisions'])}")
    print(f"proposal: {res['proposal']}")


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
