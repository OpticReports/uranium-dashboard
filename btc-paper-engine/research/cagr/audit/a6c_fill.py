"""Pullback limit-entry fill model: backtest fills only if low(t+1) < close(t)
(strict); live executor's limit at close(t) is typically marketable (fees study:
4/4 intended-maker entries crossed). Measure unfilled share and the always-fill
counterfactual."""
import sys, os, inspect, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness as H
from app.engine import core
bars = H.load_bars("btcusd"); closes = {"btcusd": H.closes_of(bars)}; inds = H.compute_indicators(bars, 20)
src = inspect.getsource(core._process_pullback)
old = 'filled = (bar.low < p.limit) if p.side == "L" else (bar.high > p.limit)'
assert old in src
ns = dict(core.__dict__); exec(src.replace(old, "filled = True").replace("def _process_pullback", "def _pp_always"), ns)
for a, b in (("2013-01-01", "2026-07-31"), ("2019-01-01", "2026-07-31")):
    T0, T1 = H.ts_of(a), H.ts_of(b)+86399
    base = H.leg_trades(bars, "pullback", start_ts=T0, end_ts=T1, inds=inds)
    orig = core._process_pullback; core._process_pullback = ns["_pp_always"]
    try: alw = H.leg_trades(bars, "pullback", start_ts=T0, end_ts=T1, inds=inds)
    finally: core._process_pullback = orig
    sb = H.stats(H.simulate([H.LegSpec(base, 1.0)], closes, 1.0, T0, T1))
    sa = H.stats(H.simulate([H.LegSpec(alw, 1.0)], closes, 1.0, T0, T1))
    print(f"{a}..{b}: backtest-fill n={sb['n']} CAGR {sb['cagr']*100:.1f}% dd {sb['maxdd']*100:.1f}% | always-fill n={sa['n']} CAGR {sa['cagr']*100:.1f}% dd {sa['maxdd']*100:.1f}%")
# signals that never fill
T0 = H.ts_of("2013-01-01"); idx = {b.ts: i for i, b in enumerate(bars)}
sig = unf = 0
for i, b in enumerate(bars[:-1]):
    if b.ts < T0: continue
    s = core.eval_signal(b, inds[i], core.SignalCfg())
    if s is None: continue
    sig += 1; n = bars[i+1]
    if (s == "L" and not n.low < b.close) or (s == "S" and not n.high > b.close): unf += 1
print("raw signal bars since 2013:", sig, "next bar never trades through the limit:", unf, f"({unf/sig*100:.1f}%)")
