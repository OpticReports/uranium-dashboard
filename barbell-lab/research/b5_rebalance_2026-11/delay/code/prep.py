"""Build daily sleeve-return matrices for B.5 delay study (PREREG sec 3, with logged deviations)."""
import json, io, os, sys
import numpy as np, pandas as pd
ROOT = sys.argv[1]
RAW = os.path.join(ROOT, 'raw'); X = os.path.join(RAW, 'x'); OUT = os.path.join(ROOT, 'data'); os.makedirs(OUT, exist_ok=True)
FIX = '/home/user/uranium-dashboard/barbell-lab/research/barbell_timer/fixtures'
src = {}

def french(path, section_marker=None):
    lines = open(path, encoding='latin-1').read().splitlines()
    start = 0
    if section_marker:
        start = next(i for i, l in enumerate(lines) if section_marker in l)
    hdr = next(i for i in range(start, len(lines)) if lines[i].startswith(','))
    cols = [c.strip() for c in lines[hdr].split(',')[1:]]
    rows = []
    for l in lines[hdr + 1:]:
        p = [s.strip() for s in l.split(',')]
        if len(p) < 2 or not p[0].isdigit() or len(p[0]) != 8: break
        rows.append([p[0]] + [float(v) for v in p[1:]])
    df = pd.DataFrame(rows, columns=['d'] + cols)
    df.index = pd.to_datetime(df.pop('d'), format='%Y%m%d')
    df = df.replace([-99.99, -999.0], np.nan) / 100.0
    return df

ff = french(f'{X}/F-F_Research_Data_Factors_daily.csv')
cal = ff.index
rf = ff['RF']; mkt = ff['Mkt-RF'] + ff['RF']
sz_bm = french(f'{X}/6_Portfolios_2x3_Daily.csv', 'Average Value Weighted Returns -- Daily')
sz_op = french(f'{X}/6_Portfolios_ME_OP_2x3_daily.csv', 'Average Value Weighted Returns')  # header says Monthly but rows are daily (8-digit dates)
dx = french(f'{X}/Developed_ex_US_6_Portfolios_ME_BE-ME_Daily.csv', 'Average Value Weighted Returns -- Daily')
print('sz_op cols', list(sz_op.columns))
us_sv = sz_bm['SMALL HiBM']; qual = sz_op['BIG HiOP']; dx_sv = dx['SMALL HiBM']

def to_cal(ret, name):
    """Compound a return series onto the US trading calendar (non-US dates roll into next US date)."""
    r = ret.dropna()
    lvl = (1 + r).cumprod()
    first = r.index[0]
    lvl = pd.concat([pd.Series([1.0], index=[first - pd.Timedelta(days=1)]), lvl])
    u = lvl.reindex(lvl.index.union(cal)).ffill().reindex(cal)
    out = u.pct_change()
    out[cal <= first - pd.Timedelta(days=1)] = np.nan
    out[cal < first] = np.nan
    # first US date >= first: return since synthetic base
    return out

def level_to_cal(lvl):
    lvl = lvl.dropna()
    u = lvl.reindex(lvl.index.union(cal)).ffill().reindex(cal)
    r = u.pct_change(); r[cal <= lvl.index[0]] = np.nan
    return r

dx_sv_c = to_cal(dx_sv, 'dx_sv')
# ---- gold: GCUSD (repo fixture, FMP) to 2004-11-17, GLD (Yahoo adj) from 2004-11-18
g = json.load(open(f'{FIX}/fmp_gcusd_light.json'))['rows']
gc = pd.Series({pd.Timestamp(r['date']): r['price'] for r in g}).sort_index()
gld = pd.read_csv(f'{RAW}/GLD.csv', skiprows=3, header=None, index_col=0, parse_dates=True)[1].astype(float)
gc_r = level_to_cal(gc); gld_r = level_to_cal(gld)
splice = pd.Timestamp('2004-11-18')
gold = gc_r.copy(); gold[cal > splice] = gld_r[cal > splice]
# ---- 10y Treasury TR from DGS10 (curl'ed today from FRED)
y = pd.read_csv(f'{RAW}/DGS10.csv', index_col=0, parse_dates=True).iloc[:, 0]
y = pd.to_numeric(y, errors='coerce').dropna() / 100
yc = y.reindex(y.index.union(cal)).ffill().reindex(cal)
dts = pd.Series(cal, index=cal).diff().dt.days
D = (1 / yc) * (1 - 1 / (1 + yc / 2) ** 20)
bond = yc.shift(1) * dts / 365 - D.shift(1) * (yc - yc.shift(1))
bond[cal <= y.index[0]] = np.nan
# ---- USD: DTWEXM (<=1994-12-31) -> DTWEXB (1995-01-04..2005-12-31) -> DTWEXBGS (2006+)
def fred(n):
    s = pd.read_csv(f'{RAW}/{n}.csv', index_col=0, parse_dates=True).iloc[:, 0]
    return pd.to_numeric(s, errors='coerce').dropna()
um, ub, ubg = fred('DTWEXM'), fred('DTWEXB'), fred('DTWEXBGS')
usd = level_to_cal(um)
usd[cal >= pd.Timestamp('1995-01-04')] = level_to_cal(ub)[cal >= pd.Timestamp('1995-01-04')]
usd[cal >= pd.Timestamp('2006-01-03')] = level_to_cal(ubg)[cal >= pd.Timestamp('2006-01-03')]

# ---- KMLM analogue (PREREG sec 3)
legs = pd.DataFrame({'eq': ff['Mkt-RF'], 'bond': bond - rf, 'gold': gold - rf, 'usd': usd})
def tsmom(legs):
    lg = legs.copy()
    trail = np.log1p(lg).rolling(252, min_periods=252).sum()
    me = pd.Series(cal, index=cal).dt.to_period('M')
    is_me = me != me.shift(-1)
    sig = np.sign(trail.where(is_me)).ffill().shift(1)   # set at month-end close, applied from next day
    vol = np.sqrt(lg.pow(2).ewm(span=60, min_periods=60).mean() * 252).shift(1)
    pos = sig * 0.10 / vol
    legr = pos * lg
    ok = legr.notna().all(axis=1)
    out = rf + legr.mean(axis=1)
    out[~ok] = np.nan
    return out, pos
kmlm, kpos = tsmom(legs)

cash = rf
veiex = level_to_cal(pd.read_csv(f'{RAW}/VEIEX.csv', skiprows=3, header=None, index_col=0, parse_dates=True)[1].astype(float))
def kml_splice():
    a = level_to_cal(pd.read_csv(f'{RAW}/ASFYX.csv', skiprows=3, header=None, index_col=0, parse_dates=True)[1].astype(float))
    k = level_to_cal(pd.read_csv(f'{RAW}/KMLM.csv', skiprows=3, header=None, index_col=0, parse_dates=True)[1].astype(float))
    s = a.copy(); s[cal >= pd.Timestamp('2020-12-03')] = k[cal >= pd.Timestamp('2020-12-03')]
    return s, k
asfyx_kmlm, kmlm_etf = kml_splice()

def build(name, cols, w, extra_note=''):
    df = pd.DataFrame(cols).dropna()
    # contiguity check
    full = pd.DataFrame(cols).loc[df.index[0]:df.index[-1]]
    gaps = int(full.isna().any(axis=1).sum())
    df = full.fillna(0.0)  # interior holes -> 0 return (counted)
    rfx = rf.reindex(df.index)
    df.to_pickle(f'{OUT}/{name}.pkl'); rfx.to_pickle(f'{OUT}/{name}_rf.pkl')
    src[name] = dict(cols=list(cols), weights=w, start=str(df.index[0].date()), end=str(df.index[-1].date()),
                     n_days=len(df), interior_nan_rows_set_to_zero=gaps, note=extra_note)
    print(name, src[name])

WA = [.235, .235, .153, .141, .177, .059]
build('A', {'AVUV~US_SV': us_sv, 'PHYS~gold': gold, 'QUAL~US_BigHiOP': qual, 'KMLM~TSMOM': kmlm,
            'AVDV+AVEM~DevxUS_SV': dx_sv_c, 'TAIL~cash': cash}, WA, 'AVEM weight folded into AVDV (DEVIATION D2)')
build('A_veiex', {'AVUV~US_SV': us_sv, 'PHYS~gold': gold, 'QUAL~US_BigHiOP': qual, 'KMLM~TSMOM': kmlm,
            'AVDV~DevxUS_SV': dx_sv_c, 'AVEM~VEIEX': veiex, 'TAIL~cash': cash}, [.235, .235, .153, .141, .118, .059, .059])
build('A_long', {'AVUV+AVDV+AVEM~US_SV': us_sv, 'PHYS~gold': gold, 'QUAL~US_BigHiOP': qual, 'KMLM~TSMOM': kmlm,
            'TAIL~cash': cash}, [.412, .235, .153, .141, .059])
build('A_asfyx', {'AVUV~US_SV': us_sv, 'PHYS~gold': gold, 'QUAL~US_BigHiOP': qual, 'KMLM~ASFYX->KMLM': asfyx_kmlm,
            'AVDV+AVEM~DevxUS_SV': dx_sv_c, 'TAIL~cash': cash}, WA)
pput = pd.read_csv(f'{RAW}/PPUT_History.csv', index_col=0); pput.index = pd.to_datetime(pput.index, format='%m/%d/%Y')
sptr = pd.read_csv(f'{RAW}/SP500TR.csv', skiprows=3, header=None, index_col=0, parse_dates=True)[1].astype(float)
tail_ov = cash + level_to_cal(pput['PPUT'].astype(float)) - level_to_cal(sptr)
build('A_pput', {'AVUV~US_SV': us_sv, 'PHYS~gold': gold, 'QUAL~US_BigHiOP': qual, 'KMLM~TSMOM': kmlm,
            'AVDV+AVEM~DevxUS_SV': dx_sv_c, 'TAIL~cash+PPUT-SPXTR': tail_ov}, WA)
build('B', {'US_mkt': mkt, 'UST10_TR': bond, 'gold': gold}, [.4, .4, .2])

# KMLM analogue vs KMLM ETF correlation on overlap
j = pd.concat([kmlm, kmlm_etf], axis=1).dropna(); j = j[j.index >= '2020-12-03']
jw = (1 + j).resample('W-FRI').prod() - 1
src['kmlm_check'] = dict(daily_corr=round(float(j.corr().iloc[0, 1]), 3), weekly_corr=round(float(jw.corr().iloc[0, 1]), 3),
                         n_days=len(j), ann_ret_analogue=float((1 + j.iloc[:, 0]).prod() ** (252 / len(j)) - 1),
                         ann_ret_kmlm=float((1 + j.iloc[:, 1]).prod() ** (252 / len(j)) - 1))
# gold proxy check: GCUSD vs GLD on overlap
o = pd.concat([gc_r, gld_r], axis=1).dropna(); o = o[(o.index > '2004-11-19') & (o.index <= '2026-08-12')]
src['gold_check'] = dict(daily_corr_GCUSD_vs_GLD=round(float(o.corr().iloc[0, 1]), 4), n=len(o),
                         gcusd_daily_abs_ret_gt_3pct_days_pre2004=int((gc_r[cal < splice].abs() > 0.03).sum()))
src['sources'] = {
  'French': 'mba.tuck.dartmouth.edu ken.french ftp: F-F_Research_Data_Factors_daily, 6_Portfolios_2x3_daily (VW, SMALL HiBM), 6_Portfolios_ME_OP_2x3_daily (VW, BIG HiOP), Developed_ex_US_6_Portfolios_ME_BE-ME_daily (VW, SMALL HiBM); built from 202609 CRSP/Bloomberg; ends 2026-09-30',
  'FRED': 'fredgraph.csv DGS10 (1962-01-02..2026-11-12), DTWEXM (1973-01-02..2019-12-31), DTWEXB (1995-01-04..2019-12-31), DTWEXBGS (2006-01-02..2026-11-06)',
  'gold': 'GCUSD COMEX continuous front-month price (repo fixture barbell-lab/research/barbell_timer/fixtures/fmp_gcusd_light.json, 1976-02-26..) to 2004-11-17; GLD Yahoo adj close from 2004-11-18',
  'Yahoo': 'GLD 2004-11-18.., VEIEX 1994-05-04.., KMLM 2020-12-02.., ASFYX 2010-08-03.., ^SP500TR 1988-01-04..',
  'CBOE': 'PPUT_History.csv cdn-api.cboe.com 1986-06-30..2026-11-13'}
src['sz_op_columns'] = list(sz_op.columns)
json.dump(src, open(f'{OUT}/sources.json', 'w'), indent=1, default=str)
