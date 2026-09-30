import sys, os
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import harness as H, candidates as C
W = C.World(); bars = W.bars["btcusd"]; idx = {b.ts: i for i, b in enumerate(bars)}
T0, T1 = H.ts_of("2019-01-01"), H.ts_of("2026-09-28")
pb = H.leg_trades(bars, "pullback", start_ts=T0, end_ts=T1, inds=W.inds[("btcusd",20)])
tr = H.leg_trades(bars, "donchian", start_ts=T0, end_ts=T1, inds=W.inds[("btcusd",20)], donchian_fn=H.process_donchian_resting_stop)
def held(trs):
    m = {}
    for t in trs:
        e = t.exit_ts or T1
        for i in range(idx[t.entry_ts], idx.get(e, len(bars)-1)):
            m[bars[i].ts] = t.side
    return m
P, T = held(pb), held(tr)
opp = sum(1 for ts, s in T.items() if ts in P and P[ts] != s)
print("2019+: trend-held bars", len(T), "opposed to pullback", opp, "(%.0f%%)" % (100*opp/len(T)))
# trend STOP exits that occurred while opposed (subordinate under 75/25 -> no resting venue stop)
n = sum(1 for t in tr if t.exit_ts and t.exit_ts in P and P[t.exit_ts] != t.side)
print("trend exits while opposed:", n, "of", sum(1 for t in tr if t.exit_ts))
