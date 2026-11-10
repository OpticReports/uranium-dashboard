#!/usr/bin/env python3
"""Re-verifier 1, probe 2: the DRAWDOWN rail (not in the table), the honesty
line's '$7.0k' claim, funding coverage per offset, the 1999 maxDD timing, and
REVIEW.md's quoted sensitivities vs results.json."""
from __future__ import annotations
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
STRESS = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, STRESS)
import stress, run_all                                   # noqa: E402
from stress import build_spliced, run_path, _date, DAY   # noqa: E402
NOW = stress.SEED_NOW
res = json.load(open(os.path.join(STRESS, "results.json")))

print("== DRAWDOWN rail consumption, every headline run (variant A intrabar), both K")
for scen, _ in run_all.SCENARIOS:
    S = res["scenarios"][scen]
    for Kk in ("K0.75", "K0.3"):
        row = []
        for off in run_all.OFFSETS:
            s = S["runs"][Kk][run_all.okey(off)]
            ru = s["rail_use"]
            row.append(f"{run_all.okey(off)} dd {ru['drawdown']['used_pct']:.0%} ({ru['drawdown']['min_margin']:,.0f} @ {ru['drawdown']['date'][:10]}) "
                       f"daily {ru['daily_loss']['used_pct']:.0%}")
        print(f"  {scen:5s} {Kk:5s} | " + " | ".join(row))
print("  table column present for the drawdown rail:", any("drawdown rail" in l or "dd rail" in l.lower() for l in res["table"]))

print("\n== honesty line 9 (no-DRAWDOWN-halt margin claims) vs the sensitivities")
sens = res["scenarios"]["COVID"]["sensitivity"]
print("  headline COVID K0.75 (XBTUSD + funding) dd min_margin:", res["scenarios"]["COVID"]["runs"]["K0.75"]["off+0"]["rail_use"]["drawdown"])
print("  no_btc_funding COVID K0.75 dd min_margin:", sens["no_btc_funding"]["K0.75"]["rail_use"]["drawdown"])
bars = build_spliced("btcusd", "2020-02-13", 12, 0, now=NOW)
fund, _ = run_all.funding_for(bars.anchor_ts, len(bars.path), bars.t0, "XBTUSD")
bf = run_all.btc_funding_from(fund)
r_nc = run_path("COVID_nocarry_fund", bars, 0.75, carry_value=None, btc_funding=bf, save=False, extra=dict(offset_days=0))
r_nc0 = run_path("COVID_nocarry_nofund", bars, 0.75, carry_value=None, btc_funding=None, save=False, extra=dict(offset_days=0))
print(f"  no-carry-income, WITH BTC funding: dd rail {r_nc['rail_use']['drawdown']}  12m {r_nc['balances']['365']['equity']:,.0f}  maxDD {r_nc['max_dd']:.2%}  halts {r_nc['halts_count']}")
print(f"  no-carry-income, no funding      : dd rail {r_nc0['rail_use']['drawdown']}  12m {r_nc0['balances']['365']['equity']:,.0f}")
print("  honesty[9]:", res["honesty"][9][:400])
# what slippage on the two flattening stops nearest the closest approach would it take? (order of magnitude)
rr = json.load(open(os.path.join(STRESS, res["scenarios"]["COVID"]["runs"]["K0.75"]["off+0"]["file"])))
j = rr["ts"].index(next(t for t in rr["ts"] if _date(t) == res["scenarios"]["COVID"]["runs"]["K0.75"]["off+0"]["rail_use"]["drawdown"]["date"]))
print(f"  at closest approach {_date(rr['ts'][j])}: worst intrabar eq {rr['worst_intrabar_equity'][j]:,.0f}, close eq {rr['equity_total'][j]:,.0f}, "
      f"margin_dd {rr['margin_drawdown'][j]:,.0f}, day_start {rr['day_start'][j]:,.0f}, carry {rr['carry_value'][j]:,.0f}, funding cum {rr['btc_funding_cum'][j]:,.0f}")
held = [t for t in rr["trades"] if t["entry_ts"] <= rr["ts"][j] and (t["exit_ts"] is None or t["exit_ts"] >= rr["ts"][j])]
print("  positions held then:", [(t["leg"], t["side"], round(t["qty"], 4), t["entry_px"], t["reason"], t["exit_date"]) for t in held])
# gross notional held -> $ per 1% adverse move
gross = sum(t["qty"] * rr["spliced_closes"][j][1] for t in held)
print(f"  gross notional {gross:,.0f} -> a further {100 * rr['margin_drawdown'][j] / gross if gross else float('nan'):.2f}% adverse move (or that much slippage) would have crossed the DRAWDOWN line")

print("\n== funding coverage per offset (headline XBTUSD)")
for scen, _ in run_all.SCENARIOS:
    S = res["scenarios"][scen]
    print("  " + scen + ": " + ", ".join(f"{k} cov {p['funding']['coverage']} mean {p['funding']['mean_ann_pct']:+.1f}% neg {p['funding']['neg_stamps_pct']}%" for k, p in S["paths"].items()))

print("\n== 1999 K0.75 maxDD with funding -13.61% vs without -14.45%: timing")
for lab, s in (("with", res["scenarios"]["1999"]["runs"]["K0.75"]["off+0"]), ("without", res["scenarios"]["1999"]["sensitivity"]["no_btc_funding"]["K0.75"])):
    r = json.load(open(os.path.join(STRESS, s["file"])))
    eq = np.concatenate([[100000.0], np.asarray(r["equity_total"])])
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1
    i = int(np.argmin(dd)); ip = int(np.argmax(eq[:i + 1]))
    ts = [None] + r["ts"]
    print(f"  {lab:8s} maxDD {dd[i]:.4%} trough {_date(ts[i])} eq {eq[i]:,.0f} from peak {_date(ts[ip])} eq {eq[ip]:,.0f}; funding cum at peak {r['btc_funding_cum'][ip - 1] if ip else 0:+,.0f} at trough {r['btc_funding_cum'][i - 1]:+,.0f}")

print("\n== REVIEW.md quoted numbers vs results.json")
chk = {
    "no-engine-halts 12m COVID 128,193": res["scenarios"]["COVID"]["sensitivity"]["no_engine_book_halts"]["balances"]["365"],
    "no-engine-halts 12m 2008 125,924": res["scenarios"]["2008"]["sensitivity"]["no_engine_book_halts"]["balances"]["365"],
    "no-engine-halts 12m 1999 105,439": res["scenarios"]["1999"]["sensitivity"]["no_engine_book_halts"]["balances"]["365"],
    "quanto COVID K0.75 135,840": res["scenarios"]["COVID"]["runs_quanto"]["K0.75"]["off+0"]["balances"]["365"],
    "quanto 2008 K0.75 137,205": res["scenarios"]["2008"]["runs_quanto"]["K0.75"]["off+0"]["balances"]["365"],
    "COVID K0.75 range 103,701..127,699": (res["scenarios"]["COVID"]["range_12m"]["K0.75"]["min"], res["scenarios"]["COVID"]["range_12m"]["K0.75"]["max"]),
    "1999 crash-only 116,600..123,023": (res["scenarios"]["1999"]["range_12m"]["K0.75"]["crash_only"]["min"], res["scenarios"]["1999"]["range_12m"]["K0.75"]["crash_only"]["max"]),
    "1999 pending_live 117,116 / drop 115,762": res["scenarios"]["1999"]["seam_range"]["K0.75"]["by_variant"],
    "worst intrabar COVID -8,884 / 2008 -5,026 / 1999 -7,051": [res["scenarios"][s]["runs"]["K0.75"]["off+0"]["worst_day_intrabar"]["usd"] for s in ("COVID", "2008", "1999")],
}
for k, v in chk.items():
    print(f"  {k:55s} -> {v}")
print("  2008 XBTUSD gate on%:", res["scenarios"]["2008"]["runs"]["K0.75"]["off+0"]["carry"]["bars_on_pct"], " COVID:", res["scenarios"]["COVID"]["runs"]["K0.75"]["off+0"]["carry"]["bars_on_pct"])
print("  knife-edge threshold in run_all:", run_all.KNIFE_EDGE_FRAC, "x peak =", run_all.KNIFE_EDGE_FRAC * 107860, "; table footnote:", [l for l in res["table"] if "knife-edge" in l][0][:200])
print("  table rows carry the word KNIFE-EDGE:", any("KNIFE" in l for l in res["table"]))
