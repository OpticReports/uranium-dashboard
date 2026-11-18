"""Q3: what the harvester holds around volatility spikes, and how its ZVOL entries pay.
Usage: python3 q3_events.py DATA_DIR"""
import json, math, sys
import lib, sim

D = sys.argv[1]; C = D + "/cache"; P = sim.panel(D)
r = sim.run(P, cost_bps=5.0)
days = r["days"]; idx = {d: i for i, d in enumerate(days)}
vix = lib.series("^VIX", C, "close"); v3 = lib.series("^VIX3M", C, "close")
vd = [d for d in sorted(vix) if d <= lib.END]
# spike definitions
sp1 = [vd[i] for i in range(1, len(vd)) if vix[vd[i]] / vix[vd[i - 1]] - 1 >= 0.15]
sp2 = []
for i in range(252, len(vd)):
    win = sorted(vix[x] for x in vd[i - 252:i]); p90 = win[int(.9 * 252)]
    if vix[vd[i]] > p90 and vix[vd[i - 1]] <= sorted(vix[x] for x in vd[i - 253:i - 1])[int(.9 * 252)]:
        sp2.append(vd[i])
out = {}
for name, ev, lo in (("VIX +15% in a day", sp1, "2006-07-10"), ("VIX crosses above its 1-year 90th percentile", sp2, "2006-07-10")):
    for era, a, b in (("pre-ZVOL 2006-07..2023-04", lo, "2023-04-18"), ("real era 2023-04..2026-11", "2023-04-19", "2026-11-17")):
        E = [d for d in ev if a <= d <= b and d in idx and 5 <= idx[d] < len(days) - 10]
        prof = {k: {"zvol": 0.0, "vxz": 0.0, "puls": 0.0, "ret": 0.0, "zfund": 0.0} for k in range(-5, 11)}
        cum = []
        for d in E:
            i = idx[d]; c = 0.0
            for k in range(-5, 11):
                w = r["w"][i + k]                    # weights held INTO day i+k
                prof[k]["zvol"] += w["ZVOL"]; prof[k]["vxz"] += w["VXZ"]; prof[k]["puls"] += w["PULS"]
                prof[k]["ret"] += r["ret"][i + k]; prof[k]["zfund"] += P["ZVOL"][days[i + k]]
            cum.append({"day0": r["ret"][i], "d1_10": math.prod(1 + r["ret"][i + k] for k in range(1, 11)) - 1,
                        "m5_10": math.prod(1 + r["ret"][i + k] for k in range(-5, 11)) - 1,
                        "short_d0": P["ZVOL"][d], "short_1_10": math.prod(1 + P["ZVOL"][days[i + k]] for k in range(1, 11)) - 1})
        m = len(E) or 1
        out[f"{name} | {era}"] = {"n": len(E), "profile": {k: {q: v / m for q, v in p.items()} for k, p in prof.items()},
                                  "harv_day0_mean": sum(c["day0"] for c in cum) / m, "harv_d1_10_mean": sum(c["d1_10"] for c in cum) / m,
                                  "harv_m5_10_mean": sum(c["m5_10"] for c in cum) / m, "harv_m5_10_win": sum(1 for c in cum if c["m5_10"] > 0) / m,
                                  "always_short_day0_mean": sum(c["short_d0"] for c in cum) / m, "always_short_1_10_mean": sum(c["short_1_10"] for c in cum) / m,
                                  "harv_m5_10_worst": min((c["m5_10"] for c in cum), default=None)}
# ZVOL entries: weight rises from 0
ent = [i for i in range(1, len(days)) if r["w"][i]["ZVOL"] > 1e-9 and r["w"][i - 1]["ZVOL"] <= 1e-9]
epis = []
for i in ent:
    j = i
    while j < len(days) and r["w"][j]["ZVOL"] > 1e-9:
        j += 1
    leg = sum(r["w"][k]["ZVOL"] * P["ZVOL"][days[k]] for k in range(i, j))          # contribution to the sleeve
    d0 = days[i - 1]                                                                # decision day
    ts = (v3.get(d0) / vix.get(d0) - 1) if (v3.get(d0) and vix.get(d0)) else None
    epis.append({"decided": d0, "days": j - i, "leg": leg, "peak_w": max(r["w"][k]["ZVOL"] for k in range(i, j)),
                 "fund": math.prod(1 + P["ZVOL"][days[k]] for k in range(i, j)) - 1, "vix3m_over_vix": ts, "vix": vix.get(d0)})
def summ(E):
    if not E:
        return {"n": 0}
    f = [e["fund"] for e in E]
    return {"n": len(E), "mean_fund_return": sum(f) / len(f), "median": sorted(f)[len(f) // 2], "win": sum(1 for x in f if x > 0) / len(f),
            "worst": min(f), "best": max(f), "sum_leg": sum(e["leg"] for e in E), "avg_days": sum(e["days"] for e in E) / len(E)}
out["zvol_episodes"] = {}
for era, a, b in (("pre-ZVOL 2006-07..2023-04", "2006-07-03", "2023-04-18"), ("real era 2023-04..2026-11", "2023-04-19", "2026-11-17"), ("2026", "2026-01-01", "2026-11-17")):
    E = [e for e in epis if a <= e["decided"] <= b]
    out["zvol_episodes"][era] = {"all": summ(E), "contango (VIX3M > VIX)": summ([e for e in E if e["vix3m_over_vix"] is not None and e["vix3m_over_vix"] > 0]),
                                 "inverted (VIX3M <= VIX)": summ([e for e in E if e["vix3m_over_vix"] is not None and e["vix3m_over_vix"] <= 0]),
                                 "VIX < 20": summ([e for e in E if e["vix"] and e["vix"] < 20]), "VIX 20-30": summ([e for e in E if e["vix"] and 20 <= e["vix"] < 30]),
                                 "VIX >= 30": summ([e for e in E if e["vix"] and e["vix"] >= 30])}
out["episodes_2026"] = [e for e in epis if e["decided"] >= "2026-01-01"]
out["worst_episodes"] = sorted(epis, key=lambda e: e["leg"])[:12]
json.dump(out, open("out/q3_events.json", "w"), indent=1)
pc = lambda x: f"{x:+.2%}" if isinstance(x, float) else str(x)
for k, v in out.items():
    if "|" in k:
        pr = v["profile"]
        print(k, "n", v["n"], "| HARV day0", pc(v["harv_day0_mean"]), "d+1..+10", pc(v["harv_d1_10_mean"]), "d-5..+10", pc(v["harv_m5_10_mean"]), "win", f"{v['harv_m5_10_win']:.0%}", "worst", pc(v["harv_m5_10_worst"]), "| always-short day0", pc(v["always_short_day0_mean"]), "d+1..+10", pc(v["always_short_1_10_mean"]))
        print("    ZVOL weight by day:", {kk: round(pr[kk]["zvol"], 2) for kk in (-5, -3, -1, 0, 1, 2, 3, 5, 10)}, "| VXZ:", {kk: round(pr[kk]["vxz"], 2) for kk in (-5, -3, -1, 0, 1, 2, 3, 5, 10)})
for era, v in out["zvol_episodes"].items():
    print("episodes", era)
    for g, s in v.items():
        if s["n"]:
            print(f"    {g:26s} n {s['n']:4d} mean {pc(s['mean_fund_return'])} median {pc(s['median'])} win {s['win']:.0%} worst {pc(s['worst'])} best {pc(s['best'])} sum leg {s['sum_leg']:+.3f} avg days {s['avg_days']:.1f}")
print("2026 episodes:", [(e["decided"], e["days"], round(e["peak_w"], 2), pc(e["fund"]), pc(e["leg"])) for e in out["episodes_2026"]])
print("worst:", [(e["decided"], e["days"], pc(e["fund"]), pc(e["leg"])) for e in out["worst_episodes"]])
