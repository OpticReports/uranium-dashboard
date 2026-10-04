"""C1 - POST-HOC combinations, built AFTER reading the pre-registered table.
Everything here is in-sample selection by construction and is labelled so
in the report. Run after run.py:

    python -m research.xbi_strategies.combos
"""
from __future__ import annotations

import json
import math

import numpy as np

from research.xbi_strategies.run import JUDGE, OUT, SUBPERIODS, judge
from research.xbi_strategies.xbi_lib import Market, first_index_on_or_after, simulate, stats, weekly

VOL_TARGET = 0.20


def build(m: Market) -> dict[str, tuple[int, callable, str]]:
    start = first_index_on_or_after(m, "2007-11-15")      # same amended start as run.py
    vol60 = {s: m.vol(s, 60) for s in ("XBI", "TLT", "GLD")}
    sma200 = m.sma("XBI", 200)
    px = m.px["XBI"]

    def inv_vol(i):
        iv = {s: 1.0 / vol60[s][i] for s in vol60 if vol60[s][i] > 0}
        tot = sum(iv.values())
        return {s: v / tot for s, v in iv.items()} if tot else {}

    def port_vol(w, i):                     # realized 60d vol of the weighted mix, through i
        syms = list(w)
        R = np.array([m.ret[s][i - 59:i + 1] for s in syms])
        if np.isnan(R).any():
            return float("nan")
        p = np.array([w[s] for s in syms]) @ R
        return p.std(ddof=1) * math.sqrt(252)

    def monthly(fn):                        # decide at month-end, drift in between (None = no trade)
        def f(i, st):
            if m.month_end[i] or "w" not in st:
                st["w"] = fn(i)
                return st["w"]
            return None
        return f

    def c1a(i):                             # R1 levered to a 20% vol target, cap 2.0, margin cost
        w = inv_vol(i)
        pv = port_vol(w, i) if w else float("nan")
        k = min(2.0, VOL_TARGET / pv) if pv and pv == pv and pv > 0 else 1.0
        return {s: x * k for s, x in w.items()}

    def c1b(i):                             # R1 with the XBI sleeve gated by SMA200 (sleeve to BIL when below)
        w = inv_vol(i)
        if "XBI" in w and not px[i] > sma200[i]:
            w.pop("XBI")
        return w

    def c1c(i):                             # naive thirds, same assets: is R1 the inverse-vol trick or the assets?
        return {"XBI": 1 / 3, "TLT": 1 / 3, "GLD": 1 / 3}

    def c1d(i):                             # XBI sleeve fixed at 50%, rest split TLT/GLD by inverse vol
        iv = {s: 1.0 / vol60[s][i] for s in ("TLT", "GLD") if vol60[s][i] > 0}
        tot = sum(iv.values())
        w = {"XBI": 0.5}
        w.update({s: 0.5 * v / tot for s, v in iv.items()})
        return w

    return {"C1a": (start, monthly(c1a), "POST-HOC: inverse-vol XBI/TLT/GLD levered to 20% vol (cap 2.0, margin)"),
            "C1b": (start, monthly(c1b), "POST-HOC: inverse-vol XBI/TLT/GLD, XBI leg gated by SMA200"),
            "C1c": (start, monthly(c1c), "POST-HOC: equal thirds XBI/TLT/GLD (is R1 the assets or the sizing?)"),
            "C1d": (start, monthly(c1d), "POST-HOC: XBI 50% + TLT/GLD inverse-vol 50%")}


def main() -> None:
    m = Market()
    out = json.loads(OUT.read_text())
    end = m.n - 1
    b0 = simulate(m, lambda i, st: {"XBI": 1.0}, first_index_on_or_after(m, "2007-11-15"))["eq"]
    for vid, (start, rule, note) in build(m).items():
        res = simulate(m, rule, start)
        eq = res["eq"]
        full = stats(m.d, eq, start, end)
        subs, bsubs = {}, {}
        for k, a, b in SUBPERIODS:
            i0 = max(start, first_index_on_or_after(m, a))
            i1 = min(end, max(i for i in range(m.n) if m.dates[i] <= b))
            subs[k] = stats(m.d, eq, i0, i1)
            bsubs[k] = stats(m.d, b0, i0, i1)
        bfull = stats(m.d, b0, start, end)
        out["variants"][vid] = {"note": note, "start": m.dates[start], "full": full, "subperiods": subs,
                                "turnover_py": res["turnover_py"], "cost_drag_py": res["cost_drag_py"],
                                "avg_gross": res["avg_gross"], "post_hoc": True,
                                "bench_same_window": {"full": bfull, "subperiods": bsubs},
                                "judge": judge(full, subs, bfull, bsubs),
                                "curve_weekly": weekly(m.d, eq, start, end)}
        print(f"{vid:3s} {full['cagr']:+7.1%} dd {full['max_dd']:6.1%} sh {full['sharpe']:5.2f} "
              f"cal {full['calmar']:5.2f} gross {res['avg_gross']:4.2f}  {note}")
    out["passers_post_hoc"] = [v for v in ("C1a", "C1b", "C1c", "C1d") if out["variants"][v]["judge"]["passes"]]
    print("POST-HOC PASS:", out["passers_post_hoc"] or "none", "| judge:", JUDGE)
    OUT.write_text(json.dumps(out, indent=0, default=lambda x: None if isinstance(x, float) and math.isnan(x) else x))


if __name__ == "__main__":
    main()
