# Finder C's synthetic vs real DXY; recompute C's band test and momentum signal on REAL monthly series (avg and close) with C's frozen 16-onset list
import csv, sys, numpy as np
A='../finderA/data/dollar_monthly.csv'; S='../finderC/raw/data/dxy_synthetic_monthly.csv'; G10='../scoping/raw/GS10.csv'
real_avg={r['month']:float(r['dxy_avg']) for r in csv.DictReader(open(A)) if r['dxy_avg']}
real_cl={r['month']:float(r['dxy_close']) for r in csv.DictReader(open(A)) if r['dxy_close']}
syn={m:float(v) for m,v in list(csv.reader(open(S)))[1:]}
print('synthetic vs real monthly avg at checkpoints:')
for m in ['1973-03','1985-02','1992-09','2001-07','2008-03','2011-04','2020-03','2022-09','2025-01','2026-09']:
    print(f"  {m} syn {syn.get(m,float('nan')):7.1f} real_avg {real_avg.get(m,float('nan')):7.1f} diff {syn.get(m,0)-real_avg.get(m,0):+6.1f} ({100*(syn.get(m,0)/real_avg.get(m,1)-1):+.1f}%)")
com=[m for m in syn if m in real_avg]
d=np.array([syn[m]-real_avg[m] for m in com]); pd_=np.array([100*(syn[m]/real_avg[m]-1) for m in com])
print(f"  overlap n={len(com)} mean diff {d.mean():+.2f} sd {d.std():.2f} max|diff| {abs(d).max():.1f} at {com[int(abs(d).argmax())]}; pct diff mean {pd_.mean():+.2f} sd {pd_.std():.2f}")
pre=[m for m in com if m<'1999-01']; post=[m for m in com if m>='1999-01']
print('  pre-1999 mean pct diff', round(np.mean([100*(syn[m]/real_avg[m]-1) for m in pre]),2), 'post', round(np.mean([100*(syn[m]/real_avg[m]-1) for m in post]),2))
CR=['1974-06','1982-08','1987-10','1992-09','1994-12','1997-07','1998-08','2001-02','2008-09','2010-05','2013-05','2015-08','2018-08','2020-03','2022-09','2023-03']
def midx(m): y,mm=m.split('-'); return int(y)*12+int(mm)-1
cidx=sorted(midx(c) for c in CR)
def band(dxy, months, lo,hi,K=12,minlen=1,label=''):
    ex=[]; cur=None
    for m in months:
        v=dxy[m]; out='above' if v>hi else ('below' if v<lo else None)
        if out and cur and cur['side']==out: cur['end']=m; cur['n']+=1
        elif out:
            if cur: ex.append(cur)
            cur={'side':out,'start':m,'end':m,'n':1}
        else:
            if cur: ex.append(cur); cur=None
    if cur: ex.append(cur)
    ex=[e for e in ex if e['n']>=minlen]
    hit=sum(any(midx(e['start'])<=c<=midx(e['end'])+K for c in cidx) for e in ex)
    base=np.mean([any(midx(m)<=c<=midx(m)+K for c in cidx) for m in months])
    pre=sum(any(dxy[m]>hi or dxy[m]<lo for m in months if c-K<=midx(m)<=c) for c in cidx)
    print(f"  {label} [{lo},{hi}] minlen={minlen} K={K}: {len(ex)} excursions, {hit} hit ({100*hit/len(ex):.0f}%), base {100*base:.0f}%, in-band share {100*np.mean([lo<=dxy[m]<=hi for m in months]):.0f}%, onsets with out-of-band in prior {K}m {pre}/16")
    return ex
def momentum(dxy, months, label):
    mom={m:100*(dxy[m]/dxy[months[i-12]]-1) for i,m in enumerate(months) if i>=12}
    base=np.mean([any(i<c<=i+12 for c in cidx) for i in [midx(m) for m in months]])
    print(f"  {label}: base rate (strict lead) {100*base:.0f}%")
    for th in (5,10,15):
        A=B=C=Dn=0
        for m in months:
            if m not in mom: continue
            i=midx(m); sig=mom[m]>th; cr=any(i<c<=i+12 for c in cidx)
            A+=sig and cr; B+=sig and not cr; C+=(not sig) and cr; Dn+=(not sig) and not cr
        print(f"    >+{th}%: A={A} B={B} C={C} D={Dn} NSR={(B/(B+Dn))/(A/(A+C)):.2f} P(onset|sig)={100*A/(A+B):.0f}% called={100*A/(A+C):.0f}%")
for lab,ser in [('SYNTHETIC (C, 1973-01..2026-09)',syn),('REAL avg 1973-01..2026-09',{m:v for m,v in real_avg.items() if '1973-01'<=m<='2026-09'}),('REAL close 1973-01..2026-09',{m:v for m,v in real_cl.items() if '1973-01'<=m<='2026-09'}),('REAL avg 1971-01..2026-11',real_avg)]:
    months=sorted(ser); print('\n',lab, len(months))
    band(ser,months,85,105,12,1,'band'); band(ser,months,85,105,12,3,'band'); band(ser,months,85,105,24,1,'band')
    momentum(ser,months,'momentum')
# quadrant counts on real avg with GS10 (monthly), -3m..0 window
gs10={}
for r in csv.DictReader(open(G10)):
    if r['GS10'] not in ('','.'): gs10[r['observation_date'][:7]]=float(r['GS10'])
def quad(ser,label):
    months=sorted(ser); q={}
    rows=[]
    for c in CR:
        i=months.index(c); m3=months[i-3]
        ddx=100*(ser[c]/ser[m3]-1); dy=gs10[c]-gs10[m3]
        k=('USD up' if ddx>0 else 'USD down')+'/'+('yld up' if dy>0 else 'yld down'); q[k]=q.get(k,0)+1
        rows.append((c, round(ddx,1), round(dy,2), k))
    print(label, q); 
    for r in rows: print('   ',r)
quad(syn,'quadrant SYN'); quad(real_avg,'quadrant REAL avg'); quad(real_cl,'quadrant REAL close')
# DXY higher 3 months after onset (8/16 claimed); 
for lab,ser in [('syn',syn),('real avg',real_avg)]:
    months=sorted(ser); n=sum(ser[months[months.index(c)+3]]>ser[c] for c in CR); print(lab,'DXY higher 3m after onset:', n,'/16')
