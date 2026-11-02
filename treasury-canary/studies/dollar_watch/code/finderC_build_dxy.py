# Build a synthetic monthly DXY (1973-01 .. 2026-09) from FRED bilateral monthly averages.
# Post-1999: ICE formula 50.14348112 * EURUSD^-0.576 * USDJPY^0.136 * GBPUSD^-0.119 * USDCAD^0.091 * USDSEK^0.042 * USDCHF^0.036
# Pre-1999: euro leg replaced by legacy currencies with the pre-1999 ICE weights (DEM .208, FRF .131, ITL .090, NLG .083, BEF .064) -> sum .576
# Series is chained at 1999-01 so the pre-1999 segment is a geometric index spliced to the post-1999 ICE level.
import csv, math, sys, os
D='<scratch>/dxy/finderC/raw/data/'
def load(s):
    out={}
    with open(D+f'fred_{s}.csv') as f:
        r=csv.reader(f); next(r)
        for d,v in r:
            try: out[d[:7]]=float(v)
            except: pass
    return out
S={k:load(k) for k in ['EXUSEU','EXJPUS','EXUSUK','EXCAUS','EXSDUS','EXSZUS','EXGEUS','EXFRUS','EXITUS','EXNEUS','EXBEUS']}
months=sorted(set(S['EXJPUS'])&set(S['EXUSUK'])&set(S['EXCAUS'])&set(S['EXSDUS'])&set(S['EXSZUS']))
months=[m for m in months if m>='1973-01']
post={}
for m in months:
    if m in S['EXUSEU']:
        post[m]=50.14348112*S['EXUSEU'][m]**-0.576*S['EXJPUS'][m]**0.136*S['EXUSUK'][m]**-0.119*S['EXCAUS'][m]**0.091*S['EXSDUS'][m]**0.042*S['EXSZUS'][m]**0.036
# pre-1999 geometric index (unnormalised)
pre={}
for m in months:
    if m<'1999-01' and all(m in S[k] for k in ['EXGEUS','EXFRUS','EXITUS','EXNEUS','EXBEUS']):
        pre[m]=(S['EXGEUS'][m]**0.208*S['EXFRUS'][m]**0.131*S['EXITUS'][m]**0.090*S['EXNEUS'][m]**0.083*S['EXBEUS'][m]**0.064
                *S['EXJPUS'][m]**0.136*S['EXUSUK'][m]**-0.119*S['EXCAUS'][m]**0.091*S['EXSDUS'][m]**0.042*S['EXSZUS'][m]**0.036)
# splice: scale pre so that Dec-1998 pre matches Jan-1999 post via the legacy->euro conversion. Use overlap month 1998-12 -> use ratio post['1999-01']/pre['1998-12'] adjusted by the Jan-99 change... simpler: compute pre for 1999-01..2001-12 as well using legacy rates (fixed to EUR then), and scale by mean ratio over 1999-01..2001-12.
pre2={}
for m in months:
    if '1999-01'<=m<='2001-12' and all(m in S[k] for k in ['EXGEUS','EXFRUS','EXITUS','EXNEUS','EXBEUS']):
        pre2[m]=(S['EXGEUS'][m]**0.208*S['EXFRUS'][m]**0.131*S['EXITUS'][m]**0.090*S['EXNEUS'][m]**0.083*S['EXBEUS'][m]**0.064
                *S['EXJPUS'][m]**0.136*S['EXUSUK'][m]**-0.119*S['EXCAUS'][m]**0.091*S['EXSDUS'][m]**0.042*S['EXSZUS'][m]**0.036)
ratios=[post[m]/pre2[m] for m in pre2]
k=sum(ratios)/len(ratios)
print('splice factor', k, 'ratio sd', (sum((r-k)**2 for r in ratios)/len(ratios))**0.5, file=sys.stderr)
dxy={}
for m in months:
    if m in post: dxy[m]=post[m]
    elif m in pre: dxy[m]=pre[m]*k
with open(D+'dxy_synthetic_monthly.csv','w') as f:
    w=csv.writer(f); w.writerow(['month','dxy_synth'])
    for m in sorted(dxy): w.writerow([m, round(dxy[m],3)])
# checkpoints vs known DXY (monthly avg approx): 1973-03 ~100 (base), 1985-02 ~160 (peak 164.7 daily), 1992-09 ~80, 2001-07 ~118, 2008-03 ~72, 2011-04 ~74, 2017-01 ~101, 2022-09 ~111, 2025-01 ~108
for m in ['1973-03','1978-10','1980-07','1985-02','1988-01','1992-09','1995-04','2001-07','2002-01','2008-03','2008-11','2011-04','2015-03','2017-01','2020-03','2022-09','2024-12','2025-01','2025-06','2026-09']:
    print(m, round(dxy.get(m,float('nan')),1))
