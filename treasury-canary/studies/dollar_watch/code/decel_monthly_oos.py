"""Monthly analogue of the deceleration rule, scored on 1973-2005 (parameters fixed from the daily 2006+
version by analogy, never tuned here): fire when the 3-month rate of climb <= 50% of its trailing-12-month
max, that max >= 6%, DXY >= 97% of its 12-month high, 10y yield lower than 3 months before the ROC max;
12-month cooling. Outcome: Baa-10y spread change and S&P return over the next 6 and 12 months, and
whether the DXY had peaked within +/-3 months of the fire (ex post)."""
import csv, json, sys, os, numpy as np
OUT=sys.argv[1]; rows=list(csv.DictReader(open(os.path.join(OUT,"dollar_monthly.csv"))))
m=[r["month"] for r in rows]; D=np.array([float(r["dxy_spliced"]) for r in rows]); Y=np.array([float(r["gs10"]) for r in rows]); SPR=np.array([float(r["baa_minus_gs10"]) for r in rows]); P=np.array([float(r["spx_shiller"]) for r in rows])
roc=np.full(len(D),np.nan)
for k in range(3,len(D)): roc[k]=D[k]/D[k-3]-1
fires=[]; last=-99
for k in range(15,len(D)-12):
    mx=np.nanmax(roc[k-12:k+1]); kmx=k-12+int(np.nanargmax(roc[k-12:k+1]))
    if mx>=0.06 and roc[k]<=0.5*mx and D[k]>=0.97*max(D[k-12:k+1]) and Y[k]<Y[max(0,kmx-3)] and k-last>=12:
        last=k; pk=k-3+int(np.argmax(D[max(0,k-3):min(len(D),k+13)]))
        fires.append({"fire":m[k],"dxy":round(float(D[k]),1),"roc3_max_pct":round(100*mx,1),"roc_max_month":m[kmx],"dollar_more_rise_pct":round(100*(max(D[k:k+13])/D[k]-1),1),
                      "dollar_peak_within_pm3m":bool(abs(pk-k)<=3 and D[pk]>=max(D[k-3:k+13])*0.999),"spread_chg_6m":round(float(SPR[k+6]-SPR[k]),2),"spread_chg_12m":round(float(SPR[k+12]-SPR[k]),2),
                      "spx_6m_pct":round(100*float(P[k+6]/P[k]-1),1),"spx_12m_pct":round(100*float(P[k+12]/P[k]-1),1),"sample":"pre-2006 (unseen)" if m[k]<"2006-01" else "2006+ (seen daily)"})
json.dump(fires,open(os.path.join(OUT,"decel_monthly_oos.json"),"w"),indent=1)
for f in fires: print(f)
pre=[f for f in fires if f["sample"].startswith("pre")]
print("pre-2006 firings:",len(pre),"| dollar peaked within +/-3m:",sum(f["dollar_peak_within_pm3m"] for f in pre),"| median further rise %:",np.median([f["dollar_more_rise_pct"] for f in pre]),"| S&P 12m>0:",sum(f["spx_12m_pct"]>0 for f in pre),"| spread narrower 12m:",sum(f["spread_chg_12m"]<0 for f in pre))
# base rates for comparison: any month 1973-2005
base=[k for k in range(15,len(D)-12) if m[k]<"2006-01"]
print("base 1973-2005: S&P 12m>0:",round(np.mean([P[k+12]>P[k] for k in base]),2),"| spread narrower 12m:",round(np.mean([SPR[k+12]<SPR[k] for k in base]),2),"| dollar peak within +/-3m (ex post):",round(np.mean([abs((k-3+int(np.argmax(D[max(0,k-3):min(len(D),k+13)])))-k)<=3 for k in base]),2))
