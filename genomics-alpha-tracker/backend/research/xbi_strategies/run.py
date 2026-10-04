"""XBI strategy study - the pre-registered variants (PREREG.md). Run:

    cd genomics-alpha-tracker/backend && python -m research.xbi_strategies.run

Writes research/xbi_strategies/results.json (stats + weekly curves) and
prints the judging table. Nothing here is tuned after seeing results except
C1, which is labelled as such.
"""
from __future__ import annotations

import json
import math

import numpy as np

from research.xbi_strategies.xbi_lib import (
    HERE, Market, first_index_on_or_after, simulate, stats, weekly,
)

OUT = HERE / "results.json"
SUBPERIODS = [("2007-09→2012", "2007-09-01", "2012-12-31"),
              ("2013→2018", "2013-01-01", "2018-12-31"),
              ("2019→2026-10", "2019-01-01", "2026-12-31")]
JUDGE = {"dd_improvement_pp": 0.10, "cagr_giveup_pp": 0.02, "subperiods_needed": 2}


def build_rules(m: Market) -> dict[str, tuple[int, callable, str]]:
    """id -> (start index, rule, note). Indicators precomputed once."""
    sma200 = m.sma("XBI", 200)
    px = m.px["XBI"]
    vol20 = m.vol("XBI", 20)
    dd1y = m.drawdown_from_high("XBI", 252)
    mom121 = m.momentum("XBI", 252, 21)
    mom12_spy = m.momentum("SPY", 252, 21)
    mom12_bil = m.momentum("BIL", 252, 21)
    rsi2 = m.rsi("XBI", 2)
    beta60 = m.beta("XBI", "SPY", 60)
    ratio = m.px["XBI"] / m.px["SPY"]
    ratio_sma = np.full(m.n, np.nan)
    for i in range(199, m.n):
        w = ratio[i - 199:i + 1]
        if not np.isnan(w).any():
            ratio_sma[i] = w.mean()
    sma10m = np.full(m.n, np.nan)                     # 10 month-end closes
    me_idx = [i for i in range(m.n) if m.month_end[i]]
    for k in range(9, len(me_idx)):
        sma10m[me_idx[k]] = np.mean([px[j] for j in me_idx[k - 9:k + 1]])
    vol60 = {s: m.vol(s, 60) for s in ("XBI", "TLT", "GLD")}
    name_mom = {s: m.momentum(s, 252, 21) for s in m.names}
    name_sma = {s: m.sma(s, 200) for s in m.names}

    # Round-2 amendment: start at the first bar where EVERY 252-bar indicator
    # is valid (PREREG said 200 bars; T3/T4/D1 sat flat for 52 bars otherwise).
    START = first_index_on_or_after(m, "2007-11-15")
    START_LEV = first_index_on_or_after(m, "2015-06-01")
    START_NAMES = first_index_on_or_after(m, "2016-09-01")

    # The engine carries positions; a rule returns None to say "no trade
    # today" and the book drifts. Three wrappers express the three cadences.
    def hold(w):                       # decide at month-end only, drift in between
        def f(i, st):
            if m.month_end[i] or "w" not in st:
                st["w"] = w(i, st)
                return st["w"]
            return None
        return f

    def sticky(w):                     # daily discrete rule: trade only when the decision changes
        def f(i, st):
            t = w(i, st)
            if st.get("last") != t:
                st["last"] = t
                return t
            return None
        return f

    def banded(target, band=0.05):     # continuous sizing with a no-trade band on the TARGET
        def f(i, st):
            t = target(i, st)
            t = 0.0 if t != t else t                    # NaN indicator → flat
            if "w" not in st or abs(t - st["w"]) > band:
                st["w"] = t
                return {"XBI": t} if t else {}
            return None
        return f

    def t1(i, st): return {"XBI": 1.0} if px[i] > sma200[i] else {}
    def t2(i, st): return {"XBI": 1.0} if not np.isnan(sma10m[i]) and px[i] > sma10m[i] else {}
    def t3(i, st): return {"XBI": 1.0} if mom121[i] > 0 else {}
    def t4(i, st):
        best = max((mom121[i], "XBI"), (mom12_spy[i], "SPY"))
        bil = mom12_bil[i] if not np.isnan(mom12_bil[i]) else 0.0
        return {best[1]: 1.0} if best[0] > bil else {}
    def t5(i, st): return {"XBI": 1.0} if ratio[i] > ratio_sma[i] else {"SPY": 1.0}

    def vt(cap):
        return lambda i, st: min(cap, 0.20 / vol20[i]) if vol20[i] > 0 else 0.0
    def v3_target(i, st): return min(1.0, 0.20 / vol20[i]) if px[i] > sma200[i] and vol20[i] > 0 else 0.0
    def d1_target(i, st): return float(np.clip(1.0 - dd1y[i] / 0.40, 0.25, 1.0))
    def d2(i, st):
        if dd1y[i] > 0.20:
            st["in"] = True
        elif dd1y[i] == 0.0:
            st["in"] = False
        return {"XBI": 1.0 if st.get("in") else 0.5}

    def season(i): return m.d[i].month in (11, 12, 1, 2, 3)
    def s1(i, st): return {"XBI": 1.0} if season(i) else {}
    def s2(i, st): return {"XBI": 1.0} if season(i) and px[i] > sma200[i] else {}

    def m1(i, st):
        if st.get("in"):
            st["bars"] += 1
            if rsi2[i] > 70 or st["bars"] >= 10:
                st["in"] = False
                return {}
            return {"XBI": 1.0}
        if rsi2[i] < 10:
            st["in"], st["bars"] = True, 0
            return {"XBI": 1.0}
        return {}

    def p1(i, st):
        b = beta60[i]
        return {"XBI": 1.0, "SPY": -min(1.0, max(0.0, b))} if not np.isnan(b) else {"XBI": 1.0}
    def p2(i, st): return {"XBI": 1.0, "IBB": -1.0}
    def p3(i, st): return {"XBI": 1.0, "XLV": -1.0}
    def p4(i, st): return {"XBI": 1.0, "LABU": -0.10, "LABD": -0.10}
    def p5(i, st): return {"LABU": -0.5, "LABD": -0.5}

    def n1(i, st):
        cands = [(name_mom[s][i], s) for s in m.names if not np.isnan(name_mom[s][i])]
        worst = sorted(cands)[:5]
        w = {"XBI": 1.0}
        w.update({s: -0.10 for _, s in worst})
        return w
    def n2(i, st):
        broken = [s for s in m.names if not np.isnan(name_sma[s][i]) and m.px[s][i] < name_sma[s][i]]
        w = {"XBI": 1.0}
        if broken:
            w.update({s: -0.50 / len(broken) for s in broken})
        return w

    def r1(i, st):
        iv = {s: 1.0 / vol60[s][i] for s in vol60 if vol60[s][i] > 0}
        tot = sum(iv.values())
        return {s: v / tot for s, v in iv.items()} if tot else {}

    return {
        "B0": (START, sticky(lambda i, st: {"XBI": 1.0}), "XBI buy & hold (benchmark)"),
        "B1": (START, sticky(lambda i, st: {"SPY": 1.0}), "SPY buy & hold"),
        "B2": (START, hold(lambda i, st: {"XBI": 0.5}), "50/50 XBI/BIL, monthly rebalance"),
        "B3": (START, hold(lambda i, st: {"XBI": 0.6, "TLT": 0.4}), "60/40 XBI/TLT, monthly rebalance"),
        "T1": (START, sticky(t1), "close > SMA200 → XBI else BIL"),
        "T2": (START, hold(t2), "month-end close > 10m SMA → XBI else BIL"),
        "T3": (START, hold(t3), "12-1 momentum > 0 → XBI else BIL"),
        "T4": (START, hold(t4), "dual momentum XBI/SPY vs BIL (hurdle 0 until BIL has 12m, 2008-05)"),
        "T5": (START, sticky(t5), "XBI/SPY ratio > SMA200 → XBI else SPY"),
        "V1": (START, banded(vt(1.0)), "vol target 20%, cap 1.0, 5pp band"),
        "V2": (START, banded(vt(1.5)), "vol target 20%, cap 1.5 (margin), 5pp band"),
        "V3": (START, banded(v3_target), "SMA200 gate × vol target 20%, 5pp band"),
        "D1": (START, banded(d1_target), "de-risk as 1y drawdown deepens, 5pp band"),
        "D2": (START, sticky(d2), "buy the dip: 0.5 base, 1.0 while DD>20% (drifts between flips)"),
        "S1": (START, sticky(s1), "XBI Nov–Mar, BIL otherwise"),
        "S2": (START, sticky(s2), "Nov–Mar and close > SMA200"),
        "M1": (START, sticky(m1), "RSI(2)<10 buy, exit >70 or 10 bars"),
        "P1": (START, hold(p1), "long XBI / short β·SPY (60d, cap 1), monthly re-level"),
        "P2": (START, hold(p2), "long XBI / short IBB, monthly re-level"),
        "P3": (START, hold(p3), "long XBI / short XLV, monthly re-level"),
        "P4": (START_LEV, hold(p4), "XBI + short 10% LABU + 10% LABD, monthly reset"),
        "P5": (START_LEV, p5, "short 50% LABU / 50% LABD, daily reset (cost on every reset)"),
        "N1": (START_NAMES, hold(n1), "XBI + short 5 worst 12-1 of the eligible survivors (9→31 names), monthly"),
        "N2": (START_NAMES, hold(n2), "XBI + short eligible survivors below SMA200 (9→31 names, 50% total), monthly"),
        "R1": (START, hold(r1), "inverse-vol XBI/TLT/GLD, monthly rebalance"),
    }


def param_maps(m: Market, start: int) -> dict:
    px, out = m.px["XBI"], {"T1_sma": {}, "V1_target": {}}
    for n in range(100, 301, 25):
        s = m.sma("XBI", n)
        def trule(i, st, s=s):
            t = {"XBI": 1.0} if px[i] > s[i] else {}
            if st.get("last") != t:
                st["last"] = t
                return t
            return None
        res = simulate(m, trule, start)
        st = stats(m.d, res["eq"], start, m.n - 1)
        out["T1_sma"][str(n)] = {k: st[k] for k in ("cagr", "max_dd", "sharpe", "calmar")}
    vol20 = m.vol("XBI", 20)
    for tgt in (0.15, 0.175, 0.20, 0.225, 0.25):
        def rule(i, st, tgt=tgt):
            t = min(1.0, tgt / vol20[i]) if vol20[i] > 0 else 0.0
            if "w" not in st or abs(t - st["w"]) > 0.05:
                st["w"] = t
                return {"XBI": t}
            return None
        st = stats(m.d, simulate(m, rule, start)["eq"], start, m.n - 1)
        out["V1_target"][f"{tgt:.3f}"] = {k: st[k] for k in ("cagr", "max_dd", "sharpe", "calmar")}
    return out


def judge(full: dict, subs: dict, bench_full: dict, bench_subs: dict) -> dict:
    dd_ok = bench_full["max_dd"] - full["max_dd"] >= JUDGE["dd_improvement_pp"]
    cagr_ok = full["cagr"] >= bench_full["cagr"] - JUDGE["cagr_giveup_pp"]
    sub_wins = sum(1 for k, s in subs.items() if s and bench_subs.get(k) and s["max_dd"] < bench_subs[k]["max_dd"])
    return {"dd_ok": bool(dd_ok), "cagr_ok": bool(cagr_ok), "subperiod_dd_wins": sub_wins,
            "passes": bool(dd_ok and cagr_ok and sub_wins >= JUDGE["subperiods_needed"])}


def main() -> None:
    m = Market()
    rules = build_rules(m)
    end = m.n - 1
    out: dict = {"generated": m.dates[-1], "window_end": m.dates[-1], "judge": JUDGE,
                 "subperiods": {k: [a, b] for k, a, b in SUBPERIODS}, "variants": {}}
    curves: dict[str, np.ndarray] = {}
    for vid, (start, rule, note) in rules.items():
        res = simulate(m, rule, start)
        eq = res["eq"]
        curves[vid] = eq
        full = stats(m.d, eq, start, end)
        subs = {}
        for k, a, b in SUBPERIODS:
            i0 = max(start, first_index_on_or_after(m, a))
            i1 = min(end, max(i for i in range(m.n) if m.dates[i] <= b))
            subs[k] = stats(m.d, eq, i0, i1) if i1 - i0 > 60 else None
        out["variants"][vid] = {"note": note, "start": m.dates[start], "full": full, "subperiods": subs,
                                "turnover_py": res["turnover_py"], "cost_drag_py": res["cost_drag_py"],
                                "avg_gross": res["avg_gross"], "curve_weekly": weekly(m.d, eq, start, end)}
        print(f"{vid:3s} {full['cagr']:+7.1%} dd {full['max_dd']:6.1%} sh {full['sharpe']:5.2f} "
              f"cal {full['calmar']:5.2f} uw {full['underwater_days']:5d}d  {note}")
    # judge against B0 on the SAME window as each variant (late starters get XBI re-based)
    b0 = curves["B0"]
    for vid, v in out["variants"].items():
        if vid == "B0":
            continue
        s = m.idx[v["start"]]
        bench_full = stats(m.d, b0, s, end)
        bench_subs = {}
        for k, a, b in SUBPERIODS:
            i0 = max(s, first_index_on_or_after(m, a))
            i1 = min(end, max(i for i in range(m.n) if m.dates[i] <= b))
            bench_subs[k] = stats(m.d, b0, i0, i1) if i1 - i0 > 60 else None
        v["bench_same_window"] = {"full": bench_full, "subperiods": bench_subs}
        v["judge"] = judge(v["full"], v["subperiods"], bench_full, bench_subs)
    out["param_maps"] = param_maps(m, rules["B0"][0])
    passers = [vid for vid, v in out["variants"].items() if v.get("judge", {}).get("passes")]
    out["passers"] = passers
    print("PASS:", passers or "none")
    OUT.write_text(json.dumps(out, indent=0, default=lambda x: None if isinstance(x, float) and math.isnan(x) else x))
    print("wrote", OUT.relative_to(HERE.parent.parent))


if __name__ == "__main__":
    main()
