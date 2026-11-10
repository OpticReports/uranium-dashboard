"""Would the ENGINE's own 1x books (S3 dd_halt .30, S4 dd_halt .50, exit-step,
one-way) have halted? The harness runs dd_halt=1e9; live does not."""
import sys, os, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import harness as H, candidates as C
from app.engine.core import BookCfg, TradeCfg
W = C.World(); bars = W.bars["btcusd"]
d = lambda t: time.strftime("%Y-%m-%d", time.gmtime(t))
for start in ("2013-01-01", "2017-01-01", "2019-01-01", "2022-01-01", "2024-07-01"):
    t0 = H.ts_of(start); t1 = H.ts_of("2026-09-28")
    for strat, halt, fn in (("pullback", .30, None), ("donchian", .50, None), ("donchian", .50, H.process_donchian_resting_stop)):
        trs = H.leg_trades(bars, strat, start_ts=t0, end_ts=t1, inds=W.inds[("btcusd",20)], donchian_fn=fn)
        eq = pk = 1.0; hit = None; mdd = 0
        for t in trs:
            if t.exit_ts is None: continue
            r = (t.exit_price/t.entry_price - 1) * (1 if t.side == "L" else -1) - 2*H.LIVE_TAKER_BPS/1e4
            eq *= 1 + r; pk = max(pk, eq); mdd = min(mdd, eq/pk-1)
            if hit is None and eq/pk - 1 <= -halt: hit = d(t.exit_ts)
        print(f"{start} {strat:8s}{' H1' if fn else '   '} halt@{halt:.2f}: exit-step maxDD {mdd*100:6.1f}%  first halt {hit}")
