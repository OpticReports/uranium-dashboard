"""Q6: the pre-named refinements against the unchanged rule (5 bps per unit traded, like Composer).
R1: SVXY (-0.5x front month) in place of ZVOL. R3: no long-vol leg (VXZ -> PULS). R2 (carry gate) is not
run: no predictor other than the rule's own trigger passed Q5. Usage: python3 q6_refine.py DATA_DIR"""
import json, math, random, sys
import lib, sim

D = sys.argv[1]; P = sim.panel(D)
VAR = {"BASE (unchanged rule)": dict(), "R1 SVXY instead of ZVOL": dict(short_fund="SVXY"), "R3 no long-vol leg": dict(long_leg=False)}
WIN = {"pre-ZVOL 2011-01..2023-04-18 (ETF-based)": ("2011-01-03", "2023-04-18"), "pre-2011 2006-07..2010-12 (futures-built)": ("2006-07-03", "2010-12-31"),
       "real era 2023-04-19..2026-11-17": ("2023-04-19", "2026-11-17")}
out = {}
rng = random.Random(20261118)
for wn, (a, b) in WIN.items():
    runs = {k: sim.run(P, cost_bps=5.0, start=a, end=b, **kw) for k, kw in VAR.items()}
    days = runs["BASE (unchanged rule)"]["days"]; n = len(days); tb = [P["BIL"][d] for d in days]
    paths = [lib.stationary_bootstrap_idx(n, 10, rng) for _ in range(2000)]
    res = {}
    for k, r in runs.items():
        s = lib.stats(r["ret"], tb)
        res[k] = {"cagr": s["cagr"], "sharpe": s["sharpe"], "maxdd": s["maxdd"], "vol": s["vol"], "worst_day": s["worst"], "cvar5": s["cvar5"],
                  "turn_per_year": sum(r["turn"]) / n * 252}
        if not k.startswith("BASE"):
            base = runs["BASE (unchanged rule)"]["ret"]; dc, dsh, ddd = [], [], []
            for p in paths:
                x = lib.stats([r["ret"][i] for i in p], [tb[i] for i in p]); y = lib.stats([base[i] for i in p], [tb[i] for i in p])
                dc.append(x["cagr"] - y["cagr"]); dsh.append(x["sharpe"] - y["sharpe"]); ddd.append(x["maxdd"] - y["maxdd"])
            q = lambda v: [sorted(v)[int(.05 * len(v))], sorted(v)[int(.95 * len(v))]]
            sb = lib.stats(base, tb)
            res[k]["vs_base"] = {"cagr": [s["cagr"] - sb["cagr"]] + q(dc), "sharpe": [s["sharpe"] - sb["sharpe"]] + q(dsh), "maxdd": [s["maxdd"] - sb["maxdd"]] + q(ddd)}
    out[wn] = res
json.dump(out, open("out/q6_refine.json", "w"), indent=1)
for wn, res in out.items():
    print("==", wn)
    for k, v in res.items():
        s = f"  {k:26s} CAGR {v['cagr']:+.1%} Sharpe {v['sharpe']:.2f} maxDD {v['maxdd']:.1%} vol {v['vol']:.1%} worst day {v['worst_day']:+.1%}"
        if "vs_base" in v:
            b = v["vs_base"]; s += f" | dCAGR {b['cagr'][0]:+.1%} [{b['cagr'][1]:+.1%}, {b['cagr'][2]:+.1%}] dSharpe {b['sharpe'][0]:+.2f} [{b['sharpe'][1]:+.2f}, {b['sharpe'][2]:+.2f}] dMaxDD {b['maxdd'][0]:+.1%} [{b['maxdd'][1]:+.1%}, {b['maxdd'][2]:+.1%}]"
        print(s)
