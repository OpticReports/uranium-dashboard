"""XBI study round 2 - the CAGR-seeking variants of PREREG2.md. Run:

    cd genomics-alpha-tracker/backend && python -m research.xbi_strategies.run2

Writes results2.json. Passers get two sensitivity rows (margin +1pp, costs
x2) that must also pass.
"""
from __future__ import annotations

import json
import math

import numpy as np

from research.xbi_strategies import xbi_lib as X
from research.xbi_strategies.run import SUBPERIODS
from research.xbi_strategies.xbi_lib import HERE, Market, first_index_on_or_after, simulate, stats, weekly

OUT = HERE / "results2.json"
JUDGE2 = {"cagr_edge_pp": 0.02, "dd_no_worse": True, "subperiods_needed": 2}
ROTATION = ["XBI", "SPY", "QQQ", "IWM", "GLD", "TLT"]


def build(m: Market) -> dict[str, tuple[int, callable, str]]:
    px, sma200 = m.px["XBI"], m.sma("XBI", 200)
    vol20 = m.vol("XBI", 20)
    dd1y = m.drawdown_from_high("XBI", 252)
    mom = {s: m.momentum(s, 252, 21) for s in ROTATION}
    vol60 = {s: m.vol(s, 60) for s in ("XBI", "TLT", "GLD", "QQQ")}
    START = first_index_on_or_after(m, "2007-11-15")
    START_LEV = first_index_on_or_after(m, "2015-06-01")
    week_end = np.array([i == m.n - 1 or m.d[i].isocalendar()[1] != m.d[i + 1].isocalendar()[1]
                         for i in range(m.n)])

    def hold(fn, flag=m.month_end):
        def f(i, st):
            if flag[i] or "w" not in st:
                st["w"] = fn(i)
                return st["w"]
            return None
        return f

    def sticky(fn):
        def f(i, st):
            t = fn(i)
            if st.get("last") != t:
                st["last"] = t
                return t
            return None
        return f

    def banded(fn, band=0.05):
        def f(i, st):
            t = fn(i)
            t = 0.0 if t != t else t
            if "w" not in st or abs(t - st["w"]) > band:
                st["w"] = t
                return {"XBI": t} if t else {}
            return None
        return f

    def lev(k): return lambda i: {"XBI": k}
    def g1(i): return {"XBI": 2.0} if px[i] > sma200[i] else {}
    def g2(i): return {"XBI": 1.5 if px[i] > sma200[i] else 0.5}
    def g3(i): return min(2.0, 0.35 / vol20[i]) if vol20[i] > 0 else 0.0
    def g4(i): return g3(i) if px[i] > sma200[i] else 0.0
    def x1(i): return {"XBI": 1.5 if (px[i] > sma200[i] and dd1y[i] > 0.10) else 1.0}

    def x2(i, st):                           # stateful: trade only when the lever flips
        if dd1y[i] > 0.25:
            st["in"] = True
        elif dd1y[i] == 0.0:
            st["in"] = False
        t = {"XBI": 1.5 if st.get("in") else 1.0}
        if st.get("last") != t:
            st["last"] = t
            return t
        return None

    def s3(i): return {"XBI": 1.5 if m.d[i].month in (11, 12, 1, 2, 3) else 0.75}

    def ranked(i, universe):
        c = [(mom[s][i], s) for s in universe if not np.isnan(mom[s][i])]
        return sorted(c, reverse=True)
    def m2(i):
        r = ranked(i, ROTATION)
        return {r[0][1]: 1.0} if r and r[0][0] > 0 else {}
    def m3(i):
        r = [x for x in ranked(i, ROTATION)[:2] if x[0] > 0]
        return {s: 0.5 for _, s in r}
    def m4(i):
        r = ranked(i, [s for s in ROTATION if s != "XBI"])
        w = {"XBI": 0.5}
        if r and r[0][0] > 0:
            w[r[0][1]] = 0.5
        return w

    def port_vol(w, i):
        syms = list(w)
        R = np.array([m.ret[s][i - 59:i + 1] for s in syms])
        if np.isnan(R).any():
            return float("nan")
        return float((np.array([w[s] for s in syms]) @ R).std(ddof=1) * math.sqrt(252))

    def levered_iv(assets, target, cap):
        def f(i):
            iv = {s: 1.0 / vol60[s][i] for s in assets if vol60[s][i] > 0}
            tot = sum(iv.values())
            if not tot:
                return {}
            w = {s: v / tot for s, v in iv.items()}
            pv = port_vol(w, i)
            k = min(cap, target / pv) if pv == pv and pv > 0 else 1.0
            return {s: x * k for s, x in w.items()}
        return f

    return {
        "B0": (START, sticky(lambda i: {"XBI": 1.0}), "XBI buy & hold (benchmark)"),
        "L1": (START, hold(lev(1.25)), "1.25× XBI, monthly re-level, margin"),
        "L2": (START, hold(lev(1.5)), "1.5× XBI, monthly re-level, margin"),
        "L3": (START, hold(lev(2.0)), "2.0× XBI, monthly re-level, margin"),
        "L4": (START_LEV, sticky(lambda i: {"LABU": 1.0}), "LABU (3× daily-reset) buy & hold"),
        "L5": (START_LEV, hold(lambda i: {"XBI": 0.5, "LABU": 0.5}, week_end), "50/50 XBI/LABU, weekly rebalance"),
        "L6": (START_LEV, hold(lambda i: {"LABD": -0.33}), "short LABD 33% (≈1× long, decay tailwind), 8% borrow"),
        "L7": (START_LEV, hold(lambda i: {"LABD": -0.50}), "short LABD 50% (≈1.5× long), 8% borrow"),
        "G1": (START, sticky(g1), "2× XBI above SMA200, else BIL"),
        "G2": (START, sticky(g2), "1.5× above SMA200, 0.5× below"),
        "G3": (START, banded(g3), "vol target 35%, cap 2.0, 5pp band"),
        "G4": (START, banded(g4), "SMA200 gate × vol target 35%, cap 2.0"),
        "X1": (START, sticky(x1), "1.5× while above SMA200 and 1y DD > 10%, else 1.0"),
        "X2": (START, x2, "1.5× while 1y DD > 25%, 1.0 after a new high"),
        "S3": (START, sticky(s3), "1.5× Nov–Mar, 0.75× Apr–Oct"),
        "M2": (START, hold(m2), "top-1 12-1 momentum of XBI/SPY/QQQ/IWM/GLD/TLT, else BIL, monthly"),
        "M3": (START, hold(m3), "top-2 equal-weight of the same set, monthly"),
        "M4": (START, hold(m4), "50% XBI + 50% top-1 momentum of the others, monthly"),
        "RP2": (START, hold(levered_iv(("XBI", "TLT", "GLD"), 0.30, 2.5)), "inverse-vol XBI/TLT/GLD levered to 30% vol, cap 2.5"),
        "RP3": (START, hold(levered_iv(("XBI", "QQQ", "GLD", "TLT"), 0.25, 2.5)), "inverse-vol XBI/QQQ/GLD/TLT levered to 25% vol, cap 2.5"),
    }


def judge2(full, subs, bfull, bsubs):
    cagr_ok = full["cagr"] >= bfull["cagr"] + JUDGE2["cagr_edge_pp"]
    dd_ok = full["max_dd"] <= bfull["max_dd"]
    wins = sum(1 for k, s in subs.items() if s and bsubs.get(k) and s["cagr"] > bsubs[k]["cagr"])
    return {"cagr_ok": bool(cagr_ok), "dd_ok": bool(dd_ok), "subperiod_cagr_wins": wins,
            "passes": bool(cagr_ok and dd_ok and wins >= JUDGE2["subperiods_needed"])}


def run_one(m, start, rule, end):
    res = simulate(m, rule, start)
    eq = res["eq"]
    full = stats(m.d, eq, start, end)
    subs = {}
    for k, a, b in SUBPERIODS:
        i0 = max(start, first_index_on_or_after(m, a))
        i1 = min(end, max(i for i in range(m.n) if m.dates[i] <= b))
        subs[k] = stats(m.d, eq, i0, i1) if i1 - i0 > 60 else None
    return res, eq, full, subs


def main() -> None:
    m = Market()
    rules = build(m)
    end = m.n - 1
    out = {"generated": m.dates[-1], "judge": JUDGE2, "subperiods": {k: [a, b] for k, a, b in SUBPERIODS},
           "variants": {}}
    b0_res, b0, b0_full, b0_subs = run_one(m, rules["B0"][0], rules["B0"][1], end)
    for vid, (start, rule, note) in rules.items():
        res, eq, full, subs = run_one(m, start, rule, end)
        bfull = stats(m.d, b0, start, end)
        bsubs = {}
        for k, a, b in SUBPERIODS:
            i0 = max(start, first_index_on_or_after(m, a))
            i1 = min(end, max(i for i in range(m.n) if m.dates[i] <= b))
            bsubs[k] = stats(m.d, b0, i0, i1) if i1 - i0 > 60 else None
        v = {"note": note, "start": m.dates[start], "full": full, "subperiods": subs,
             "turnover_py": res["turnover_py"], "cost_drag_py": res["cost_drag_py"], "avg_gross": res["avg_gross"],
             "bench_same_window": {"full": bfull, "subperiods": bsubs},
             "curve_weekly": weekly(m.d, eq, start, end)}
        v["judge"] = judge2(full, subs, bfull, bsubs) if vid != "B0" else None
        if v["judge"] and v["judge"]["passes"]:
            sens = {}
            # margin +1pp
            X.MARGIN_SPREAD = 0.025
            r2, _, f2, s2 = run_one(m, start, rule, end)
            X.MARGIN_SPREAD = 0.015
            sens["margin_plus_1pp"] = {"full": f2, "judge": judge2(f2, s2, bfull, bsubs)}
            # costs x2
            saved = dict(X.COST_BPS)
            for k in X.COST_BPS:
                X.COST_BPS[k] = saved[k] * 2
            r3, _, f3, s3 = run_one(m, start, rule, end)
            X.COST_BPS.update(saved)
            sens["costs_x2"] = {"full": f3, "judge": judge2(f3, s3, bfull, bsubs)}
            v["sensitivity"] = sens
            v["judge"]["robust"] = bool(sens["margin_plus_1pp"]["judge"]["passes"] and sens["costs_x2"]["judge"]["passes"])
        out["variants"][vid] = v
        j = v["judge"] or {}
        print(f"{vid:3s} {full['cagr']:+7.1%} dd {full['max_dd']:6.1%} sh {full['sharpe']:5.2f} "
              f"gross {res['avg_gross']:4.2f} wins {j.get('subperiod_cagr_wins', '-')} "
              f"{'PASS' if j.get('passes') else '    '}{' robust' if j.get('robust') else ''}  {note}")
    out["passers"] = [k for k, v in out["variants"].items() if v["judge"] and v["judge"]["passes"]]
    out["robust_passers"] = [k for k in out["passers"] if out["variants"][k]["judge"].get("robust")]
    print("PASS:", out["passers"] or "none", "| ROBUST:", out["robust_passers"] or "none")
    OUT.write_text(json.dumps(out, indent=0, default=lambda x: None if isinstance(x, float) and math.isnan(x) else x))


if __name__ == "__main__":
    main()
