# Independent re-implementation of dollar_scoping.py summary tables from out/dollar_monthly.csv, plus Shiller checks
import csv, json, numpy as np, xlrd, os
O='../scoping/out/'; R='../scoping/raw/'
rows=list(csv.DictReader(open(O+'dollar_monthly.csv')))
m=[r['month'] for r in rows]; D=np.array([float(r['dxy_spliced']) for r in rows]); Y=np.array([float(r['gs10']) for r in rows]); SPR=np.array([float(r['baa_minus_gs10']) for r in rows]); P=np.array([float(r['spx_shiller']) for r in rows]); Rc=np.array([int(r['usrec']) for r in rows])
T=len(m); H=12; print('months', m[0], m[-1], T)
# check dxy_spliced == finder A dxy_avg
fa={r['month']:float(r['dxy_avg']) for r in csv.DictReader(open('../finderA/data/dollar_monthly.csv')) if r['dxy_avg']}
print('dxy col vs finderA avg: max abs diff', max(abs(D[i]-fa[m[i]]) for i in range(T)))
recs=[]
for t in range(6,T-1):
    if t+H>=T: break   # need 12 full forward months
    d6=D[t]/D[t-6]-1; y6=Y[t]-Y[t-6]
    fut=P[t:t+H+1]; pk=np.maximum.accumulate(fut); dd=float(np.max(1-fut/pk))
    spr=float(SPR[t:t+H+1].max()-SPR[t])
    rec=any(Rc[k]==1 and Rc[k-1]==0 for k in range(t+1,t+H+1))
    recs.append(dict(t=t,d6=d6,y6=y6,dxy=D[t],dd=dd,spr=spr,rec=rec))
print('n full', len(recs))
def S(sel,lab):
    n=len(sel); 
    if not n: print(lab,'n=0'); return
    print(f"{lab:50s} n={n:4d} P(dd>=20%)={np.mean([r['dd']>=.2 for r in sel]):.2f} P(spr+100)={np.mean([r['spr']>=1 for r in sel]):.2f} P(rec)={np.mean([r['rec'] for r in sel]):.2f} medDD={np.median([r['dd'] for r in sel]):.3f}")
S(recs,'all')
for thr in (.05,.08,.10,.15): S([r for r in recs if r['d6']>=thr], f'6m rise >= {thr:.0%}')
for thr in (.05,.08,.10): S([r for r in recs if r['d6']<=-thr], f'6m fall <= -{thr:.0%}')
S([r for r in recs if r['d6']>=.05 and r['y6']<=-.25],'up5 & 10y down 25'); S([r for r in recs if r['d6']>=.05 and r['y6']>=.25],'up5 & 10y up 25')
S([r for r in recs if r['dxy']>105],'DXY>105'); S([r for r in recs if r['dxy']<85],'DXY<85'); S([r for r in recs if 85<=r['dxy']<=105],'in band')
q=np.percentile([r['d6'] for r in recs],[20,40,60,80]); print('quintile cuts', q.round(4))
S([r for r in recs if r['d6']<q[0]],'q1'); S([r for r in recs if r['d6']>=q[3]],'q5')
# recession starts in sample
starts=[m[k] for k in range(1,T) if Rc[k]==1 and Rc[k-1]==0]; print('recession starts', starts)
# months with dd>=20 in 6m>=15 group
sel=[r for r in recs if r['d6']>=.15]; print('6m>=15% months:', [(m[r['t']], round(r['dd'],2), round(r['spr'],2), r['rec']) for r in sel])
# Shiller decoding check
wb=xlrd.open_workbook(R+'shiller_ie_data.xls'); sh=wb.sheet_by_name('Data')
spx={}
for i in range(8, sh.nrows):
    d=sh.cell_value(i,0); p=sh.cell_value(i,1)
    if isinstance(d,float) and d>1870 and isinstance(p,float):
        y=int(d); mth=int(round((d-y)*100)); 
        if mth==0: mth=10
        spx[f"{y}-{mth:02d}"]=(p, d)
print('Shiller rows', len(spx), 'last', max(spx), spx[max(spx)])
for k in ['1987-09','1987-10','1987-11','1987-12','2009-02','2009-03','2009-04','2000-08','2000-10','2020-03','2023-09','2023-10','2023-11']:
    print('  ', k, spx.get(k))
# Raw cells around 1987.1 to show the decoding
for i in range(8, sh.nrows):
    d=sh.cell_value(i,0)
    if isinstance(d,float) and 1987.0<=d<1988.0: print('   raw', repr(d), sh.cell_value(i,1))
# FRED SP500 monthly mean at splice
sp={}
for r in csv.DictReader(open(R+'SP500.csv')):
    if r['SP500'] not in ('','.'): sp.setdefault(r['observation_date'][:7],[]).append(float(r['SP500']))
spm={k:sum(v)/len(v) for k,v in sp.items()}
print('FRED SP500 monthly mean:', {k:round(spm[k],1) for k in ['2023-08','2023-09','2023-10','2023-11'] if k in spm})
print('Shiller vs FRED where both:', [(k, round(spx[k][0],1), round(spm[k],1)) for k in sorted(spm) if k in spx][-4:])
print('out csv spx around splice:', [(r['month'], r['spx_shiller']) for r in rows if '2023-07'<=r['month']<='2023-12'])
# S&P 1987: Shiller monthly avg Oct-1987 should be ~280 (Sep ~318, Nov ~245)
# real-time turn look-ahead check: for each speed episode, recompute turn using only past data (it's defined as D[k]<=0.97*max(D[k-6..k]) which is backward-looking) 
js=json.load(open(O+'dollar_summary.json'))
for e in js['speed_episodes']:
    t=m.index(e['trigger']); turn=None
    for k in range(t+1, min(T-12,t+24)):
        if D[k]<=0.97*max(D[max(0,k-6):k+1]): turn=m[k]; break
    print('  ep', e['trigger'], 'turn claimed', e['realtime_turn'], 'recomputed', turn, 'peak', e['dxy_peak'], 'ex-post peak within t..t+12 ->', m[t+int(np.argmax(D[t:t+13]))])
print('current', m[-1], D[-1], round(D[-1]/D[-7]-1,4), round(D[-1]/D[-13]-1,4))
