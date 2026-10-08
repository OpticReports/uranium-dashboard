"""Placebos for the gate variants: random month blocks with the same share of 'off' days
(trend gates) or the same number of tight months (macro gates), 40 draws, both panels.
Also per-year returns for B0/B1/G2/G4/M4 in panel B.  Saves gate_placebo.json."""
import os, json, math, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate_study as gs
from replay import load_prices
out = {}
P = load_prices(real_synth=True); daysA, hA, pxA = gs.base_run(P, '2015-06-01', '2026-10-06')
PL = gs.build_lh_prices(); daysB, hB, pxB = gs.base_run(PL, '1990-01-02', '2026-10-06')
rng = random.Random(11)
for pan, (days, h, px, PP) in {'A': (daysA, hA, pxA, P), 'B': (daysB, hB, pxB, PL)}.items():
    spy = PP['SPY']; G, ma50, ma100, ma200 = gs.gates_trend(spy); M = gs.build_macro_allows(spy, ma50, ma100, ma200, days)
    allows = dict(G); allows.update({k: v for k, v in M.items() if not k.startswith('INV')})
    b1 = G['B1 binary SPY<200d']
    res = {}
    for name, al in allows.items():
        ds = [d for d in days if d in al]; months = sorted({d[:7] for d in ds})
        r, to, hold = gs.variant_returns(days, h, px, al); real = gs.metrics(r, days)
        if name.startswith('M'):
            tight = {m: False for m in months}
            for d in ds:
                if al[d] != b1.get(d, 1.0): tight[d[:7]] = True
            n_t = sum(tight.values())
        else:
            # trend gates: monthly mean allow; shuffle months of the allow pattern
            mean = {}
            for d in ds: mean.setdefault(d[:7], []).append(al[d])
            mean = {m: sum(v)/len(v) for m, v in mean.items()}
        draws = []
        for k in range(40):
            if name.startswith('M'):
                perm = months[:]; rng.shuffle(perm); tset = set(perm[:n_t])
                pal = {d: (0.0 if (d[:7] in tset and d in ma50 and spy[d] < ma50[d]) else b1.get(d, 1.0)) for d in ds}
            else:
                perm = months[:]; rng.shuffle(perm); mp = dict(zip(months, perm))
                pal = {d: mean[mp[d[:7]]] for d in ds}       # same monthly allow pattern, randomly re-dated
            rr, _, _ = gs.variant_returns(days, h, px, pal); draws.append(gs.metrics(rr, days))
        q = lambda key, p: sorted(x[key] for x in draws)[int(p*39)]
        res[name] = {'real': real, 'placebo': {key: [q(key, .05), q(key, .5), q(key, .95)] for key in ('cagr', 'sharpe', 'sortino', 'maxdd', 'calmar')},
                     'real_pct': {key: round(sum(1 for x in draws if x[key] < real[key])/40, 3) for key in ('cagr', 'sharpe', 'sortino', 'calmar')},
                     'real_pct_maxdd_lower': round(sum(1 for x in draws if x['maxdd'] > real['maxdd'])/40, 3)}
        print(pan, f"{name[:44]:44s} real CAGR {real['cagr']:+.1%} Sh {real['sharpe']:.2f} DD {real['maxdd']:.0%} | placebo CAGR {res[name]['placebo']['cagr'][1]:+.1%} [{res[name]['placebo']['cagr'][0]:+.1%},{res[name]['placebo']['cagr'][2]:+.1%}] Sh p50 {res[name]['placebo']['sharpe'][1]:.2f} DD p50 {res[name]['placebo']['maxdd'][1]:.0%} | real pct CAGR {res[name]['real_pct']['cagr']:.2f} Sharpe {res[name]['real_pct']['sharpe']:.2f} DD-better {res[name]['real_pct_maxdd_lower']:.2f}")
    out[pan] = res
    if pan == 'B':
        yr = {}
        for name in ('B0 as built', 'B1 binary SPY<200d', 'G2 vote 50/100/200d', 'G4 drawdown ramp 5%->15%', 'M4 oil +50% yoy -> 100d'):
            al = allows.get(name, {}); r, _, _ = gs.variant_returns(days, h, px, al); y = {}
            for d, x in r.items(): y[d[:4]] = y.get(d[:4], 1.0)*(1+x)
            yr[name] = {k: round(v-1, 4) for k, v in y.items()}
        out['by_year_B'] = yr
        print('\nby year (panel B):'); ys = sorted(yr['B0 as built'])
        for name in yr: print(f"  {name[:22]:22s}", ' '.join(f"{y[2:]}:{yr[name][y]:+.0%}" for y in ys))
json.dump(out, open(f'{gs.SP}/gate_placebo.json', 'w')); print('saved')
