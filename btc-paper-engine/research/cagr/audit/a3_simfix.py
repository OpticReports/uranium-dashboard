"""simulate() with the sizing mark taken at the PREVIOUS close (harness
updates last_close to THIS bar's close before computing eq_now), optionally
also excluding same-bar exits' realised P&L from the sizing equity."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import harness as H

def simulate_fixed(legs, closes, k=1.0, start_ts=None, end_ts=None,
                   fee_bps=H.LIVE_TAKER_BPS, start_equity=100_000.0,
                   exits_after_sizing=False):
    f = fee_bps / 1e4
    grid = sorted(set().union(*[set(c) for c in closes.values()]))
    if start_ts is not None: grid = [t for t in grid if t >= start_ts]
    if end_ts is not None: grid = [t for t in grid if t <= end_ts]
    entries, exits = {}, {}
    for li, lg in enumerate(legs):
        for t in lg.trades:
            if start_ts is not None and t.entry_ts < start_ts: continue
            if end_ts is not None and t.entry_ts > end_ts: continue
            entries.setdefault(t.entry_ts, []).append((li, t))
            if t.exit_ts is not None and (end_ts is None or t.exit_ts <= end_ts):
                exits.setdefault(t.exit_ts, []).append((li, t))
    cash = start_equity; op = {}; eq_out = []; prev = {}
    for ts in grid:
        # sizing equity: cash + open marked at PREVIOUS close
        def mark(px_map):
            return sum(p["qty"]*(px_map.get(legs[li].asset, p["ep"])-p["ep"])*p["sgn"] for (li,_),p in op.items())
        if exits_after_sizing:
            eq_size = cash + mark(prev)
        for li, t in exits.get(ts, []):
            p = op.pop((li, t.entry_ts), None)
            if p is None: continue
            cash += p["qty"]*(t.exit_price-t.entry_price)*p["sgn"] - f*p["qty"]*t.exit_price
        if not exits_after_sizing:
            eq_size = cash + mark(prev)
        for li, t in entries.get(ts, []):
            if eq_size <= 0: break
            notional = legs[li].weight*k*eq_size
            cash -= f*notional
            op[(li, t.entry_ts)] = dict(qty=notional/t.entry_price, ep=t.entry_price, sgn=1.0 if t.side=="L" else -1.0)
        for a, c in closes.items():
            if ts in c: prev[a] = c[ts]
        eq = cash + mark(prev); eq_out.append(eq)
        if eq <= 0: break
    return H.SimResult(ts=np.array(grid[:len(eq_out)]), equity=np.array(eq_out), gross_lev=np.zeros(len(eq_out)), n_trades=0, fees=0)

if __name__ == "__main__":
    import baseline as B
    bars = H.load_bars("btcusd"); closes = {"btcusd": H.closes_of(bars)}; inds = H.compute_indicators(bars, 20)
    t0, t1 = H.ts_of("2013-01-01"), H.ts_of("2026-12-31")+86399
    legs = B.legs_for(bars, t0, t1, inds=inds)
    # how often does an entry coincide with another leg already open?
    for k in (0.2, 1.0, 2.0, 3.0):
        a = H.stats(H.simulate(legs, closes, k=k, start_ts=t0, end_ts=t1))
        b = H.stats(simulate_fixed(legs, closes, k=k, start_ts=t0, end_ts=t1))
        c = H.stats(simulate_fixed(legs, closes, k=k, start_ts=t0, end_ts=t1, exits_after_sizing=True))
        print(f"k={k}: harness CAGR {a['cagr']*100:.3f}% dd {a['maxdd']*100:.2f}% | prev-close sizing CAGR {b['cagr']*100:.3f}% dd {b['maxdd']*100:.2f}% | +exits-after-sizing CAGR {c['cagr']*100:.3f}% dd {c['maxdd']*100:.2f}%")
    # sanity: single-leg, identical by construction?
    one = [legs[0]]
    a = H.stats(H.simulate(one, closes, k=1, start_ts=t0, end_ts=t1)); b = H.stats(simulate_fixed(one, closes, k=1, start_ts=t0, end_ts=t1))
    print("single pullback leg harness vs fixed CAGR", a['cagr'], b['cagr'])
