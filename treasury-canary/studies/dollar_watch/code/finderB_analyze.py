"""Episode lead/lag analysis + current readings. usage: python3 -I analyze.py RAWDIR"""
import sys, csv, json, io, math, datetime as dt
import pandas as pd, numpy as np
RAW = sys.argv[1]
def fred(name):
    rows=[r for r in csv.reader(open(f'{RAW}/{name}.raw', encoding='utf-8')) if r]
    s=pd.Series({pd.Timestamp(r[0]): (float(r[1]) if r[1] not in ('.','') else np.nan) for r in rows[1:] if len(r)>=2})
    return s.sort_index().dropna()
def fmp(name):
    d=json.load(open(f'{RAW}/{name}.raw'))
    return pd.Series({pd.Timestamp(x['date']): x['price'] for x in d}).sort_index()
def yahoo(name):
    d=json.load(open(f'{RAW}/{name}.raw'))['chart']['result'][0]
    return pd.Series(d['indicators']['quote'][0]['close'], index=pd.to_datetime(d['timestamp'], unit='s').normalize()).dropna()
S={}
bgs=fred('DTWEXBGS'); old=fred('DTWEXB')
k=bgs.loc['2006-01-03']/old.loc['2006-01-03']
S['usd_broad']=pd.concat([old[old.index<'2006-01-03']*k, bgs])
S['usd_eme']=fred('DTWEXEMEGS'); S['usd_afe']=fred('DTWEXAFEGS')
S['cp_fin_spread']=(fred('DCPF3M')-fred('DTB3')).dropna()
S['cp_nonfin_spread']=(fred('DCPN3M')-fred('DTB3')).dropna()
S['ted']=fred('TEDRATE'); S['swpt']=fred('SWPT'); S['vix']=fred('VIXCLS'); S['stlfsi']=fred('STLFSI4')
S['custody']=fred('WMTSECL1'); S['nfci_risk']=fred('NFCIRISK'); S['kcfsi']=fred('KCFSI')
S['sofr_99_minus_sofr']=(fred('SOFR99')-fred('SOFR')).dropna()
S['sofr_minus_iorb']=(fred('SOFR')-fred('IORB')).dropna()
ofr=pd.read_csv(f'{RAW}/ofr_fsi.raw', parse_dates=['Date']).set_index('Date')
S['ofr_fsi']=ofr['OFR FSI']; S['ofr_funding']=ofr['Funding']; S['ofr_em']=ofr['Emerging markets']; S['ofr_safe']=ofr['Safe assets']
S['gold']=fmp('fmp_xauusd_full'); S['emb']=fmp('fmp_emb_full'); S['cew']=fmp('fmp_cew_full'); S['eem']=fmp('fmp_eem_full')
S['dxy_m']=yahoo('yahoo_dxy_daily')
# equal-weight EM FX basket (USD per local; higher = weaker EM) from FRED pairs
pairs={'DEXBZUS':1,'DEXMXUS':1,'DEXSFUS':1,'DEXINUS':1,'DEXKOUS':1,'DEXTHUS':1,'DEXCHUS':1,'DEXMAUS':1}
logs=pd.concat({p: np.log(fred(p)) for p in pairs}, axis=1).dropna()
S['emfx_basket']=np.exp((logs-logs.iloc[0]).mean(axis=1))*100  # 1995=100; up = EM FX weaker
S['jpy']=fred('DEXJPUS'); S['chf']=fred('DEXSZUS')
S['oil_brent']=fred('DCOILBRENTEU')
# NY Fed swap operations -> outstanding by date
ops=pd.read_csv(f'{RAW}/nyfed_fxs_search_csv.raw')
ops=ops[ops['Operation Type']=='U.S. Dollar Liquidity Swap']
ops['Amount']=pd.to_numeric(ops['Amount'],errors='coerce'); ops['s']=pd.to_datetime(ops['Settlement Date']); ops['m']=pd.to_datetime(ops['Maturity Date'])
days=pd.date_range(ops['s'].min(), '2026-11-02')
out=pd.Series(0.0,index=days)
for _,r in ops.iterrows():
    out[(days>=r['s'])&(days<r['m'])]+=r['Amount']
S['nyfed_swaps_outstanding_bn']=out/1e9

# ---- episodes: window, and the direction of "stress" for each series (+1 = up is stress)
EP={'2008':('2008-03-01','2009-06-30'),'2015-16':('2014-07-01','2016-03-31'),'2018':('2018-01-01','2019-01-31'),'2020':('2020-01-01','2020-06-30'),'2022':('2022-01-01','2023-01-31'),'2023-SVB':('2023-02-01','2023-05-31'),'2025-26':('2025-01-01','2026-11-02')}
DIR={'usd_broad':1,'usd_eme':1,'usd_afe':1,'cp_fin_spread':1,'cp_nonfin_spread':1,'ted':1,'swpt':1,'vix':1,'stlfsi':1,'custody':-1,'nfci_risk':1,'kcfsi':1,'sofr_99_minus_sofr':1,'sofr_minus_iorb':1,'ofr_fsi':1,'ofr_funding':1,'ofr_em':1,'ofr_safe':1,'gold':-1,'emb':-1,'cew':-1,'eem':-1,'emfx_basket':1,'jpy':-1,'chf':-1,'nyfed_swaps_outstanding_bn':1,'dxy_m':1,'oil_brent':-1}
res={}
for ep,(a,b) in EP.items():
    res[ep]={}
    for n,s in S.items():
        w=s[(s.index>=a)&(s.index<=b)]
        if len(w)<3: continue
        ext = w.idxmax() if DIR[n]>0 else w.idxmin()
        # first-alarm date: first day in window the series exceeds its trailing-5y 95th pct (stress direction), using data before window too
        hist=s[(s.index>=pd.Timestamp(a)-pd.DateOffset(years=5))&(s.index<a)]
        alarm=None
        if len(hist)>50:
            thr=hist.quantile(0.95) if DIR[n]>0 else hist.quantile(0.05)
            hit=w[(w>thr)] if DIR[n]>0 else w[(w<thr)]
            alarm=str(hit.index[0].date()) if len(hit) else None
        res[ep][n]={'extreme_date':str(ext.date()),'extreme_val':round(float(w.loc[ext]),3),'first_alarm_95pct_5y':alarm,'start_val':round(float(w.iloc[0]),3)}
print(json.dumps(res,indent=1))
# ---- current readings / percentiles
cur={}
for n,s in S.items():
    last=s.dropna().iloc[-1]; d=s.dropna().index[-1]
    def chg(months):
        t=d-pd.DateOffset(months=months); past=s[s.index<=t]
        return None if past.empty else round(100*(last/past.iloc[-1]-1),2) if abs(past.iloc[-1])>1e-9 else None
    def pct(yrs=None):
        h=s if yrs is None else s[s.index>=d-pd.DateOffset(years=yrs)]
        return round(100*(h<last).mean(),1)
    cur[n]={'date':str(d.date()),'last':round(float(last),4),'chg_6m_pct':chg(6),'chg_12m_pct':chg(12),'pctile_all':pct(),'pctile_10y':pct(10),'hist_start':str(s.index[0].date()),'n':int(len(s))}
print('CURRENT', json.dumps(cur,indent=1))
# broad dollar peaks
u=S['usd_broad']; print('USD broad all-time max', u.idxmax().date(), round(u.max(),2), '| 2022 max', u['2022'].idxmax().date(), round(u['2022'].max(),2),'| 2020 max', u['2020'].idxmax().date(), round(u['2020'].max(),2), '| 2009 max', u['2008':'2009'].idxmax().date(), round(u['2008':'2009'].max(),2), '| 2016 max', u['2015':'2016'].idxmax().date(), round(u['2015':'2016'].max(),2), '| 2025-26 max', u['2025':'2026'].idxmax().date(), round(u['2025':'2026'].max(),2), '2025-26 min', u['2025':'2026'].idxmin().date(), round(u['2025':'2026'].min(),2))
pd.to_pickle(S, f'{RAW}/../scripts/series.pkl')
