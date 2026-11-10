#!/usr/bin/env python3
"""POST-HOC diagnostic for studies/distress-bottoms.md — not pre-registered,
not graded.

After the run, 6 of the 9 non-firing recessions (8 MISS and the censored
1929-33) traced to the pre-registered re-arming rule: after the 1920-21 (+184%)
and 1946-48 (+260%) surges the drop d = high/3 was 61 and 87 points, and
re-arming needed growth to rise that far above its post-signal low - it never
did, so 1923-24, 1929-33 and all four postwar recessions could not fire. This
script (1) re-scores the same series with a re-arm that does not scale with the
surge (re-arm once growth has turned negative, i.e. the failure wave is over);
(2) reports the hindsight growth peak at other smoothing windows (the
pre-registered diagnostic uses w = 12, which dates the peak ~3 months later by
construction); (3) summarises the frozen trader's-view rows on matched episode
sets. Everything else is SPEC v1.

    python3 bottoms_posthoc.py      # -> bottoms_posthoc.json
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bottoms as BT  # noqa: E402
import bottoms_engine as B  # noqa: E402
import load as D  # noqa: E402
from engine import mstr  # noqa: E402


def signals_rearm_negative(g: dict[int, float], periods, rule: B.Rule) -> list[dict]:
    """SPEC v1 roll-over rule, but after a signal the series re-arms once
    growth has been negative (the wave is over); H restarts there."""
    out: list[dict] = []
    run, live, start, seen_neg = 0, True, None, False
    for t in periods:
        gt = g.get(t)
        if not live:
            if gt is not None and gt < 0:
                seen_neg = True
            if seen_neg and gt is not None and gt >= 0:
                live, start, seen_neg = True, t, False
                out[-1]["rearmed_at"] = t
            run = 0
            continue
        hh = B.trailing_high(g, t, rule.look, start)
        cond = (gt is not None and hh is not None and hh[0] >= rule.theta - B.TIE
                and gt <= hh[0] - B.drop(hh[0], rule) + B.TIE)
        run = run + 1 if cond else 0
        if run >= rule.k:
            out.append({"t": t, "g": gt, "high": hh[0], "high_at": hh[1], "d": B.drop(hh[0], rule),
                        "rearmed_at": None})
            live, run = False, 0
    return out


def main():
    res = json.load(open(os.path.join(HERE, "bottoms_results.json")))
    rule = B.Rule(**res["rule"])
    spans = BT.spans_p(D.dnb_count_segments())
    G = {}
    for s in spans:
        g = B.growth(s["values"], rule, span=s["range"])
        G[s["name"]] = {"g": g, "signals": signals_rearm_negative(g, range(s["range"][0], s["range"][1] + 1), rule),
                        "range": s["range"]}
    P, _ = D.shiller_monthly()
    eqt = BT.equity_targets(P)
    rows = []
    for p, tau in BT.P_EPISODES:
        hi = BT.window_end(p, tau)
        gs = [G[s["name"]] for s in BT.episode_span(spans, p)]
        ep = BT.score_episode(gs, 1, p, hi, tau, 0, 9, p, rule)
        b = eqt[p]
        eq_e = (ep["release_m"] - b["b"]) if ep.get("release_m") is not None and b["status"] != "no equity low" \
            else None
        rows.append({"peak": mstr(p), "release": ep["signal"]["release"] if ep.get("signal") else None,
                     "outcome_confirms": ep["outcome"], "e_trough": ep["e"], "e_equity": eq_e})
    es = [r["e_trough"] for r in rows if r["e_trough"] is not None]
    out = {"note": __doc__.strip().split("\n\n")[1].replace("\n", " "),
           "episodes": rows, "confirms_hits": sum(r["outcome_confirms"] == "HIT" for r in rows),
           "fired": len(es), "median_e_trough_of_signals": float(np.median(es)),
           "e_equity_of_signals": sorted(r["e_equity"] for r in rows if r["e_equity"] is not None),
           "all_signals": [mstr(s["t"] + 1) for nm in G for s in G[nm]["signals"]]}
    # (2) hindsight growth peak vs the trough at other smoothing windows
    from dataclasses import replace
    gpk = {}
    for w in (1, 3, 6, 12):
        Gw = BT.growth_by_span(spans, replace(rule, w=w))
        es_w, before = [], 0
        for p, tau in BT.P_EPISODES:
            rel, _ = BT._gpeak(Gw, spans, p, p, BT.window_end(p, tau))
            if rel is not None:
                es_w.append(rel - tau)
                before += rel < tau
        gpk[str(w)] = {**BT.os_ci(es_w), "n_before_trough": before}
    out["g_peak_vs_trough_by_w"] = gpk
    # (3) trader's view on matched episode sets (frozen rows, no recomputation)
    rows = res["trader"]["episodes"]
    fired = [pk for pk, r in rows.items() if r.get("rollover_P", {}).get("entry")]
    def med(keys, rule_name, stat):
        xs = [rows[k][rule_name][stat] for k in keys if rows[k].get(rule_name, {}).get("entry")
              and stat in rows[k][rule_name]]
        return {"n": len(xs), "median": float(np.median(xs)) if xs else None}
    out["trader_on_rollover_recessions"] = {
        "episodes": fired,
        "rules": {rn: {st: med(fired, rn, st) for st in ("ret_12m", "ret_24m", "worst_dd_12m", "rebound_missed")}
                  for rn in ("rollover_P", "arm_P", "peak_plus_6", "minus_20pct", "random_armed_P")}}
    with open(os.path.join(HERE, "bottoms_posthoc.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: out[k] for k in ("confirms_hits", "fired", "median_e_trough_of_signals",
                                          "e_equity_of_signals")}))
    print(json.dumps(out["g_peak_vs_trough_by_w"]))
    print(json.dumps(out["trader_on_rollover_recessions"]["rules"], indent=0)[:1500])


if __name__ == "__main__":
    main()
