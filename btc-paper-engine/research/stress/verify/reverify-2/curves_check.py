"""Recompute balances, maxDD, total==btc+carry, 12m timestamp semantics and
the S3 paper book (margin to its line) from the saved offset-0 runs."""
import json, os, time, glob
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
STRESS = os.path.abspath(os.path.join(HERE, "..", ".."))
BAR, DAY = 14400, 86400
res = json.load(open(os.path.join(STRESS, "results.json")))
def d(ts): return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts))
def maxdd(p):
    p = np.asarray(p, float); pk = np.maximum.accumulate(p); return float((p / pk - 1).min())
def paper_book(trades, t0, eq, peak, dd_halt, fee_side=6.0):
    rt = 2 * fee_side / 1e4; halt = None; line = peak * (1 - dd_halt); minm = eq - line
    for t in trades:
        if t["exit_ts"] is not None and t["exit_ts"] < t0: continue
        if halt is not None and t["entry_ts"] > halt: continue
        if t["exit_ts"] is None: continue
        qty = round(eq / t["entry_price"], 6); sgn = 1 if t["side"] == "L" else -1
        eq += qty * (t["exit_price"] - t["entry_price"]) * sgn - qty * t["entry_price"] * rt
        peak = max(peak, eq); line = peak * (1 - dd_halt)
        if halt is None: minm = min(minm, eq - line)
        if halt is None and eq / peak - 1 <= -dd_halt: halt = t["exit_ts"]; m_at = eq - line
    return halt, (m_at if halt else None), minm
for scen in ("COVID", "2008", "1999"):
    for K in ("0.75", "0.3"):
        for sv in ("csv", "pending_live", "drop_seam"):
            f = os.path.join(STRESS, "runs", f"{scen}_K{K}_off_0_A_intra_eh_first_cross_carryXBTUSD_bfund_{sv}.json")
            r = json.load(open(f))
            ts = np.asarray(r["ts"]); tot = np.asarray(r["equity_total"]); btc = np.asarray(r["equity_btc"]); car = np.asarray(r["carry_value"])
            assert np.abs(tot - btc - car).max() < 0.02, "total != btc + carry"
            bal = {}
            for dd_ in (91, 182, 273, 365):
                tgt = r["t0"] + dd_ * DAY
                i = int(np.searchsorted(ts, tgt, side="right") - 1)
                bal[dd_] = (float(tot[i]), int(ts[i]), int(ts[i]) + BAR - tgt)   # close ts minus target
            md = maxdd(np.concatenate([[100000.0], tot]))
            s = res["scenarios"][scen]
            summ = (s["runs"][f"K{float(K):g}"]["off+0"] if sv == "csv" else s["sensitivity"]["seam_" + sv][f"K{float(K):g}"])
            ok = all(abs(bal[x][0] - summ["balances"][str(x)]) < 0.01 for x in bal) and abs(md - summ["max_dd"]) < 1e-4
            # engine paper book S3 recompute from the raw engine trades
            halt, m_at, minm = paper_book(r["engine_trades"]["pullback"], r["t0"], 104840.0, 107860.0, 0.30)
            e = r["engine_halts_info"]["pullback"]
            ok2 = ((d(halt) if halt else None) == e["halt_date"]) and (m_at is None and e["margin_at_halt"] is None or abs(m_at - e["margin_at_halt"]) < 0.01) and abs(minm - e["min_margin"]) < 0.01
            print(scen, K, sv, "bal", {x: round(v[0]) for x, v in bal.items()}, "365 close-minus-target(h)", bal[365][2] / 3600, "maxDD", round(md, 4), "match", ok, "| S3", e["halt_date"], e["margin_at_halt"], "mine", (d(halt) if halt else None), (round(m_at, 2) if m_at else None), round(minm, 2), "match", ok2, "| last bar close - (t0+365d) h:", (int(ts[-1]) + BAR - (r["t0"] + 365 * DAY)) / 3600)
# events at t0 for the COVID K0.75 run (re-mirror of the live S4 long)
r = json.load(open(os.path.join(STRESS, "runs", "COVID_K0.75_off_0_A_intra_eh_first_cross_carryXBTUSD_bfund_csv.json")))
print("\nCOVID K0.75 events (first 12):")
for e in r["events"][:12]: print("  ", d(e[0]), e[1], e[2], e[3])
print("first 4 trades:")
for t in r["trades"][:4]: print("  ", {k: t[k] for k in ("leg", "side", "entry_date", "entry_px", "exit_date", "exit_px", "qty", "pnl", "funding", "reason", "kind")})
print("pullback engine trades around the seam:")
for t in r["engine_trades"]["pullback"][:3]: print("  ", t)
print("rail_use", r["rail_use"]); print("worst_day", r["worst_day"], "\nworst_day_intrabar", r["worst_day_intrabar"])
