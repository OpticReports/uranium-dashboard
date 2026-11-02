# Test the "band" claim: count DXY excursions outside [lo,hi] 1973-2026 and how many are followed by a crisis onset within K months.
import csv, sys
D='<scratch>/dxy/finderC/raw/data/'
dxy={}
with open(D+'dxy_synthetic_monthly.csv') as f:
    r=csv.reader(f); next(r)
    for m,v in r: dxy[m]=float(v)
months=sorted(dxy)
# FROZEN crisis-onset list (global / EM dollar-funding stress onsets), month = onset
CRISES={'1974-06':'Herstatt/Franklin Natl (FX-bank failures)','1982-08':'Mexico default / LatAm debt','1987-10':'Black Monday',
'1992-09':'ERM crisis','1994-12':'Tequila','1997-07':'Asian crisis','1998-08':'Russia/LTCM','2001-02':'Turkey (then Argentina 2001-12)',
'2008-09':'Lehman / GFC','2010-05':'Euro sovereign (Greece)','2013-05':'Taper tantrum','2015-08':'China deval / commodity bust',
'2018-08':'Turkey/Argentina','2020-03':'COVID dash-for-cash','2022-09':'UK LDI / dollar peak EM stress','2023-03':'SVB/Credit Suisse'}
def midx(m): y,mm=m.split('-'); return int(y)*12+int(mm)-1
cidx=sorted(midx(c) for c in CRISES)
def excursions(lo,hi,minlen=1):
    ex=[]; cur=None
    for m in months:
        v=dxy[m]; out = 'above' if v>hi else ('below' if v<lo else None)
        if out and cur and cur['side']==out: cur['end']=m; cur['n']+=1; cur['ext']=max(cur['ext'],abs(v-(hi if out=='above' else lo)))
        elif out:
            if cur: ex.append(cur)
            cur={'side':out,'start':m,'end':m,'n':1,'ext':abs(v-(hi if out=='above' else lo))}
        else:
            if cur: ex.append(cur); cur=None
    if cur: ex.append(cur)
    return [e for e in ex if e['n']>=minlen]
def crisis_within(start,end,K):
    s=midx(start); e=midx(end)
    hits=[c for c in cidx if s<=c<=e+K]
    return hits
def run(lo,hi,K=12,minlen=1):
    ex=excursions(lo,hi,minlen)
    print(f'\nBand [{lo},{hi}] minlen={minlen}m K={K}m: {len(ex)} excursions')
    n_hit=0
    for e in ex:
        h=crisis_within(e['start'],e['end'],K)
        n_hit+= bool(h)
        print(f"  {e['side']:5s} {e['start']}..{e['end']} ({e['n']:3d}m, max ext {e['ext']:5.1f}) -> crisis in-window: {', '.join(sorted(CRISES)[cidx.index(c)] for c in h) or '-'}")
    print(f'  excursions followed/accompanied by crisis onset: {n_hit}/{len(ex)} = {n_hit/len(ex):.0%}' if ex else '  none')
    # base rate: fraction of all months with a crisis onset within next K months (or during)
    tot=0; base=0
    for m in months:
        i=midx(m); tot+=1; base+= any(i<=c<=i+K for c in cidx)
    print(f'  BASE RATE: P(crisis onset within {K}m of a random month) = {base/tot:.0%}; months in-band share = {sum(lo<=dxy[m]<=hi for m in months)/len(months):.0%}')
    # crisis-conditional: were crises preceded by out-of-band?
    pre=0
    for c in cidx:
        win=[m for m in months if c-K<=midx(m)<=c]
        pre+= any(dxy[m]>hi or dxy[m]<lo for m in win)
    print(f'  share of crises with DXY outside band at some point in the prior {K}m: {pre}/{len(cidx)}')
for lo,hi in [(85,105),(80,110),(85,100),(90,105)]:
    run(lo,hi,12,1)
run(85,105,12,3); run(85,105,24,1)
# momentum: 12m change percentile vs crises
print('\n12m DXY change at each crisis onset (and 6m):')
for c in sorted(CRISES):
    i=months.index(c) if c in months else None
    if i and i>=12: print(f"  {c} {CRISES[c][:28]:28s} lvl {dxy[c]:6.1f}  6m {100*(dxy[c]/dxy[months[i-6]]-1):+5.1f}%  12m {100*(dxy[c]/dxy[months[i-12]]-1):+5.1f}%  +6m after {100*(dxy[months[min(i+6,len(months)-1)]]/dxy[c]-1):+5.1f}%")
