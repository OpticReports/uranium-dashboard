import csv, numpy as np, pandas as pd
A='../finderA/data/'
# 1. strict-window recount (s+1..s+12) for finder A excursions and speed
dm=[r for r in csv.DictReader(open(A+'dollar_monthly.csv')) if r['dxy_close']]
months=[r['month'] for r in dm]; close={r['month']:float(r['dxy_close']) for r in dm}; idx={m:i for i,m in enumerate(months)}
cr=[c for c in csv.DictReader(open(A+'crises.csv')) if c['is_crisis']=='1']; starts={c['start'] for c in cr}
def start_in(i0,i1): return any(months[k] in starts for k in range(max(0,i0),min(len(months)-1,i1)+1))
runs=[]; cur=None
for m in months:
    side='above' if close[m]>105 else ('below' if close[m]<85 else None)
    if side and cur and cur[0]==side: cur[2]=m
    else:
        if cur: runs.append(cur)
        cur=[side,m,m] if side else None
if cur: runs.append(cur)
mg=[]
for side,s,e in runs:
    if mg and mg[-1][0]==side and idx[s]-idx[mg[-1][2]]-1<=3: mg[-1][2]=e
    else: mg.append([side,s,e])
for lab,rs in [('raw',runs),('merged3',mg)]:
    inc=sum(start_in(idx[s],idx[s]+11) for _,s,e in rs); strict=sum(start_in(idx[s]+1,idx[s]+12) for _,s,e in rs); same=sum(s in starts for _,s,e in rs)
    inc24=sum(start_in(idx[s],idx[s]+23) for _,s,e in rs); strict24=sum(start_in(idx[s]+1,idx[s]+24) for _,s,e in rs)
    print(f"{lab}: n={len(rs)} hit12 inclusive(s..s+11)={inc} strict(s+1..s+12)={strict} same-month-start={same} | hit24 incl={inc24} strict={strict24}")
for thr in (8,10,15):
    trig=[i>=6 and 100*(close[months[i]]/close[months[i-6]]-1)>=thr for i in range(len(months))]
    rs=[]; cur=None
    for i,t in enumerate(trig):
        if t and cur: cur[2]=months[i]
        elif t: cur=['r',months[i],months[i]]
        elif cur: rs.append(cur); cur=None
    if cur: rs.append(cur)
    print(f"speed>={thr}: n={len(rs)} hit12 incl={sum(start_in(idx[s],idx[s]+11) for _,s,e in rs)} strict={sum(start_in(idx[s]+1,idx[s]+12) for _,s,e in rs)} same-month={sum(s in starts for _,s,e in rs)}")
# 2. gold 2020 / 2022 intraday
gd={r['date']:(float(r['high']),float(r['low']),float(r['close'])) for r in csv.DictReader(open(A+'gold_daily.csv'))}
print('2020-03-09 high', gd['2020-03-09'][0], '2020-03-16 low', gd['2020-03-16'][1], f"{100*(gd['2020-03-16'][1]/gd['2020-03-09'][0]-1):.1f}%")
seg={d:v for d,v in gd.items() if '2020-03-01'<=d<='2020-03-31'}; print('Mar-2020 max high', max(seg.items(), key=lambda x:x[1][0]), 'min low', min(seg.items(), key=lambda x:x[1][1]))
print('2022-10-21 low', gd['2022-10-21'][1], '2022-11-03 low', gd['2022-11-03'][1], '2022-03-08 high', gd['2022-03-08'][0], f"to 10-21: {100*(gd['2022-10-21'][1]/gd['2022-03-08'][0]-1):.1f}%  to 11-03: {100*(gd['2022-11-03'][1]/gd['2022-03-08'][0]-1):.1f}%")
seg={d:v for d,v in gd.items() if '2022-09-01'<=d<='2022-11-30'}; print('Sep-Nov 2022 min low', min(seg.items(), key=lambda x:x[1][1]))
# 3. C's +3m counts with real avg and gold WB monthly; BIS yoy values
ravg={r['month']:float(r['dxy_avg']) for r in csv.DictReader(open(A+'dollar_monthly.csv')) if r['dxy_avg']}
gm={r['month']:float(r['wb_pinksheet_avg']) for r in csv.DictReader(open(A+'gold_monthly.csv')) if r['wb_pinksheet_avg']}
CR=['1974-06','1982-08','1987-10','1992-09','1994-12','1997-07','1998-08','2001-02','2008-09','2010-05','2013-05','2015-08','2018-08','2020-03','2022-09','2023-03']
ms=sorted(ravg); up=[]; gdown=[]
for c in CR:
    i=ms.index(c); d3=100*(ravg[ms[i+3]]/ravg[c]-1); g3=100*(gm[ms[i+3]]/gm[c]-1) if ms[i+3] in gm and c in gm else float('nan')
    up.append(d3>0); gdown.append(g3<0); print(f"  {c} DXY 0..+3m {d3:+.1f}  gold 0..+3m {g3:+.1f}")
print('DXY higher +3m:', sum(up),'/16; gold lower +3m:', sum(gdown),'/16')
print('DXY avg 2020-03', ravg['2020-03'], '2020-04', ravg['2020-04'], '2009-02', ravg['2009-02'], '2009-03', ravg['2009-03'])
gli=pd.read_csv('raw/bis_gli.csv'); gli=gli[gli.OBS_VALUE.notna()]
s=pd.Series(gli.OBS_VALUE.values/1e6, index=gli.TIME_PERIOD.values); yoy=100*(s/s.shift(4)-1)
print('BIS yoy 2008Q3-2010Q1:', yoy['2008-Q3':'2010-Q1'].round(1).to_dict()); print('BIS yoy 2022Q2-2024Q1:', yoy['2022-Q2':'2024-Q1'].round(1).to_dict())
# 4. decel_test calendar replication (bd ∩ vix only)
def fredd(p):
    o={}
    for r in csv.DictReader(open(p)):
        k=[c for c in r if c!='observation_date'][0]
        if r[k] not in ('','.'): o[r['observation_date']]=float(r[k])
    return o
bd=fredd('../scoping/raw/DTWEXBGS.csv'); vix=fredd('../scoping/raw/VIXCLS.csv')
days=sorted(d for d in bd if d in vix); B=np.array([bd[d] for d in days])
idx_=[i for i,d in enumerate(days) if '2008-06-01'<=d<='2009-06-30']; a,b=idx_[0],idx_[-1]; pk=a+int(np.argmax(B[a:b+1]))
roc=np.array([B[k]/B[k-20]-1 for k in range(a,pk+1)]); rk=a+int(np.argmax(roc))
print('decel_test calendar (bd∩vix): ROC20 peak', days[rk], round(100*roc.max(),1), 'rise after', round(100*(B[pk]/B[rk]-1),1), '| 2008-10-13 in bd?', '2008-10-13' in bd, 'in vix?', '2008-10-13' in vix)
# 7/8. finder A: peak-before-end count and Spearman
cm=list(csv.DictReader(open(A+'crises_metrics.csv')))
print('dxy_peak_before_end values:', {r['id']:r['dxy_peak_before_end'] for r in cm})
from scipy.stats import spearmanr
x=[float(r['dxy_chg_eve_to_peak_stress_pct']) for r in cm if r['is_crisis']=='1']; y=[float(r['spx_maxdd_pct']) for r in cm if r['is_crisis']=='1']
print('Spearman(dxy eve->peak, spx maxDD):', spearmanr(x,y), 'n', len(x), '(note sign: maxDD negative numbers?)', y[:5])
# Granger DXY->VIX on real avg monthly 1990-2026 (replicate C)
vixm={}
for r in csv.DictReader(open('../scoping/raw/VIXCLS.csv')):
    if r['VIXCLS'] not in ('','.'): vixm.setdefault(r['observation_date'][:7],[]).append(float(r['VIXCLS']))
vixm={k:np.mean(v) for k,v in vixm.items()}
mm=[m for m in ms if m in vixm and '1990-01'<=m<='2026-09']; dd=np.diff(np.log([ravg[m] for m in mm])); dv=np.diff(np.log([vixm[m] for m in mm]))
def granger(x,y,p):
    n=len(y); Y=y[p:]; Xr=np.column_stack([np.ones(n-p)]+[y[p-k:n-k] for k in range(1,p+1)]); Xu=np.column_stack([Xr]+[x[p-k:n-k] for k in range(1,p+1)])
    br=np.linalg.lstsq(Xr,Y,rcond=None)[0]; bu=np.linalg.lstsq(Xu,Y,rcond=None)[0]
    sr=((Y-Xr@br)**2).sum(); su=((Y-Xu@bu)**2).sum(); return ((sr-su)/p)/(su/(n-p-Xu.shape[1]))
for p in (1,3,6): print(f'Granger p={p}: DXY->VIX F={granger(dd,dv,p):.2f}; VIX->DXY F={granger(dv,dd,p):.2f} (n={len(dd)})')
