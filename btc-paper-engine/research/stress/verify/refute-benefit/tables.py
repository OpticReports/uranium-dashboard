import json, os, numpy as np
HERE = "/home/user/uranium-dashboard/btc-paper-engine/research/stress"; RUNS = os.path.join(HERE, "runs")
cj = json.load(open(os.path.join(HERE, "candidates.json")))
sw = json.load(open("sweep.json"))
CRASH_OFFS = {s: [int(k.replace("off", "").replace("+", "")) for k in cj["crash"][s]["crash_offsets"]] for s in ["COVID", "2008", "1999"]}
print("crash-path offsets used for the range:", CRASH_OFFS)
print("\n=== +-30% SWEEP: registered decision test per variant (offset-0 maxDD and range-worst vs baseline; 2019+ and ACTIVE-era $/yr) ===")
base = {s: cj["crash"][s]["runs"]["baseline"] for s in CRASH_OFFS}
def okey(o): return f"off{o:+d}" if o else "off+0"
b19 = cj["eras"]["2019+ (2019-01-01..2026-10-07)"]["runs"]["baseline"]["usd_per_year"]
bE = {e: cj["eras"][e]["runs"]["baseline"]["usd_per_year"] for e in ["E3 2020-21", "E4 2022-24H1", "E5 2024H2-26"]}
yrs = {}
for e, pref in [("E3 2020-21", "E3"), ("E4 2022-24H1", "E4"), ("E5 2024H2-26", "E5")]:
    yrs[e] = json.load(open(os.path.join(RUNS, f"{pref}_K0.75_off_0_A_intra_eh_first_cross_nocarry_bfund_csv.json")))["years"]
pooled_base = sum(bE[e] * yrs[e] for e in bE) / sum(yrs.values())
rows = []
# registered candidates first (from candidates.json) then the sweep variants
def line(label, get_crash, get_era):
    all_ok, any_better, parts = True, False, []
    for s in CRASH_OFFS:
        b0, c0 = base[s]["off+0"]["max_dd"], get_crash(s, 0)["max_dd"]
        br = min(base[s][okey(o)]["max_dd"] for o in CRASH_OFFS[s]); cr = min(get_crash(s, o)["max_dd"] for o in CRASH_OFFS[s])
        n_worse = sum(1 for o in [-28, -14, 0, 14, 28] if get_crash(s, o)["max_dd"] < base[s][okey(o)]["max_dd"] - 1e-9)
        n_worse12 = sum(1 for o in [-28, -14, 0, 14, 28] if get_crash(s, o)["b12"] < base[s][okey(o)]["balances"]["365"] - 1)
        ok = c0 >= b0 - 1e-9 and cr >= br - 1e-9
        all_ok &= ok; any_better |= (c0 > b0 + 1e-9) or (cr > br + 1e-9)
        parts.append(f"{s:5s} dd0 {b0:6.1%}->{c0:6.1%} rng {br:6.1%}->{cr:6.1%} worse@{n_worse}/5 offs, 12m worse@{n_worse12}/5 {'ok' if ok else 'FAIL'}")
    y19 = get_era("Y2019plus"); yE = {e: get_era(e) for e in bE}
    pooled = sum(yE[e] * yrs[e] for e in bE) / sum(yrs.values())
    verdict = "PROPOSE" if (all_ok and any_better and y19 / b19 >= 0.9) else "DO NOT PROPOSE"
    verdict_active = "pass" if (all_ok and any_better and pooled / pooled_base >= 0.9) else "fail"
    print(f"{label:28s} {verdict:15s} | " + " | ".join(parts) + f" | 2019+ {y19 / b19:6.1%} | active-era pooled {pooled / pooled_base:6.1%} (E3 {yE['E3 2020-21'] / bE['E3 2020-21']:.0%} E4 {yE['E4 2022-24H1'] / bE['E4 2022-24H1']:.0%} E5 {yE['E5 2024H2-26'] / bE['E5 2024H2-26']:.0%}) -> with active-era cost test: {verdict_active}")
for cand in ["C1", "C2", "C1+C2"]:
    line(f"{cand} (registered)",
         lambda s, o, c=cand: dict(max_dd=cj["crash"][s]["runs"][c][okey(o)]["max_dd"], b12=cj["crash"][s]["runs"][c][okey(o)]["balances"]["365"]),
         lambda e, c=cand: cj["eras"]["2019+ (2019-01-01..2026-10-07)" if e == "Y2019plus" else e]["runs"][c]["usd_per_year"])
emap = {"E3 2020-21": "E3", "E4 2022-24H1": "E4", "E5 2024H2-26": "E5", "Y2019plus": "Y2019plus"}
for label, V in sw.items():
    line(label, lambda s, o, V=V: V["crash"][s][str(o)], lambda e, V=V: V["eras"][emap[e]]["usd_per_year"])
print(f"\nbaseline pooled active-era $/yr (E3+E4+E5, {sum(yrs.values()):.2f} yrs): {pooled_base:,.0f}; 2019+ baseline {b19:,.0f}")

print("\n=== uniform cut at the registered C1/C2/C1+C2 exposure ratios: pooled active-era $/yr ===")
BAR = 14400
def exposure(r, leg):
    n = r["n_path_bars"]; tot = 0.0
    for t in r["trades"]:
        if t["leg"] != leg: continue
        end = t["exit_ts"] if t["exit_ts"] is not None else r["ts"][-1] + BAR
        tot += t["qty"] * t["entry_px"] * max(1, (end - t["entry_ts"]) // BAR)
    return tot / n
for cand, tag in [("C1", "_optC1"), ("C2", "_optC2"), ("C1+C2", "_optC1_C2")]:
    tot_c, tot_u, tot_b = 0.0, 0.0, 0.0
    for e, pref in [("E3 2020-21", "E3"), ("E4 2022-24H1", "E4"), ("E5 2024H2-26", "E5")]:
        b = json.load(open(os.path.join(RUNS, f"{pref}_K0.75_off_0_A_intra_eh_first_cross_nocarry_bfund_csv.json")))
        c = json.load(open(os.path.join(RUNS, f"{pref}_K0.75_off_0_A_intra_eh_first_cross_nocarry_bfund_csv{tag}.json")))
        r_pb = exposure(c, "pullback") / exposure(b, "pullback")
        pb = np.asarray(b["leg_mtm"]["pullback"]); tr = np.asarray(b["leg_mtm"]["trend"])
        tot_b += b["equity_btc"][-1] - 70000; tot_c += c["equity_btc"][-1] - 70000; tot_u += r_pb * pb[-1] + tr[-1]
    Y = sum(yrs.values())
    print(f"{cand:6s} pooled $/yr base {tot_b / Y:,.0f} cand {tot_c / Y:,.0f} ({tot_c / tot_b:.1%}) uniform-cut {tot_u / Y:,.0f} ({tot_u / tot_b:.1%})")

print("\n=== 2019+ C1 decomposition: gross vs net, vs the proposal's '15 winners -5.6k / 3 stops +2.2k' ===")
b = json.load(open(os.path.join(RUNS, "Y2019plus_K0.75_off_0_A_intra_eh_first_cross_nocarry_bfund_csv.json")))
c = json.load(open(os.path.join(RUNS, "Y2019plus_K0.75_off_0_A_intra_eh_first_cross_nocarry_bfund_csv_optC1.json")))
pb0 = {t["entry_ts"]: t for t in b["trades"] if t["leg"] == "pullback"}; pb1 = {t["entry_ts"]: t for t in c["trades"] if t["leg"] == "pullback"}
rs = [(pb0[k], pb1[k]) for k in pb0 if abs(pb1[k]["qty"] - pb0[k]["qty"]) > 1e-9]
for key in ["pnl", "gross"]:
    w = [(a[key], b_[key]) for a, b_ in rs if a[key] > 0]; l = [(a[key], b_[key]) for a, b_ in rs if a[key] <= 0]
    print(f"  by {key:5s}: winners {len(w)} forgone {sum(y - x for x, y in w):+8,.0f} | losers {len(l)} saved {sum(y - x for x, y in l):+8,.0f} | net {sum(y - x for x, y in w) + sum(y - x for x, y in l):+8,.0f}")
stops = [(a, b_) for a, b_ in rs if a["reason"] == "STOP"]
print(f"  resized trades with reason STOP: {len(stops)} saved {sum(b_['pnl'] - a['pnl'] for a, b_ in stops):+8,.0f}; non-STOP resized: {len(rs) - len(stops)} delta {sum(b_['pnl'] - a['pnl'] for a, b_ in rs if a['reason'] != 'STOP'):+8,.0f}")
print(f"  total pullback realised delta {sum(t['pnl'] for t in pb1.values()) - sum(t['pnl'] for t in pb0.values()):+8,.0f}; $/yr delta x years {(cj['eras']['2019+ (2019-01-01..2026-10-07)']['runs']['C1']['usd_per_year'] - b19) * b['years']:+8,.0f}")
