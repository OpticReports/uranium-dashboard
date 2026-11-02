# Re-implement decel_realtime rule (rearm) from scoping/raw and from fresh FRED pulls; verify decel_test numbers
import csv, numpy as np, json, pandas as pd
def fredd(path):
    o={}
    for r in csv.DictReader(open(path)):
        k=[c for c in r if c!='observation_date'][0]
        if r[k] not in ('','.'): o[r['observation_date']]=float(r[k])
    return o
def run(R, tag):
    bd=fredd(R+'DTWEXBGS.csv'); vix=fredd(R+'VIXCLS.csv'); sp=fredd(R+'SP500.csv'); y10=fredd(R+'DGS10.csv')
    days=sorted(d for d in bd if d in vix and d in y10); B=np.array([bd[d] for d in days]); V=np.array([vix[d] for d in days]); Y=np.array([y10[d] for d in days]); SP=np.array([sp.get(d,np.nan) for d in days])
    print(f'\n[{tag}] days {days[0]}..{days[-1]} n={len(days)}; SP500 from {min(sp)}')
    roc=np.full(len(B),np.nan); roc[20:]=B[20:]/B[:-20]-1
    fires=[]; last=-999; last_mx=0
    for k in range(80,len(B)-1):
        win=roc[k-60:k+1]; mx=np.nanmax(win); kmx=k-60+int(np.nanargmax(win))
        c1=mx>=0.04; c2=roc[k]<=0.5*mx; c3=B[k]>=0.97*B[k-60:k+1].max(); c4=Y[k]<Y[max(0,kmx-20)]
        if c1 and c2 and c3 and c4 and (k-last>120 or mx>=1.5*last_mx):
            last=k; last_mx=mx
            pk=k+int(np.argmax(B[k:k+250]))
            f=dict(fire=days[k], dollar=round(B[k],1), mx=round(100*mx,1), mxday=days[kmx], roc_now=round(100*roc[k],1), vix=round(V[k],1), peak=days[pk], more=round(100*(B[pk]/B[k]-1),1),
                   spx60=(round(SP[k+60]/SP[k]-1,4) if k+60<len(SP) and not np.isnan(SP[k]) and not np.isnan(SP[k+60]) else None), vix60=round(V[min(len(V)-1,k+60)]-V[k],1))
            fires.append(f); print('  ', f)
    print('  n fires', len(fires))
    # decel_test daily checks
    for lo,hi,lab in (("2008-06-01","2009-06-30","GFC"),("2022-01-01","2023-01-31","2022")):
        idx=[i for i,d in enumerate(days) if lo<=d<=hi]; a,b=idx[0],idx[-1]; pk=a+int(np.argmax(B[a:b+1]))
        rc=np.array([B[k]/B[k-20]-1 for k in range(a,pk+1)]); rk=a+int(np.argmax(rc)); vk=a+int(np.argmax(V[a:b+1]))
        print(f'  decel_test {lab}: $ peak {days[pk]} {B[pk]:.1f}; ROC20 peak {days[rk]} {100*rc.max():.1f}%; VIX peak {days[vk]}; $ rise after rocpk {100*(B[pk]/B[rk]-1):.1f}%')
run('../scoping/raw/','scoping raw')
run('raw/fred_','fresh FRED')
# monthly decel_test checks on out/dollar_monthly.csv
rows=list(csv.DictReader(open('../scoping/out/dollar_monthly.csv'))); m=[r['month'] for r in rows]; D=np.array([float(r['dxy_spliced']) for r in rows]); P=np.array([float(r['spx_shiller']) for r in rows])
for trig in ('2008-09','2022-05'):
    t=m.index(trig); w0=max(6,t-6); w1=min(len(m)-1,t+18); pk=w0+int(np.argmax(D[w0:w1+1]))
    roc3=np.array([D[k]/D[k-3]-1 for k in range(w0,pk+1)]); rk=w0+int(np.argmax(roc3)); st=w0+int(np.argmin(P[w0:min(len(m)-1,pk+6)+1]))
    print(f'monthly {trig}: $ peak {m[pk]}, ROC3 peak {m[rk]} ({100*roc3.max():.1f}%), S&P trough {m[st]}, rise after {100*(D[pk]/D[rk]-1):.1f}%')
    print('    6m change at trigger', round(D[t]/D[t-6]-1,3), 'previous triggers >=8% in 12m?', [(m[k], round(D[k]/D[k-6]-1,3)) for k in range(t-12,t) if D[k]/D[k-6]-1>=0.08])
