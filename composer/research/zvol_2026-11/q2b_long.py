"""Q2/Q3 on the long path: does the rule's timing hold outside the real-ZVOL era it was adopted on?
Usage: python3 q2b_long.py DATA_DIR"""
import json, math, sys
import lib, sim

D = sys.argv[1]; P = sim.panel(D)
ERAS = [("2006-07..2010-12 (futures-built)", "2006-07-03", "2010-12-31"), ("2011-01..2017-12", "2011-01-01", "2017-12-31"),
        ("2018-01..2023-04-18", "2018-01-01", "2023-04-18"), ("pre-ZVOL all (2006-07..2023-04-18)", "2006-07-03", "2023-04-18"),
        ("real ZVOL era (2023-04-19..2026-11-17)", "2023-04-19", "2026-11-17"), ("full", "2006-07-03", "2026-11-17")]
out = {"eras": {}, "years": {}}
for name, a, b in ERAS:
    r = sim.run(P, start=a, end=b, cost_bps=5.0)
    n = len(r["days"]); tb = [P["BIL"][d] for d in r["days"]]
    F = ("ZVOL", "VXZ", "PULS")
    aw = {t: sum(w[t] for w in r["w"]) / n for t in F}
    static = [sum(aw[t] * P[t][d] for t in F) for d in r["days"]]
    alw = [P["ZVOL"][d] for d in r["days"]]
    obs = sum(r["gross"])
    R = {t: [P[t][d] for d in r["days"]] for t in F}; W = {t: [w[t] for w in r["w"]] for t in F}
    step = max(1, (n - 40) // 1000)
    sh = [sum(sum(W[t][(i + k) % n] * R[t][i] for t in F) for i in range(n)) for k in range(20, n - 20, step)]
    zx = sum(W["ZVOL"][i] * (R["ZVOL"][i] - R["PULS"][i]) for i in range(n)); vx = sum(W["VXZ"][i] * (R["VXZ"][i] - R["PULS"][i]) for i in range(n))
    zsh = [sum(W["ZVOL"][(i + k) % n] * (R["ZVOL"][i] - R["PULS"][i]) for i in range(n)) for k in range(20, n - 20, step)]
    vsh = [sum(W["VXZ"][(i + k) % n] * (R["VXZ"][i] - R["PULS"][i]) for i in range(n)) for k in range(20, n - 20, step)]
    out["eras"][name] = {"n": n, "net": lib.stats(r["ret"], tb), "gross": lib.stats(r["gross"], tb), "static_mix": lib.stats(static, tb),
                         "always_short_midterm": lib.stats(alw, tb), "tbills_cagr": lib.stats(tb)["cagr"], "avg_w": aw,
                         "placebo_p": sum(1 for x in sh if x >= obs) / len(sh),
                         "zvol_leg_excess": zx, "zvol_leg_placebo_p": sum(1 for x in zsh if x >= zx) / len(zsh),
                         "vxz_leg_excess": vx, "vxz_leg_placebo_p": sum(1 for x in vsh if x >= vx) / len(vsh),
                         "zvol_bps_when_held": 1e4 * sum(W["ZVOL"][i] * R["ZVOL"][i] for i in range(n)) / max(1e-12, sum(W["ZVOL"])),
                         "zvol_bps_all_days": 1e4 * sum(R["ZVOL"]) / n,
                         "vxz_bps_when_held": 1e4 * sum(W["VXZ"][i] * R["VXZ"][i] for i in range(n)) / max(1e-12, sum(W["VXZ"])),
                         "vxz_bps_all_days": 1e4 * sum(R["VXZ"]) / n}
full = sim.run(P, cost_bps=5.0)
for y in range(2006, 2027):
    idx = [i for i, d in enumerate(full["days"]) if d[:4] == str(y)]
    if idx:
        rr = [full["ret"][i] for i in idx]
        out["years"][y] = {"net": math.prod(1 + x for x in rr) - 1, "maxdd": lib.stats(rr)["maxdd"],
                           "zvol_leg": sum(full["w"][i]["ZVOL"] * P["ZVOL"][full["days"][i]] for i in idx),
                           "vxz_leg": sum(full["w"][i]["VXZ"] * P["VXZ"][full["days"][i]] for i in idx),
                           "always_short": math.prod(1 + P["ZVOL"][full["days"][i]] for i in idx) - 1,
                           "tbills": math.prod(1 + P["BIL"][full["days"][i]] for i in idx) - 1, "worst_day": min(rr)}
json.dump({"days": full["days"], "ret": full["ret"], "gross": full["gross"], "w": full["w"]}, open(D + "/long_path.json", "w"))
json.dump(out, open("out/q2b_long.json", "w"), indent=1)
f = lambda x: f"{x:+.1%}" if isinstance(x, float) else str(x)
for k, v in out["eras"].items():
    print(f"{k}: n={v['n']} | net {f(v['net']['cagr'])} Sharpe {v['net']['sharpe']:.2f} maxDD {v['net']['maxdd']:.1%} worst day {f(v['net']['worst'])} | gross {f(v['gross']['cagr'])} | static mix {f(v['static_mix']['cagr'])} | always short mid-term {f(v['always_short_midterm']['cagr'])} DD {v['always_short_midterm']['maxdd']:.0%} | bills {f(v['tbills_cagr'])} | placebo p {v['placebo_p']:.3f} | ZVOL leg {v['zvol_leg_excess']:+.2f} (p {v['zvol_leg_placebo_p']:.3f}; {v['zvol_bps_when_held']:.0f} vs {v['zvol_bps_all_days']:.1f} bps) | VXZ leg {v['vxz_leg_excess']:+.2f} (p {v['vxz_leg_placebo_p']:.3f}; {v['vxz_bps_when_held']:.0f} vs {v['vxz_bps_all_days']:.1f} bps)")
for y, v in out["years"].items():
    print(y, "net", f(v["net"]), "maxDD", f"{v['maxdd']:.1%}", "ZVOL leg", f"{v['zvol_leg']:+.3f}", "VXZ leg", f"{v['vxz_leg']:+.3f}", "always-short", f(v["always_short"]), "bills", f(v["tbills"]), "worst day", f(v["worst_day"]))
