"""CANDIDATE A - rail redesign evidence.

mirror.py's cap is ACCOUNT-WIDE, not per leg:
    cap_notional = min(MAX_NOTIONAL_USD, MAX_ACCOUNT_LEV * base)      (L1481-91)
    room = cap_notional/px - sum(other legs' qty + netted_qty)        (L1493-1517)
so the quantity a rail must admit is CONCURRENT GROSS across both legs, bar by
bar -- not the per-trade max. Measured here on the real engine timeline.

Also prices the halt-coherence consequence: under vol-targeting the per-trade
dollar risk is a CONSTANT, so "how many maximum-risk losers does the DD halt
need" becomes a single number instead of a distribution.

Output: candA_rails.json
"""
import csv
import json
import os
import sys
from dataclasses import replace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)
from app.engine.core import Bar, BookCfg                    # noqa: E402
from app.engine.replay import run_replay                    # noqa: E402
from app.config import RESEARCH_SIGNAL, RESEARCH_TRADE      # noqa: E402

BARS_CSV = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
SIZ = {"pullback": 2.5, "trend": 5.0}
W = {"pullback": 0.75, "trend": 0.25}
BLEND_LEV, EQUITY, BAR_S = 1.5, 100_055.0, 4 * 3600
K_LIVE = 15_000.0 / (BLEND_LEV * EQUITY)
# live executor config
MAX_NOTIONAL_USD, MAX_ACCOUNT_LEV, SIZING_BASE_USD = 20_000.0, 2.0, 50_000.0
DD_HALT_PCT, DAILY_LOSS_HALT_PCT = 0.35, 0.06


def load_bars():
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(BARS_CSV))]


def run_leg(bars, leg):
    tc = replace(RESEARCH_TRADE, stop_atr=SIZ[leg])
    cfg = (BookCfg(name="P", sizing="fixed", strategy="pullback", leverage=1.0,
                   cap=1.0, dd_halt=0.30) if leg == "pullback" else
           BookCfg(name="T", sizing="fixed", strategy="donchian", trail_atr=5.0,
                   leverage=1.0, cap=1.0, dd_halt=0.50))
    bk = run_replay(bars, [cfg], RESEARCH_SIGNAL, tc, cash_apy=0.0).books[cfg.name]
    return [dict(entry_ts=t.entry_ts, exit_ts=t.exit_ts,
                 s=tc.stop_atr * t.atr_at_entry / t.entry_price) for t in bk.trades]


def main():
    bars = load_bars()
    rows = {l: run_leg(bars, l) for l in ("pullback", "trend")}
    sbar = {l: float(np.mean([r["s"] for r in rows[l]])) for l in rows}
    ts_all = np.array([b.ts for b in bars])
    out = {"meta": dict(equity=EQUITY, k_live=K_LIVE, blend_lev=BLEND_LEV,
                        max_notional_usd=MAX_NOTIONAL_USD,
                        max_account_lev=MAX_ACCOUNT_LEV,
                        sizing_base_usd=SIZING_BASE_USD,
                        live_cap_notional=min(MAX_NOTIONAL_USD,
                                              MAX_ACCOUNT_LEV * SIZING_BASE_USD))}

    # ---- bar-level concurrent GROSS notional at today's live k ---------
    def timeline(beta, cap):
        g = np.zeros(len(ts_all))
        risk = np.zeros(len(ts_all))
        for leg, rr in rows.items():
            for r in rr:
                su = (r["s"] ** beta) * (sbar[leg] ** (1 - beta))
                nf = min(sbar[leg] / su, cap)
                notl = K_LIVE * BLEND_LEV * W[leg] * nf * EQUITY
                m = (ts_all >= r["entry_ts"]) & (ts_all < r["exit_ts"])
                g[m] += notl
                risk[m] += notl * r["s"]
        return g, risk

    res = {}
    for tag, beta, cap in (("FIXED", 0.0, 1.0), ("VT_cap1.5", 1.0, 1.5),
                           ("VT_cap2.0", 1.0, 2.0), ("VT_uncapped", 1.0, 99.0)):
        g, risk = timeline(beta, cap)
        inm = g > 0
        res[tag] = dict(
            pct_bars_in_market=float(inm.mean()),
            gross_when_in_market=dict(
                mean=float(g[inm].mean()), median=float(np.median(g[inm])),
                p90=float(np.percentile(g[inm], 90)),
                p99=float(np.percentile(g[inm], 99)), max=float(g.max())),
            risk_when_in_market=dict(
                mean=float(risk[inm].mean()), median=float(np.median(risk[inm])),
                p99=float(np.percentile(risk[inm], 99)), max=float(risk.max())),
            pct_bars_over_live_cap=float((g > out["meta"]["live_cap_notional"]).mean()),
            pct_in_market_bars_over_live_cap=float(
                (g[inm] > out["meta"]["live_cap_notional"]).mean()),
            max_notional_usd_required=float(g.max()))
    f = res["FIXED"]
    for tag, v in res.items():
        v["vs_FIXED"] = dict(
            mean_gross=v["gross_when_in_market"]["mean"] / f["gross_when_in_market"]["mean"],
            max_gross=v["gross_when_in_market"]["max"] / f["gross_when_in_market"]["max"],
            rail_required=v["max_notional_usd_required"] / f["max_notional_usd_required"])
    out["concurrent_gross_at_live_k"] = res
    for tag, v in res.items():
        print(f"{tag:12s} gross when in mkt: mean=${v['gross_when_in_market']['mean']:>8,.0f} "
              f"p99=${v['gross_when_in_market']['p99']:>8,.0f} "
              f"MAX=${v['gross_when_in_market']['max']:>8,.0f} "
              f"({v['vs_FIXED']['mean_gross']:.3f}x mean, {v['vs_FIXED']['max_gross']:.3f}x max) "
              f"| bars over the live $20k cap: {v['pct_bars_over_live_cap']:.2%}")

    # ---- halt coherence ------------------------------------------------
    # per-trade dollar risk at live k; FIXED is a distribution, VT a constant
    hc = {}
    for tag, beta, cap in (("FIXED", 0.0, 1.0), ("VT_uncapped", 1.0, 99.0)):
        per = []
        for leg, rr in rows.items():
            for r in rr:
                su = (r["s"] ** beta) * (sbar[leg] ** (1 - beta))
                nf = min(sbar[leg] / su, cap)
                per.append(K_LIVE * BLEND_LEV * W[leg] * nf * EQUITY * r["s"])
        per = np.array(per)
        dd_need = DD_HALT_PCT * SIZING_BASE_USD
        day_need = DAILY_LOSS_HALT_PCT * SIZING_BASE_USD
        hc[tag] = dict(
            risk_usd=dict(mean=float(per.mean()), median=float(np.median(per)),
                          p10=float(np.percentile(per, 10)),
                          p90=float(np.percentile(per, 90)),
                          min=float(per.min()), max=float(per.max()),
                          cv=float(per.std() / per.mean())),
            risk_pct_of_equity_mean=float(per.mean() / EQUITY),
            dd_halt_usd=dd_need, dd_halt_pct_of_real_equity=dd_need / EQUITY,
            daily_halt_usd=day_need,
            losers_to_dd_halt=dict(
                at_mean_risk=float(dd_need / per.mean()),
                at_p90_risk=float(dd_need / np.percentile(per, 90)),
                at_p10_risk=float(dd_need / np.percentile(per, 10))),
            losers_to_daily_halt_at_mean=float(day_need / per.mean()))
    out["halt_coherence"] = hc
    for tag, v in hc.items():
        print(f"{tag:12s} per-trade risk $ mean={v['risk_usd']['mean']:.0f} "
              f"CV={v['risk_usd']['cv']:.3f} p10={v['risk_usd']['p10']:.0f} "
              f"p90={v['risk_usd']['p90']:.0f} | losers to DD halt "
              f"({v['dd_halt_usd']:.0f}): {v['losers_to_dd_halt']['at_p90_risk']:.0f}"
              f"-{v['losers_to_dd_halt']['at_p10_risk']:.0f} "
              f"(mean {v['losers_to_dd_halt']['at_mean_risk']:.0f})")

    # ---- what the rails would have to become ---------------------------
    vt = res["VT_uncapped"]
    out["rail_requirement"] = dict(
        today_cap_notional=out["meta"]["live_cap_notional"],
        fixed_max_gross=f["max_notional_usd_required"],
        vt_max_gross=vt["max_notional_usd_required"],
        max_notional_usd_needed_for_vt=vt["max_notional_usd_required"],
        rail_multiple=vt["max_notional_usd_required"] / out["meta"]["live_cap_notional"],
        mean_deployment_multiple=vt["vs_FIXED"]["mean_gross"],
        rail_cost_per_unit_of_size=(
            (vt["max_notional_usd_required"] / out["meta"]["live_cap_notional"])
            / vt["vs_FIXED"]["mean_gross"]),
        note="MAX_ACCOUNT_LEV 2.0 x base 50,000 = 100,000 is NOT the binder "
             "today; MAX_NOTIONAL_USD 20,000 is.")
    r = out["rail_requirement"]
    print(f"\nRAIL: today cap ${r['today_cap_notional']:,.0f} | FIXED needs "
          f"${r['fixed_max_gross']:,.0f} | VT needs ${r['vt_max_gross']:,.0f} "
          f"= {r['rail_multiple']:.2f}x the rail for "
          f"{r['mean_deployment_multiple']:.3f}x the deployed size "
          f"({r['rail_cost_per_unit_of_size']:.2f} rail-x per size-x)")

    p = os.path.join(HERE, "candA_rails.json")
    json.dump(out, open(p, "w"), default=float)
    print("wrote", p)


if __name__ == "__main__":
    main()
