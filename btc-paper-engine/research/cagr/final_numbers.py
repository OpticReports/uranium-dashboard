"""Fixed-base (live-like) numbers for the recommendation. Writes final_numbers.json."""
import json, numpy as np, harness as H, candidates as C

def static(wt, resting=True):
    def b(W, t0, t1):
        fn = H.process_donchian_resting_stop if resting else None
        return ([H.LegSpec(W.trades("btcusd","pullback",t0,t1),(1-wt)*1.5),
                 H.LegSpec(W.trades("btcusd","donchian",t0,t1,donchian_fn=fn),wt*1.5)],
                {"btcusd":W.closes["btcusd"]})
    return b

CONF = {"live today (75/25, k=0.20)": (static(0.25, False), 0.20),
        "75/25, k=0.30": (static(0.25, False), 0.30),
        "REC: H1 + 70/30, k=0.30": (static(0.30, True), 0.30),
        "H1 + 70/30, k=0.45 (rejected size)": (static(0.30, True), 0.45)}
W = C.World(); out = {}; curves = {}
for start in ("2014-01-01", "2019-01-01"):
    t0, t1 = H.ts_of(start), H.ts_of("2026-07-31") + 86399
    for name, (b, k) in CONF.items():
        legs, cl = b(W, t0, t1)
        r = H.simulate(legs, cl, k=k, start_ts=t0, end_ts=t1, fixed_base=100_000.0)
        eq = np.concatenate([[100_000.0], r.equity]); peak = np.maximum.accumulate(eq)
        dd_usd = float((eq - peak).min()); dd_pct = float((eq / peak - 1).min())
        yrs = (r.ts[-1] - r.ts[0] + H.BAR_S) / (365.25 * 86400)
        day = r.ts // 86400; brk = 0
        for d in np.unique(day):
            idx = np.where(day == d)[0]; e0 = eq[idx[0]]           # prior close
            if (e0 - eq[idx + 1].min()) > 6000: brk += 1
        pnl = eq[-1] - 100_000.0
        out[f"{start[:4]}+ | {name}"] = dict(avg_pnl_per_yr=pnl / yrs, pct_per_yr_on_100k=pnl / yrs / 1000,
            max_dd_usd=dd_usd, max_dd_pct=dd_pct, daily_loss_breaches=brk,
            peak_gross_usd=float(np.nanmax(r.gross_lev * r.equity)))
        curves[f"{start[:4]}|{name}"] = (r.ts.tolist(), r.equity.tolist())
        o = out[f"{start[:4]}+ | {name}"]
        print(f"{start[:4]}+  {name:36s} ${o['avg_pnl_per_yr']:>8,.0f}/yr ({o['pct_per_yr_on_100k']:4.1f}% of $100k)  "
              f"maxDD ${o['max_dd_usd']:>9,.0f}  daily>$6k: {brk}  peak gross ${o['peak_gross_usd']:>7,.0f}")
json.dump(out, open("final_numbers.json", "w"), indent=1)
json.dump(curves, open("final_curves.json", "w"))
