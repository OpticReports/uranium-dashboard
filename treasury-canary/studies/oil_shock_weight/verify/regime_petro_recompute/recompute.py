"""Independent recompute of block regime_petro from the spec + frozen inputs (no run.py read)."""
import json, numpy as np, pandas as pd
from scipy.stats import pearsonr, spearmanr

D = '/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil/data'
OUT = '/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil/verify/regime_petro_recompute'
p = pd.read_csv(f'{D}/panel.csv', parse_dates=['date']).set_index('date')
ev = json.load(open(f'{D}/events.json'))
tic = pd.read_csv(f'{D}/tic_oil_exporters.csv', parse_dates=['date']).set_index('date')
out = {}

def P(d): return pd.Period(d, 'M')
onsets = [P(x) for x in ev['recession_onsets']]
last_resolved = P(ev['last_resolved_month_h12'])
H = 12
per = p.index.to_period('M')
p.index = per

# ---------- 1. D1-RED episodes (own construction from spec) ----------
on = (p.oil_12m_pct >= 50)
usrec = p.usrec.astype(int)
# raw runs over ALL ON months, merged when gap <= 6 OFF months
on_months = list(per[on.values])
runs = []
for m in on_months:
    if runs and (m - runs[-1][-1]).n <= 7:  # <=6 OFF months between => diff <= 7
        runs[-1].append(m)
    else:
        runs.append([m])
# Spec-literal: episode = ON months with USREC_t = 0, merged the same way
on0_months = list(per[(on & (usrec == 0)).values])
runs0 = []
for m in on0_months:
    if runs0 and (m - runs0[-1][-1]).n <= 7:
        runs0[-1].append(m)
    else:
        runs0.append([m])

def regime(m):
    y = m.year
    return 'R0' if y <= 1985 else 'R1' if y <= 2008 else 'R2' if y <= 2019 else 'R3'

claimed = set()
def outcome(first, last):
    # pending if any month unresolved
    if last > last_resolved:  # month t resolved iff t+12 <= 2025-08
        return 'PENDING', None
    for e in onsets:
        if first >= e and (first - e).n <= 3:
            return 'COINCIDENT', str(e)
    for e in onsets:
        if first < e <= last + H and e not in claimed:
            claimed.add(e)
            return 'HIT', str(e)
    return 'FALSE POSITIVE', None

rows = []
for r in runs:
    first_raw, last_raw = r[0], r[-1]
    members = [m for m in r if usrec[m] == 0]
    if members:
        first, last = members[0], members[-1]
    else:
        first, last = first_raw, last_raw  # in-recession-only; block keeps under raw first ON
    peak = float(p.loc[r, 'oil_12m_pct'].max())
    if first < P('1953-04'):
        oc, e = 'NOT SCORED', None
    elif not members:
        oc, e = outcome(first_raw, last_raw)
        oc = oc + ' (in-recession-only)'
    else:
        oc, e = outcome(first, last)
    rows.append(dict(start=str(first), raw_first=str(first_raw), raw_last=str(last_raw),
                     n_on_usrec0=len(members), peak=round(peak, 1), regime=regime(first), outcome=oc, event=e))
ep = pd.DataFrame(rows)
print(ep.to_string())
out['episodes'] = rows
out['spec_literal_runs_usrec0'] = [[str(r[0]), str(r[-1]), len(r)] for r in runs0]

# ---------- 2. supply / demand classification ----------
disruptions = {'1973-10': 'OPEC embargo', '1978-11': 'Iran', '1980-09': 'Iran-Iraq', '1990-08': 'Kuwait',
               '2002-12': 'Venezuela', '2003-03': 'Iraq', '2011-02': 'Libya', '2019-09': 'Abqaiq', '2022-02': 'Ukraine'}
dis = {P(k): v for k, v in disruptions.items()}
cls = []
for r in rows:
    s = P(r['start'])
    if s >= P('2026-01'):
        c, basis = 'unclassified', '2026 event unnamed'
    else:
        hit = [(d, v) for d, v in dis.items() if d <= s <= d + 3]
        if hit:
            c, basis = 'supply', f'{hit[0][1]} {hit[0][0]} (+{(s-hit[0][0]).n}m)'
        else:
            prior = [d for d in dis if d < s]
            c = 'demand'
            basis = f'nearest prior {max(prior)} ({(s-max(prior)).n}m earlier)' if prior else 'none'
    # IGREA cross-check: igrea_12m_chg at start vs median of trailing 120 months incl start (min 60)
    ig = p.igrea_12m_chg
    if s in ig.index and pd.notna(ig[s]):
        idx = ig.index.get_loc(s)
        w = ig.iloc[max(0, idx - 119): idx + 1].dropna()
        med = float(w.median()) if len(w) >= 60 else np.nan
        igv = float(ig[s])
        igc = ('demand-consistent' if igv > med else 'supply-consistent') if pd.notna(med) else 'n/a'
        nw = len(w)
    else:
        igv, med, igc, nw = np.nan, np.nan, 'n/a', 0
    agree = (igc.split('-')[0] == c) if c in ('supply', 'demand') and igc != 'n/a' else None
    cls.append(dict(start=r['start'], cls=c, basis=basis, igrea=igv, med=med, n=nw, igrea_cls=igc, agree=agree, outcome=r['outcome']))
cl = pd.DataFrame(cls)
print(cl.to_string())
summ = {}
for c in ['supply', 'demand', 'unclassified']:
    sub = cl[(cl.cls == c) & (~cl.outcome.str.startswith('NOT SCORED'))]
    summ[c] = dict(n=len(sub), hit=int(sub.outcome.str.startswith('HIT').sum()),
                   fp=int(sub.outcome.str.startswith('FALSE').sum()),
                   coincident=int(sub.outcome.str.startswith('COINC').sum()),
                   pending=int(sub.outcome.str.startswith('PEND').sum()), episodes=list(sub.start))
print(summ)
out['supply_demand_summary'] = summ
ag = cl[cl.agree.notna()]
out['igrea_agree'] = dict(agree=int(ag.agree.sum()), of=len(ag), disagree=list(ag[ag.agree == False].start))

# ---------- 3(iii) INDPRO / PAYEMS 12m response ----------
resp = []
for r in rows:
    s = P(r['start']); e = s + 12
    if e in p.index and pd.notna(p.indpro.get(e)):
        ip = float(p.indpro[e] / p.indpro[s] * 100 - 100); pe = float(p.payems[e] / p.payems[s] * 100 - 100)
    else:
        ip = pe = np.nan
    resp.append(dict(start=r['start'], indpro_12m=ip, payems_12m=pe))
resp = pd.DataFrame(resp).set_index('start')
print(resp.round(4))
sup_r0r1 = [r['start'] for r in cls if r['cls'] == 'supply' and regime(P(r['start'])) in ('R0', 'R1')]
sr = resp.loc[sup_r0r1]
out['resp_2021_03'] = resp.loc['2021-03'].round(4).to_dict()
out['resp_R0R1_supply'] = dict(episodes=sup_r0r1,
                               indpro=[round(sr.indpro_12m.mean(), 4), round(sr.indpro_12m.min(), 4), round(sr.indpro_12m.max(), 4), len(sr)],
                               payems=[round(sr.payems_12m.mean(), 4), round(sr.payems_12m.min(), 4), round(sr.payems_12m.max(), 4), len(sr)])
print(out['resp_R0R1_supply'])

# ---------- H4b: corr by regime with moving-block bootstrap ----------
def mbb_ci(x, y, block=12, draws=1000, seed=20260915, stat='pearson'):
    rng = np.random.default_rng(seed)
    n = len(x); nb = int(np.ceil(n / block)); starts_max = n - block
    vals = []
    for _ in range(draws):
        st = rng.integers(0, starts_max + 1, size=nb)
        idx = np.concatenate([np.arange(s, s + block) for s in st])[:n]
        xs, ys = x[idx], y[idx]
        vals.append(pearsonr(xs, ys)[0] if stat == 'pearson' else spearmanr(xs, ys)[0])
    return float(np.nanpercentile(vals, 5)), float(np.nanpercentile(vals, 95))

def mbb_ci_wrap(x, y, block=12, draws=1000, seed=20260915, stat='pearson'):
    # circular variant, for sensitivity
    rng = np.random.default_rng(seed)
    n = len(x); nb = int(np.ceil(n / block))
    vals = []
    for _ in range(draws):
        st = rng.integers(0, n, size=nb)
        idx = np.concatenate([(np.arange(s, s + block)) % n for s in st])[:n]
        vals.append(pearsonr(x[idx], y[idx])[0] if stat == 'pearson' else spearmanr(x[idx], y[idx])[0])
    return float(np.nanpercentile(vals, 5)), float(np.nanpercentile(vals, 95))

regs = {'R1': ('1986-01', '2008-12'), 'R2': ('2009-01', '2019-12'), 'R3': ('2020-01', '2026-08')}
cust = p.custody_12m_pct.replace([np.inf, -np.inf], np.nan)
h4b = {}
for name, ycol in [('usd', p.usd_12m_pct), ('custody', cust)]:
    for rg, (a, b) in regs.items():
        sub = pd.concat([p.oil_12m_pct, ycol], axis=1).loc[P(a):P(b)].dropna()
        if len(sub) < 24: continue
        x, y = sub.iloc[:, 0].values, sub.iloc[:, 1].values
        pr = pearsonr(x, y)[0]; sp = spearmanr(x, y)[0]
        ci = mbb_ci(x, y); ciw = mbb_ci_wrap(x, y); cis = mbb_ci(x, y, stat='spearman')
        h4b[f'{name}_{rg}'] = dict(n=len(sub), first=str(sub.index[0]), last=str(sub.index[-1]),
                                   pearson=round(pr, 4), ci90=[round(ci[0], 4), round(ci[1], 4)], ci90_wrap=[round(ciw[0], 4), round(ciw[1], 4)],
                                   spearman=round(sp, 4), sp_ci90=[round(cis[0], 4), round(cis[1], 4)])
        print(name, rg, h4b[f'{name}_{rg}'])
out['h4b'] = h4b
# Also recompute from levels (independent of panel's pre-computed 12m columns)
oil12 = p.wti.pct_change(12) * 100; usd12 = p.usd_broad.pct_change(12) * 100
for rg, (a, b) in regs.items():
    sub = pd.concat([oil12, usd12], axis=1).loc[P(a):P(b)].dropna()
    out['h4b'][f'usd_{rg}_fromlevels'] = round(pearsonr(sub.iloc[:, 0], sub.iloc[:, 1])[0], 4)

# ---------- named custody episodes ----------
cb = p.custody_bn.replace(0, np.nan)
out['custody_2014_16_pct'] = round(float(cb[P('2016-02')] / cb[P('2014-06')] * 100 - 100), 4)
out['custody_2022_pct'] = round(float(cb[P('2022-12')] / cb[P('2022-02')] * 100 - 100), 4)
out['oil_2014_16_pct'] = round(float(p.wti[P('2016-02')] / p.wti[P('2014-06')] * 100 - 100), 2)
out['oil_2022_pct'] = round(float(p.wti[P('2022-12')] / p.wti[P('2022-02')] * 100 - 100), 2)
tic.index = tic.index.to_period('M')
out['seg2_2014_06'] = round(float(tic.seg2_share_pct[P('2014-06')]), 4)
out['seg2_2016_02'] = round(float(tic.seg2_share_pct[P('2016-02')]), 4)
out['seg2_2014_16_pp'] = round(out['seg2_2016_02'] - out['seg2_2014_06'], 4)
out['seg2_2022_02'] = round(float(tic.seg2_share_pct[P('2022-02')]), 4)
out['seg2_2022_12'] = round(float(tic.seg2_share_pct[P('2022-12')]), 4)
print({k: v for k, v in out.items() if k.startswith(('custody', 'oil_20', 'seg2'))})

# ---------- H4a ----------
dec = tic[tic.index.month == 12]
h4a = {}
for seg, col in [('seg1', 'seg1_share_pct'), ('seg2', 'seg2_share_pct'), ('norway', 'norway_share_pct')]:
    s = dec[col].dropna()
    ds = s.diff()  # Dec-to-Dec change (consecutive available Decembers)
    # require exactly 12 months apart
    ok = [i for i in range(1, len(s)) if (s.index[i] - s.index[i - 1]).n == 12]
    obs = pd.DataFrame({'dshare': [s.iloc[i] - s.iloc[i - 1] for i in ok],
                        'oil': [p.wti[s.index[i]] / p.wti[s.index[i] - 12] * 100 - 100 for i in ok]},
                       index=[s.index[i] for i in ok])
    pr, pp = pearsonr(obs.oil, obs.dshare); sp, spp = spearmanr(obs.oil, obs.dshare)
    h4a[seg] = dict(n=len(obs), first=str(obs.index[0]), last=str(obs.index[-1]), pearson=round(pr, 4), pearson_p=round(pp, 3),
                    spearman=round(sp, 4), spearman_p=round(spp, 3))
    print(seg, h4a[seg]); print(obs.round(2).to_string())
h4a['seg2_share_2021_12'] = round(float(dec.seg2_share_pct[P('2021-12')]), 4)
h4a['seg2_share_2022_12'] = round(float(dec.seg2_share_pct[P('2022-12')]), 4)
h4a['seg2_change_2022_pp'] = round(h4a['seg2_share_2022_12'] - h4a['seg2_share_2021_12'], 4)
h4a['norway_change_2022_pp'] = round(float(dec.norway_share_pct[P('2022-12')] - dec.norway_share_pct[P('2021-12')]), 4)
out['h4a'] = h4a
print(h4a)

json.dump(out, open(f'{OUT}/recompute_numbers.json', 'w'), indent=1, default=str)
