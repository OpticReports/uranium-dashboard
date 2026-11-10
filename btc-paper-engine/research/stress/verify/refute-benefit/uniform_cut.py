"""Refuter step C: is the candidate just a size cut?  Exposure-matched
uniform pullback cut, computed from the saved per-bar per-leg MTM.
Linear in the pullback leg because (i) sizing is fixed-base, (ii) no
executor halt fired on any run, (iii) the gross cap never binds at K 0.75
with size_mult <= 1.  (Verified by two real re-runs in verify_linear.py.)
Also the K-matched version (both legs scaled) the task literally asks for."""
import json, os
import numpy as np
HERE = "/home/user/uranium-dashboard/btc-paper-engine/research/stress"
RUNS = os.path.join(HERE, "runs")
BAR = 14400
tags = {"C1": "_optC1", "C2": "_optC2", "C1+C2": "_optC1_C2"}
OFFS = ["off-28", "off-14", "off_0", "off_14", "off_28"]

def max_dd(eq, start=100000.0):
    eq = np.asarray(eq, float); peak = np.maximum.accumulate(np.concatenate([[start], eq]))[1:]
    return float(np.min(eq / peak - 1.0))

def exposure(r, leg):
    n = r["n_path_bars"]; tot = 0.0
    for t in r["trades"]:
        if t["leg"] != leg: continue
        end = t["exit_ts"] if t["exit_ts"] is not None else r["ts"][-1] + BAR
        tot += t["qty"] * t["entry_px"] * max(1, (end - t["entry_ts"]) // BAR)
    return tot / n

def bal365(r, eq=None):
    """balance at day 365 (or the last bar) from an equity vector on r's ts grid"""
    if eq is None: return r["balances"]["365"]["equity"]
    t0 = r["t0"]; ts = np.asarray(r["ts"])
    i = np.searchsorted(ts, t0 + 365 * 86400, side="right") - 1
    i = min(i, len(ts) - 1)
    return float(eq[i])

def compare(label, base, cand):
    pb0 = np.asarray(base["leg_mtm"]["pullback"]); tr0 = np.asarray(base["leg_mtm"]["trend"])
    carry = np.asarray(base["carry_value"]) if base.get("carry_value") is not None else np.full(len(pb0), 30000.0)
    eq0 = 70000.0 + pb0 + tr0 + carry
    assert np.max(np.abs(eq0 - np.asarray(base["equity_total"]))) < 0.05, "identity broken"
    r_pb = exposure(cand, "pullback") / exposure(base, "pullback")
    # (a) uniform pullback cut at C's exposure ratio
    eq_u = 70000.0 + r_pb * pb0 + tr0 + carry
    # (b) K-matched: both legs scaled so that TOTAL gross exposure matches the candidate's
    g_base = exposure(base, "pullback") + exposure(base, "trend")
    g_cand = exposure(cand, "pullback") + exposure(cand, "trend")
    r_k = g_cand / g_base
    eq_k = 70000.0 + r_k * (pb0 + tr0) + carry
    out = dict(r_pb=r_pb, r_k=r_k,
               b12=(bal365(base), bal365(cand), bal365(base, eq_u), bal365(base, eq_k)),
               dd=(max_dd(base["equity_total"]), max_dd(cand["equity_total"]), max_dd(eq_u), max_dd(eq_k)),
               yr=tuple((x - 70000.0) / base["years"] for x in (base["equity_btc"][-1], cand["equity_btc"][-1], (70000.0 + r_pb * pb0 + tr0)[-1], (70000.0 + r_k * (pb0 + tr0))[-1])))
    return out

res = {}
print("=== CRASH paths: candidate vs exposure-matched UNIFORM pullback cut (U) and K-matched both-leg cut (Kм) ===")
print("cols: 12m base | cand | U | K   ||  maxDD base | cand | U | K   (U = baseline x r_pb on the pullback leg; cand beats U only if its number is better)")
for scen in ["COVID", "2008", "1999"]:
    for cfg, tag in tags.items():
        rows = []
        for off in OFFS:
            base = json.load(open(os.path.join(RUNS, f"{scen}_K0.75_{off}_A_intra_eh_first_cross_carryXBTUSD_bfund_csv.json")))
            cand = json.load(open(os.path.join(RUNS, f"{scen}_K0.75_{off}_A_intra_eh_first_cross_carryXBTUSD_bfund_csv{tag}.json")))
            o = compare(f"{scen} {off} {cfg}", base, cand)
            res[(scen, off, cfg)] = o
            b = o["b12"]; d = o["dd"]
            beats_12 = b[1] > b[2] + 1; beats_dd = d[1] > d[2] + 1e-4
            rows.append(f"{off:6s} r_pb {o['r_pb']:.3f} | 12m {b[0]:>7,.0f} {b[1]:>7,.0f} U {b[2]:>7,.0f} K {b[3]:>7,.0f} {'cand>U' if beats_12 else 'U>=cand':7s} | dd {d[0]:6.1%} {d[1]:6.1%} U {d[2]:6.1%} K {d[3]:6.1%} {'cand>U' if beats_dd else 'U>=cand'}")
        print(f"{scen:5s} {cfg:6s}"); [print("    " + x) for x in rows]

print("\n=== ERAS: $/yr and maxDD, candidate vs exposure-matched uniform cut ===")
era_files = {"E2 2017-19": "E2", "E3 2020-21": "E3", "E4 2022-24H1": "E4", "E5 2024H2-26": "E5", "2019+": "Y2019plus"}
for ename, pref in era_files.items():
    base = json.load(open(os.path.join(RUNS, f"{pref}_K0.75_off_0_A_intra_eh_first_cross_nocarry_bfund_csv.json")))
    for cfg, tag in tags.items():
        cand = json.load(open(os.path.join(RUNS, f"{pref}_K0.75_off_0_A_intra_eh_first_cross_nocarry_bfund_csv{tag}.json")))
        o = compare(f"{ename} {cfg}", base, cand)
        y = o["yr"]; d = o["dd"]
        print(f"{ename:12s} {cfg:6s} r_pb {o['r_pb']:.3f} | $/yr base {y[0]:>7,.0f} cand {y[1]:>7,.0f} ({y[1]/y[0]-1:+6.1%}) U {y[2]:>7,.0f} ({y[2]/y[0]-1:+6.1%}) -> cand vs U {y[1]-y[2]:+7,.0f}/yr {'cand>U' if y[1] > y[2] + 1 else 'U>=cand'} | maxDD base {d[0]:6.1%} cand {d[1]:6.1%} U {d[2]:6.1%} {'cand>U' if d[1] > d[2] + 1e-4 else 'U>=cand'}")
