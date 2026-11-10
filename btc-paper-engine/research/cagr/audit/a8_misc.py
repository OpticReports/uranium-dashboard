import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import harness as H
d = lambda t: time.strftime("%Y-%m-%d %H", time.gmtime(int(t)))
# (a) stats() drops the first bar: trade entered on the first grid bar
BAR = H.BAR_S
closes = {"btcusd": {0: 100.0, BAR: 50.0, 2*BAR: 60.0}}
tr = [H.Trade("p", "L", 0, 100.0, None, None, "OPEN")]
r = H.simulate([H.LegSpec(tr, 1.0)], closes, k=1.0, fee_bps=0.0, start_equity=1000.0)
closes2 = {"btcusd": {0: 100.0, BAR: 80.0, 2*BAR: 40.0}}
tr2 = [H.Trade("p", "L", 0, 100.0, None, None, "OPEN")]
# first-bar move: open 100 -> close 80 on bar 0 itself
closes3 = {"btcusd": {0: 80.0, BAR: 80.0}}
r3 = H.simulate([H.LegSpec([H.Trade("p","L",0,100.0,None,None,"OPEN")], 1.0)], closes3, k=1.0, fee_bps=0.0, start_equity=1000.0)
s3 = H.stats(r3)
print("(a) entry at 100 on first bar, closes 80,80: equity", r3.equity, "stats maxdd", s3["maxdd"], "(true -20%)", "cagr basis eq[0]", r3.equity[0])
# (b) alt gap-fill ever used; alt vs base on other pairs
for pair in ("btcusd","ethusd","ltcusd","xrpusd"):
    bars = H.load_bars(pair); by = {b.ts: b for b in bars}
    T0 = H.ts_of("2013-01-01")
    base = H.leg_trades(bars, "donchian", start_ts=T0)
    alt = H.leg_trades(bars, "donchian", start_ts=T0, donchian_fn=H.process_donchian_resting_stop)
    gapfills = sum(1 for t in alt if t.exit_ts and t.exit_price == by[t.exit_ts].open and ((t.side=="L" and by[t.exit_ts].open < by[t.exit_ts].high) or t.side=="S"))
    sb = {t.entry_ts: (t.exit_ts, t.exit_price) for t in base}; sa = {t.entry_ts: (t.exit_ts, t.exit_price) for t in alt}
    diff = sum(1 for e in set(sb)|set(sa) if sb.get(e) != sa.get(e))
    cl = {pair: H.closes_of(bars)}
    s1 = H.stats(H.simulate([H.LegSpec(base,1.0,pair)], cl, 1.0, T0)); s2 = H.stats(H.simulate([H.LegSpec(alt,1.0,pair)], cl, 1.0, T0))
    print(f"(b) {pair}: n base {len(base)} alt {len(alt)} differing entries {diff} alt gap-fills-at-open {gapfills} | CAGR base {s1['cagr']*100:.1f}% alt {s2['cagr']*100:.1f}% dd {s1['maxdd']*100:.1f}/{s2['maxdd']*100:.1f}")
b = H.load_bars("btcusd"); print("(c) data ends", d(b[-1].ts), "E6 window length days", (b[-1].ts - H.ts_of("2026-08-01"))/86400)
# (d) two assets, one with a missing bar -> stale mark
cl = {"a": {0: 100.0, BAR: 110.0, 2*BAR: 120.0}, "b": {0: 10.0, 2*BAR: 12.0}}
r = H.simulate([H.LegSpec([H.Trade("x","L",0,10.0,None,None,"OPEN")],1.0,"b")], cl, 1.0, fee_bps=0.0, start_equity=1000.0)
print("(d) asset b missing bar at ts=BAR: equity path", r.equity, "(stale mark carried: correct)")
# (e) entry of a trade whose asset has no bar at entry ts but exit exists - grid union ok; exit on ts not in grid when end_ts cuts
