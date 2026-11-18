"""EXPLORATORY (not pre-registered; labelled as such in the report).
(a) risk-matched: replace HARV's 15% with x% switcher + (15-x)% T-bills, x chosen so the book's volatility
    equals KEEP's. Which earns more per unit of risk? (b) is the edge fading: rolling one-year net return
    of the rule over 2006-2026, calendar-year ranks, and the last 252 sessions against all earlier windows.
(c) dollars at stake today: ZVOL held into the 2026-11-18 ex-date. Usage: python3 q7_extra.py DATA_DIR"""
import json, math, sys
import lib, sim
import q4_books as q4            # reuses the engines and lenses (re-runs its bootstrap on import; slow but simple)

D = sys.argv[1]
out = {}
allidx = list(range(q4.n))
for ln, sh in q4.LENSES.items():
    keep = q4.metrics(q4.book_rets(q4.BOOKS["KEEP 29/29/27/15"], allidx, sh), q4.R["BIL"])
    lo, hi = 0.0, 0.15
    for _ in range(40):
        x = (lo + hi) / 2
        m = q4.metrics(q4.book_rets((.29, .29, .27, 0, x, .15 - x), allidx, sh), q4.R["BIL"])
        if m["vol"] < keep["vol"]:
            lo = x
        else:
            hi = x
    m = q4.metrics(q4.book_rets((.29, .29, .27, 0, x, .15 - x), allidx, sh), q4.R["BIL"])
    out.setdefault("risk_matched", {})[ln] = {"switcher_share": x, "keep": keep, "matched": m}
P = sim.panel(D); r = sim.run(P, cost_bps=5.0)
n = len(r["days"]); roll = []
for i in range(252, n + 1):
    w = r["ret"][i - 252:i]
    roll.append((r["days"][i - 1], math.prod(1 + x for x in w) - 1))
last = roll[-1][1]; prior = [x for d, x in roll if d < "2023-04-19"]
out["rolling_1y"] = {"last": last, "last_date": roll[-1][0], "share_of_pre_ZVOL_windows_below": sum(1 for x in prior if x <= last) / len(prior),
                     "pre_ZVOL_median": sorted(prior)[len(prior) // 2], "pre_ZVOL_p10": sorted(prior)[int(.1 * len(prior))], "pre_ZVOL_p90": sorted(prior)[int(.9 * len(prior))],
                     "share_negative_pre_ZVOL": sum(1 for x in prior if x < 0) / len(prior)}
out["rolling_series"] = roll[::5]
snap = json.load(open(D + "/snapshots.json"))["2026-11-17"]["symphonies"]
z = lib.load("ZVOL", D + "/cache")["rows"]["2026-11-17"]["close"]
ex = {}
for k, i in (("HARV", "ORQNCfZnA18wmsMWVhf8"), ("KMLM", "YPTSJFJwD2ZKfAeYJUbW")):
    s = snap[i]; w = s["holdings"].get("ZVOL", 0.0)
    ex[k] = {"value": s["value"], "zvol_weight": w, "shares": s["value"] * w / z, "distribution_usd": s["value"] * w / z * 0.485,
             "displayed_drop": w * 0.485 / z}
out["ex_date_2026_11_18"] = ex
json.dump(out, open("out/q7_extra.json", "w"), indent=1)
for ln, v in out["risk_matched"].items():
    k, m = v["keep"], v["matched"]
    print(f"{ln}: HARV 15% -> {v['switcher_share']:.1%} switcher + {0.15 - v['switcher_share']:.1%} bills | KEEP CAGR {k['cagr']:+.1%} DD {k['maxdd']:.1%} worst21 {k['worst21']:+.1%} | matched CAGR {m['cagr']:+.1%} DD {m['maxdd']:.1%} worst21 {m['worst21']:+.1%} (vol {k['vol']:.1%} = {m['vol']:.1%})")
print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in out["rolling_1y"].items()})
print(json.dumps(ex, default=lambda x: round(x, 4)))
