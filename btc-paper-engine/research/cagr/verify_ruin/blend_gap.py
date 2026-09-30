import sys, os, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import numpy as np, harness as H, candidates as C
W = C.World(); bars = W.bars["btcusd"]; by = {b.ts: b for b in bars}; idx = {b.ts: i for i, b in enumerate(bars)}
d = lambda t: time.strftime("%Y-%m-%d %H", time.gmtime(t))
T0, T1 = H.ts_of("2013-01-01"), H.ts_of("2026-09-28")
# --- H2a blend as it would be published: w_trend = wT/(wP+wT), lev = wP+wT
legs, _ = C.CANDIDATES["H5a H1+H2a"](W, T0, T1)
ws = []
for b in bars:
    if b.ts < T0: continue
    wp, wt = legs[0].weight_fn(b.ts), legs[1].weight_fn(b.ts)
    if wp == wp and wt == wt: ws.append((b.ts, wt/(wp+wt), wp+wt))
a = np.array([(x[1], x[2]) for x in ws])
print("H2a published blend: w_trend min %.3f p1 %.3f mean %.3f p99 %.3f max %.3f | lev min %.3f mean %.3f p99 %.3f max %.3f" % (
    a[:,0].min(), np.percentile(a[:,0],1), a[:,0].mean(), np.percentile(a[:,0],99), a[:,0].max(), a[:,1].min(), a[:,1].mean(), np.percentile(a[:,1],99), a[:,1].max()))
print("  bars with lev>2.0 (sane_blend reject):", int((a[:,1] > 2.0).sum()), " lev>1.515 (exposure_over_cap at KELLY_M_CAP*1.5):", int((a[:,1] > 1.515).sum()), "of", len(a))
imax = a[:,1].argmax(); print("  max lev at", d(ws[imax][0]))
# fallback count: weights equal to baseline constants (NaN sigma)
fb = sum(1 for t, w, l in ws if abs(l - 1.5) < 1e-12 and abs(w - 0.25) < 1e-12); print("  fallback-to-baseline bars:", fb)
# how many bars of history the vol needs vs live engine window
print("  lookback needed: %d bars of each leg's 1x per-bar return (+ warmup 210 + trade state); live engine keeps history_bars=800" % H.BARS_PER_YEAR)
# per-year mean of blend
yrs = {}
for t, w, l in ws: yrs.setdefault(time.gmtime(t).tm_year, []).append((w, l))
print("  per-year mean w_trend/lev:", {y: (round(np.mean([x[0] for x in v]),3), round(np.mean([x[1] for x in v]),3)) for y, v in sorted(yrs.items())})

# --- pullback STOP gap-through (engine books fill at stop even when open already beyond)
pb = H.leg_trades(bars, "pullback", start_ts=T0, end_ts=T1, inds=W.inds[("btcusd",20)])
gaps = []
for t in pb:
    if t.reason != "STOP" or t.exit_ts is None: continue
    b = by[t.exit_ts]
    worse = (b.open < t.exit_price) if t.side == "L" else (b.open > t.exit_price)
    if worse: gaps.append((d(t.exit_ts), t.side, round(abs(b.open/t.exit_price-1)*100, 2)))
print("pullback STOP exits:", sum(1 for t in pb if t.reason=="STOP"), " filled at stop though open already through it:", len(gaps), "sum pp %.2f" % sum(g[2] for g in gaps), gaps[:10])
# stops that would fill beyond the bar's range? (stop inside range always since low<=stop)
# --- worst adverse moves while BOTH legs long (H5b trade lists), price only
tr = H.leg_trades(bars, "donchian", start_ts=T0, end_ts=T1, inds=W.inds[("btcusd",20)], donchian_fn=H.process_donchian_resting_stop)
def held(trs, side):
    s = set()
    for t in trs:
        if t.side != side: continue
        e = t.exit_ts or T1
        i0, i1 = idx[t.entry_ts], idx.get(e, len(bars)-1)
        for i in range(i0, i1+1): s.add(bars[i].ts)
    return s
bothL = held(pb, "L") & held(tr, "L"); bothS = held(pb, "S") & held(tr, "S")
print("bars with both legs long: %d, both short: %d" % (len(bothL), len(bothS)))
res = []
for i, b in enumerate(bars):
    if b.ts < T0 or b.ts not in bothL: continue
    pc = bars[i-1].close
    res.append(((b.low/pc - 1)*100, d(b.ts)))
res.sort(); print("worst single-bar prev-close->low while both long (%):", [(round(x,1), t) for x, t in res[:8]])
res2 = [x for x in res if x[1] >= "2019"]; print("  since 2019:", [(round(x,1), t) for x, t in res2[:6]])
# multi-bar: worst 6-bar (1 day) and 18-bar (3 day) close->min low where both long at start
for n in (6, 18):
    out = []
    for i, b in enumerate(bars):
        if b.ts < T0 or b.ts not in bothL or i+n >= len(bars): continue
        lo = min(x.low for x in bars[i+1:i+1+n]); out.append(((lo/b.close-1)*100, d(b.ts)))
    out.sort(); o2 = [x for x in out if x[1] >= "2019"]
    print(f"worst {n}-bar close->low after a both-long close (%): all {[(round(x,1),t) for x,t in out[:3]]} since2019 {[(round(x,1),t) for x,t in o2[:3]]}")
