import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness as H
for pair in ("btcusd","ethusd","ltcusd","xrpusd"):
    b = H.load_bars(pair)
    ts = [x.ts for x in b]
    gaps = [(ts[i-1], ts[i]) for i in range(1,len(ts)) if ts[i]-ts[i-1] != H.BAR_S]
    dup = len(ts)-len(set(ts))
    nonmono = sum(1 for i in range(1,len(ts)) if ts[i] <= ts[i-1])
    zv = sum(1 for x in b if x.volume == 0)
    flat = sum(1 for x in b if x.high == x.low)
    bad = sum(1 for x in b if not (x.low <= min(x.open,x.close) and x.high >= max(x.open,x.close)))
    misal = sum(1 for t in ts if t % H.BAR_S)
    big = sum(g[1]-g[0] for g in gaps)//H.BAR_S - len(gaps)
    print(pair, len(b), "first", ts[0], "gaps", len(gaps), "missing bars", big, "dup", dup, "nonmono", nonmono,
          "zero-vol", zv, "H==L", flat, "OHLC-inconsistent", bad, "misaligned", misal)
    if gaps[:3]: print("   first gaps", gaps[:3], "largest", max((g[1]-g[0])//H.BAR_S for g in gaps) if gaps else 0)
    # open vs prev close gap
    import statistics
    g = [abs(b[i].open/b[i-1].close-1) for i in range(1,len(b))]
    print("   |open/prevclose-1| median %.5f p99 %.4f max %.3f" % (statistics.median(g), sorted(g)[int(.99*len(g))], max(g)))
