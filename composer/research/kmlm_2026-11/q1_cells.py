"""Q1: every cell declared in PREREG.md (74), simulated once on tiers A+B (one continuous path) and, for
the switch-type cells, on tier C. Writes out/cells_ab.json and out/cells_c.json: per cell its daily
returns, turnover, trades, flips of the switch flag and knife-edge share. No statistic is judged here
(q2_stats.py does that).

Tier B starts 2021-06-01, not 2020-12-02: the KMLM fund needs up to 121 closes before every cell's
indicator exists (DEVIATIONS.md 1). The path is continuous across B and A.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import data  # noqa: E402
import ksim as ks  # noqa: E402

END = "2026-11-19"            # the 11-20 bar was not final when fetched (review A, M1; DEVIATIONS.md 12)
B_START, A_START = "2021-06-01", "2023-04-19"
C_START, C_END = "2007-09-04", "2020-12-01"
CAL_END = "2020-12-01"                 # quantile-matched thresholds are calibrated on history to here
F1_N = (3, 5, 7, 8, 9, 10, 11, 12, 14, 17, 20, 25, 30, 40, 60)
VOTES = ((8, 10, 12), (5, 10, 20), (7, 10, 14, 20, 30))
F3_N = (5, 7, 14, 20)
F4_N = (5, 10, 20, 40, 60, 120)
F5_N = (10, 20, 50, 100, 200)
F6_PAIRS = ((5, 20), (10, 20), (10, 50), (20, 50), (50, 200))
BUMP = 0.003                           # knife-edge: would the flag differ with XLK's close 0.3% higher or lower?


def both(a, b, f):
    return {d: (None if a.get(d) is None or b.get(d) is None else f(a[d], b[d])) for d in a}


def flag_rsi(P, n, bump=0.0):
    x = ks.rsi_series(P["XLK"], n) if not bump else rsi_bumped(P["XLK"], n, bump)
    return both(x, ks.rsi_series(P["KMLM"], n), lambda u, v: u > v)


def rsi_bumped(p, w, bump):
    """Wilder RSI on each day as it would read with THAT day's close moved by `bump` (earlier closes as they were)"""
    ds = sorted(p)
    out, ag, al = {ds[0]: None}, 0.0, 0.0
    for i in range(1, len(ds)):
        x = p[ds[i]] - p[ds[i - 1]]
        xb = p[ds[i]] * (1 + bump) - p[ds[i - 1]]
        if i <= w:
            agb, alb = ag + max(xb, 0) / w, al + max(-xb, 0) / w
            ag += max(x, 0) / w
            al += max(-x, 0) / w
        else:
            agb, alb = (ag * (w - 1) + max(xb, 0)) / w, (al * (w - 1) + max(-xb, 0)) / w
            ag = (ag * (w - 1) + max(x, 0)) / w
            al = (al * (w - 1) + max(-x, 0)) / w
        out[ds[i]] = None if i < max(ks.sr.RSI_MIN, w + 1) else (100.0 if alb == 0 else 100 - 100 / (1 + agb / alb))
    return out


def bumped(p, bump):
    return {d: v * (1 + bump) for d, v in p.items()}


def avg_bumped(p, w, bump, kind):
    """the average on each day with that day's close bumped"""
    ds = sorted(p)
    base = (ks.sma_series if kind == "sma" else ks.ema_series)(p, w)
    out = {}
    a = 2.0 / (w + 1)
    for d in ds:
        if base[d] is None:
            out[d] = None
        else:
            out[d] = base[d] + (p[d] * bump) * (1.0 / w if kind == "sma" else a)
    return out


def switch_flags(P):
    """{cell id: (flag {day: bool|None}, flag_up, flag_down)} for every switch-type cell that is injected"""
    x = P["XLK"]
    out = {}
    for n in F1_N:
        out[f"F1a.rsi{n}"] = tuple(flag_rsi(P, n, b) for b in (0.0, BUMP, -BUMP))
    for mem in VOTES:
        fs = [[flag_rsi(P, n, b) for n in mem] for b in (0.0, BUMP, -BUMP)]
        vote = lambda L: {d: (None if any(f.get(d) is None for f in L) else sum(f[d] for f in L) * 2 > len(L)) for d in x}  # noqa: E731
        out["F2.vote" + "-".join(map(str, mem))] = tuple(vote(L) for L in fs)
    for n in F4_N:
        k = ks.ret_series(P["KMLM"], n)
        out[f"F4.mom{n}"] = tuple(both(ks.ret_series(x if not b else {d: v for d, v in x.items()}, n) if not b else
                                       {d: (None if r is None else ((1 + r / 100) * (1 + b) - 1) * 100)
                                        for d, r in ks.ret_series(x, n).items()}, k, lambda u, v: u > v)
                                  for b in (0.0, BUMP, -BUMP))
    for kind in ("sma", "ema"):
        ser = ks.sma_series if kind == "sma" else ks.ema_series
        for n in F5_N:
            out[f"F5.{kind}{n}"] = tuple(
                {d: (None if m is None else x[d] * (1 + b) > m) for d, m in avg_bumped(x, n, b, kind).items()}
                for b in (0.0, BUMP, -BUMP))
        for f, s in F6_PAIRS:
            out[f"F6.{kind}{f}x{s}"] = tuple(
                both(avg_bumped(x, f, b, kind), avg_bumped(x, s, b, kind), lambda u, v: u > v)
                for b in (0.0, BUMP, -BUMP))
    return out


def matched_thresholds(tree, n):
    """for each pop / dip fund, the RSI(n) threshold exceeded as often as the live RSI(10) threshold was
    over the fund's history to CAL_END (PREREG F3)"""
    out = {}
    for nodes, above in ((ks.pop_nodes(tree), True), (ks.dip_nodes(tree), False)):
        thr = {}
        for node in nodes:
            t, live = node["lhs-val"], float(node["rhs-val"])
            p = data.series(t, CAL_END)
            r10 = [v for v in ks.rsi_series(p, 10).values() if v is not None]
            rn = sorted(v for v in ks.rsi_series(p, n).values() if v is not None)
            f = sum((v > live) if above else (v < live) for v in r10) / len(r10)
            k = (1 - f) if above else f
            thr[t] = rn[min(len(rn) - 1, max(0, int(round(k * (len(rn) - 1)))))]
        out["pops" if above else "dips"] = thr
    return out


def flips(flag, days):
    v = [flag[d] for d in days if flag.get(d) is not None]
    return sum(a != b for a, b in zip(v, v[1:]))


def run(P, start, end, tier_c=False):
    tree = ks.approved()
    flags = switch_flags(P)
    cells, days_ref = {}, [None]

    def add(cid, family, tr, fl=None, note=None):
        r = ks.simulate(tr, P, start, end, flags=[fl[0]] if fl else None)
        if cells and r["days"] != days_ref[0]:          # an undefined flag would drop a session silently (review A, N2)
            raise RuntimeError(f"{cid}: not the base's sessions")
        days_ref[0] = days_ref[0] or r["days"]
        c = {"family": family, "ret": r["ret"], "to": r["turnover"], "turnover": sum(r["turnover"]),
             "trades": r["trades"]}
        if fl:
            dd = [d for d in r["target"]]
            c["flips"] = flips(fl[0], dd)
            c["knife_share"] = sum(1 for d in dd if fl[0].get(d) is not None and
                                   (fl[1].get(d) != fl[0][d] or fl[2].get(d) != fl[0][d])) / len(dd)
        if note:
            c["note"] = note
        cells[cid] = c
        return r

    base = add("base", "base", tree, flags["F1a.rsi10"])
    days = base["days"]
    for n in F1_N:
        add(f"F1a.rsi{n}", "F1a", ks.v_switch_rsi(tree, n), flags[f"F1a.rsi{n}"])
        add(f"F1b.rsi{n}", "F1b", ks.v_switch_rsi(tree, n, picks=True), flags[f"F1a.rsi{n}"])
    for mem in VOTES:
        cid = "F2.vote" + "-".join(map(str, mem))
        add(cid, "F2", ks.v_switch_flag(tree), flags[cid])
        add("F2.split" + "-".join(map(str, mem)), "F2", ks.v_split(tree, mem))
    if not tier_c:
        for n in F3_N:
            thr = matched_thresholds(tree, n)
            add(f"F3a.pops{n}", "F3", ks.v_thresholds(tree, n, pops=thr["pops"]), note=thr["pops"])
            add(f"F3b.dips{n}", "F3", ks.v_thresholds(tree, n, dips=thr["dips"]), note=thr["dips"])
            add(f"F3c.both{n}", "F3", ks.v_thresholds(tree, n, pops=thr["pops"], dips=thr["dips"]))
    for n in F4_N:
        add(f"F4.mom{n}", "F4", ks.v_switch_form(tree, ("cumulative-return", "XLK", n), ("cumulative-return", "KMLM", n)),
            flags[f"F4.mom{n}"])
    for n in F5_N:
        add(f"F5.sma{n}", "F5", ks.v_switch_form(tree, ("current-price", "XLK", None), ("moving-average-price", "XLK", n)),
            flags[f"F5.sma{n}"])
        add(f"F5.ema{n}", "F5", ks.v_switch_flag(tree), flags[f"F5.ema{n}"])
    for f, s in F6_PAIRS:
        add(f"F6.sma{f}x{s}", "F6", ks.v_switch_form(tree, ("moving-average-price", "XLK", f), ("moving-average-price", "XLK", s)),
            flags[f"F6.sma{f}x{s}"])
        add(f"F6.ema{f}x{s}", "F6", ks.v_switch_flag(tree), flags[f"F6.ema{f}x{s}"])
    return {"days": days, "cells": cells}


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    t0 = time.time()
    ab = run(data.panel_ab(END), B_START, END)
    ab.update({"b_start": B_START, "a_start": A_START, "end": END, "cost": ks.COST})
    n_decl = len([c for c in ab["cells"] if c != "base"])
    assert n_decl == 74, n_decl
    json.dump(ab, open(os.path.join(HERE, "out", "cells_ab.json"), "w"))
    print(f"A+B: {n_decl} cells, {len(ab['days'])} sessions {ab['days'][0]}..{ab['days'][-1]}, {time.time() - t0:.0f}s")
    if "--no-c" not in sys.argv:
        t0 = time.time()
        c = run(data.panel_c(), C_START, C_END, tier_c=True)
        c.update({"start": C_START, "end": C_END})
        json.dump(c, open(os.path.join(HERE, "out", "cells_c.json"), "w"))
        print(f"C: {len(c['cells']) - 1} cells, {len(c['days'])} sessions {c['days'][0]}..{c['days'][-1]}, {time.time() - t0:.0f}s")
