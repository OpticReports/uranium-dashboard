"""Refuter step A: recompute candidate vs baseline from the SAVED run files
(no re-run), compare to candidates.json, and decompose each candidate's
delta into the pullback trades it resized. Also exposure ratios."""
import json, glob, os, sys
import numpy as np
HERE = "/home/user/uranium-dashboard/btc-paper-engine/research/stress"
RUNS = os.path.join(HERE, "runs")
cj = json.load(open(os.path.join(HERE, "candidates.json")))
BAR = 14400

def max_dd(eq, start=100000.0):
    eq = np.asarray(eq, float); peak = np.maximum.accumulate(np.concatenate([[start], eq]))[1:]
    return float(np.min(eq / peak - 1.0))

def bal365(r):
    return r["balances"]["365"]["equity"]

def exposure(r, leg):
    """bar-weighted mean gross notional of one leg over the path (qty x entry px x bars held / n bars)"""
    n = r["n_path_bars"]
    tot = 0.0
    for t in r["trades"]:
        if t["leg"] != leg: continue
        end = t["exit_ts"] if t["exit_ts"] is not None else r["ts"][-1] + BAR
        bars = max(1, (end - t["entry_ts"]) // BAR)
        tot += t["qty"] * t["entry_px"] * bars
    return tot / n

tags = {"baseline": "", "C1": "_optC1", "C2": "_optC2", "C1+C2": "_optC1_C2"}
OFFS = ["off-28", "off-14", "off_0", "off_14", "off_28"]
okey = {"off-28": "off-28", "off-14": "off-14", "off_0": "off+0", "off_14": "off+14", "off_28": "off+28"}
mism = 0
SKIP=False
print("=== CRASH: recompute from run files vs candidates.json (12m | maxDD close | maxDD intrabar) ===")
for scen in ["COVID", "2008", "1999"]:
    S = cj["crash"][scen]
    for cfg, tag in tags.items():
        row = []
        for off in OFFS:
            f = os.path.join(RUNS, f"{scen}_K0.75_{off}_A_intra_eh_first_cross_carryXBTUSD_bfund_csv{tag}.json")
            r = json.load(open(f))
            assert r["options"]["tag"] == ("base" if cfg == "baseline" else cfg), (f, r["options"])
            b = bal365(r); dd = max_dd(r["equity_total"]); ddi = r["max_dd_intrabar"]
            s = S["runs"][cfg][okey[off]]
            ok = abs(b - s["balances"]["365"]) < 0.01 and abs(dd - s["max_dd"]) < 1e-4 and abs(dd - r["max_dd"]) < 1e-4
            mism += (not ok)
            if not SKIP: row.append(f"{okey[off]}: {b:>9,.0f} {dd:7.2%} {ddi:7.2%}{'' if ok else ' MISMATCH'}")
        crash_offs = S["crash_offsets"]
        dds = [max_dd(json.load(open(os.path.join(RUNS, f"{scen}_K0.75_{off}_A_intra_eh_first_cross_carryXBTUSD_bfund_csv{tag}.json")))["equity_total"]) for off in OFFS if okey[off] in crash_offs]
        worst = min(dds)
        ok2 = abs(worst - S["range"][cfg]["max_dd_worst"]) < 1e-4
        mism += (not ok2)
        if not SKIP: print(f"{scen:5s} {cfg:8s} | " + " | ".join(row) + f" | range-worst {worst:7.2%}{'' if ok2 else ' MISMATCH'}")
print("mismatches:", mism)

print("\n=== CRASH offset 0: candidate delta decomposed into resized pullback trades (saved trades) ===")
for scen in ["COVID", "2008", "1999"]:
    base = json.load(open(os.path.join(RUNS, f"{scen}_K0.75_off_0_A_intra_eh_first_cross_carryXBTUSD_bfund_csv.json")))
    pb0 = {t["entry_ts"]: t for t in base["trades"] if t["leg"] == "pullback"}
    for cfg in ["C1", "C2", "C1+C2"]:
        r = json.load(open(os.path.join(RUNS, f"{scen}_K0.75_off_0_A_intra_eh_first_cross_carryXBTUSD_bfund_csv{tags[cfg]}.json")))
        pb1 = {t["entry_ts"]: t for t in r["trades"] if t["leg"] == "pullback"}
        assert pb0.keys() == pb1.keys()
        d_closed = sum(pb1[k]["pnl"] - pb0[k]["pnl"] for k in pb0)
        d_open = (r["leg_mtm"]["pullback"][-1] - base["leg_mtm"]["pullback"][-1]) - d_closed
        d_total = r["final_equity"] - base["final_equity"]
        resized = [(k, pb0[k], pb1[k]) for k in pb0 if abs(pb1[k]["qty"] - pb0[k]["qty"]) > 1e-9]
        win = [(a["pnl"], b["pnl"]) for _, a, b in resized if a["pnl"] > 0]
        los = [(a["pnl"], b["pnl"]) for _, a, b in resized if a["pnl"] <= 0]
        print(f"{scen:5s} {cfg:6s} d12m {d_total:+9,.0f} | closed pb delta {d_closed:+9,.0f} open/other {d_open:+7,.0f} | resized {len(resized)}/{len(pb0)}: "
              f"losers {len(los)} saved {sum(b - a for a, b in los):+8,.0f}, winners {len(win)} forgone {sum(b - a for a, b in win):+8,.0f} | "
              f"pb exposure ratio {exposure(r, 'pullback') / exposure(base, 'pullback'):.3f} (trend {exposure(r, 'trend') / exposure(base, 'trend'):.3f})")
        for k, a, b in resized:
            print(f"      {a['entry_date']} {a['side']} {a['reason']:6s} mult {a['size_mult']:.2f}->{b['size_mult']:.2f} (live {b['mult_live']:.2f} fast {b['mult_fast']:.2f} damp {b['damp']:.2f}) pnl {a['pnl']:+8,.0f} -> {b['pnl']:+8,.0f}")

print("\n=== ERAS: recompute $/yr and maxDD from run files; decomposition of candidate delta; exposure ratio ===")
era_files = {"E2 2017-19": "E2", "E3 2020-21": "E3", "E4 2022-24H1": "E4", "E5 2024H2-26": "E5", "2019+ (2019-01-01..2026-10-07)": "Y2019plus"}
for ename, pref in era_files.items():
    base = json.load(open(os.path.join(RUNS, f"{pref}_K0.75_off_0_A_intra_eh_first_cross_nocarry_bfund_csv.json")))
    pb0 = {t["entry_ts"]: t for t in base["trades"] if t["leg"] == "pullback"}
    tr0 = [t for t in base["trades"] if t["leg"] == "trend"]
    yr0 = (base["equity_btc"][-1] - 70000) / base["years"]
    pb_real0 = sum(t["pnl"] for t in pb0.values())
    print(f"{ename:32s} baseline $/yr {yr0:9,.0f} (json {cj['eras'][ename]['runs']['baseline']['usd_per_year']:9,.0f}) maxDD {max_dd(base['equity_total']):7.2%} | pb trades {len(pb0)} realised {pb_real0:+9,.0f} | trend trades {len(tr0)} realised {sum(t['pnl'] for t in tr0):+9,.0f} | S3 halt {base['engine_halts_info']['pullback']['halt_date']} dropped {base['engine_halts_info']['pullback']['dropped']}")
    for cfg in ["C1", "C2", "C1+C2"]:
        r = json.load(open(os.path.join(RUNS, f"{pref}_K0.75_off_0_A_intra_eh_first_cross_nocarry_bfund_csv{tags[cfg]}.json")))
        pb1 = {t["entry_ts"]: t for t in r["trades"] if t["leg"] == "pullback"}
        assert pb0.keys() == pb1.keys()
        yr1 = (r["equity_btc"][-1] - 70000) / r["years"]
        resized = [(pb0[k], pb1[k]) for k in pb0 if abs(pb1[k]["qty"] - pb0[k]["qty"]) > 1e-9]
        win = [(a["pnl"], b["pnl"]) for a, b in resized if a["pnl"] > 0]
        los = [(a["pnl"], b["pnl"]) for a, b in resized if a["pnl"] <= 0]
        pb_real1 = sum(t["pnl"] for t in pb1.values())
        exr = exposure(r, "pullback") / exposure(base, "pullback")
        print(f"   {cfg:6s} $/yr {yr1:9,.0f} ({yr1 / yr0 - 1:+6.1%}; json {cj['eras'][ename]['runs'][cfg]['usd_per_year']:9,.0f}) maxDD {max_dd(r['equity_total']):7.2%} | "
              f"pb realised {pb_real1:+9,.0f} (delta {pb_real1 - pb_real0:+8,.0f} = {((pb_real1 - pb_real0) / abs(pb_real0)) if pb_real0 else float('nan'):+6.1%} of |pb P&L|) | resized {len(resized)}: "
              f"losers {len(los)} saved {sum(b - a for a, b in los):+8,.0f}, winners {len(win)} forgone {sum(b - a for a, b in win):+8,.0f} | pb exposure ratio {exr:.3f}")
