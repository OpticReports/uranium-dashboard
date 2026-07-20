"""Offline reconstruction of the VIX-midterm harvester through 2018+2020.
Voters w=2..7 on SPY RSI (Wilder): <25 -> (UVXY RSI14>70 ? stand-aside : short-vol)
                                   >80 -> long VXZ ; else cash.
ZVOL synthetic = -1x VXZ daily - 0.6bp/day drag. Cash = 2%/yr.
Variants: BASE / GUARD (block short-vol when HYG 1d < -1%) / RIDER (stand-aside -> long VXZ).
Fidelity check: BASE sim vs actual Composer backtest 2023-04+.
"""
import json, datetime, math
SC = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad"

def load(t):
    r = json.load(open(f"{SC}/yh-{t}.json"))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    out = {}
    for ts, c in zip(r["timestamp"], q["close"]):
        if c is not None:
            out[datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date()] = c
    return out

spy, uvxy, vxz, hyg = load("SPY"), load("UVXY"), load("VXZ"), load("HYG")

def wilder_rsi(closes, n):
    rsis = [None]*len(closes)
    gains = losses = 0.0
    for i in range(1, len(closes)):
        ch = closes[i]-closes[i-1]
        g, l = max(ch,0), max(-ch,0)
        if i <= n:
            gains += g; losses += l
            if i == n:
                ag, al = gains/n, losses/n
                rsis[i] = 100 - 100/(1+ag/al) if al else 100.0
        else:
            ag = (ag*(n-1)+g)/n; al = (al*(n-1)+l)/n
            rsis[i] = 100 - 100/(1+ag/al) if al else 100.0
    return rsis

sdates = sorted(spy)
sclose = [spy[d] for d in sdates]
rsi_spy = {n: dict(zip(sdates, wilder_rsi(sclose, n))) for n in range(2, 8)}
udates = sorted(uvxy)
rsi_uvxy = dict(zip(udates, wilder_rsi([uvxy[d] for d in udates], 14)))

vdates = sorted(vxz)
vret = {vdates[i]: vxz[vdates[i]]/vxz[vdates[i-1]]-1 for i in range(1, len(vdates))}
hret = {}
hd = sorted(hyg)
for i in range(1, len(hd)):
    hret[hd[i]] = hyg[hd[i]]/hyg[hd[i-1]]-1
CASH = 0.02/252
DRAG = 0.00006

def run(variant, d0, d1):
    days = [d for d in vdates if d0 <= d <= d1 and d in rsi_spy[2] and d in rsi_uvxy]
    curve = [1.0]; out_days = []
    for i in range(1, len(days)):
        d, prev = days[i], days[i-1]      # signals from prev close, returns on d
        r_tot = 0.0
        for n in range(2, 8):
            rs = rsi_spy[n].get(prev); ru = rsi_uvxy.get(prev)
            if rs is None or ru is None: r = CASH
            elif rs < 25:
                if ru > 70:
                    r = vret.get(d, 0.0) if variant == "RIDER" else CASH
                else:
                    blocked = variant == "GUARD" and hret.get(prev, 0) < -0.01
                    r = CASH if blocked else (-vret.get(d, 0.0) - DRAG)
            elif rs > 80: r = vret.get(d, 0.0)
            else: r = CASH
            r_tot += r/6
        curve.append(curve[-1]*(1+r_tot))
        out_days.append(d)
    return out_days, curve[1:]

def stats(days, curve):
    yrs = len(curve)/252
    cagr = curve[-1]**(1/yrs)-1 if curve[-1] > 0 else -1
    rets = [curve[i]/curve[i-1]-1 for i in range(1, len(curve))]
    mu = sum(rets)/len(rets); sd = math.sqrt(sum((x-mu)**2 for x in rets)/(len(rets)-1))
    peak, mdd = curve[0], 0
    for v in curve:
        peak = max(peak, v); mdd = max(mdd, 1-v/peak)
    return cagr, (mu/sd*math.sqrt(252) if sd else 0), mdd

def window_ret(days, curve, a, b):
    ix = [i for i, d in enumerate(days) if a <= d <= b]
    if not ix: return None
    return curve[ix[-1]]/curve[ix[0]]-1

D0, D1 = datetime.date(2018,1,26), datetime.date(2023,4,18)
EP = [("Volmageddon Feb-2018", datetime.date(2018,2,1),  datetime.date(2018,2,28)),
      ("Dec-2018",             datetime.date(2018,12,1), datetime.date(2018,12,31)),
      ("COVID crash",          datetime.date(2020,2,19), datetime.date(2020,3,23)),
      ("COVID recovery",       datetime.date(2020,3,24), datetime.date(2020,6,30)),
      ("2022 full year",       datetime.date(2022,1,1),  datetime.date(2022,12,31))]
print(f"{'variant':7} {'CAGR':>7} {'Sharpe':>7} {'maxDD':>7} | " + " | ".join(e[0] for e in EP))
for var in ("BASE","GUARD","RIDER"):
    days, curve = run(var, D0, D1)
    c,s,dd = stats(days, curve)
    eps = [window_ret(days, curve, a, b) for _,a,b in EP]
    print(f"{var:7} {c:+7.1%} {s:7.2f} {dd:7.1%} | " + " | ".join(f"{e:+8.1%}" for e in eps))

# fidelity check vs actual Composer backtest 2023-04+
actual = json.load(open(f"{SC}/curve-vixfut-long.json"))
days, curve = run("BASE", datetime.date(2023,4,19), datetime.date(2026,7,17))
simc = dict(zip([d.isoformat() for d in days], curve))
common = sorted(set(simc) & set(actual))
sv = [simc[d] for d in common]; av = [actual[d] for d in common]
sr = [sv[i]/sv[i-1]-1 for i in range(1,len(sv))]
ar = [av[i]/av[i-1]-1 for i in range(1,len(av))]
mu_s, mu_a = sum(sr)/len(sr), sum(ar)/len(ar)
cov = sum((a-mu_s)*(b-mu_a) for a,b in zip(sr,ar))
corr = cov/math.sqrt(sum((a-mu_s)**2 for a in sr)*sum((b-mu_a)**2 for b in ar))
yrs = len(common)/252
print(f"\nFIDELITY (sim vs Composer, {len(common)} td): daily corr {corr:.3f}; "
      f"sim cagr {(sv[-1]/sv[0])**(1/yrs)-1:+.1%} vs actual {(av[-1]/av[0])**(1/yrs)-1:+.1%}")
