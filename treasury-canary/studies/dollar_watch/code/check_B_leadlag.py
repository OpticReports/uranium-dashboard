import csv, numpy as np, datetime as dt, pandas as pd
R='raw/'
def fred(fn):
    o={}
    for r in csv.DictReader(open(R+fn)):
        k=[c for c in r if c!='observation_date'][0]
        if r[k] not in ('','.'): o[r['observation_date']]=float(r[k])
    return pd.Series(o); 
bd=fred('fred_DTWEXBGS.csv'); bd.index=pd.to_datetime(bd.index)
cp=fred('fred_DCPF3M.csv'); tb=fred('fred_DTB3.csv'); sp=(cp-tb).dropna(); sp.index=pd.to_datetime(sp.index)
ofr=pd.read_csv(R+'ofr_fsi.csv', parse_dates=['Date']).set_index('Date')
fund=ofr['Funding']
# broad dollar peaks per episode
for lo,hi in [('2007-06-01','2009-06-30'),('2015-01-01','2016-06-30'),('2018-01-01','2019-01-31'),('2020-01-01','2020-06-30'),('2022-01-01','2022-12-31')]:
    s=bd[lo:hi]; pk=s.idxmax(); 
    c=sp[lo:hi]; cpk=c.idxmax()
    f=fund[lo:hi]; fpk=f.idxmax()
    print(f"{lo[:4]}: broad$ peak {pk.date()} {s.max():.1f}; CP-bill peak {cpk.date()} {c.max():.2f} ({(cpk-pk).days:+d}d); OFR funding peak {fpk.date()} {f.max():.2f} ({(fpk-pk).days:+d}d)")
    if lo.startswith('2007'): print('   broad $ trough 2008:', s[:'2008-12-31'].idxmin().date(), s[:'2008-12-31'].min())
# alarms: first day > trailing-5y 95th pct (expanding/rolling)
def alarm(s, lo, hi, q=0.95, years=5):
    s=s.dropna()
    for d in s[lo:hi].index:
        w=s[d-pd.DateOffset(years=years):d-pd.Timedelta(days=1)]
        if len(w)>250 and s[d]>w.quantile(q): return d.date(), round(float(s[d]),3), round(float(w.quantile(q)),3)
    return None
print('OFR funding alarm 2007 window (2007-06..2009-06):', alarm(fund,'2007-06-01','2009-06-30'))
print('OFR funding alarm 2022 window (2022-01..2022-12):', alarm(fund,'2022-01-01','2022-12-31'))
print('CP-bill alarm 2007:', alarm(sp,'2007-06-01','2009-06-30'), ' 2022:', alarm(sp,'2022-01-01','2022-12-31'))
# gold trough 2008 from finder A gold_daily
gd=pd.read_csv('../finderA/data/gold_daily.csv', parse_dates=['date']).set_index('date')['close']
g=gd['2008-03-01':'2009-06-30']; print('gold 2008 window max', g.idxmax().date(), round(g.max(),1), 'trough', g['2008-07-01':].idxmin().date(), round(g['2008-07-01':].min(),1), 'days before 2009-03-03:', (pd.Timestamp('2009-03-03')-g['2008-07-01':].idxmin()).days, f"{100*(g['2008-07-01':].min()/g.max()-1):.1f}%")
g=gd['2020-02-01':'2020-04-30']; print('gold 2020 trough', g.idxmin().date(), round(g.min(),1), 'from', g[:g.idxmin()].idxmax().date(), round(g[:g.idxmin()].max(),1), f"{100*(g.min()/g[:g.idxmin()].max()-1):.1f}%")
g=gd['2022-01-01':'2022-12-31']; print('gold 2022 trough', g.idxmin().date(), round(g.min(),1), 'from', g[:g.idxmin()].idxmax().date(), round(g[:g.idxmin()].max(),1), f"{100*(g.min()/g[:g.idxmin()].max()-1):.1f}%")
# CP-bill 2022-07-01 one-day spike check
print('DCPF3M/DTB3 around 2022-07-01:'); 
for d in ['2022-06-28','2022-06-29','2022-06-30','2022-07-01','2022-07-05','2022-07-06']: print('  ',d, cp.get(d), tb.get(d))
c=sp['2022-01-01':'2022-12-31'].drop(pd.Timestamp('2022-07-01')); print('2022 CP-bill peak excluding 07-01:', c.idxmax().date(), round(c.max(),2), 'rolling-5d-mean peak', sp['2022-01-01':'2022-12-31'].rolling(5).mean().idxmax().date())
# Johnson regression from johnson_quarterly.csv
jq=pd.read_csv('../finderB/scripts/johnson_quarterly.csv', index_col=0, parse_dates=True)
d=jq.dropna()
print('\njohnson_quarterly n', len(d), d.index[0].date(), d.index[-1].date())
print('corr yoy contemporaneous', round(d.g_credit_yoy.corr(d.g_usd_yoy),3), 'usd leading 1q', round(d.g_credit_yoy.corr(d.g_usd_yoy.shift(1)),3), 'qoq', round(d.g_credit.corr(d.g_usd),3))
fy=d[d.g_usd_yoy<0]; ry=d[d.g_usd_yoy>0]; print(f"yoy credit growth when usd down {fy.g_credit_yoy.mean():.2f} (n={len(fy)}) up {ry.g_credit_yoy.mean():.2f} (n={len(ry)})")
# note: these are LOG changes x100, not simple %; convert
print('simple-% version:', round(100*(np.exp(fy.g_credit_yoy/100).mean()-1),2), round(100*(np.exp(ry.g_credit_yoy/100).mean()-1),2))
# independent rebuild of credit & usd from fresh pulls
gli=pd.read_csv(R+'bis_gli.csv'); gli=gli[gli.OBS_VALUE.notna()]
cred=pd.Series(gli.OBS_VALUE.values/1e6, index=pd.PeriodIndex(gli.TIME_PERIOD, freq='Q').to_timestamp(how='end').normalize()).sort_index()
bgs=fred('fred_TWEXBGSMTH.csv'); old=fred('fred_TWEXBMTH.csv'); bgs.index=pd.to_datetime(bgs.index); old.index=pd.to_datetime(old.index)
k=bgs.iloc[0]/old.loc['2006-01-01']; usd=pd.concat([old[old.index<'2006-01-01']*k,bgs]); usdq=usd.resample('QE').last(); usdq.index=usdq.index.normalize()
df=pd.DataFrame({'credit':cred,'usd':usdq}).dropna(); df['gc']=100*np.log(df.credit).diff(4); df['gu']=100*np.log(df.usd).diff(4); dd=df.dropna()
print('fresh rebuild: n', len(dd), 'corr', round(dd.gc.corr(dd.gu),3), 'credit yoy usd down', round(dd[dd.gu<0].gc.mean(),2), 'up', round(dd[dd.gu>0].gc.mean(),2), 'n', (dd.gu<0).sum(), (dd.gu>0).sum())
print('compare finderB usd series vs mine, last rows:'); print(pd.DataFrame({'B':jq.usd, 'mine':usdq}).dropna().tail(3))
print('TWEXBGSMTH first', bgs.index[0].date(), 'TWEXBMTH last', old.index[-1].date())
# negative yoy quarters
print('negative yoy credit quarters:', [str(i.date()) for i in dd[dd.gc<0].index])
