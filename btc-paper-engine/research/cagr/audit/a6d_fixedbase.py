"""Live executor sizes off a FIXED SIZING_BASE_USD (render.yaml: 100000), not
compounding MTM equity. Compare simulate() (compounding) with a fixed-base loop
(notional = weight*k*base) on the deployed S5 blend, full 2013-2026 and 2019+."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import harness as H, baseline as B
bars = H.load_bars("btcusd"); closes = {"btcusd": H.closes_of(bars)}; inds = H.compute_indicators(bars, 20)
def fixed_base(legs, k, t0, t1, base=100_000.0, f=4.32e-4):
    c = closes["btcusd"]; ent, ext = {}, {}
    for li, lg in enumerate(legs):
        for t in lg.trades:
            if t.entry_ts < t0 or t.entry_ts > t1: continue
            ent.setdefault(t.entry_ts, []).append((li, t))
            if t.exit_ts is not None and t.exit_ts <= t1: ext.setdefault(t.exit_ts, []).append((li, t))
    cash = base; op = {}; eq = []
    for ts in sorted(x for x in c if t0 <= x <= t1):
        for li, t in ext.get(ts, []):
            p = op.pop((li, t.entry_ts)); cash += p[0]*(t.exit_price-t.entry_price)*p[1] - f*p[0]*t.exit_price
        for li, t in ent.get(ts, []):
            n = legs[li].weight*k*base; cash -= f*n; op[(li, t.entry_ts)] = (n/t.entry_price, 1 if t.side=="L" else -1, t.entry_price)
        e = cash + sum(q*(c[ts]-ep)*s for q, s, ep in op.values()); eq.append(e)
    eq = np.array(eq); pk = np.maximum.accumulate(np.concatenate([[base], eq]))
    return (np.concatenate([[base], eq])/pk-1).min(), eq[-1]/base-1
for a, b in (("2013-01-01", "2026-12-31"), ("2019-01-01", "2026-12-31")):
    t0, t1 = H.ts_of(a), H.ts_of(b)+86399
    legs = B.legs_for(bars, t0, t1, inds=inds)
    for k in (0.2, 0.3958, 0.4338):
        r = H.simulate(legs, closes, k=k, start_ts=t0, end_ts=t1)
        dd_c = H.max_dd(np.concatenate([[1e5], r.equity])); tot_c = r.equity[-1]/1e5-1
        dd_f, tot_f = fixed_base(legs, k, t0, t1)
        print(f"{a[:4]}+ k={k:.4f}: compounding maxDD {dd_c*100:6.1f}% total {tot_c*100:7.1f}% | fixed-base maxDD(of peak equity) {dd_f*100:6.1f}% total {tot_f*100:7.1f}%")
