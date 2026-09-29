import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness as H
b = H.load_bars("btcusd")
d = lambda t: time.strftime("%Y-%m-%d %H", time.gmtime(t))
g = sorted(((abs(b[i].open/b[i-1].close-1), i) for i in range(1,len(b))), reverse=True)[:8]
for v,i in g: print("gap %.3f"%v, d(b[i].ts), b[i-1].close, b[i].open, b[i].high, b[i].low, b[i].close)
t13 = H.ts_of("2013-01-01")
zv = [x for x in b if x.volume==0]
print("zero-vol total", len(zv), "after 2013:", sum(1 for x in zv if x.ts>=t13), "after 2014:", sum(1 for x in zv if x.ts>=H.ts_of("2014-01-01")))
yrs = {}
for x in zv: yrs[d(x.ts)[:4]] = yrs.get(d(x.ts)[:4],0)+1
print(yrs)
# extreme bar ranges
r = sorted(((x.high/x.low-1, x) for x in b if x.ts>=t13), key=lambda z:-z[0])[:5]
for v,x in r: print("range %.3f"%v, d(x.ts), x.open,x.high,x.low,x.close,x.volume)
