import csv, sys, json, datetime as dt
A='../finderA/data/'
dm={r['month']:float(r['dxy_close']) for r in csv.DictReader(open(A+'dollar_monthly.csv')) if r['dxy_close']}
months=sorted(dm)
cr=list(csv.DictReader(open(A+'crises.csv')))
def prev(m):
    return months[months.index(m)-1]
fell=[]; rose=[]
print('id start peak eve_close peak_close pct')
for c in cr:
    if c['is_crisis']!='1': continue
    eve=dm[prev(c['start'])]; pk=dm[c['peak_stress']]
    p=100*(pk/eve-1)
    (fell if p<0 else rose).append(c['id'])
    print(c['id'], c['start'], c['peak_stress'], round(eve,2), round(pk,2), f"{p:+.1f}")
print('fell', len(fell), fell); print('rose', len(rose))
# gold daily checks
gd=[(r['date'],float(r['high']),float(r['low']),float(r['close'])) for r in csv.DictReader(open(A+'gold_daily.csv'))]
def maxdd(lo,hi,use='close'):
    seg=[x for x in gd if lo<=x[0]<=hi]
    pk=-1; pkd=None; best=(0,None,None)
    for d,h,l,c in seg:
        v=c
        if v>pk: pk=v; pkd=d
        dd=1-v/pk
        if dd>best[0]: best=(dd,pkd,d)
    return best
for lab,lo,hi in [('GFC',"2008-01-01","2009-06-30"),('2020',"2020-01-01","2020-05-31"),('2022',"2022-01-01","2022-12-31"),('dotcom',"2000-01-01","2003-03-31"),('2026',"2026-01-01","2026-11-02"),('2013',"2013-01-01","2013-12-31"),('2011',"2011-08-01","2012-01-31")]:
    dd,p,t=maxdd(lo,hi); print(lab,'close-to-close maxDD', f"{-100*dd:.1f}%", p,'->',t)
# intraday high->low variants
seg=[x for x in gd if '2026-01-01'<=x[0]<='2026-11-02']
hi=max(seg,key=lambda x:x[1]); lo=min(seg,key=lambda x:x[2]); print('2026 intraday high',hi[0],hi[1],'low',lo[0],lo[2], f"{100*(lo[2]/hi[1]-1):.1f}%")
hc=max(seg,key=lambda x:x[3]); lc=min(seg,key=lambda x:x[3]); print('2026 close high',hc[0],hc[3],'close low',lc[0],lc[3], f"{100*(lc[3]/hc[3]-1):.1f}%")
for lab,lo_,hi_ in [('GFC',"2008-01-01","2009-06-30"),('2020',"2020-02-01","2020-04-30"),('2022',"2022-01-01","2022-12-31")]:
    seg=[x for x in gd if lo_<=x[0]<=hi_]; h=max(seg,key=lambda x:x[1]); l=min((x for x in seg if x[0]>h[0]),key=lambda x:x[2]); print(lab,'intraday hi',h[0],h[1],'-> lo',l[0],l[2],f"{100*(l[2]/h[1]-1):.1f}%")
# monthly dotcom
gm={r['month']:r for r in csv.DictReader(open(A+'gold_monthly.csv'))}
print('gold monthly 1999-10', gm['1999-10']['gold_best'], '2001-04', gm['2001-04']['gold_best'], f"{100*(float(gm['2001-04']['gold_best'])/float(gm['1999-10']['gold_best'])-1):.1f}%")
# min of monthly best 2000-01..2003-03 and max 1999-10..
seg={m:float(gm[m]['gold_best']) for m in gm if '1999-01'<=m<='2003-03' and gm[m]['gold_best']}
print('monthly max 1999-2003', max(seg.items(), key=lambda x:x[1]), 'min', min(seg.items(), key=lambda x:x[1]))
# 2022 chain from daily DXY
dd={r['date']:float(r['close']) for r in csv.DictReader(open(A+'dxy_daily.csv'))}
f=dd['2022-02-28']; print('freeze',f, '2022-08-26',dd.get('2022-08-26'), f"{100*(dd['2022-08-26']/f-1):+.1f}", '2022-08-29', dd.get('2022-08-29'), f"{100*(dd['2022-08-29']/f-1):+.1f}", '2022-08-31', dd.get('2022-08-31'), f"{100*(dd['2022-08-31']/f-1):+.1f}", '09-27', dd['2022-09-27'], f"{100*(dd['2022-09-27']/f-1):+.1f}", '10-12', dd['2022-10-12'], f"{100*(dd['2022-10-12']/f-1):+.1f}")
print('2022-08-28 is a', dt.date(2022,8,28).strftime('%A'))
print('2021-06-01', dd.get('2021-06-01'), f"{100*(f/dd['2021-06-01']-1):+.1f}% to freeze")
print('DXY 2022 Oct-Dec fall: 2022-09-27', dd['2022-09-27'], '2022-12-30', dd['2022-12-30'], f"{100*(dd['2022-12-30']/dd['2022-09-27']-1):+.1f}%")
print('2026 DXY 96.2 -> 102.6: 2026-01-29', dd['2026-01-29'], '2026-10-12', dd['2026-10-12'], f"{100*(dd['2026-10-12']/dd['2026-01-29']-1):+.1f}%")
# 6m/12m DXY change to 2026-11-02
import bisect
ks=sorted(dd)
def at(d):
    i=bisect.bisect_right(ks,d)-1; return ks[i], dd[ks[i]]
print('6m ago', at('2026-05-02'), '12m ago', at('2025-11-02'), 'now', dd['2026-11-02'], f"6m {100*(dd['2026-11-02']/at('2026-05-02')[1]-1):+.1f} 12m {100*(dd['2026-11-02']/at('2025-11-02')[1]-1):+.1f}")
