"""Improvement candidates, tested the house way (real era + crash replays + placebo).

C1  short-vol termination: when VIX > VIX3M at the decision close (term structure in
    backwardation), the KMLM risk-on leg's SVIX and HARV's ZVOL go to PULS instead.
C2  HG bear-market dip gate: the HG dip-buy branch (TQQQ RSI<30 -> leveraged dip
    basket) goes to BIL when SPY < its 200d MA at the decision close.
Each: effect on the 2023-26 real era (real tickers), on the COVID replay (4 KMLM
proxies), on the HG dotcom/GFC reconstructions (C2), and a placebo: the same
number of block-days drawn at random (200 draws) -> percentile of the real gate.
"""
import os, json, math, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from replay import *
from hist_replay import build_prices
trees = json.load(open(f'{SP}/trees.json'))
vix = yh('^VIX'); v3 = yh('^VIX3M'); spy = yh('SPY')
BACK = {d for d in vix if d in v3 and vix[d] > v3[d]}
sds = sorted(spy); MA200 = {sds[i]: sum(spy[sds[i-199:i+1]][0] if False else spy[x] for x in sds[i-199:i+1])/200 for i in range(199, len(sds))}
BEAR = {d for d in MA200 if spy[d] < MA200[d]}
tq = yh('TQQQ'); tds = sorted(tq); TQMA = {tds[i]: sum(tq[x] for x in tds[i-199:i+1])/200 for i in range(199, len(tds))}
BEAR_TQ = {d for d in TQMA if tq[d] < TQMA[d]}
class _All(set):
    def __contains__(self, d): return True
PULS2BIL = _All()

def run_gated(sim, tree, days, eng, block_days, w0=None, mode='C1'):
    """C1/C2 applied post-decision: block_days is the set of decision closes on which the gate is ON."""
    rets, hold = {}, {}
    subs = sim._find_filter_groups(tree); sim.sub = {sid: [(days[0], 1.0)] for sid in subs}
    for i in range(1, len(days)):
        d0, d1 = days[i-1], days[i]
        for sid, st in subs.items():
            sw = sim.weights(st, d0); tot = sum(sw.values()); sr = 0.0
            for t, x in sw.items():
                p0, p1 = sim.p[t].get(d0), sim.p[t].get(d1)
                if p0 and p1: sr += (x/tot if tot else 0)*(p1/p0-1)
            sim.sub[sid].append((d1, sim.sub[sid][-1][1]*(1+sr)))
        w = sim.weights(tree, d0) if not (w0 and i == 1) else dict(w0)
        if d0 in block_days:
            w = dict(w)
            if mode == 'C1' and eng == 'KMLM' and 'SVIX' in w: w['PULS'] = w.get('PULS', 0) + w.pop('SVIX')
            if mode == 'C1' and eng == 'HARV' and 'ZVOL' in w: w['PULS'] = w.get('PULS', 0) + w.pop('ZVOL')
            if mode == 'C2' and eng == 'HG' and any(t in w for t in ('TQQQ', 'UPRO', 'UDOW', 'SSO', 'TNA')):
                w = {'BIL': 1.0}          # C2: trend-long branch blocked in a bear (dip-buys untouched)
            if mode == 'C3' and 'PULS' in w:
                w['BIL'] = w.get('BIL', 0) + w.pop('PULS')   # C3: cash leg PULS -> BIL
        tot = sum(w.values()); r = 0.0
        for t, x in w.items():
            p0, p1 = sim.p[t].get(d0), sim.p[t].get(d1)
            if p0 and p1: r += (x/tot if tot else 0)*(p1/p0-1)
        rets[d1] = r; hold[d1] = {t: round(x/tot, 4) for t, x in w.items() if tot and x/tot > 1e-6}
    return rets, hold

def stats(rc, a=None, b=None):
    ds = [d for d in sorted(rc) if (a is None or d >= a) and (b is None or d <= b)]
    cum = math.prod(1+rc[d] for d in ds); v = 1; peak = 1; mdd = 0
    for d in ds: v *= 1+rc[d]; peak = max(peak, v); mdd = max(mdd, 1-v/peak)
    yrs = len(ds)/252
    return {'cum': round(cum, 3), 'cagr': round(cum**(1/yrs)-1, 4) if yrs > 0.5 else None, 'maxdd': round(mdd, 4), 'n': len(ds)}

def test(eng, P, a, b, gate_set, windows, label, placebo=True, seed=1, mode='C1'):
    sim = SimW(P, rsi_method='wilder'); tk = tree_tickers(trees[eng]); days = common_days(P, tk, a, b)
    base_r, base_h = run_tree(sim, trees[eng], days); base = composer_equiv(base_r, base_h, days, eng)
    gated_r, gated_h = run_gated(sim, trees[eng], days, eng, gate_set, mode=mode); gated = composer_equiv(gated_r, gated_h, days, eng)
    n_on = sum(1 for d in days if d in gate_set)
    res = {'label': label, 'gate_days': n_on, 'of': len(days), 'windows': {}}
    for wn, (x, y) in windows.items():
        res['windows'][wn] = {'base': stats(base, x, y), 'gated': stats(gated, x, y)}
    if placebo:
        rng = random.Random(seed); deltas = []
        real_delta = stats(gated)['cum']/stats(base)['cum']-1
        for k in range(60):
            fake = set(rng.sample(days, n_on)); fr, fh = run_gated(sim, trees[eng], days, eng, fake, mode=mode); fc = composer_equiv(fr, fh, days, eng)
            deltas.append(stats(fc)['cum']/stats(base)['cum']-1)
        deltas.sort(); pct = sum(x < real_delta for x in deltas)/len(deltas)
        res['placebo'] = {'real_delta_cum': round(real_delta, 4), 'placebo_p50': round(deltas[30], 4), 'placebo_p05': round(deltas[3], 4), 'placebo_p95': round(deltas[57], 4), 'real_percentile': round(pct, 3)}
    print(f"\n[{label}] gate on {n_on}/{len(days)} days")
    for wn, v in res['windows'].items(): print(f"   {wn:28s} base cum {v['base']['cum']:7.3f} dd {v['base']['maxdd']:.1%} | gated cum {v['gated']['cum']:7.3f} dd {v['gated']['maxdd']:.1%}")
    if placebo: print('   placebo:', res['placebo'])
    return res

import os
ONLY = os.environ.get('ONLY')
out = json.load(open(f'{SP}/improve.json')) if ONLY and os.path.exists(f'{SP}/improve.json') else {}
# ---- C1 on the real era (real tickers) ----
P = load_prices(real_synth=True)
for eng in (() if ONLY == 'C3' else ('KMLM', 'HARV')):
    out[f'C1_{eng}_real'] = test(eng, P, '2023-04-18', '2026-10-06', BACK, {'real era 2023-04..2026-10': (None, None), 'Aug-2024 spike': ('2024-07-15', '2024-09-15'), 'Apr-2025': ('2025-03-20', '2025-05-15')}, f'C1 backwardation block, {eng}, real era')
# ---- C1 on COVID (4 proxies for KMLM; HARV once) ----
for proxy in (() if ONLY == 'C3' else ('AQMIX', 'FMF', 'DBMF', 'DBC')):
    Pc = load_prices(kmlm_proxy=proxy)
    out[f'C1_KMLM_covid_{proxy}'] = test('KMLM', Pc, '2019-09-03', '2021-03-31', BACK, {'crash 02-19..03-23': ('2020-02-20', '2020-03-23'), '12m from 02-19': ('2020-02-20', '2021-02-19')}, f'C1, KMLM COVID ({proxy})', placebo=(proxy == 'AQMIX'))
Pc = load_prices(kmlm_proxy='DBMF')
if ONLY != 'C3': out['C1_HARV_covid'] = test('HARV', Pc, '2019-09-03', '2021-03-31', BACK, {'crash 02-19..03-23': ('2020-02-20', '2020-03-23'), '12m from 02-19': ('2020-02-20', '2021-02-19')}, 'C1, HARV COVID')
# ---- C2 on HG: trend-long branch blocked when SPY<200d (C2a) or TQQQ<200d (C2b) ----
Ph, _ = build_prices()
for gname, gset in (() if ONLY == 'C3' else (('C2a SPY<200d', BEAR), ('C2b TQQQ<200d', BEAR_TQ))):
    out[f'{gname}_HG_real'] = test('HG', P, '2023-04-18', '2026-10-06', gset, {'real era 2023-04..2026-10': (None, None)}, f'{gname} trend-gate, HG, real era', mode='C2')
    out[f'{gname}_HG_2015_23'] = test('HG', P, '2015-06-01', '2023-04-18', gset, {'2015-06..2023-04': (None, None), '2022 bear': ('2022-01-03', '2022-12-30'), 'COVID 12m': ('2020-02-20', '2021-02-19'), 'COVID crash': ('2020-02-20', '2020-03-23')}, f'{gname}, HG 2015-2023 (real tickers)', placebo=False, mode='C2')
    out[f'{gname}_HG_dotcom'] = test('HG', Ph, '1999-06-01', '2003-12-31', gset, {'2000-03-10..2002-10-09': ('2000-03-11', '2002-10-09'), '12m from 2000-03-10': ('2000-03-11', '2001-03-09'), 'full 1999-06..2003-12': (None, None)}, f'{gname}, HG dotcom recon', placebo=False, mode='C2')
    out[f'{gname}_HG_gfc'] = test('HG', Ph, '2007-01-03', '2010-12-31', gset, {'2007-10-09..2009-03-09': ('2007-10-10', '2009-03-09'), '12m from Lehman': ('2008-09-15', '2009-09-14'), 'full 2007-01..2010-12': (None, None)}, f'{gname}, HG GFC recon', placebo=False, mode='C2')
# ---- C3: cash leg PULS -> BIL (HARV, KMLM): real era + COVID ----
for eng in ('HARV', 'KMLM'):
    out[f'C3_{eng}_real'] = test(eng, P, '2023-04-18', '2026-10-06', PULS2BIL, {'real era 2023-04..2026-10': (None, None)}, f'C3 PULS->BIL, {eng}, real era', placebo=False, mode='C3')
    out[f'C3_{eng}_covid'] = test(eng, Pc, '2019-09-03', '2021-03-31', PULS2BIL, {'crash 02-19..03-23': ('2020-02-20', '2020-03-23'), '12m from 02-19': ('2020-02-20', '2021-02-19')}, f'C3 PULS->BIL, {eng}, COVID (DBMF)', placebo=False, mode='C3')
json.dump(out, open(f'{SP}/improve.json', 'w')); print('saved')
