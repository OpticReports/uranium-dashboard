# Independent re-implementation of finder A's band/speed tests from dollar_monthly.csv + crises.csv
import csv, sys
DM, CR = sys.argv[1], sys.argv[2]
dm=[r for r in csv.DictReader(open(DM)) if r['dxy_close']]
months=[r['month'] for r in dm]; close={r['month']:float(r['dxy_close']) for r in dm}
idx={m:i for i,m in enumerate(months)}
allc=list(csv.DictReader(open(CR)))
def run(crises, label):
    starts={c['start'] for c in crises}
    incr=set()
    for c in crises:
        e=c['end'] or months[-1]
        incr.update(m for m in months if c['start']<=m<=e)
    def start_in(i0,i1):  # any start with index in [i0,i1]
        return any(months[k] in starts for k in range(max(0,i0),min(len(months)-1,i1)+1))
    n=len(months)
    br12=sum(start_in(i+1,i+12) for i in range(n-12))/(n-12)
    br24=sum(start_in(i+1,i+24) for i in range(n-24))/(n-24)
    brin=len(incr)/n
    print(f"\n== {label}: {len(crises)} crises | base P(start in (m,m+12]) = {br12:.3f} (n={n-12}); 24m = {br24:.3f} (n={n-24}); in-window share = {brin:.3f}")
    # excursions 85-105 close, raw and merged gap<=3
    runs=[]; cur=None
    for m in months:
        side='above' if close[m]>105 else ('below' if close[m]<85 else None)
        if side and cur and cur[0]==side: cur[2]=m
        else:
            if cur: runs.append(cur)
            cur=[side,m,m] if side else None
    if cur: runs.append(cur)
    def stats(rs, tag):
        h12=sum(start_in(idx[s],idx[s]+11) for _,s,e in rs); h24=sum(start_in(idx[s],idx[s]+23) for _,s,e in rs)
        inside=sum(s in incr for _,s,e in rs)
        print(f"  {tag}: n={len(rs)} hit12={h12} ({100*h12/len(rs):.0f}%) hit24={h24} ({100*h24/len(rs):.0f}%) began-inside-crisis={inside}")
        return rs
    stats(runs,'85-105 raw')
    for gap in (3,6):
        mg=[]
        for side,s,e in runs:
            if mg and mg[-1][0]==side and idx[s]-idx[mg[-1][2]]-1<=gap: mg[-1][2]=e
            else: mg.append([side,s,e])
        stats(mg,f'85-105 merged gap<={gap}')
        if gap==3:
            for side,s,e in mg: print(f"      {side:5} {s}..{e} ({idx[e]-idx[s]+1}m) inside={s in incr} hit12={start_in(idx[s],idx[s]+11)} hit24={start_in(idx[s],idx[s]+23)}")
    # speed
    for thr in (8,10,15):
        trig=[i>=6 and 100*(close[months[i]]/close[months[i-6]]-1)>=thr for i in range(len(months))]
        rs=[]; cur=None
        for i,t in enumerate(trig):
            if t and cur: cur[2]=months[i]
            elif t: cur=['run',months[i],months[i]]
            elif cur: rs.append(cur); cur=None
        if cur: rs.append(cur)
        h12=sum(start_in(idx[s],idx[s]+11) for _,s,e in rs); h24=sum(start_in(idx[s],idx[s]+23) for _,s,e in rs); inside=sum(s in incr for _,s,e in rs)
        print(f"  6m rise>={thr}%: n={len(rs)} hit12={h12} hit24={h24} began-inside={inside}")
        if thr==10: print('     starts:', [(s, s in incr) for _,s,e in rs])
# full list
full=[c for c in allc if c['is_crisis']=='1']
run(full,'finder A full list')
# strict list: systemic/global episodes that appear in Laeven-Valencia (systemic banking) or RR as multi-country waves, or are unambiguous global dollar-funding events
STRICT_IDS=['C01','C03','C04','C07','C08','C09','C10','C11','C12','C13','C14','C15','C17','C20','C22']
run([c for c in allc if c['id'] in STRICT_IDS],'strict 15 (drop 1976 sterling, ContIll, taper, 2018, repo, China prop, SVB, yen, LibDay, 2026)')
STRICT12=['C01','C03','C04','C07','C08','C10','C11','C12','C13','C14','C15','C20']
run([c for c in allc if c['id'] in STRICT12],'strict 12 (also drop ERM, 2014-16, 2022)')
# check 1985-02 monthly close vs daily
print('\n1985-02 monthly close', close['1985-02'], '1985-03', close['1985-03'])
