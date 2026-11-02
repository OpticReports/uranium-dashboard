"""SCOPING: Casey's deceleration rule. Does the PEAK RATE OF CLIMB of the dollar (second derivative turning
negative) come before the dollar's own peak and line up with the peak of the stress (S&P trough, spread
peak, VIX peak)? Monthly 1973-2026 on the spliced major-currency series; daily 2006-2026 on the broad
dollar (DTWEXBGS) with VIX (and FRED SP500 from 2016)."""
import csv, json, sys, os, numpy as np, datetime as dt
RAW, OUT = sys.argv[1], sys.argv[2]
rows=list(csv.DictReader(open(os.path.join(OUT,"dollar_monthly.csv"))))
m=[r["month"] for r in rows]; D=np.array([float(r["dxy_spliced"]) for r in rows]); P=np.array([float(r["spx_shiller"]) for r in rows]); SPR=np.array([float(r["baa_minus_gs10"]) for r in rows])
T=len(m); out={"monthly":[]}
last=-99
for t in range(6,T-18):
    if D[t]/D[t-6]-1>=0.08 and t-last>=12:
        last=t
        w0=max(6,t-6); w1=min(T-1,t+18)             # window: 6 months before the trigger to 18 after
        pk=w0+int(np.argmax(D[w0:w1+1]))
        roc3=np.array([D[k]/D[k-3]-1 for k in range(w0,pk+1)]); rocpk=w0+int(np.argmax(roc3))
        strough=w0+int(np.argmin(P[w0:min(T-1,pk+6)+1])); sprpk=w0+int(np.argmax(SPR[w0:min(T-1,pk+6)+1]))
        out["monthly"].append({"trigger":m[t],"dollar_peak":m[pk],"roc3_peak":m[rocpk],"roc3_max":round(float(roc3.max()),3),
            "spx_trough":m[strough],"spread_peak":m[sprpk],"lead_rocpk_to_dollarpk_m":pk-rocpk,"rocpk_to_spx_trough_m":strough-rocpk,"rocpk_to_spread_peak_m":sprpk-rocpk,
            "dollar_rise_after_rocpk_pct":round(100*(D[pk]/D[rocpk]-1),1)})
# daily
def fredd(fid):
    o={}
    for r in csv.DictReader(open(os.path.join(RAW,fid+".csv"))):
        if r[fid] not in ("","."): o[r["observation_date"]]=float(r[fid])
    return o
bd=fredd("DTWEXBGS"); vix=fredd("VIXCLS"); sp=fredd("SP500")
days=sorted(d for d in bd if d in vix); B=np.array([bd[d] for d in days]); V=np.array([vix[d] for d in days]); SP=np.array([sp.get(d,np.nan) for d in days])
out["daily"]=[]
for lo,hi,lab in (("2008-06-01","2009-06-30","GFC 2008-09"),("2020-01-15","2020-06-30","COVID 2020"),("2022-01-01","2023-01-31","2022 hikes/gilt/JGB"),("2014-06-01","2016-03-31","EM/oil 2014-16"),("2018-01-01","2019-01-31","EM/Q4 2018"),("2025-01-01","2025-06-30","tariff shock 2025")):
    idx=[i for i,d in enumerate(days) if lo<=d<=hi]
    if len(idx)<60: continue
    a,b=idx[0],idx[-1]; seg=B[a:b+1]; pk=a+int(np.argmax(seg))
    roc=np.array([B[k]/B[k-20]-1 for k in range(a,pk+1)]); rocpk=a+int(np.argmax(roc))
    vpk=a+int(np.argmax(V[a:b+1])); spseg=SP[a:b+1]; stro=(a+int(np.nanargmin(spseg))) if not np.all(np.isnan(spseg)) else None
    out["daily"].append({"episode":lab,"dollar_peak":days[pk],"roc20_peak":days[rocpk],"roc20_max_pct":round(100*float(roc.max()),1),"vix_peak":days[vpk],"spx_trough":days[stro] if stro else None,
        "lead_rocpk_to_dollarpk_days":pk-rocpk,"rocpk_vs_vixpk_days":vpk-rocpk,"rocpk_vs_spxtrough_days":(stro-rocpk) if stro else None,"dollar_rise_after_rocpk_pct":round(100*(B[pk]/B[rocpk]-1),1),
        "dollar_level_peak":round(float(B[pk]),1)})
json.dump(out,open(os.path.join(OUT,"decel_test.json"),"w"),indent=1)
print("MONTHLY (3-month rate of climb; months):")
for e in out["monthly"]: print("  ",e)
print("DAILY (20-day rate of climb, broad dollar; trading days):")
for e in out["daily"]: print("  ",e)
