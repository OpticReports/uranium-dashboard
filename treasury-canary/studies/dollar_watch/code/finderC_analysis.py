# Free-data checks: gold & DXY around crisis onsets; dollar-yield sign quadrant at onsets; dollar->VIX/TED lead-lag (Granger via numpy OLS).
import csv, math, sys, numpy as np, openpyxl
D='<scratch>/dxy/finderC/raw/data/'
OUT='<scratch>/dxy/finderC/'
def fred_monthly(s, agg='mean'):
    out={}
    with open(D+f'fred_{s}.csv') as f:
        r=csv.reader(f); next(r)
        for d,v in r:
            try: out.setdefault(d[:7],[]).append(float(v))
            except: pass
    return {k:(sum(v)/len(v) if agg=='mean' else v[-1]) for k,v in out.items()}
dxy={}
with open(D+'dxy_synthetic_monthly.csv') as f:
    r=csv.reader(f); next(r)
    for m,v in r: dxy[m]=float(v)
# gold & oil from World Bank CMO monthly
wb=openpyxl.load_workbook(D+'wb_cmo_monthly.xlsx', read_only=True); ws=wb['Monthly Prices']
rows=list(ws.iter_rows(values_only=True)); hdr=rows[4]
gi=[i for i,h in enumerate(hdr) if h and 'Gold' in str(h)][0]; oi=[i for i,h in enumerate(hdr) if h and 'Brent' in str(h)][0]
gold={}; brent={}
for r in rows[6:]:
    if r[0] and isinstance(r[0],str) and r[0][:4].isdigit():
        m=r[0][:4]+'-'+r[0][5:7]
        if r[gi] is not None: gold[m]=float(r[gi])
        if r[oi] is not None: brent[m]=float(r[oi])
print('gold', min(gold), max(gold), 'hdr', hdr[gi], hdr[oi])
gs10=fred_monthly('GS10'); vix=fred_monthly('VIXCLS'); ted=fred_monthly('TEDRATE'); nfci=fred_monthly('NFCI'); swpt=fred_monthly('SWPT','last')
CRISES={'1974-06':'Herstatt','1982-08':'LatAm debt','1987-10':'Black Monday','1992-09':'ERM','1994-12':'Tequila','1997-07':'Asia','1998-08':'Russia/LTCM','2001-02':'Turkey/Arg','2008-09':'Lehman','2010-05':'Euro sov','2013-05':'Taper','2015-08':'China/commod','2018-08':'TRY/ARS','2020-03':'COVID','2022-09':'LDI/EM FX','2023-03':'SVB/CS'}
months=sorted(dxy)
def sh(m,k):
    i=months.index(m)+k; return months[min(max(i,0),len(months)-1)]
def pct(d,a,b): return 100*(d[b]/d[a]-1) if a in d and b in d else float('nan')
print('\nAround crisis onset (monthly avgs): DXY & gold % changes; 10y yield change (pp); quadrant on the -3m..0 window')
print(f"{'onset':8s}{'name':13s}{'DXY-6..0':>9s}{'DXY0..+3':>9s}{'DXY0..+6':>9s}{'DXYmax+12':>10s}{'Gold-3..0':>10s}{'Gold0..+3':>10s}{'GoldMinDD+6':>12s}{'d10y-3..0':>10s}{'quadrant':>22s}")
quad={}
for c,n in sorted(CRISES.items()):
    i=months.index(c)
    g_dd=min(pct(gold,c,months[j]) for j in range(i,min(i+7,len(months))) if months[j] in gold)
    dx_max=max(pct(dxy,c,months[j]) for j in range(i,min(i+13,len(months))))
    dy=gs10.get(c,float('nan'))-gs10.get(sh(c,-3),float('nan'))
    ddx=pct(dxy,sh(c,-3),c)
    q=('USD up' if ddx>0 else 'USD down')+' / '+('yld up' if dy>0 else 'yld down')
    quad[q]=quad.get(q,0)+1
    print(f"{c:8s}{n:13s}{pct(dxy,sh(c,-6),c):9.1f}{pct(dxy,c,sh(c,3)):9.1f}{pct(dxy,c,sh(c,6)):9.1f}{dx_max:10.1f}{pct(gold,sh(c,-3),c):10.1f}{pct(gold,c,sh(c,3)):10.1f}{g_dd:12.1f}{dy:10.2f}{q:>22s}")
print('quadrant counts (3m window into onset):', quad)
# unconditional comparison
allm=[m for m in months[6:-6]]
up3=[pct(dxy,m,sh(m,3)) for m in allm]; print(f"Unconditional: mean DXY 0..+3m change {np.nanmean(up3):+.2f}%, share positive {np.mean(np.array(up3)>0):.0%}")
# Gold-DXY rolling 36m correlation of monthly log changes
gm=[m for m in months if m in gold]
lg=np.diff([math.log(gold[m]) for m in gm]); ld=np.diff([math.log(dxy[m]) for m in gm])
roll=[(gm[i+36], np.corrcoef(lg[i:i+36],ld[i:i+36])[0,1]) for i in range(0,len(lg)-36)]
print('\nGold-DXY 36m rolling corr of monthly log changes: full-sample corr', round(np.corrcoef(lg,ld)[0,1],2), '| decade means:',
      {dec: round(np.mean([c for m,c in roll if m[:3]==dec]),2) for dec in ['197','198','199','200','201','202']})
# Lead-lag: does DXY 1m change Granger-cause VIX change (and vice versa), 1990-2026 monthly; TED 1986-2021
def granger(x,y,p=3):
    # test whether lags of x help predict y beyond lags of y (F-test), using numpy OLS
    n=len(y); Y=y[p:]; Xr=np.column_stack([np.ones(n-p)]+[y[p-k:n-k] for k in range(1,p+1)])
    Xu=np.column_stack([Xr]+[x[p-k:n-k] for k in range(1,p+1)])
    br,_,_,_=np.linalg.lstsq(Xr,Y,rcond=None); bu,_,_,_=np.linalg.lstsq(Xu,Y,rcond=None)
    ssr_r=((Y-Xr@br)**2).sum(); ssr_u=((Y-Xu@bu)**2).sum()
    F=((ssr_r-ssr_u)/p)/(ssr_u/(n-p-Xu.shape[1]))
    return F, n-p
def series_pair(a,b,start,end):
    mm=[m for m in months if m in a and m in b and start<=m<=end]
    return mm, np.array([a[m] for m in mm]), np.array([b[m] for m in mm])
mm,xd,xv=series_pair(dxy,vix,'1990-01','2026-09'); dd=np.diff(np.log(xd)); dv=np.diff(np.log(xv))
for p in (1,3,6):
    F1,n=granger(dd,dv,p); F2,_=granger(dv,dd,p)
    print(f'Granger p={p}: DXY->VIX F={F1:.2f}; VIX->DXY F={F2:.2f}  (n={n}; F crit 5% ~ {2.6 if p==3 else (3.85 if p==1 else 2.1)})')
cc=[(k, np.corrcoef(dd[max(0,-k):len(dd)-max(0,k)], dv[max(0,k):len(dv)-max(0,-k)])[0,1]) for k in range(-6,7)]
print('Cross-corr corr(dDXY_t, dVIX_{t+k}) k=-6..6:', [(k,round(c,2)) for k,c in cc])
mm,xd,xt=series_pair(dxy,ted,'1986-01','2021-12'); dd=np.diff(np.log(xd)); dt=np.diff(xt)
for p in (1,3):
    F1,n=granger(dd,dt,p); F2,_=granger(dt,dd,p); print(f'Granger p={p}: DXY->TED F={F1:.2f}; TED->DXY F={F2:.2f} (n={n})')
cc=[(k, np.corrcoef(dd[max(0,-k):len(dd)-max(0,k)], dt[max(0,k):len(dt)-max(0,-k)])[0,1]) for k in range(-6,7)]
print('Cross-corr corr(dDXY_t, dTED_{t+k}):', [(k,round(c,2)) for k,c in cc])
# 12m DXY momentum percentile vs crisis onset within 12m: simple signals test
mom={m:pct(dxy,months[i-12],m) for i,m in enumerate(months) if i>=12}
cidx=sorted(months.index(c) for c in CRISES)
def nsr(th, side):
    A=B=C=Dn=0
    for i,m in enumerate(months):
        if m not in mom: continue
        sig = mom[m]>th if side=='up' else mom[m]<th
        cr = any(i< c <= i+12 for c in cidx)   # crisis onset within next 12m (strictly ahead)
        if sig and cr: A+=1
        elif sig and not cr: B+=1
        elif (not sig) and cr: C+=1
        else: Dn+=1
    return A,B,C,Dn
print('\nSignals test: 12m DXY change threshold -> crisis onset in NEXT 12m (strict lead). A=hits B=false C=missed D=quiet; NSR=(B/(B+D))/(A/(A+C)); P(crisis|signal)=A/(A+B)')
base=sum(any(i<c<=i+12 for c in cidx) for i in range(len(months)))/len(months)
print(f'base rate P(onset within next 12m)={base:.0%}')
for side,ths in (('up',[5,8,10,12,15]),('down',[-5,-8,-10,-12])):
    for th in ths:
        A,B,C,Dn=nsr(th,side); 
        if A+C and B+Dn and A: print(f'  {side:4s} th={th:+3d}%: A={A:3d} B={B:3d} C={C:3d} D={Dn:3d}  NSR={(B/(B+D if False else B+Dn))/(A/(A+C)):.2f}  P(crisis|sig)={A/(A+B):.0%}  share of crisis-months called={A/(A+C):.0%}')
# |abs| momentum
for th in (8,10,12):
    A=B=C=Dn=0
    for i,m in enumerate(months):
        if m not in mom: continue
        sig=abs(mom[m])>th; cr=any(i<c<=i+12 for c in cidx)
        A+=sig and cr; B+=sig and not cr; C+=(not sig) and cr; Dn+=(not sig) and not cr
    print(f'  |mom|>{th}%: A={A} B={B} C={C} D={Dn} NSR={(B/(B+Dn))/(A/(A+C)):.2f} P(crisis|sig)={A/(A+B):.0%}')
# chart
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
fig,ax=plt.subplots(4,1,figsize=(13,15),gridspec_kw={'height_ratios':[2,1.2,1.2,1.2]})
x=np.arange(len(months)); lab=[m for m in months]
ax[0].plot(x,[dxy[m] for m in months],color='#1f4e79',lw=1.2,label='DXY (synthetic from FRED bilaterals)')
ax[0].axhspan(85,105,color='#999',alpha=0.15,label='Johnson band 85-105')
for c in CRISES: ax[0].axvline(months.index(c),color='#c0392b',alpha=0.5,lw=0.8)
ax[0].set_title('DXY 1973-2026 with Johnson band and 16 frozen crisis onsets (red). 22 band excursions; 9 (41%) have an onset in-window vs 31% base rate')
ax[0].legend(loc='upper right'); ax[0].set_ylabel('index')
ax[1].plot(x[12:],[mom[m] for m in months[12:]],color='#1f4e79',lw=1); ax[1].axhline(0,color='k',lw=0.5)
for c in CRISES: ax[1].axvline(months.index(c),color='#c0392b',alpha=0.5,lw=0.8)
ax[1].set_ylabel('12m DXY change %'); ax[1].set_title('Dollar momentum (12m %). Signal >+10%: P(onset next 12m | signal) see notes; onsets cluster AFTER the rise only in 1982/2001/2022')
gx=[months.index(m) for m in gm]; ax[2].plot(gx,[gold[m] for m in gm],color='#b8860b',lw=1); ax[2].set_yscale('log'); ax[2].set_ylabel('Gold $/oz (log)')
for c in CRISES: ax[2].axvline(months.index(c),color='#c0392b',alpha=0.5,lw=0.8)
ax[2].set_title('Gold: falls into/at onset in 2008, 2013, 2015, 2020(briefly), 2022 but RISES through 1974, 1982(?), 2010, 2023 -> not "every crisis"')
ym=[m for m in months if m in gs10]; ax[3].plot([months.index(m) for m in ym],[gs10[m] for m in ym],color='#2e7d32',lw=1); ax[3].set_ylabel('US 10y %')
for c in CRISES: ax[3].axvline(months.index(c),color='#c0392b',alpha=0.5,lw=0.8)
ax[3].set_title('US 10y yield: dollar-up + yield-down into onset = safe-haven regime; dollar-up + yield-up = Fed/policy regime')
ticks=[i for i,m in enumerate(months) if m.endswith('-01') and int(m[:4])%4==1]; 
for a in ax: a.set_xticks(ticks); a.set_xticklabels([months[i][:4] for i in ticks]); a.set_xlim(0,len(months))
plt.tight_layout(); plt.savefig(OUT+'dxy_band_crises.png',dpi=110); print('chart saved')
