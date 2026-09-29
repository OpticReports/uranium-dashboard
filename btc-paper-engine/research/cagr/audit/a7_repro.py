"""Independent end-to-end reproduction: S3 pullback leg alone, weight 1.0,
k=1, 4.32 bps/side, 2013-01-01 .. 2026-07-31. Trades from PRODUCTION
run_replay (not leg_trades); own portfolio loop (not simulate)."""
import csv, math, os, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
from app.engine.core import Bar, BookCfg, SignalCfg, TradeCfg
from app.engine.replay import run_replay
import calendar, time
ts_of = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%d"))
with open(os.path.join(HERE, "data", "bars_4h_btcusd.csv")) as fh:
    bars = [Bar(int(r["ts_open_unix"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"])) for r in csv.DictReader(fh)]
T0, T1 = ts_of("2013-01-01"), ts_of("2026-07-31") + 86399
cfg = BookCfg(name="S3", sizing="fixed", strategy="pullback", leverage=1.0, cap=1.0, start_equity=1.0, dd_halt=1e9)
res = run_replay(bars, [cfg], SignalCfg(), TradeCfg(taker_fee_bps=4.32), start_ts=T0, end_ts=T1)
bk = res.books["S3"]
trades = [(t.side, t.entry_ts, t.entry_price, t.exit_ts, t.exit_price) for t in bk.trades]
if bk.position is not None:
    p = bk.position; trades.append((p.side, p.entry_ts, p.entry_price, None, None))
f = 4.32e-4
ent = {t[1]: t for t in trades}; ext = {t[3]: t for t in trades if t[3] is not None}
cash, pos, eqs, tss = 100_000.0, None, [], []
for b in bars:
    if b.ts < T0 or b.ts > T1: continue
    if pos is not None and b.ts in ext and ext[b.ts][1] == pos["t"][1]:
        s, _, ep, _, xp = pos["t"]; sg = 1 if s == "L" else -1
        cash += pos["q"] * (xp - ep) * sg - f * pos["q"] * xp; pos = None
    if b.ts in ent:
        t = ent[b.ts]; assert pos is None
        eq = cash                      # flat => MTM equity is cash
        q = eq / t[2]; cash -= f * eq; pos = dict(t=t, q=q)
    u = 0.0 if pos is None else pos["q"] * (b.close - pos["t"][2]) * (1 if pos["t"][0] == "L" else -1)
    eqs.append(cash + u); tss.append(b.ts)
yrs = (tss[-1] - tss[0] + 14400) / (365.25 * 86400)
peak, mdd = 100_000.0, 0.0
for e in eqs:
    peak = max(peak, e); mdd = min(mdd, e / peak - 1)
print("n trades", len(trades), "open at end", bk.position is not None)
print("final equity %.2f  years %.4f" % (eqs[-1], yrs))
print("CAGR vs start_equity   %.4f%%" % (100 * ((eqs[-1] / 100_000) ** (1 / yrs) - 1)))
print("CAGR vs eq[0] (harness) %.4f%%" % (100 * ((eqs[-1] / eqs[0]) ** (1 / yrs) - 1)))
print("MTM maxDD %.4f%%" % (100 * mdd))
# harness for comparison
sys.path.insert(0, HERE)
import harness as H
tr = H.leg_trades(H.load_bars("btcusd"), "pullback", start_ts=T0, end_ts=T1)
r = H.simulate([H.LegSpec(tr, 1.0)], {"btcusd": H.closes_of(H.load_bars("btcusd"))}, k=1.0, start_ts=T0, end_ts=T1)
s = H.stats(r)
print("HARNESS: CAGR %.4f%%  maxDD %.4f%%  final %.2f  n %d" % (100 * s["cagr"], 100 * s["maxdd"], r.equity[-1], s["n"]))
print("trade lists identical:", [(t.side, t.entry_ts, t.entry_price, t.exit_ts, t.exit_price) for t in tr] == trades)
