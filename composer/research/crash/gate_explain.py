"""HG bear gate (C2): HG with/without the gate through 2000-02, 2008, 2015-26 (+ book effect)."""
import os, json, math, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from replay import *
from hist_replay import build_prices
from improve import run_gated, stats
import book_sim as bs
trees = json.load(open('trees.json'))
spy = yh('SPY'); sds = sorted(spy)
MA = {sds[i]: sum(spy[x] for x in sds[i-199:i+1])/200 for i in range(199, len(sds))}
BEAR = {d for d in MA if spy[d] < MA[d]}
def run(P, a, b, gate):
    sim = SimW(P, rsi_method='wilder'); tk = tree_tickers(trees['HG']); days = common_days(P, tk, a, b)
    r0, h0 = run_tree(sim, trees['HG'], days); r1, h1 = run_gated(sim, trees['HG'], days, 'HG', gate, mode='C2')
    return days, composer_equiv(r0, h0, days, 'HG'), composer_equiv(r1, h1, days, 'HG'), h0, h1
def curve(rc, days, start=1.0):
    out = [(days[0], start)]
    for d in days[1:]: out.append((d, out[-1][1]*(1+rc[d])))
    return out
def mdd(c):
    pk = c[0][1]; m = 0
    for _, v in c: pk = max(pk, v); m = max(m, 1-v/pk)
    return m
Ph, _ = build_prices(); P = load_prices(real_synth=True)
out = {}
for lab, PP, a, b in (('dotcom 1999-06..2003-12', Ph, '1999-06-01', '2003-12-31'), ('GFC 2007-01..2010-12', Ph, '2007-01-03', '2010-12-31'), ('real tickers 2015-06..2026-10', P, '2015-06-01', '2026-10-06')):
    days, r0, r1, h0, h1 = run(PP, a, b, BEAR)
    c0, c1 = curve(r0, days), curve(r1, days)
    ncash = sum(1 for d in days[1:] if h1[d] == {'BIL': 1.0} and h0[d] != {'BIL': 1.0})
    yrs = len(days)/252
    out[lab] = {'days': days, 'base': [v for _, v in c0], 'gated': [v for _, v in c1],
                'base_cum': c0[-1][1], 'gated_cum': c1[-1][1], 'base_cagr': c0[-1][1]**(1/yrs)-1, 'gated_cagr': c1[-1][1]**(1/yrs)-1,
                'base_mdd': mdd(c0), 'gated_mdd': mdd(c1), 'gate_days': sum(1 for d in days if d in BEAR), 'extra_cash_days': ncash, 'n': len(days)}
    print(f"{lab:32s} n={len(days)} gate on {out[lab]['gate_days']} days, HG forced to cash on {ncash} of them | base {c0[-1][1]:.2f}x ({out[lab]['base_cagr']:+.1%}/yr) DD {mdd(c0):.0%} | gated {c1[-1][1]:.2f}x ({out[lab]['gated_cagr']:+.1%}/yr) DD {mdd(c1):.0%}")
    # yearly breakdown
    yrsplit = {}
    for i, d in enumerate(days[1:], 1):
        y = d[:4]; yrsplit.setdefault(y, [1.0, 1.0]); yrsplit[y][0] *= 1+r0[d]; yrsplit[y][1] *= 1+r1[d]
    out[lab]['by_year'] = {y: (v[0]-1, v[1]-1) for y, v in yrsplit.items()}
    print('   by year:', ', '.join(f"{y} {v[0]-1:+.0%}/{v[1]-1:+.0%}" for y, v in sorted(yrsplit.items())))
    # book effect: HG gated, others as in the study (GFC/dotcom conservative: KMLM = ungated HG, sleeve recon or T-bill, HARV T-bill)
    if 'GFC' in lab or 'dotcom' in lab:
        H = json.load(open('hist_replay.json')); irx = json.load(open('yh/_IRX.json')); tb = {d: (c/100)/252 for d, c in zip(irx['dates'], irx['close']) if c is not None}
        if 'GFC' in lab:
            sl = H['runs']['SLEEVE_gfc']['rets']; start = '2007-10-09'
        else:
            sl = {d: tb.get(d, 0.0) for d in r0}; start = '2000-03-10'
        dd = [d for d in days if d >= start and d in sl][:400]
        for gname, hg in (('base', r0), ('gated HG', r1)):
            rets = {'HG': hg, 'KMLM': r0, 'SLEEVE': sl, 'HARV': {d: tb.get(d, 0.0) for d in r0}}
            path, fires, alerts = bs.simulate(rets, dd, guards=True); s = bs.summarize(path, start)
            print(f"   book ({gname}, KMLM = ungated HG): 12m {s['m12']['ret']:+.1%} ${s['m12']['value']/1e3:.0f}k  maxDD over 400d {s['maxdd']:.0%}  TUW {s['tuw_max_days']}d")
            out[lab][f'book_{gname}'] = s
    if 'real' in lab:
        # live-era book 2023-04-19..2026-10-06 with the real engines (Composer curves) and HG swapped for the gated sim
        bt = json.load(open('composer_bt.json'))
        def rr(c): ds = sorted(c); return {ds[i]: c[ds[i]]/c[ds[i-1]]-1 for i in range(1, len(ds))}
        km, sv, hv = rr(bt['KMLM_real']['curve']), rr(bt['SLEEVE_real']['curve']), rr(bt['HARV_real']['curve'])
        dd = [d for d in days if d >= '2023-04-19' and d in km]
        for gname, hg in (('base', r0), ('gated HG', r1)):
            rets = {'HG': hg, 'KMLM': km, 'SLEEVE': sv, 'HARV': hv}
            path, fires, alerts = bs.simulate(rets, dd, guards=True, start_alloc='targets'); s = bs.summarize(path, dd[0], horizons_days=(252, 504, 756))
            print(f"   live-era book 2023-04..2026-10 ({gname}): end {s['end']['ret']:+.0%}  maxDD {s['maxdd']:.0%}  (HG sim {gname})")
            out[lab][f'book_{gname}'] = s
json.dump(out, open('gate_explain.json', 'w'))
