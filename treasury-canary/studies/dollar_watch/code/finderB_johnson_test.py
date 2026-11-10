"""Johnson sign test: BIS USD credit to non-banks outside US (GLI, $) vs broad dollar. usage: python3 -I johnson_test.py RAWDIR"""
import sys, csv, pandas as pd, numpy as np
RAW=sys.argv[1]
def bis(name):
    rows=list(csv.DictReader(open(f'{RAW}/{name}.raw',encoding='utf-8')))
    s=pd.Series({pd.Period(r['TIME_PERIOD'],freq='Q').to_timestamp(how='end').normalize(): float(r['OBS_VALUE']) for r in rows if r['OBS_VALUE']})
    return s.sort_index()
tot=bis('bis_gli_v1_csv')/1e6; eme=bis('bis_gli_eme_hist')/1e6   # $tn
# bulk file: get bank loans / debt securities / EUR / JPY totals
b=pd.read_csv(f'{RAW}/bis_bulk/WS_GLI_csv_col.csv')
def pick(curr, cty, sec, lend, pos, instr, unit):
    r=b[(b.CURR_DENOM==curr)&(b.BORROWERS_CTY==cty)&(b.BORROWERS_SECTOR==sec)&(b.LENDERS_SECTOR==lend)&(b.L_POS_TYPE==pos)&(b.L_INSTR==instr)&(b.UNIT_MEASURE==unit)]
    assert len(r)==1, (curr,cty,instr,unit,len(r), r.TITLE.tolist())
    r=r.iloc[0]; cols=[c for c in b.columns if c[:2] in ('19','20') and '-Q' in c]
    s=pd.Series({pd.Period(c,freq='Q').to_timestamp(how='end').normalize(): r[c] for c in cols}).dropna().astype(float)
    return s.sort_index(), r.TITLE
print('bulk shape', b.shape); print(b[['CURR_DENOM','BORROWERS_CTY','BORROWERS_SECTOR','LENDERS_SECTOR','L_POS_TYPE','L_INSTR','UNIT_MEASURE','TITLE']].drop_duplicates().to_string()[:6000])
loans,_=pick('USD','3P','N','B','I','G','USD'); ids,_=pick('USD','3P','N','A','I','D','USD')
eur,t_eur=pick('EUR','3P','N','A','I','B','EUR') if len(b[(b.CURR_DENOM=='EUR')&(b.BORROWERS_CTY=='3P')]) else (None,None)
print('\nUSD credit to non-banks outside US ($tn):'); print(tot.tail(6).round(3).to_string())
print('yoy %', (100*(tot/tot.shift(4)-1)).tail(6).round(2).to_string())
print('EME ($tn)', eme.tail(4).round(3).to_string(), 'yoy', (100*(eme/eme.shift(4)-1)).tail(4).round(2).to_string())
print('loans ($tn)', (loans/1e6).tail(2).round(3).to_string(), 'IDS ($tn)', (ids/1e6).tail(2).round(3).to_string())
# dollar: monthly broad index spliced
def fred(name):
    rows=[r for r in csv.reader(open(f'{RAW}/{name}.raw',encoding='utf-8')) if r]
    return pd.Series({pd.Timestamp(r[0]): float(r[1]) for r in rows[1:] if len(r)>=2 and r[1] not in ('.','')}).sort_index()
bgs=fred('TWEXBGSMTH'); old=fred('TWEXBMTH'); k=bgs.iloc[0]/old.loc['2006-01-01']
usd=pd.concat([old[old.index<'2006-01-01']*k,bgs]); usdq=usd.resample('QE').last()
usdq.index=usdq.index.normalize()
df=pd.DataFrame({'credit':tot,'usd':usdq}).dropna()
df['g_credit']=100*np.log(df.credit).diff(); df['g_usd']=100*np.log(df.usd).diff()
df['g_credit_yoy']=100*np.log(df.credit).diff(4); df['g_usd_yoy']=100*np.log(df.usd).diff(4)
d=df.dropna()
print('\nQuarterly sample', d.index[0].date(), d.index[-1].date(), len(d))
for lag in range(-4,5):
    c=d.g_credit.corr(d.g_usd.shift(lag)); cy=d.g_credit_yoy.corr(d.g_usd_yoy.shift(lag))
    print(f'lag {lag:+d} (usd shifted; +=usd earlier) corr qoq {c:+.3f}  yoy {cy:+.3f}')
fall=d[d.g_usd<0]; rise=d[d.g_usd>0]
print(f'\nmean qoq USD-credit growth when dollar FELL that quarter: {fall.g_credit.mean():.2f}% (n={len(fall)}); when dollar ROSE: {rise.g_credit.mean():.2f}% (n={len(rise)})')
fy=d[d.g_usd_yoy<0]; ry=d[d.g_usd_yoy>0]
print(f'mean yoy USD-credit growth when dollar down yoy: {fy.g_credit_yoy.mean():.2f}% (n={len(fy)}); dollar up yoy: {ry.g_credit_yoy.mean():.2f}% (n={len(ry)})')
# contraction episodes
neg=d[d.g_credit_yoy<0]; print('\nquarters with NEGATIVE yoy USD credit growth:', [str(i.date()) for i in neg.index])
# same for EME
dfe=pd.DataFrame({'credit':eme,'usd':usdq}).dropna(); dfe['gc']=100*np.log(dfe.credit).diff(4); dfe['gu']=100*np.log(dfe.usd).diff(4); de=dfe.dropna()
print('EME yoy corr', round(de.gc.corr(de.gu),3), 'EME credit yoy when usd down', round(de[de.gu<0].gc.mean(),2), 'usd up', round(de[de.gu>0].gc.mean(),2))
# levels regression: log credit vs log usd with trend
import numpy.linalg as la
X=np.column_stack([np.ones(len(d)), np.arange(len(d)), np.log(d.usd)]); y=np.log(d.credit)
beta=la.lstsq(X,y,rcond=None)[0]; print('levels: log(credit) = a + b*t + c*log(usd); c =', round(beta[2],3), '(negative = stronger dollar <-> less USD credit, trend-adjusted)')
# by episode: yoy growth of USD credit at the dollar peaks
for q in ['2009-03-31','2016-03-31','2018-12-31','2020-03-31','2022-09-30','2025-03-31','2026-06-30']:
    if pd.Timestamp(q) in d.index: print(q, 'credit yoy %', round(d.loc[q,'g_credit_yoy'],2), 'usd yoy %', round(d.loc[q,'g_usd_yoy'],2))
df.to_csv(f'{RAW}/../scripts/johnson_quarterly.csv')
