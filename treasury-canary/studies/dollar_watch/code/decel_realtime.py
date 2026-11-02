"""Real-time deceleration signal (daily, broad dollar 2006+): FIRE when the 20-day rate of climb has
fallen to <= 50% of its trailing-60-day maximum, that maximum was >= 4% (a genuine scramble), the
dollar is still within 3% of its 60-day high (so it is deceleration, not reversal), and the 10y yield
fell over the scramble (safe-haven type). One firing per 120 days. Outcome: S&P (FRED SP500, 2016+)
and VIX over the next 20/60/120 trading days; for 2008 S&P is unavailable daily -> VIX only."""
import csv, json, sys, os, numpy as np
RAW, OUT = sys.argv[1], sys.argv[2]
def fredd(fid):
    o={}
    for r in csv.DictReader(open(os.path.join(RAW,fid+".csv"))):
        if r[fid] not in ("","."): o[r["observation_date"]]=float(r[fid])
    return o
bd=fredd("DTWEXBGS"); vix=fredd("VIXCLS"); sp=fredd("SP500"); y10=fredd("DGS10")
days=sorted(d for d in bd if d in vix and d in y10); B=np.array([bd[d] for d in days]); V=np.array([vix[d] for d in days]); Y=np.array([y10[d] for d in days]); SP=np.array([sp.get(d,np.nan) for d in days])
roc=np.full(len(B),np.nan)
for k in range(20,len(B)): roc[k]=B[k]/B[k-20]-1
fires=[]; last=-999; last_mx=0.0
REARM = len(sys.argv) > 3 and sys.argv[3] == "rearm"     # re-fire inside the cooling window if a bigger scramble (1.5x) arrived
for k in range(80,len(B)-1):
    mx=np.nanmax(roc[k-60:k+1]); kmx=k-60+int(np.nanargmax(roc[k-60:k+1]))
    if mx>=0.04 and roc[k]<=0.5*mx and B[k]>=0.97*max(B[k-60:k+1]) and Y[k]<Y[max(0,kmx-20)] and (k-last>120 or (REARM and mx>=1.5*last_mx)):
        last=k; last_mx=mx
        def fwd(arr,h): return float(arr[k+h]/arr[k]-1) if k+h<len(arr) and not np.isnan(arr[k+h]) and not np.isnan(arr[k]) else None
        pk=k+int(np.argmax(B[k:min(len(B),k+250)]))
        fires.append({"fire":days[k],"dollar":round(float(B[k]),1),"roc20_max_pct":round(100*mx,1),"roc_max_day":days[kmx],"roc20_now_pct":round(100*roc[k],1),
                      "vix":round(float(V[k]),1),"dollar_peak_next250":days[pk],"dollar_more_rise_pct":round(100*(B[pk]/B[k]-1),1),
                      "spx_fwd20":fwd(SP,20),"spx_fwd60":fwd(SP,60),"spx_fwd120":fwd(SP,120),"vix_fwd60_chg":round(float(V[min(len(V)-1,k+60)]-V[k]),1)})
json.dump(fires,open(os.path.join(OUT,"decel_realtime%s.json"%("_rearm" if REARM else "")),"w"),indent=1)
for f in fires: print(f)
print("n fires", len(fires))
