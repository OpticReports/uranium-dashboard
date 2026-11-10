import sys, os, time, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import harness as H
from app.engine import core
from app.engine.core import BookCfg, Book, SignalCfg, TradeCfg
d = lambda t: time.strftime("%Y-%m-%d %H", time.gmtime(int(t)))
bars = H.load_bars("btcusd"); by = {b.ts: b for b in bars}; closes={"btcusd":H.closes_of(bars)}
inds = H.compute_indicators(bars, 20)
T0, T1 = H.ts_of("2013-01-01"), H.ts_of("2026-07-31")+86399
pt = H.leg_trades(bars, "pullback", start_ts=T0, end_ts=T1, inds=inds)
dt = H.leg_trades(bars, "donchian", start_ts=T0, end_ts=T1, inds=inds)
# per-year log return of each leg (weight 1, k=1)
for name, tr in (("pullback", pt), ("donchian", dt)):
    r = H.simulate([H.LegSpec(tr, 1.0)], closes, k=1.0, start_ts=T0, end_ts=T1)
    yr = {}
    for ts, e in zip(r.ts, r.equity): yr.setdefault(time.gmtime(int(ts)).tm_year, []).append(e)
    prev = 100_000.0; row = []
    for y in sorted(yr): row.append(f"{y}:{(yr[y][-1]/prev-1)*100:+.0f}%"); prev = yr[y][-1]
    print(name, " ".join(row))
# pullback stops that gapped through (fill at stop though open beyond it)
g = [t for t in pt if t.reason=="STOP" and ((t.side=="L" and by[t.exit_ts].open < t.exit_price) or (t.side=="S" and by[t.exit_ts].open > t.exit_price))]
print("pullback STOP exits:", sum(1 for t in pt if t.reason=="STOP"), "gap-through filled at stop (better than open):", len(g),
      "sum favourable pct-pts %.2f" % sum(abs(t.exit_price/by[t.exit_ts].open-1)*100 for t in g))
for t in sorted(g, key=lambda t: -abs(t.exit_price/by[t.exit_ts].open-1))[:4]:
    print("   ", t.side, d(t.exit_ts), "stop", round(t.exit_price,2), "open", by[t.exit_ts].open)
# unit-book qty rounding headroom: min over entries of (unit equity)/price vs 5e-7
for strat in ("pullback", "donchian"):
    for pair in ("btcusd","ethusd","ltcusd","xrpusd"):
        bb = H.load_bars(pair)
        cfg = BookCfg(name="x", sizing="fixed", strategy=strat, leverage=1.0, cap=1.0, start_equity=1.0, dd_halt=1e9)
        from app.engine.replay import run_replay
        bk = run_replay(bb, [cfg], SignalCfg(), TradeCfg(taker_fee_bps=4.32), start_ts=T0 if pair=="btcusd" else None).books["x"]
        m = min(t.equity_before/t.entry_price for t in bk.trades)
        mq = min(abs(t.qty*t.entry_price/t.equity_before-1) for t in bk.trades)
        worst = max(abs(t.qty*t.entry_price/t.equity_before-1) for t in bk.trades)
        print(f"  unit book {strat:8s} {pair}: min equity {min(t.equity_before for t in bk.trades):.4f} min eq/price {m:.2e} (qty rounds to 0 below 5e-7); worst notional rounding err {worst*100:.2f}%")
