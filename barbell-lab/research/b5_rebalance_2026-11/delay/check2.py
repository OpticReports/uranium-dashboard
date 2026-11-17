"""Counter-agent #2: independent re-derivation of k=1 vs k=4 (and k=3,5) for Universe B (rebuilt from raw)
and Universe A (author's matrix, after column verification), with an independent engine.
Run: python3 -I check2.py <studydir>"""
import sys, json, numpy as np, pandas as pd
D = sys.argv[1]; RAW = D + '/raw'; X = RAW + '/x'
FIX = '/home/user/uranium-dashboard/barbell-lab/research/barbell_timer/fixtures/fmp_gcusd_light.json'
SEED = 20261116; out = {}

# ---------- my own French parser: section by title, 8-digit dates only, codes -> NaN, % -> decimal
def fr(path, title=None, col=None):
    L = open(path, encoding='latin-1').read().splitlines(); i = 0
    if title: i = next(j for j, l in enumerate(L) if l.strip().startswith(title))
    while not L[i].startswith(','): i += 1
    cols = [c.strip() for c in L[i].split(',')[1:]]; recs = {}
    for l in L[i + 1:]:
        p = [s.strip() for s in l.split(',')]
        if not (p[0].isdigit() and len(p[0]) == 8): break
        recs[p[0]] = [float(v) for v in p[1:]]
    df = pd.DataFrame.from_dict(recs, orient='index', columns=cols); df.index = pd.to_datetime(df.index, format='%Y%m%d')
    bad = df.isin([-99.99, -999.0]).sum().sum()
    df = df.mask(df.isin([-99.99, -999.0])) / 100.0
    return df, int(bad)
ff, b0 = fr(X + '/F-F_Research_Data_Factors_daily.csv')
bm, b1 = fr(X + '/6_Portfolios_2x3_Daily.csv', 'Average Value Weighted Returns -- Daily')
op, b2 = fr(X + '/6_Portfolios_ME_OP_2x3_daily.csv', 'Average Value Weighted Returns')
cal = ff.index; rf = ff['RF']; mkt = ff['Mkt-RF'] + ff['RF']
out['french'] = dict(codes_found=[b0, b1, b2], rows=[len(ff), len(bm), len(op)], end=str(cal[-1].date()),
                     op_daily_rows_spacing_days=float(pd.Series(op.index).diff().dt.days.median()),
                     mkt_max_abs=float(mkt.abs().max()), rf_mean_ann=float(rf.mean() * 252))

def lvl2r(lv):  # price level -> simple returns on French calendar
    lv = lv.dropna().sort_index(); u = lv.reindex(lv.index.union(cal)).ffill().reindex(cal)
    r = u / u.shift(1) - 1; r[cal <= lv.index[0]] = np.nan; return r
g = json.load(open(FIX))['rows']; gc = pd.Series({pd.Timestamp(r['date']): float(r['price']) for r in g}).sort_index()
gld = pd.read_csv(RAW + '/GLD.csv', skiprows=3, header=None, index_col=0, parse_dates=True)[1].astype(float)
gcr, gldr = lvl2r(gc), lvl2r(gld)
gold = gcr.where(cal <= pd.Timestamp('2004-11-18'), gldr)   # GLD returns from 2004-11-19 (its first return)
gold_gc_only = gcr.copy()                                    # futures fixture throughout (to 2026-08-12)
# bond: full reprice of a 10y par bond (semiannual) at the new yield + accrued carry (convexity included; author has none)
y = pd.to_numeric(pd.read_csv(RAW + '/DGS10.csv', index_col=0, parse_dates=True).iloc[:, 0], errors='coerce').dropna() / 100
yc = y.reindex(y.index.union(cal)).ffill().reindex(cal); y0 = yc.shift(1)
dt = pd.Series(cal, index=cal).diff().dt.days
price = (y0 / 2) * (1 - (1 + yc / 2) ** -20) / (yc / 2) + (1 + yc / 2) ** -20
bond = price - 1 + y0 * dt / 365.0
A = pd.read_pickle(D + '/data/A.pkl'); Bauth = pd.read_pickle(D + '/data/B.pkl')

# ---------- independent engine (plain loop, one k)
def sim(R, me, w, k, fam, c=5e-4, record=False):
    T, N = R.shape; h = w.copy(); pend = -1; trigs = []; H = np.empty((T, N)); H[0] = h; logV = 0.0
    tot_cost = 0.0
    for t in range(1, T):
        h = h * (1 + R[t])
        if pend == t:
            V = h.sum(); cost = c * np.abs(w * V - h).sum(); h = w * (V - cost); pend = -1; tot_cost += cost / V
        if pend < 0:
            V = h.sum(); dev = np.abs(h / V / w - 1)
            fire = me[t] if fam == 'M' else ((dev > .2).any() and (fam == 'D' or me[t]))
            if fire:
                trigs.append(t)
                if k == 0:
                    cost = c * np.abs(w * V - h).sum(); h = w * (V - cost)
                else: pend = t + k
        H[t] = h
    V = h.sum(); cagr = V ** (252 / (T - 1)) - 1
    return (cagr, trigs, H) if record else cagr

def ev_diff(R, H, ts, w, ks, c=5e-4, hz=11):
    res = {k: [] for k in ks}
    for t in ts:
        if t + hz > len(R) - 1: continue
        for k in ks:
            h = H[t] / H[t].sum()
            for j in range(1, hz + 1):
                h = h * (1 + R[t + j])
                if j == k: V = h.sum(); h = w * (V - c * np.abs(w * V - h).sum())
            res[k].append(np.log(h.sum()))
    return {k: np.array(v) for k, v in res.items()}

def signflip(d, n=100_000):
    rng = np.random.default_rng(SEED); s = rng.choice([-1., 1.], size=(n, len(d)))
    return (1 + ((s * d).mean(1) >= d.mean() - 1e-15).sum()) / (1 + n)

def holm(ps):
    o = np.argsort(ps); adj = np.empty(len(ps)); m = 0
    for r, i in enumerate(o): m = max(m, min(1, (len(ps) - r) * ps[i])); adj[i] = m
    return adj

def boot(R, me, w, fam, k, nb=2000, bl=252):
    """vectorized MBB over resamples (my own), CAGR(k)-CAGR(1) bps."""
    X = R[1:]; M = me[1:]; T = len(X); rng = np.random.default_rng(SEED + 99)
    nbk = -(-T // bl); st = rng.integers(0, T - bl + 1, size=(nb, nbk))
    idx = (st[:, :, None] + np.arange(bl)).reshape(nb, -1)[:, :T]
    res = {}
    for kk in (1, k):
        h = np.tile(w, (nb, 1)); pend = np.full(nb, -1)
        for t in range(T):
            h = h * (1 + X[idx[:, t]]); due = pend == t
            if due.any():
                V = h[due].sum(1, keepdims=True); cst = 5e-4 * np.abs(w * V - h[due]).sum(1, keepdims=True)
                h[due] = w * (V - cst); pend[due] = -1
            V = h.sum(1, keepdims=True); br = (np.abs(h / V / w - 1) > .2).any(1); mt = M[idx[:, t]]
            fire = mt if fam == 'M' else (br if fam == 'D' else br & mt)
            fire = fire & (pend < 0); pend[fire] = t + kk
        res[kk] = h.sum(1) ** (252 / T) - 1
    d = (res[k] - res[1]) * 1e4
    return [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]

def segs(idx):
    s, e = idx[0], idx[-1]; m = s + (e - s) / 2
    return {'full': (s, e), 'H1': (s, m), 'H2': (m + pd.Timedelta(days=1), e), 'pre2013': (s, pd.Timestamp('2012-12-31'))}

def cellrun(df, w, name, fams=('M', 'D'), do_boot=()):
    w = np.asarray(w, float); r = {}
    for fam in fams:
        for sg, (a, b) in segs(df.index).items():
            S = df[(df.index >= a) & (df.index <= b)]; R = S.values
            per = S.index.to_period('M'); me = np.r_[per[:-1] != per[1:], True]
            c1, ts, H1 = sim(R, me, w, 1, fam, record=True)
            cg = {k: sim(R, me, w, k, fam) for k in (3, 4, 5)}
            ed = ev_diff(R, H1, ts, w, (1, 3, 4, 5)); dd = {k: ed[k] - ed[1] for k in (3, 4, 5)}
            ps = [signflip(dd[k]) for k in (3, 4, 5)]; hp = holm(ps)
            c10 = {k: (sim(R, me, w, k, fam, c=1e-3) - sim(R, me, w, 1, fam, c=1e-3)) * 1e4 for k in (4,)}
            r[f'{fam}|{sg}'] = dict(start=str(S.index[0].date()), end=str(S.index[-1].date()), n_ev=len(dd[4]),
                cagr_k1=c1, diff_bps={k: round((cg[k] - c1) * 1e4, 2) for k in (3, 4, 5)},
                ev_mean_bps={k: round(dd[k].mean() * 1e4, 3) for k in (3, 4, 5)},
                p1s={k: round(p, 5) for k, p in zip((3, 4, 5), ps)}, holm={k: round(p, 5) for k, p in zip((3, 4, 5), hp)},
                diff_k4_at_10bps=round(c10[4], 2))
            if (fam, sg) in do_boot: r[f'{fam}|{sg}']['boot_k4_ci'] = boot(R, me, w, fam, 4)
            print(name, fam, sg, r[f'{fam}|{sg}'], flush=True)
    return r

# ---------- Universe B rebuilt independently
B = pd.DataFrame({'US_mkt': mkt, 'UST10_TR': bond, 'gold': gold}).dropna()
cmp = pd.concat([B, Bauth], axis=1, join='inner')
out['B_vs_author'] = dict(start_mine=str(B.index[0].date()), start_auth=str(Bauth.index[0].date()), n=len(cmp),
    corr=[float(np.corrcoef(cmp.iloc[:, i], cmp.iloc[:, i + 3])[0, 1]) for i in range(3)],
    maxabs=[float((cmp.iloc[:, i] - cmp.iloc[:, i + 3]).abs().max()) for i in range(3)],
    bond_cagr_mine_auth=[float((1 + cmp.iloc[:, 1]).prod() ** (252 / len(cmp)) - 1), float((1 + cmp.iloc[:, 4]).prod() ** (252 / len(cmp)) - 1)])
print(out['B_vs_author'], flush=True)
# A columns verification vs raw
ca = pd.concat([A['AVUV~US_SV'], bm['SMALL HiBM'], A['QUAL~US_BigHiOP'], op['BIG HiOP'], A['TAIL~cash'], rf], axis=1, join='inner')
out['A_cols_maxabs_vs_raw'] = [float((ca.iloc[:, 2 * i] - ca.iloc[:, 2 * i + 1].fillna(0)).abs().max()) for i in range(3)]
# look-ahead probe: shift returns so the fill would see t+k; a correct engine must be invariant to future-only perturbation
R0 = B.values[:3000]; per = B.index[:3000].to_period('M'); me0 = np.r_[per[:-1] != per[1:], True]
_, ts0, _ = sim(R0, me0, np.array([.4, .4, .2]), 4, 'D', record=True)
R1 = R0.copy(); R1[ts0[0] + 1:] *= 3.0
_, ts1, _ = sim(R1, me0, np.array([.4, .4, .2]), 4, 'D', record=True)
out['lookahead_probe_first_trigger_same'] = bool(ts0[0] == ts1[0])

out['B'] = cellrun(B, [.4, .4, .2], 'B', do_boot={('M', 'full'), ('M', 'H1'), ('M', 'H2')})
out['A'] = cellrun(A, [.235, .235, .153, .141, .177, .059], 'A', fams=('M',), do_boot={('M', 'full'), ('M', 'H1'), ('M', 'H2')})
# deviation probes
Bgc = pd.DataFrame({'US_mkt': mkt, 'UST10_TR': bond, 'gold': gold_gc_only}).dropna()
out['B_gold_futures_throughout'] = cellrun(Bgc, [.4, .4, .2], 'B_gc', fams=('M',))
B5050 = pd.DataFrame({'US_mkt': mkt, 'UST10_TR': bond}).dropna()
B5050 = B5050[B5050.index >= B.index[0]]
out['B_nogold_5050'] = cellrun(B5050, [.5, .5], 'B_5050', fams=('M',))
Agc = A.copy(); Agc['PHYS~gold'] = gold_gc_only.reindex(A.index); Agc = Agc.dropna()
out['A_gold_futures_throughout'] = cellrun(Agc, [.235, .235, .153, .141, .177, .059], 'A_gc', fams=('M',))
Anok = A.drop(columns=['KMLM~TSMOM']).copy(); Anok['TAIL~cash'] = A['TAIL~cash']
out['A_kmlm_as_cash'] = cellrun(A.assign(**{'KMLM~TSMOM': A['TAIL~cash']}), [.235, .235, .153, .141, .177, .059], 'A_kcash', fams=('M',))
json.dump(out, open(D + '/check2_out.json', 'w'), indent=1, default=float)
