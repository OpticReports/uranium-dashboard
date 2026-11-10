"""Two real re-runs of the baseline with the pullback weight scaled to C1's
exposure ratio, to confirm the analytic uniform-cut numbers (linearity)."""
import sys, json, os
HERE = "/home/user/uranium-dashboard/btc-paper-engine/research/stress"
sys.path.insert(0, HERE)
import stress, run_all, harness
import carry_sleeve as cs
from stress import Options, build_spliced, run_path, run_era, DAY
NOW = stress.SEED_NOW
# COVID off 0, r_pb 0.749 (from uniform_cut.py); E3, r_pb 0.934
bb = build_spliced("btcusd", "2020-02-13", run_all.MONTHS, 0, now=NOW)
be = build_spliced("ethusd", "2020-02-13", run_all.MONTHS, 0, now=NOW)
fund, _ = run_all.funding_for(bb.anchor_ts, len(bb.path), bb.t0, run_all.HEADLINE_FUNDING)
cv, bf = run_all.run_carry(be, fund).value, run_all.btc_funding_from(fund)
base = json.load(open(os.path.join(HERE, "runs/COVID_K0.75_off_0_A_intra_eh_first_cross_carryXBTUSD_bfund_csv.json")))
c1 = json.load(open(os.path.join(HERE, "runs/COVID_K0.75_off_0_A_intra_eh_first_cross_carryXBTUSD_bfund_csv_optC1.json")))
BAR = 14400
def exposure(r, leg):
    n = r["n_path_bars"]; tot = 0.0
    for t in r["trades"]:
        if t["leg"] != leg: continue
        end = t["exit_ts"] if t["exit_ts"] is not None else r["ts"][-1] + BAR
        tot += t["qty"] * t["entry_px"] * max(1, (end - t["entry_ts"]) // BAR)
    return tot / n
r_pb = exposure(c1, "pullback") / exposure(base, "pullback")
stress.WEIGHTS["pullback"] = stress.W_PULL * r_pb
r = run_path("x", bb, 0.75, carry_value=cv, btc_funding=bf, save=False, options=Options(), extra=dict(offset_days=0))
print(f"COVID off0 uniform cut r_pb={r_pb:.4f}: REAL re-run 12m {r['balances']['365']['equity']:,.2f} maxDD {r['max_dd']:.4%}  (analytic: 119,846 / -18.6%)  C1 saved: {c1['balances']['365']['equity']:,.2f} / {c1['max_dd']:.4%}")
print("   realised exposure ratio of the re-run:", round(exposure(r, "pullback") / exposure(base, "pullback"), 4), "halts", len(r["halts"]), "cap clamps", sum(1 for e in r["events"] if e[1] == "CAP_CLAMP"))
stress.WEIGHTS["pullback"] = stress.W_PULL
# E3
baseE = json.load(open(os.path.join(HERE, "runs/E3_K0.75_off_0_A_intra_eh_first_cross_nocarry_bfund_csv.json")))
c1E = json.load(open(os.path.join(HERE, "runs/E3_K0.75_off_0_A_intra_eh_first_cross_nocarry_bfund_csv_optC1.json")))
r_pb = exposure(c1E, "pullback") / exposure(baseE, "pullback")
lo = (harness.ts_of("2020-01-01") - DAY) * 1000; hi = harness.ts_of("2022-01-01") * 1000
bfE = run_all.btc_funding_from(cs.load_funding(run_all.FUNDING_FILES["XBTUSD"], lo_ms=lo, hi_ms=hi))
stress.WEIGHTS["pullback"] = stress.W_PULL * r_pb
r = run_era("E3", "2020-01-01", "2022-01-01", 0.75, carry_value=None, btc_funding=bfE, save=False, options=Options(), now=NOW)
print(f"E3 uniform cut r_pb={r_pb:.4f}: REAL re-run $/yr {(r['equity_btc'][-1] - 70000) / r['years']:,.0f} maxDD {r['max_dd']:.4%}  (analytic: 31,839 / -15.7%)  C1 saved: {(c1E['equity_btc'][-1] - 70000) / c1E['years']:,.0f} / {c1E['max_dd']:.4%}")
stress.WEIGHTS["pullback"] = stress.W_PULL
