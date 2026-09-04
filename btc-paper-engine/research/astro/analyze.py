import json, numpy as np
res = json.load(open("battery_results.json"))
ASTRO = [r for r in res if r["family"][0] in "ABCDEF"]
CTRL  = [r for r in res if r["family"] == "G_control"]
NULL  = [r for r in res if r["family"] == "H_null"]

def bh(rs, q=0.10):
    p = np.array([r["p_boot"] for r in rs]); o = np.argsort(p); m = len(p)
    thresh = q * (np.arange(1, m+1)) / m
    passed = p[o] <= thresh
    k = np.max(np.where(passed)[0]) + 1 if passed.any() else 0
    crit = p[o][k-1] if k else 0.0
    for r in rs: r["bh_pass"] = r["p_boot"] <= crit
    return crit, k

crit, k = bh(ASTRO)
print("="*78)
print(f"BATTERY: {len(ASTRO)} astrological tests | {len(CTRL)} known-real controls "
      f"| {len(NULL)} known-false nulls")
print("="*78)

def rate(rs, thr):  return sum(r["p_boot"] < thr for r in rs), len(rs)
for label, rs in (("ASTROLOGY (A-F)", ASTRO), ("CONTROLS  (G)", CTRL), ("NULLS     (H)", NULL)):
    a5, n5 = rate(rs, 0.05); a1, n1 = rate(rs, 0.01)
    print(f"{label}: p<0.05 -> {a5}/{n5} ({100*a5/n5:.1f}%)   "
          f"p<0.01 -> {a1}/{n1} ({100*a1/n1:.1f}%)   [chance: 5.0% / 1.0%]")
print()
print(f"BH-FDR q=0.10 across the {len(ASTRO)} astrological tests: "
      f"critical p={crit:.4f} -> {k} survivor(s)")
print()

print("--- 12 strongest astrological tests by bootstrap p ---")
print(f"{'test':<34}{'n_on':>6}{'edge_bps':>10}{'t':>7}{'p_boot':>9}  BH")
for r in sorted(ASTRO, key=lambda x: x["p_boot"])[:12]:
    print(f"{r['test']:<34}{r['n_on']:>6}{r['edge_bps']:>10.1f}{r['t']:>7.2f}"
          f"{r['p_boot']:>9.4f}  {'PASS' if r.get('bh_pass') else '-'}")
print()
print("--- the headline claims Casey asked about ---")
want = ["A:full_moon_day","A:full_moon_w1","A:full_moon_w3","A:new_moon_day",
        "A:new_moon_w1","A:new_moon_w3","A:waxing","A:waning",
        "B:mercury_retro","B:mercury_retro_first3","B:mercury_retro_last3",
        "B:mercury_station_w1","B:mercury_preshadow","B:mercury_postshadow",
        "B:mercury_cazimi","E:lunar_eclipse_w1","E:solar_eclipse_w1"]
byname = {r["test"]: r for r in res}
print(f"{'test':<34}{'n_on':>6}{'edge_bps':>10}{'t':>7}{'p_boot':>9}")
for w in want:
    r = byname.get(w)
    if r: print(f"{r['test']:<34}{r['n_on']:>6}{r['edge_bps']:>10.1f}{r['t']:>7.2f}{r['p_boot']:>9.4f}")
print()
print("--- known-real controls (did the battery detect anything true?) ---")
for r in sorted(CTRL, key=lambda x: x["p_boot"])[:5]:
    print(f"{r['test']:<34}{r['n_on']:>6}{r['edge_bps']:>10.1f}{r['t']:>7.2f}{r['p_boot']:>9.4f}")
print()
print("--- strongest KNOWN-FALSE null (the noise floor) ---")
for r in sorted(NULL, key=lambda x: x["p_boot"])[:3]:
    print(f"{r['test']:<34}{r['n_on']:>6}{r['edge_bps']:>10.1f}{r['t']:>7.2f}{r['p_boot']:>9.4f}")
json.dump(res, open("battery_results.json","w"), indent=1)
