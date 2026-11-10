"""SCOPING (not pre-registered): dollar momentum and level vs what followed, monthly 1973-2026.
Dollar = FRED major-currencies index (TWEXMMTH 1973-2019) spliced to the advanced-economies index
(DTWEXAFEGS monthly mean, 2006+) at the 2019-12 ratio, then rescaled to ICE DXY units by the median
ratio to Yahoo DX-Y.NYB monthly closes on overlapping months (1985+). Outcomes over the next 12
months: S&P 500 max drawdown (Shiller monthly price), max rise in the Baa - 10y Treasury spread,
NBER recession start. Features: 6-month dollar change, 6-month change in the 10y yield (sign splits
'safe-haven' rises from 'policy' rises), dollar level vs the 85/105 band."""
import csv, json, sys, os, math, datetime as dt
import numpy as np
RAW, OUT = sys.argv[1], sys.argv[2]
def fred(fid, how="mean"):
    out={}
    for r in csv.DictReader(open(os.path.join(RAW,fid+".csv"))):
        v=r[fid]
        if v in ("","."): continue
        out.setdefault(r["observation_date"][:7],[]).append(float(v))
    return {m:(sum(v)/len(v) if how=="mean" else v[-1]) for m,v in out.items()}
maj=fred("TWEXMMTH"); afe=fred("DTWEXAFEGS"); gs10=fred("GS10"); baa=fred("BAA"); rec=fred("USREC")
# splice
k=maj["2019-12"]/afe["2019-12"]
dol={m:v for m,v in maj.items()}
for m,v in afe.items():
    if m>"2019-12": dol[m]=v*k
# rescale to DXY units via yahoo overlap
j=json.load(open(os.path.join(RAW,"yahoo_dxy.json")))["chart"]["result"][0]
ym={}
for ts,c in zip(j["timestamp"],j["indicators"]["quote"][0]["close"]):
    if c is not None: ym[dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m")]=c
ratios=[ym[m]/dol[m] for m in ym if m in dol]
scale=float(np.median(ratios)); proxy={m:v*scale for m,v in dol.items()}
# REAL ICE DXY (monthly average of daily closes, finder A's Yahoo pull 1971+) replaces the proxy when present
real={}
fa=os.path.join(RAW,"finderA_dollar_monthly.csv")
if os.path.exists(fa):
    for r in csv.DictReader(open(fa)):
        if r["dxy_avg"]: real[r["month"]]=float(r["dxy_avg"])
dxy = real if real else proxy
print("dollar series:", "ICE DXY monthly avg (real)" if real else "FRED proxy", "| proxy-vs-real median ratio", round(float(np.median([real[m]/proxy[m] for m in real if m in proxy])),3) if real else None)
# Shiller S&P monthly price
import xlrd
wb=xlrd.open_workbook(os.path.join(RAW,"shiller_ie_data.xls")); sh=wb.sheet_by_name("Data")
spx={}
for i in range(8, sh.nrows):
    d=sh.cell_value(i,0); p=sh.cell_value(i,1)
    if isinstance(d,float) and d>1870 and isinstance(p,float):
        y=int(d); mth=int(round((d-y)*100)); 
        if mth==0: mth=10  # 1871.1 means Oct? Shiller uses .01..12 with .1 = Oct (floating artefact)
        spx[f"{y}-{mth:02d}"]=p
sp_recent=fred("SP500")          # monthly mean of daily closes, same basis as Shiller's monthly average
# Shiller's last row (2023-09) is a single-day close, not a monthly mean (reviewer S3): prefer FRED from 2023-09 on
for m,v in sp_recent.items():
    if m>="2023-09": spx[m]=v
months=[m for m in sorted(dxy) if m>="1973-01" and m in gs10 and m in baa and m in spx]
print("months", months[0], months[-1], len(months))
D=np.array([dxy[m] for m in months]); Y=np.array([gs10[m] for m in months]); SPR=np.array([baa[m]-gs10[m] for m in months]); P=np.array([spx[m] for m in months]); R=np.array([rec.get(m,0) for m in months])
T=len(months); H=12
rows=[]
for t in range(6, T-1):
    d6=D[t]/D[t-6]-1; y6=Y[t]-Y[t-6]; d12=D[t]/D[t-12]-1 if t>=12 else None
    fut=P[t:min(T,t+H+1)]; peak=-1e9; dd=0
    for v in fut: peak=max(peak,v); dd=max(dd,1-v/peak)
    spr_rise=float(max(SPR[t:min(T,t+H+1)])-SPR[t])
    rec_start=any(R[k]==1 and R[k-1]==0 for k in range(t+1,min(T,t+H+1)))
    rows.append({"month":months[t],"dxy":float(D[t]),"d6":float(d6),"d12":d12,"y6":float(y6),"above105":bool(D[t]>105),"below85":bool(D[t]<85),
                 "spx_maxdd12":float(dd),"spr_rise12":spr_rise,"rec_start12":bool(rec_start),"n_fut":int(len(fut)-1)})
full=[r for r in rows if r["n_fut"]==H]
def summ(sel,label):
    n=len(sel); 
    if n==0: return {"group":label,"n":0}
    return {"group":label,"n":n,"p_spx_dd20":float(np.mean([r["spx_maxdd12"]>=0.20 for r in sel])),"med_spx_dd":float(np.median([r["spx_maxdd12"] for r in sel])),
            "p_spread_up100bp":float(np.mean([r["spr_rise12"]>=1.0 for r in sel])),"med_spread_rise":float(np.median([r["spr_rise12"] for r in sel])),"p_rec_start":float(np.mean([r["rec_start12"] for r in sel]))}
res={"all":summ(full,"all months")}
q=np.percentile([r["d6"] for r in full],[20,40,60,80])
labs=["q1 weakest","q2","q3","q4","q5 strongest"]
res["by_d6_quintile"]=[]
for i in range(5):
    lo=-9 if i==0 else q[i-1]; hi=9 if i==4 else q[i]
    res["by_d6_quintile"].append(summ([r for r in full if lo<=r["d6"]<hi], f"{labs[i]} [{lo:+.3f},{hi:+.3f})"))
res["speed"]=[summ([r for r in full if r["d6"]>=thr], f"6m rise >= {thr:.0%}") for thr in (0.05,0.08,0.10,0.15)]+[summ([r for r in full if r["d6"]<=-thr], f"6m fall <= -{thr:.0%}") for thr in (0.05,0.08,0.10)]
res["quadrant"]=[summ([r for r in full if r["d6"]>=0.05 and r["y6"]<=-0.25], "dollar up >=5% & 10y down >=25bp (safe-haven type)"),
                 summ([r for r in full if r["d6"]>=0.05 and r["y6"]>=0.25], "dollar up >=5% & 10y up >=25bp (policy type)"),
                 summ([r for r in full if r["d6"]<=-0.05 and r["y6"]<=-0.25], "dollar down >=5% & 10y down"),
                 summ([r for r in full if r["d6"]<=-0.05 and r["y6"]>=0.25], "dollar down >=5% & 10y up"),
                 summ([r for r in full if abs(r["d6"])<0.05], "dollar flat (|6m| < 5%)")]
res["band"]=[summ([r for r in full if r["above105"]], "DXY > 105"), summ([r for r in full if r["below85"]], "DXY < 85"), summ([r for r in full if 85<=r["dxy"]<=105], "85 <= DXY <= 105")]
# excursions
exc=[]; state=None; start=None
for r in rows:
    s="above" if r["above105"] else "below" if r["below85"] else None
    if s!=state:
        if state is not None: exc.append({"type":state,"start":start,"end":prev})
        state=s; start=r["month"]
    prev=r["month"]
if state is not None: exc.append({"type":state,"start":start,"end":prev})
res["excursions"]=exc
# end-of-crisis test: 6m rise >= 10% episodes (first trigger, 12m cooling): forward 12m S&P return from trigger vs from the dollar's subsequent peak (ex post) vs from the real-time turn (first month 3% below the trailing 6m high after the trigger)
eps=[]; last=-99
for t in range(6,T-13):
    if D[t]/D[t-6]-1>=0.10 and t-last>=12:
        last=t
        pk=t+int(np.argmax(D[t:t+13]))
        turn=next((k for k in range(t+1,min(T-12,t+24)) if D[k]<=max(D[max(0,k-6):k+1])*0.97), None)
        e={"trigger":months[t],"dxy":round(float(D[t]),1),"spx_fwd12_from_trigger":float(P[t+12]/P[t]-1),"dxy_peak":months[pk],"spx_fwd12_from_peak":float(P[min(T-1,pk+12)]/P[pk]-1) if pk+12<T else None,
           "realtime_turn":months[turn] if turn else None,"spx_fwd12_from_turn":float(P[turn+12]/P[turn]-1) if turn and turn+12<T else None,"spx_dd_trigger_to_peak":float(1-min(P[t:pk+1])/P[t]) if pk>t else 0.0}
        eps.append(e)
res["speed_episodes"]=eps
res["current"]={"month":months[-1],"dxy":float(D[-1]),"d6":float(D[-1]/D[-7]-1),"d12":float(D[-1]/D[-13]-1),"y6":float(Y[-1]-Y[-7])}
json.dump(res,open(os.path.join(OUT,"dollar_summary.json"),"w"),indent=1)
json.dump(rows,open(os.path.join(OUT,"dollar_rows.json"),"w"))
with open(os.path.join(OUT,"dollar_monthly.csv"),"w") as f:
    w=csv.writer(f); w.writerow(["month","dxy_spliced","gs10","baa_minus_gs10","spx_shiller","usrec"])
    for i,m in enumerate(months): w.writerow([m,round(D[i],3),Y[i],round(SPR[i],3),P[i],int(R[i])])
def pr(g): return f"{g['group']:52s} n={g['n']:4d}" + (f" P(S&P dd>=20%)={g['p_spx_dd20']:.2f} medDD={g['med_spx_dd']:.2f} P(spread+100bp)={g['p_spread_up100bp']:.2f} medSpr={g['med_spread_rise']:+.2f} P(rec start)={g['p_rec_start']:.2f}" if g['n'] else "")
print(pr(res["all"]))
for k in ("by_d6_quintile","speed","quadrant","band"):
    print("--",k); [print("  ",pr(g)) for g in res[k]]
print("excursions:", [(e["type"],e["start"],e["end"]) for e in exc])
print("speed episodes:"); [print("  ",e) for e in eps]
print("current", res["current"])
