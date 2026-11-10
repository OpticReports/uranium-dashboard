"""Does the unit-size (start_equity=1.0) engine book ever silently drop a
trade because qty = round(equity/price, 6) == 0?  Compare vs start_equity=1e9."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness as H
from app.engine import core
from app.engine.core import Book, BookCfg, SignalCfg, TradeCfg
bars = H.load_bars("btcusd"); inds = H.compute_indicators(bars, 20)
tc = TradeCfg(taker_fee_bps=4.32)
def run(se, scfg, start=None):
    orig = H.Book
    class B2(core.Book): pass
    cfg = BookCfg(name="p", sizing="fixed", strategy="pullback", leverage=1.0, cap=1.0, start_equity=se, dd_halt=1e9)
    bk = Book(cfg=cfg)
    for i, bar in enumerate(bars):
        if i < 210 or (start and bar.ts < start): continue
        core.resolve_open_exit(bk, bar, tc)
        core.process_closed_bar(bk, bar, inds[i], scfg, tc, core.eval_signal(bar, inds[i], scfg))
    return [(t.entry_ts, t.exit_ts) for t in bk.trades], min(t.equity_before for t in bk.trades)
for scfg in (SignalCfg(), SignalCfg(rsi_long=50, rsi_short=50), SignalCfg(depth_atr=0.25), SignalCfg(vol_filter=False)):
    a, ma = run(1.0, scfg); b, _ = run(1e9, scfg)
    print(scfg, "from 2011: n unit", len(a), "n big", len(b), "identical", a == b, "min unit equity %.4f" % ma)
