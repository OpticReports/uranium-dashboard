"""Pre-catalyst asymmetry study runner.

Reads catalyst_events.json (curated + verified), computes per-event pre-drift
and event-move metrics, tests the quiet-into-catalyst hypothesis, and runs the
assumption-driven option payoff simulation across IV scenarios.
Writes study_results.json.
"""
from __future__ import annotations

import json
import math
import os
import statistics as st

import study_lib as sl

HERE = os.path.dirname(__file__)
IV_SCENARIOS = [0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0]
ENTRY_DAYS_BEFORE = 10
QUIET_Z = 0.75  # matches the tracker flag threshold under test


def spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 5:
        return None
    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        rk = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return rk
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def bootstrap_mean_ci(vals: list[float], n_boot: int = 4000, alpha: float = 0.10,
                      seed: int = 42) -> tuple[float, float]:
    import random
    rng = random.Random(seed)
    n = len(vals)
    means = sorted(
        sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot)
    )
    lo = means[int(alpha / 2 * n_boot)]
    hi = means[int((1 - alpha / 2) * n_boot) - 1]
    return lo, hi


def main() -> None:
    events = json.load(open(os.path.join(HERE, "catalyst_events.json")))["events"]
    rows = []
    skipped = []
    for ev in events:
        if not ev.get("verified", False):
            skipped.append((ev["ticker"], ev["event_trading_date"], "unverified"))
            continue
        try:
            bars = sl.fetch_prices(ev["ticker"], "10Y")
        except Exception as exc:  # noqa: BLE001
            skipped.append((ev["ticker"], ev["event_trading_date"], f"prices: {exc}"))
            continue
        m = sl.event_metrics(bars, ev["event_trading_date"])
        if m is None:
            skipped.append((ev["ticker"], ev["event_trading_date"], "no bar/short history"))
            continue
        row = {**ev, **m}
        row["sims"] = {}
        for iv in IV_SCENARIOS:
            sim = sl.simulate_structures(bars, m["event_idx"], ENTRY_DAYS_BEFORE, iv)
            if sim:
                row["sims"][str(iv)] = sim
        rows.append(row)

    # ---- aggregates -------------------------------------------------------
    abs_moves = [abs(r["event_ret"]) for r in rows]
    pos = [r for r in rows if r["direction"] == "positive"]
    neg = [r for r in rows if r["direction"] == "negative"]
    with_z = [r for r in rows if r["drift_z10"] is not None]
    quiet = [r for r in with_z if abs(r["drift_z10"]) <= QUIET_Z]
    running = [r for r in with_z if abs(r["drift_z10"]) > QUIET_Z]

    summary = {
        "n_events": len(rows),
        "n_skipped": len(skipped),
        "skipped": skipped,
        "n_pos": len(pos), "n_neg": len(neg),
        "median_abs_event_move": st.median(abs_moves),
        "mean_abs_event_move": st.mean(abs_moves),
        "median_abs_move_pos": st.median([abs(r["event_ret"]) for r in pos]) if pos else None,
        "median_abs_move_neg": st.median([abs(r["event_ret"]) for r in neg]) if neg else None,
        "median_pre_r10": st.median([r["r10"] for r in rows if r["r10"] is not None]),
        "spearman_absdrift_vs_absmove": spearman(
            [abs(r["drift_z10"]) for r in with_z],
            [abs(r["event_ret"]) for r in with_z],
        ),
        "spearman_drift_vs_move": spearman(
            [r["drift_z10"] for r in with_z], [r["event_ret"] for r in with_z]
        ),
        "quiet": {
            "n": len(quiet),
            "median_abs_move": st.median([abs(r["event_ret"]) for r in quiet]) if quiet else None,
            "mean_abs_move": st.mean([abs(r["event_ret"]) for r in quiet]) if quiet else None,
        },
        "running": {
            "n": len(running),
            "median_abs_move": st.median([abs(r["event_ret"]) for r in running]) if running else None,
            "mean_abs_move": st.mean([abs(r["event_ret"]) for r in running]) if running else None,
        },
    }

    # ---- option structures across IV scenarios ----------------------------
    port = {}
    for iv in IV_SCENARIOS:
        key = str(iv)
        strad = [r["sims"][key]["straddle_mult"] for r in rows
                 if key in r["sims"] and "straddle_mult" in r["sims"][key]]
        atm = [r["sims"][key]["atm_call_mult"] for r in rows
               if key in r["sims"] and "atm_call_mult" in r["sims"][key]]
        otm = [r["sims"][key]["otm_call_mult"] for r in rows
               if key in r["sims"] and "otm_call_mult" in r["sims"][key]]
        # calls only pay on the long side: naive = buy calls on EVERY event
        # (no direction knowledge) — the honest baseline for "just gamble calls".
        def stats(mults):
            if not mults:
                return None
            wins = [m for m in mults if m > 1.0]
            lo, hi = bootstrap_mean_ci(mults)
            return {
                "n": len(mults),
                "mean_mult": st.mean(mults),
                "median_mult": st.median(mults),
                "pct_total_loss": sum(1 for m in mults if m < 0.01) / len(mults),
                "pct_profitable": len(wins) / len(mults),
                "max_mult": max(mults),
                "mean_ci90": [lo, hi],
            }
        port[key] = {
            "straddle": stats(strad),
            "atm_call_all_events": stats(atm),
            "otm_call_all_events": stats(otm),
        }
        # quiet-subset straddles: LOOK-AHEAD CONTAMINATED (counter-agent
        # finding: classification uses drift through t-1 but entry is t-10,
        # so post-entry drift leaks into the split). Kept for reference only —
        # never present as tradeable economics.
        strad_q = [r["sims"][key]["straddle_mult"] for r in quiet
                   if key in r["sims"] and "straddle_mult" in r["sims"][key]]
        strad_r = [r["sims"][key]["straddle_mult"] for r in running
                   if key in r["sims"] and "straddle_mult" in r["sims"][key]]
        port[key]["straddle_quiet_LOOKAHEAD_CONTAMINATED"] = stats(strad_q)
        port[key]["straddle_running_LOOKAHEAD_CONTAMINATED"] = stats(strad_r)

    # ---- selection-bias guard: breakeven arithmetic ------------------------
    # The dataset is selected for sharp movers, so mean multiples are an UPPER
    # BOUND. Report, per IV: the straddle's breakeven |move| (~its cost in % of
    # spot) and the share of REAL events that must be "sharp" for the strategy
    # to break even if non-selected events fizzle at an assumed |move|.
    FIZZLE_MOVE = 0.08
    bias_guard = {}
    for iv in IV_SCENARIOS:
        key = str(iv)
        costs = [r["sims"][key]["straddle_cost_pct"] for r in rows
                 if key in r["sims"] and "straddle_cost_pct" in r["sims"][key]]
        mults = [r["sims"][key]["straddle_mult"] for r in rows
                 if key in r["sims"] and "straddle_mult" in r["sims"][key]]
        if not costs or not mults:
            continue
        cost = st.median(costs)
        m_mean = st.mean(mults)     # outlier-dominated (ABVX alone ~+1.0 at IV 1.0)
        m_med = st.median(mults)    # the robust representative multiple
        m_fizzle = FIZZLE_MOVE / cost  # straddle exit ~ |move| / cost

        def share(m_sel):
            if m_sel <= m_fizzle:
                return None
            return max(0.0, min(1.0, (1.0 - m_fizzle) / (m_sel - m_fizzle)))
        bias_guard[key] = {
            "median_straddle_cost_pct": cost,
            "breakeven_abs_move": cost,  # multiple=1 when |move| ~= cost
            "mean_mult_selected": m_mean,
            "median_mult_selected": m_med,
            "assumed_fizzle_move": FIZZLE_MOVE,
            "fizzle_mult": m_fizzle,
            # Counter-agent correction: show BOTH — the mean-based share is
            # flattered by tail outliers; the median-based share is the
            # honest planning number.
            "breakeven_sharp_share_mean": share(m_mean),
            "breakeven_sharp_share_median": share(m_med),
        }

    out = {"summary": summary, "portfolio": port, "bias_guard": bias_guard,
           "events": rows,
           "params": {"entry_days_before": ENTRY_DAYS_BEFORE, "quiet_z": QUIET_Z,
                      "iv_scenarios": IV_SCENARIOS,
                      "exit": "intrinsic at event-day close (time value forfeited)"}}
    with open(os.path.join(HERE, "study_results.json"), "w") as f:
        json.dump(out, f, indent=1)

    print(f"events analyzed: {len(rows)} (skipped {len(skipped)})")
    print(f"pos/neg: {len(pos)}/{len(neg)}")
    print(f"median |event move|: {summary['median_abs_event_move']:.1%}")
    print(f"quiet (|z|<={QUIET_Z}): n={len(quiet)} median |move| "
          f"{summary['quiet']['median_abs_move'] and format(summary['quiet']['median_abs_move'], '.1%')}")
    print(f"running: n={len(running)} median |move| "
          f"{summary['running']['median_abs_move'] and format(summary['running']['median_abs_move'], '.1%')}")
    print(f"spearman |drift| vs |move|: {summary['spearman_absdrift_vs_absmove']}")
    for iv in ("0.8", "1.2"):
        s = port[iv]["straddle"]
        print(f"IV {iv} straddle: mean {s['mean_mult']:.2f}x, median {s['median_mult']:.2f}x, "
              f"profitable {s['pct_profitable']:.0%}, CI90 [{s['mean_ci90'][0]:.2f}, {s['mean_ci90'][1]:.2f}]")
    for t, d, why in skipped:
        print("  skipped:", t, d, why)


if __name__ == "__main__":
    main()
