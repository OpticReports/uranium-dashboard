"""Characterise production vs resting-stop donchian trade lists; count
non-tradable fills in production (donchian + pullback)."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness as H
from app.engine.core import TradeCfg
d = lambda t: time.strftime("%Y-%m-%d %H", time.gmtime(t))
bars = H.load_bars("btcusd"); by = {b.ts: b for b in bars}; idx = {b.ts:i for i,b in enumerate(bars)}
inds = H.compute_indicators(bars, 20)
T0, T1 = H.ts_of("2013-01-01"), H.ts_of("2026-07-31")+86399
tc = TradeCfg(taker_fee_bps=H.LIVE_TAKER_BPS)
base = H.leg_trades(bars, "donchian", start_ts=T0, end_ts=T1, inds=inds, tcfg=tc)
alt = H.leg_trades(bars, "donchian", start_ts=T0, end_ts=T1, inds=inds, tcfg=tc, donchian_fn=H.process_donchian_resting_stop)
print("n base", len(base), "n alt", len(alt))
# production fills outside the bar's traded range / worse-than-open gap fills
def outside(tr):
    o = []
    for t in tr:
        if t.exit_ts is None: continue
        b = by[t.exit_ts]
        if not (b.low-1e-9 <= t.exit_price <= b.high+1e-9): o.append((t, b))
    return o
ob = outside(base)
print("production donchian STOP fills outside bar range:", len(ob))
for t,b in ob[:6]: print("  ", t.side, d(t.exit_ts), "fill", round(t.exit_price,2), "bar O/H/L/C", b.open,b.high,b.low,b.close)
# production fill better than open on a gap (long: open < trail but fill at trail)
gapb = [t for t in base if t.exit_ts and ((t.side=="L" and by[t.exit_ts].open < t.exit_price) or (t.side=="S" and by[t.exit_ts].open > t.exit_price))]
print("production donchian stops filled at a price better than an open that had already gapped through:", len(gapb),
      "sum of favourable gap (pct pts): %.2f" % sum(abs(t.exit_price/by[t.exit_ts].open-1)*100 for t in gapb))
# same-bar ratchet-then-hit: production stop where the level used was set from THIS bar's close
same = 0
for t in base:
    if not t.exit_ts: continue
    i = idx[t.exit_ts]; b = bars[i]; a = inds[i].atr14
    lvl = b.close - 5*a if t.side=="L" else b.close + 5*a
    if abs(lvl - t.exit_price) < 1e-9: same += 1
print("production stops whose fill level was ratcheted from the SAME bar's close (lookahead):", same, "of", sum(1 for t in base if t.exit_ts))
# classify differences
sb = {(t.entry_ts): t for t in base}; sa = {(t.entry_ts): t for t in alt}
common = set(sb)&set(sa)
same_exit = sum(1 for e in common if (sb[e].exit_ts, sb[e].exit_price)==(sa[e].exit_ts, sa[e].exit_price))
later = sum(1 for e in common if sb[e].exit_ts and sa[e].exit_ts and sa[e].exit_ts > sb[e].exit_ts)
earlier = sum(1 for e in common if sb[e].exit_ts and sa[e].exit_ts and sa[e].exit_ts < sb[e].exit_ts)
sametsdiffpx = sum(1 for e in common if sb[e].exit_ts==sa[e].exit_ts and sb[e].exit_price!=sa[e].exit_price)
print("common entries", len(common), "identical exit", same_exit, "alt exits later", later, "alt earlier", earlier, "same bar diff price", sametsdiffpx)
print("entries only in base", len(set(sb)-set(sa)), "only in alt", len(set(sa)-set(sb)))
# alt earlier than base: should be impossible? resting trail(t-1) <= ratcheted trail(t) for longs, so alt hits are a subset... check
for e in sorted(common):
    if sb[e].exit_ts and sa[e].exit_ts and sa[e].exit_ts < sb[e].exit_ts:
        print("  EARLIER", d(e), sb[e].side, d(sb[e].exit_ts), sb[e].exit_price, d(sa[e].exit_ts), sa[e].exit_price)
# stop on entry bar? exit_ts == entry_ts
print("alt exits on entry bar:", sum(1 for t in alt if t.exit_ts==t.entry_ts), " base:", sum(1 for t in base if t.exit_ts==t.entry_ts))
# alt fill checks: long fill = min(trail, open) must be <= open and >= low
bad = [t for t in alt if t.exit_ts and not (by[t.exit_ts].low-1e-9 <= t.exit_price <= by[t.exit_ts].high+1e-9)]
print("alt fills outside range:", len(bad))
# every alt exit: verify it equals an independently computed resting level
# simple per-trade P&L comparison
def tot(tr):
    import math
    s=0; 
    for t in tr:
        if not t.exit_ts: continue
        r = (t.exit_price/t.entry_price-1) if t.side=="L" else (1-t.exit_price/t.entry_price)
        s += math.log(max(1e-9,1+r-2*4.32e-4))
    return s
import math
print("sum log-ret base %.3f alt %.3f" % (tot(base), tot(alt)))
print("---- differing trades ----")
for e in sorted(set(sb)|set(sa)):
    b_, a_ = sb.get(e), sa.get(e)
    if b_ and a_ and (b_.exit_ts, b_.exit_price)==(a_.exit_ts, a_.exit_price): continue
    f = lambda t: None if t is None else (t.side, d(t.entry_ts), round(t.entry_price,2), d(t.exit_ts) if t.exit_ts else None, round(t.exit_price,2) if t.exit_price else None)
    print("base", f(b_), "\n alt", f(a_))
for t in gapb:
    b = by[t.exit_ts]; print("gap case", t.side, d(t.exit_ts), "prod fill", round(t.exit_price,2), "open", b.open, "in alt?", [ (d(x.exit_ts), x.exit_price) for x in alt if x.entry_ts==t.entry_ts])
