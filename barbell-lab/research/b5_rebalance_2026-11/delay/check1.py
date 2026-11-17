"""Counter-agent #1 (independent; does not import author code). Usage: python -I check1.py <study_dir>
Data integrity of every long series + own simulator / per-event / Holm / T-M bootstrap for A and B."""
import sys, json, numpy as np, pandas as pd, warnings
warnings.filterwarnings('ignore')
D = sys.argv[1]; X = f'{D}/raw/x'; OUT = {}
def P(*a): print(*a, flush=True)

# ---------- 1. French parse, independent method (read_csv on located row ranges)
def fr(path, marker):
    L = open(path, encoding='latin-1').read().splitlines()
    i = 0 if marker is None else [n for n, l in enumerate(L) if l.strip() == marker][0]
    while not L[i].startswith(','): i += 1
    j = i + 1
    while j < len(L) and L[j].split(',')[0].strip().isdigit(): j += 1
    df = pd.read_csv(path, skiprows=i, nrows=j - i - 1, encoding='latin-1', skipinitialspace=True)
    df.columns = ['d'] + [c.strip() for c in df.columns[1:]]
    df.index = pd.to_datetime(df.pop('d').astype(str).str.strip(), format='%Y%m%d')
    codes = int(df.isin([-99.99, -999.0]).sum().sum())
    assert df.index.is_monotonic_increasing and df.index.is_unique
    return df.where(~df.isin([-99.99, -999.0])) / 100, codes, len(df)
ff, c0, n0 = fr(f'{X}/F-F_Research_Data_Factors_daily.csv', None)
bm, c1, n1 = fr(f'{X}/6_Portfolios_2x3_Daily.csv', 'Average Value Weighted Returns -- Daily')
op, c2, n2 = fr(f'{X}/6_Portfolios_ME_OP_2x3_daily.csv', 'Average Value Weighted Returns -- Monthly')
dx, c3, n3 = fr(f'{X}/Developed_ex_US_6_Portfolios_ME_BE-ME_Daily.csv', 'Average Value Weighted Returns -- Daily')
OUT['french'] = dict(missing_codes=[c0, c1, c2, c3], rows=[n0, n1, n2, n3], ends=[str(x.index[-1].date()) for x in (ff, bm, op, dx)],
    op_is_daily=bool((op.index.to_series().diff().dt.days.median()) == 1),
    max_abs_daily=dict(mkt=float((ff['Mkt-RF']).abs().max()), us_sv=float(bm['SMALL HiBM'].abs().max()), qual=float(op['BIG HiOP'].abs().max()), dx_sv=float(dx['SMALL HiBM'].abs().max())),
    rf_ann_mean_pct=float(ff.RF.mean() * 252 * 100))
cal = ff.index
A = pd.read_pickle(f'{D}/data/A.pkl'); B = pd.read_pickle(f'{D}/data/B.pkl')
cmp = {}
for nm, mine, theirs in [('US_SV', bm['SMALL HiBM'], A['AVUV~US_SV']), ('QUAL', op['BIG HiOP'], A['QUAL~US_BigHiOP']),
                         ('mkt', ff['Mkt-RF'] + ff['RF'], B['US_mkt']), ('cash', ff['RF'], A['TAIL~cash'])]:
    j = pd.concat([mine, theirs], axis=1, sort=True).dropna(); cmp[nm] = float((j.iloc[:, 0] - j.iloc[:, 1]).abs().max())
# dev ex-US: compound onto US calendar my way
dl = (1 + dx['SMALL HiBM']).cumprod(); grp = np.searchsorted(cal.values, dl.index.values)  # non-US day -> next US day
lvl = pd.Series(dl.values, index=cal[np.minimum(grp, len(cal) - 1)]).groupby(level=0).last().reindex(cal).ffill()
mydx = lvl.pct_change()
j = pd.concat([mydx, A['AVDV+AVEM~DevxUS_SV']], axis=1, sort=True).dropna(); cmp['DevxUS_SV'] = float((j.iloc[:, 0] - j.iloc[:, 1]).iloc[1:].abs().max())
OUT['sleeve_max_abs_diff_vs_author'] = cmp
nanrows = A[(A == 0).sum(axis=1) >= 1]; OUT['A_rows_with_exact_zero'] = {c: int((A[c] == 0).sum()) for c in A.columns}
# US trading days missing in dev ex-US file (ffill->0)
OUT['devxus_us_days_without_obs'] = int((~cal[(cal >= dx.index[0])].isin(dx.index)).sum())

# ---------- 2. gold
g = json.load(open('/home/user/uranium-dashboard/barbell-lab/research/barbell_timer/fixtures/fmp_gcusd_light.json'))['rows']
gc = pd.Series({pd.Timestamp(r['date']): r['price'] for r in g}).sort_index()
gld = pd.read_csv(f'{D}/raw/GLD.csv', skiprows=3, header=None, index_col=0, parse_dates=True)[1].astype(float)
gcr = gc.pct_change(); pre = gcr[gcr.index < '2004-11-18'].dropna()
tdm = pre.groupby(pre.index.to_period('M')).cumcount(); tdm_rev = pre.groupby(pre.index.to_period('M')).cumcount(ascending=False)
tom = (tdm < 4) | (tdm_rev < 1)
OUT['gold_pre2004'] = dict(n=len(pre), days_gt5pct=int((pre.abs() > .05).sum()), ann_vol=float(pre.std() * np.sqrt(252)),
    mean_bps_tom=float(pre[tom].mean() * 1e4), mean_bps_other=float(pre[~tom].mean() * 1e4),
    calendar_cagr=float((gc.loc[:'2004-11-17'].iloc[-1] / gc.iloc[0]) ** (365.25 / (gc.loc[:'2004-11-17'].index[-1] - gc.index[0]).days) - 1))
jb = B['gold']; mygold = gc.reindex(cal, method='ffill').pct_change(); m = cal > pd.Timestamp('2004-11-18')
mygold[m] = gld.reindex(cal, method='ffill').pct_change()[m]
jj = pd.concat([mygold, jb], axis=1, sort=True).dropna(); OUT['gold_max_abs_diff_vs_author'] = float((jj.iloc[:, 0] - jj.iloc[:, 1]).abs().max())
OUT['gold_splice_days'] = {str(d.date()): float(jb.loc[d]) for d in jb.loc['2004-11-16':'2004-11-22'].index}

# ---------- 3. bond: exact par-bond repricing vs author's duration approx
y = pd.to_numeric(pd.read_csv(f'{D}/raw/DGS10.csv', index_col=0).iloc[:, 0], errors='coerce'); y.index = pd.to_datetime(y.index)
y = (y.dropna() / 100).reindex(cal, method='ffill'); dt = pd.Series(cal, index=cal).diff().dt.days
def pv(c, yy, T):  # price per 1 of a bond paying c semiannual, maturity T yrs, yield yy
    n = int(np.ceil(T * 2 - 1e-9)); ts = T - 0.5 * np.arange(n); df = (1 + yy / 2) ** (-2 * ts)
    return (c / 2 * df).sum() + df.min()
yv = y.values; dtv = dt.values; br = np.full(len(cal), np.nan)
for i in range(1, len(cal)):
    if np.isfinite(yv[i - 1]) and np.isfinite(yv[i]): br[i] = pv(yv[i - 1], yv[i], 10 - dtv[i] / 365) * (1 + 0) + 0 - 1 + 0  # clean price change
    # coupon accrual added below
br = pd.Series(br, index=cal)  # dirty-price repricing already contains accrual (fixed: no extra carry)
jb = pd.concat([br, B['UST10_TR']], axis=1, sort=True).dropna()
ann = (1 + jb).groupby(jb.index.year).prod() - 1
OUT['bond'] = dict(corr=float(jb.corr().iloc[0, 1]), cagr_mine=float((1 + jb.iloc[:, 0]).prod() ** (252 / len(jb)) - 1),
                   cagr_author=float((1 + jb.iloc[:, 1]).prod() ** (252 / len(jb)) - 1),
                   yrs={yy: [round(ann.loc[yy].iloc[0] * 100, 2), round(ann.loc[yy].iloc[1] * 100, 2)] for yy in (1980, 1981, 1994, 2008, 2022)})

# ---------- 4. own simulator (scalar loop, separate pending-date logic)
def sim(R, me, w, k, fam, cost):
    T, N = R.shape; h = w.copy(); fill_at = -1; trig = []; Hs = np.empty((T, N)); Hs[0] = h
    for t in range(1, T):
        h = h * (1 + R[t])
        if t == fill_at:
            V = h.sum(); h = w * (V - cost * np.abs(w * V - h).sum()); fill_at = -1
        if fill_at < 0:
            V = h.sum()
            fire = me[t] if fam == 'M' else bool((np.abs(h / V / w - 1) > .2).any())
            if fire:
                trig.append(t)
                if k == 0: h = w * (V - cost * np.abs(w * V - h).sum())
                else: fill_at = t + k
        Hs[t] = h
    return np.log(h.sum()), trig, Hs
def mef(ix):
    mo = ix.to_period('M'); return np.r_[mo[1:] != mo[:-1], True]
def holm(ps):
    o = np.argsort(ps); n = len(ps); out = np.empty(n); run = 0
    for r, i in enumerate(o): run = max(run, min(1, (n - r) * ps[i])); out[i] = run
    return out
rng0 = np.random.default_rng(99)
def ev_d(R, Hs, ts, w, k, cost, H=11):
    res = []; contrib = []
    for t in ts:
        vals = {}; paths = {}
        for kk in (1, k):
            h = Hs[t] / Hs[t].sum(); W = []
            for j in range(1, H + 1):
                W.append(h / h.sum()); h = h * (1 + R[t + j])
                if j == kk: V = h.sum(); h = w * (V - cost * np.abs(w * V - h).sum())
            vals[kk] = np.log(h.sum()); paths[kk] = np.array(W)
        res.append(vals[k] - vals[1])
        contrib.append(((paths[k] - paths[1]) * R[t + 1:t + H + 1]).sum(0))  # approx sleeve attribution
    return np.array(res), np.array(contrib)
cells = {}
UN = {'A': (A, np.array([.235, .235, .153, .141, .177, .059])), 'B': (B, np.array([.4, .4, .2]))}
author = json.load(open(f'{D}/results.json'))
atab = {(t['universe'], t['trigger'], t['segment'], t['k']): t for t in author['table']}
for U, (R0, w) in UN.items():
    s, e = R0.index[0], R0.index[-1]; mid = s + (e - s) / 2
    segs = {'full': (s, e), 'H1': (s, mid), 'H2': (mid + pd.Timedelta(days=1), e), 'pre2013': (s, pd.Timestamp('2012-12-31'))}
    for fam in ('M', 'D'):
        for sg, (a, b) in segs.items():
            Rs = R0[(R0.index >= a) & (R0.index <= b)]; R = Rs.values; n = len(R); me = mef(Rs.index)
            lv = {}; 
            for k in (1, 3, 4, 5): lv[k], tr, Hs_ = sim(R, me, w, k, fam, 5e-4); 
            l1, tr1, Hs = sim(R, me, w, 1, fam, 5e-4)
            cg = {k: np.expm1(lv[k] * 252 / (n - 1)) for k in lv}
            ts = [t for t in tr1 if t + 11 <= n - 1]
            ps = []; evm = {}
            for k in (3, 4, 5):
                d, con = ev_d(R, Hs, ts, w, k, 5e-4)
                fl = (np.random.default_rng(20261116).choice([-1., 1.], size=(20000, len(d))) * d).mean(1)
                ps.append((1 + (fl >= d.mean() - 1e-15).sum()) / 20001); evm[k] = d.mean() * 1e4
                if k == 4: c4 = con.mean(0) * 1e4; d4 = d
            hp = holm(np.array(ps))
            key = f'{U}|{fam}|{sg}'
            cells[key] = dict(n=len(ts), cagr_diff={k: round((cg[k] - cg[1]) * 1e4, 2) for k in (3, 4, 5)},
                              ev_mean={k: round(evm[k], 3) for k in (3, 4, 5)}, p1s=[round(p, 4) for p in ps], holm=[round(p, 4) for p in hp],
                              k4_sleeve_attr_bps=[round(x, 3) for x in c4],
                              author_k4=dict(cd=round(atab[(U, fam, sg, 4)]['cagr_diff_bps'], 2), ev=round(atab[(U, fam, sg, 4)]['event_mean_bps'], 3),
                                             n=atab[(U, fam, sg, 4)]['n_events'], holm=round(atab[(U, fam, sg, 4)]['holm_primary'], 4)))
            P(key, cells[key])
OUT['cells'] = cells

# ---------- 5. own vectorized T-M moving-block bootstrap (circular=False, 252-day blocks), B and A full, k=1 vs 4
def tm_boot(R0, w, NB=2000, k=4, cost=5e-4, seed=1):
    X = R0.values[1:]; ME = mef(R0.index)[1:]; T = len(X); rng = np.random.default_rng(seed)
    st = rng.integers(0, T - 252 + 1, size=(NB, int(np.ceil(T / 252))))
    idx = (st[:, :, None] + np.arange(252)).reshape(NB, -1)[:, :T]
    Rb = X[idx]; Mb = ME[idx]; res = {}
    for kk in (1, k):
        h = np.tile(w, (NB, 1)); cnt = np.full(NB, -1)
        for t in range(T):
            h *= 1 + Rb[:, t]
            cnt[cnt > 0] -= 1; due = cnt == 0
            if due.any():
                V = h[due].sum(1); h[due] = w * (V - cost * np.abs(w * V[:, None] - h[due]).sum(1))[:, None]; cnt[due] = -1
            f = Mb[:, t] & (cnt < 0); cnt[f] = kk
        res[kk] = np.expm1(np.log(h.sum(1)) * 252 / T)
    d = (res[k] - res[1]) * 1e4
    return [round(float(np.percentile(d, 2.5)), 1), round(float(d.mean()), 1), round(float(np.percentile(d, 97.5)), 1)]
OUT['boot_TM_k4_mine_[lo,mean,hi]'] = {}
for U, (R0, w) in UN.items():
    s, e = R0.index[0], R0.index[-1]; mid = s + (e - s) / 2
    for sg, (a, b) in {'full': (s, e), 'H1': (s, mid), 'pre2013': (s, pd.Timestamp('2012-12-31'))}.items():
        Rs = R0[(R0.index >= a) & (R0.index <= b)]
        OUT['boot_TM_k4_mine_[lo,mean,hi]'][f'{U}|{sg}'] = tm_boot(Rs, w)
        P(U, sg, OUT['boot_TM_k4_mine_[lo,mean,hi]'][f'{U}|{sg}'])

# ---------- 6. gold-roll sensitivity: B T-M H1/pre2013 with gold excluded (50/50 eq/bond) and A with gold->cash
for nm, R0, w in [('B_no_gold_50_50', B[['US_mkt', 'UST10_TR']], np.array([.5, .5])),
                  ('A_gold_as_cash', A.assign(**{'PHYS~gold': A['TAIL~cash']}), UN['A'][1])]:
    s, e = R0.index[0], R0.index[-1]; mid = s + (e - s) / 2
    for sg, (a, b) in {'full': (s, e), 'H1': (s, mid), 'pre2013': (s, pd.Timestamp('2012-12-31'))}.items():
        Rs = R0[(R0.index >= a) & (R0.index <= b)]; R = Rs.values; n = len(R); me = mef(Rs.index)
        l1, tr1, Hs = sim(R, me, w, 1, 'M', 5e-4); l4, _, _ = sim(R, me, w, 4, 'M', 5e-4)
        ts = [t for t in tr1 if t + 11 <= n - 1]; d, _ = ev_d(R, Hs, ts, w, 4, 5e-4)
        fl = (np.random.default_rng(20261116).choice([-1., 1.], size=(20000, len(d))) * d).mean(1)
        OUT[f'sens_{nm}|M|{sg}'] = dict(cd_k4=round((np.expm1(l4 * 252 / (n - 1)) - np.expm1(l1 * 252 / (n - 1))) * 1e4, 2),
                                        ev4=round(d.mean() * 1e4, 3), p1s=round((1 + (fl >= d.mean()).sum()) / 20001, 4))
        P(nm, sg, OUT[f'sens_{nm}|M|{sg}'])
json.dump(OUT, open(f'{D}/check1_out.json', 'w'), indent=1, default=str)
P(json.dumps({k: v for k, v in OUT.items() if k != 'cells'}, indent=1, default=str))
