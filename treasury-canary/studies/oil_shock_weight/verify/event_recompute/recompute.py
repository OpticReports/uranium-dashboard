"""Independent recompute of BLOCK event from spec + frozen inputs (written before reading run.py)."""
import json, numpy as np, pandas as pd
D='/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil/data'
p=pd.read_csv(f'{D}/panel.csv',parse_dates=['date']).set_index('date')
p.index=p.index.to_period('M')
ev=json.load(open(f'{D}/events.json'))
P=lambda s: pd.Period(s,'M')
onsets=[P(s) for s in ev['recession_onsets']]
B1=[P(s) for s,_ in ev['drawdown_starts_B1_running_peak']]
B2=[P(s) for s,_ in ev['drawdown_starts_B2_local_peak']]
LAST_USREC=P('2025-08')
out={}

# ---------- 1. rebuild derived columns from raw ----------
wti=p['wti']; cpi=p['cpi']; ppi=p['ppi_crude']
my={}
my['oil_12m_pct']=(wti/wti.shift(12)-1)*100
my['real_oil_12m_pct']=((wti/cpi)/(wti/cpi).shift(12)-1)*100
my['ppi_crude_12m_pct']=(ppi/ppi.shift(12)-1)*100
def nopi(s):
    l=np.log(s)*100
    prevmax=l.shift(1).rolling(36,min_periods=36).max()
    m=(l-prevmax).clip(lower=0)
    return m, m.rolling(12,min_periods=12).sum()
my['nopi36_monthly'],my['nopi36_sum12']=nopi(wti)
my['ppi_nopi36_monthly'],my['ppi_nopi36_sum12']=nopi(ppi)
my['spread_gs']=p['gs10']-p['tb3ms']
gmin=my['spread_gs'].rolling(6,min_periods=6).min()
my['curve_flat_gs6m']=(gmin<0.25).astype(object).where(gmin.notna())
diffs={}
for k,v in my.items():
    a=p[k]; 
    if k=='curve_flat_gs6m':
        both=a.notna()&v.notna(); d=int((a[both].astype(bool)!=v[both]).sum()); diffs[k]=f'{d} bool mismatches; panel_nonnull={a.notna().sum()} mine={v.notna().sum()}'
    else:
        both=a.notna()&v.notna(); d=(a[both]-v[both]).abs(); diffs[k]=f'max|diff|={d.max():.4g} n_both={both.sum()} panel_nonnull={a.notna().sum()} mine_nonnull={v.notna().sum()} first_panel={a.first_valid_index()} first_mine={v.first_valid_index()}'
out['derived_column_check']=diffs
# NOPI sum12 with min_periods relaxations (for series start question)
_,s12b=nopi(wti); 
out['nopi_first_valid']=str(my['nopi36_sum12'].first_valid_index())
out['panel_nopi_first_valid']=str(p['nopi36_sum12'].first_valid_index())

# ---------- 2. instrument agreement ----------
def grade(x): return np.where(x>=50,'red',np.where(x>=25,'yellow','benign'))
w=p.loc['1987-01':'2026-08',['oil_12m_pct','wti_daily_252_pct']].dropna()
g1=grade(w['oil_12m_pct'].values); g2=grade(w['wti_daily_252_pct'].values)
out['ia_d1_months']=len(w); out['ia_d1_grade_agreement']=round(float((g1==g2).mean()),4)
out['ia_d1_onoff_agreement']=round(float(((g1=='red')==(g2=='red')).mean()),4)
out['ia_d1_live_red_panel_not']=int(((g2=='red')&(g1!='red')).sum()); out['ia_d1_panel_red_live_not']=int(((g1=='red')&(g2!='red')).sum())
out['ia_d1_live_red_panel_not_months']=[str(i) for i in w.index[(g2=='red')&(g1!='red')]]
out['ia_d1_panel_red_live_not_months']=[str(i) for i in w.index[(g1=='red')&(g2!='red')]]
c=p.loc['1982-01':'2026-08',['curve_flat_gs6m','curve_flat_daily183']].dropna()
c=c.astype(bool)
out['ia_curve_months']=len(c); out['ia_curve_agreement']=round(float((c.iloc[:,0]==c.iloc[:,1]).mean()),4)
out['ia_curve_daily_only']=int((c.iloc[:,1]&~c.iloc[:,0]).sum()); out['ia_curve_monthly_only']=int((c.iloc[:,0]&~c.iloc[:,1]).sum())
out['ia_curve_disagreement_months']=[str(i) for i in c.index[c.iloc[:,0]!=c.iloc[:,1]]]
cmin=p['spread_cmt'].rolling(6,min_periods=6).min()
cmtflat=(cmin<0.25).astype(object).where(cmin.notna())
cc=pd.DataFrame({'cmt':cmtflat,'gs':my['curve_flat_gs6m']}).loc['1982-01':'2026-08'].dropna().astype(bool)
out['ia_cmt_months']=len(cc); out['ia_cmt_first']=str(cc.index[0]); out['ia_cmt_agreement']=round(float((cc.cmt==cc.gs).mean()),4)
out['ia_cmt_disagreements']=int((cc.cmt!=cc.gs).sum()); out['ia_cmt_only']=int((cc.cmt&~cc.gs).sum()); out['ia_gs_only']=int((cc.gs&~cc.cmt).sum())
out['ia_cmt_disagreement_months']=[str(i) for i in cc.index[cc.cmt!=cc.gs]]

# ---------- 3. episode machinery ----------
usrec=p['usrec'].astype(int)
def episodes(on):
    """on: boolean Series indexed by Period (NaN->False). Raw ON months; gap<=6 OFF months merges."""
    on=on.fillna(False).astype(bool)
    months=list(on.index[on.values])
    eps=[]; cur=[]
    for m in months:
        if cur and (m-cur[-1]).n-1>6: eps.append(cur); cur=[]
        cur.append(m)
    if cur: eps.append(cur)
    return eps
def classify(on, events, h, win_start, win_end_onset, series_start, doubledip=True, kind='nber'):
    """returns per-episode outcomes, per-event outcomes, month precision, base rate."""
    on=on.fillna(False).astype(bool)
    last_res=LAST_USREC-h
    eps=episodes(on)
    evs=[e for e in events if e>=win_start]  # events in window (onsets 1953-08+ for common)
    evs=[e for e in evs if e<=win_end_onset]
    def evaluable(e): return (e-h)>=series_start
    rows=[]; credited=set()
    for ep in eps:
        raw_first, raw_last = ep[0], ep[-1]
        if raw_first<win_start: continue
        free=[m for m in ep if usrec.get(m,1)==0]
        pending=any(m>last_res for m in free)
        # hit test
        hits=[]
        for e in evs:
            if e in credited: continue
            lo,hi = raw_first, raw_last+h
            if doubledip and e==P('1981-08') and kind=='nber':
                # score only against ON months in 1980-08..1981-07
                dd=[m for m in ep if P('1980-08')<=m<=P('1981-07')]
                if not dd: continue
                lo,hi=dd[0],dd[-1]+h
                if not (lo<e<=hi): continue
                hits.append(e); continue
            if lo<e<=hi: hits.append(e)
        coinc=[e for e in evs if e<=raw_first<=e+3]
        if hits:
            outc='HIT'; credited.update(hits)
        elif coinc: outc='COINCIDENT'
        elif not free: outc='IN-RECESSION'
        elif pending: outc='PENDING'
        else: outc='FALSE POSITIVE'
        rows.append(dict(start=str(free[0]) if free else f'({raw_first} in-recession)', raw=f'{raw_first}..{raw_last}', n=len(free), outcome=outc, events=[str(e) for e in hits], coinc=[str(e) for e in coinc], lead=(hits[0]-raw_first).n if hits else None))
    # per-event recall
    per={}
    for e in evs:
        if not evaluable(e): per[str(e)]='NOT EVALUABLE'; continue
        lo,hi=e-h,e-1
        if doubledip and e==P('1981-08') and kind=='nber': lo=max(lo,P('1980-08'))
        onm=[m for m in on.index[on.values] if lo<=m<=hi]
        per[str(e)]='CAUGHT' if onm else 'MISSED'
    n_eval=sum(1 for v in per.values() if v!='NOT EVALUABLE'); n_c=sum(1 for v in per.values() if v=='CAUGHT')
    # month precision
    idx=[m for m in on.index if win_start<=m<=last_res and usrec.get(m,1)==0]
    def pos(m): 
        for e in events:
            if m<e<=m+h:
                if doubledip and e==P('1981-08') and kind=='nber' and not (P('1980-08')<=m<=P('1981-07')): continue
                return True
        return False
    onidx=[m for m in idx if on[m]]
    tp=sum(pos(m) for m in onidx); base=sum(pos(m) for m in idx)
    nh=sum(r['outcome']=='HIT' for r in rows); nf=sum(r['outcome']=='FALSE POSITIVE' for r in rows)
    return dict(hits=nh,fp=nf,coinc=sum(r['outcome']=='COINCIDENT' for r in rows),pending=sum(r['outcome']=='PENDING' for r in rows),
                ep_prec=round(nh/(nh+nf),4) if nh+nf else None, recall=f'{n_c}/{n_eval}', month_tp=tp, month_n=len(onidx), month_prec=round(tp/len(onidx),4) if onidx else None,
                base_tp=base, base_n=len(idx), base=round(base/len(idx),4), episodes=rows, per_event=per,
                fps=[r['start'] for r in rows if r['outcome']=='FALSE POSITIVE'], coincs=[r['raw'].split('..')[0] for r in rows if r['outcome']=='COINCIDENT'], caught=[k for k,v in per.items() if v=='CAUGHT'])

rules={'D1-RED':(p['oil_12m_pct']>=50, P('1947-01')), 'D1-YELLOW':(p['oil_12m_pct']>=25,P('1947-01')),
       'D2':(p['nopi36_sum12']>=10, p['nopi36_sum12'].first_valid_index()),
       'D3-RED':(p['real_oil_12m_pct']>=50,P('1948-01')),'D3-YELLOW':(p['real_oil_12m_pct']>=25,P('1948-01')),
       'PPI-RED':(p['ppi_crude_12m_pct']>=50,P('1948-01')),'PPI-D2':(p['ppi_nopi36_sum12']>=10,p['ppi_nopi36_sum12'].first_valid_index())}
# note series_start = first month with a non-null reading
for k,(s,_) in rules.items(): rules[k]=(s.where(p[{'D1-RED':'oil_12m_pct','D1-YELLOW':'oil_12m_pct','D2':'nopi36_sum12','D3-RED':'real_oil_12m_pct','D3-YELLOW':'real_oil_12m_pct','PPI-RED':'ppi_crude_12m_pct','PPI-D2':'ppi_nopi36_sum12'}[k]].notna()), p[{'D1-RED':'oil_12m_pct','D1-YELLOW':'oil_12m_pct','D2':'nopi36_sum12','D3-RED':'real_oil_12m_pct','D3-YELLOW':'real_oil_12m_pct','PPI-RED':'ppi_crude_12m_pct','PPI-D2':'ppi_nopi36_sum12'}[k]].first_valid_index())
out['series_starts']={k:str(v[1]) for k,v in rules.items()}
nber={}
for h in (12,18):
    for k,(on,st) in rules.items():
        nber[f'{k}_h{h}']=classify(on,onsets,h,P('1953-04'),P('2020-03'),st)
out['nber']=nber
# secondary full-window
full={}
for h in (12,18):
    for k,(on,st) in rules.items():
        full[f'{k}_h{h}']=classify(on,onsets,h,P('1947-01'),P('2020-03'),st)
out['full']={k:{kk:v[kk] for kk in ('hits','fp','recall','month_tp','month_n','month_prec','base','per_event')} for k,v in full.items()}

# ---------- 5. curve-conditioned ----------
flat=my['curve_flat_gs6m']
crules={'curve flat alone':(flat,P('1953-09')),
        'D1-RED alone':rules['D1-RED'],'D1-RED AND curve flat':(rules['D1-RED'][0]&flat.fillna(False),P('1953-09')),
        'D2 alone':rules['D2'],'D2 AND curve flat':(rules['D2'][0]&flat.fillna(False),P('1953-09')),
        'D3-RED alone':rules['D3-RED'],'D3-RED AND curve flat':(rules['D3-RED'][0]&flat.fillna(False),P('1953-09'))}
curve={}
for h in (12,18):
    for k,(on,st) in crules.items():
        curve[f'NBER|{k}|h{h}']=classify(on,[o for o in onsets if o>=P('1957-09')],h,P('1953-09'),P('2020-03'),st)
        curve[f'B1|{k}|h{h}']=classify(on,B1,h,P('1953-09'),P('2030-01'),st,doubledip=False,kind='dd')
        curve[f'B2|{k}|h{h}']=classify(on,B2,h,P('1953-09'),P('2030-01'),st,doubledip=False,kind='dd')
out['curve']=curve

# ---------- Q5 ----------
last=p.loc[P('2026-08')]
out['q5']=dict(oil_12m_pct=round(float(last['oil_12m_pct']),4),real=round(float(last['real_oil_12m_pct']),4),nopi=round(float(last['nopi36_sum12']),4),spread_gs=round(float(last['spread_gs']),2),flat=bool(last['curve_flat_gs6m']),
  d1_grade=str(grade(np.array([last['oil_12m_pct']]))[0]),d3_grade=str(grade(np.array([last['real_oil_12m_pct']]))[0]),
  peak_2026_d1=float(p.loc['2026-01':'2026-08','oil_12m_pct'].max()),peak_2026_d3=float(p.loc['2026-01':'2026-08','real_oil_12m_pct'].max()),
  nopi_2026={str(i):r.tolist() for i,r in p.loc['2026-01':'2026-08',['nopi36_monthly','nopi36_sum12']].round(2).iterrows()},
  spread_gs_2026_04=float(p.loc[P('2026-04'),'spread_gs']), min6_2026_08=float(my['spread_gs'].rolling(6).min().loc[P('2026-08')]))
json.dump(out,open('/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil/verify/event_recompute/mine.json','w'),indent=1,default=str)
print('written')
