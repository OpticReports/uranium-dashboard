"""MECHANICAL ONLY (volatility, no returns-after, no gates, no firings): sigma_B on two calendars and vintages, and how
often the SPEC's s = sigma_X(756d ending k-61)/sigma_B hits the [0.25, 8] clip on peg-filter-eligible days."""
import csv, math, os, sys, statistics as st
REPO, DL, ALF = sys.argv[1:4]
def fredd(path, fid):
    o = {}
    for r in csv.reader(open(path)):
        if r and r[0] != "observation_date" and len(r) > 1 and r[1] not in ("", "."): o[r[0]] = float(r[1])
    return o
B = fredd(os.path.join(REPO, "DTWEXBGS.csv"), "DTWEXBGS"); Y = fredd(os.path.join(REPO, "DGS10.csv"), "DGS10"); V = fredd(os.path.join(REPO, "VIXCLS.csv"), "VIXCLS")
def sd_logchg(series, days):
    x = [math.log(series[b] / series[a]) for a, b in zip(days, days[1:])]
    return st.pstdev(x), st.stdev(x), len(x)
own = sorted(d for d in B if "2006-01-03" <= d <= "2026-10-23")
byv = sorted(d for d in own if d in Y and d in V)
for lab, cal in (("own days", own), ("B&Y&V", byv)):
    p, s, n = sd_logchg(B, cal); print(f"sigma_B {lab}: pop {100*p:.4f}% sample {100*s:.4f}% n={n}")
old = fredd(os.path.join(ALF, "v_2019-02-04.bin"), "x"); oc = sorted(d for d in old if d >= "2006-01-03")
p, s, n = sd_logchg(old, oc); p2, s2, n2 = sd_logchg(B, [d for d in own if d <= oc[-1]])
print(f"sigma_B 2006-01-03..2019-02-01: vintage 2019-02-04 {100*s:.4f}% vs current vintage {100*s2:.4f}%")
sigB = sd_logchg(B, own)[1]
IDS = ["DEXBZUS", "DEXMXUS", "DEXKOUS", "DEXSFUS", "DEXINUS", "DEXTHUS", "DEXMAUS", "DEXTAUS", "DEXSIUS", "DEXSLUS",
       "DEXCAUS", "DEXUSAL", "DEXUSNZ", "DEXNOUS", "DEXSDUS"]
for sid in IDS:
    p = os.path.join(REPO, sid + ".csv")
    if not os.path.exists(p): p = os.path.join(DL, sid + ".csv")
    X = fredd(p, sid); d = sorted(k for k in X if k >= "1973-03-01")
    lc = [math.log(X[b] / X[a]) for a, b in zip(d, d[1:])]          # change ending at index i+1
    zero = [c == 0.0 for c in lc]
    lo = hi = elig = 0; lo_years = {}; svals = []
    for k in range(756 + 61, len(d)):
        w0 = zero[k - 60:k]                               # trailing 60 changes ending at k
        if sum(w0) >= 30: continue
        win = lc[k - 61 - 756:k - 61]                     # 756 changes ending at k-61
        sx = st.stdev(win)
        if sx <= 0: continue
        elig += 1; s = sx / sigB; svals.append(s)
        if s < 0.25: lo += 1; lo_years[d[k][:4]] = lo_years.get(d[k][:4], 0) + 1
        if s > 8: hi += 1
    yrs = sorted(lo_years); spans = []
    for y in yrs:
        if spans and int(y) == int(spans[-1][1]) + 1: spans[-1][1] = y
        else: spans.append([y, y])
    print(f"{sid}: eligible days {elig} | s median {st.median(svals):.2f} p10 {sorted(svals)[len(svals)//10]:.2f} p90 {sorted(svals)[9*len(svals)//10]:.2f}"
          f" | clip<0.25 binds {lo} ({100*lo/max(1,elig):.1f}%) in {','.join(a if a==b else a+'-'+b for a,b in spans) or '-'} | clip>8 {hi}")
