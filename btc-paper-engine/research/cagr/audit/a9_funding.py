"""Not modelled: perp funding. Estimate drag at HL's baseline 0.01%/8h
(10.95%/yr, longs pay shorts) from the blend's net signed exposure. Also
k_at_dd sensitivity to the 2013 thin-market episode."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import harness as H, baseline as B
bars = H.load_bars("btcusd"); closes = {"btcusd": H.closes_of(bars)}; inds = H.compute_indicators(bars, 20)
for a in ("2013-01-01", "2014-01-01", "2019-01-01"):
    t0, t1 = H.ts_of(a), H.ts_of("2026-07-31")+86399
    legs = B.legs_for(bars, t0, t1, inds=inds)
    grid = [b.ts for b in bars if t0 <= b.ts <= t1]
    net = np.zeros(len(grid)); pos = {ts: i for i, ts in enumerate(grid)}
    for lg in legs:
        for t in lg.trades:
            i0 = pos[t.entry_ts]; i1 = pos.get(t.exit_ts, len(grid)) if t.exit_ts else len(grid)
            net[i0:i1] += lg.weight * (1 if t.side == "L" else -1)
    drag = net.mean() * 0.1095
    kdd = H.k_at_dd(legs, closes, 0.30, start_ts=t0, end_ts=t1)
    s = H.stats(H.simulate(legs, closes, k=kdd, start_ts=t0, end_ts=t1))
    print(f"from {a}: mean net signed exposure at k=1 {net.mean():+.3f}x -> baseline funding drag ~{drag*100:.2f}%/yr at k=1 ({drag*20:.2f}%/yr at k=0.2); k_at_dd30 {kdd:.3f} (CAGR {s['cagr']*100:.1f}%)")
