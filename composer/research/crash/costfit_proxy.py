"""(A) Composer turnover-cost calibration for the frictionless tree simulator.
(B) Better managed-futures proxy for KMLM's regime flag (RSI10 XLK > RSI10 KMLM).
"""
import os, json, math, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from replay import *

subprocess.run([sys.executable, f'{SP}/yh_fetch.py', 'AQMIX', 'WTMF', 'FMF'], check=False)
trees = json.load(open(f'{SP}/trees.json')); bt = json.load(open(f'{SP}/composer_bt.json'))

def ols(y, x):
    n = len(x); mx = sum(x)/n; my = sum(y)/n
    b = sum((xi-mx)*(yi-my) for xi, yi in zip(x, y))/sum((xi-mx)**2 for xi in x); a = my-b*mx
    res = [yi-(a+b*xi) for xi, yi in zip(x, y)]
    return a, b, math.sqrt(sum(r*r for r in res)/(n-2))

def turnover(hold, days):
    """sum |dw| per day between consecutive holdings (weights that earn d)."""
    out = {}; prev = {}
    for d in days[1:]:
        w = hold.get(d, {}); keys = set(w) | set(prev)
        out[d] = sum(abs(w.get(k, 0) - prev.get(k, 0)) for k in keys); prev = w
    return out

# ---- (A) cost per unit sum|dw| in the real era, real tickers ---------------
P = load_prices(real_synth=True); sim = SimW(P, rsi_method='wilder')
cost = {}
for eng in ('HG', 'KMLM', 'SLEEVE', 'HARV'):
    tk = tree_tickers(trees[eng]); days = common_days(P, tk, '2023-04-18', '2026-10-06')
    r, h = run_tree(sim, trees[eng], days); to = turnover(h, days)
    cr = rets_of(bt[f'{eng}_real']['curve']); com = sorted(set(r) & set(cr) & set(to))
    y = [cr[d] - r[d] for d in com]; x = [to[d] for d in com]
    a, b, se = ols(y, x)
    zero = [y[i] for i in range(len(com)) if x[i] < 1e-9]
    cost[eng] = {'bps_per_unit_sum_abs_dw': round(b*1e4, 2), 'intercept_bps': round(a*1e4, 3), 'resid_sd_bps': round(se*1e4, 2),
                 'n': len(com), 'zero_turnover_days': len(zero), 'zero_turnover_mean_bps': round(sum(zero)/len(zero)*1e4, 3) if zero else None,
                 'mean_sum_abs_dw_per_day': round(sum(x)/len(x), 4)}
    # check: apply cost and compare cumulative
    adj = {d: r[d] - b*to[d] - a for d in com}
    ca = math.prod(1+adj[d] for d in com); cc = math.prod(1+cr[d] for d in com)
    cost[eng]['cum_sim_costed'] = round(ca, 3); cost[eng]['cum_composer'] = round(cc, 3)
    print(eng, cost[eng])
json.dump(cost, open(f'{SP}/cost_fit.json', 'w'))

# ---- (B) proxies for the KMLM regime flag ---------------------------------
def wilder_map(px, n=10):
    ds = sorted(px); s = [px[d] for d in ds]; out = {}
    g = l = 0.0
    for i in range(1, len(s)):
        ch = s[i]-s[i-1]; gg, ll = max(ch, 0), max(-ch, 0)
        if i <= n:
            g += gg; l += ll
            if i == n: ag, al = g/n, l/n; out[ds[i]] = 100-100/(1+ag/al) if al else 100.0
        else:
            ag = (ag*(n-1)+gg)/n; al = (al*(n-1)+ll)/n; out[ds[i]] = 100-100/(1+ag/al) if al else 100.0
    return out
xlk = wilder_map(yh('XLK')); km = wilder_map(yh('KMLM'))
cands = {t: yh(t) for t in ('DBMF', 'DBC', 'AQMIX', 'WTMF', 'FMF')}
# composite: equal-weight daily-rebalanced index of the trend funds available each day
def composite(names):
    rs = [rets_of(cands[n]) for n in names]; days = sorted(set.intersection(*[set(r) for r in rs]))
    return curve_from({d: sum(r[d] for r in rs)/len(rs) for d in days})
cands['COMP3'] = composite(['DBMF', 'WTMF', 'FMF']); cands['COMP4'] = composite(['DBMF', 'WTMF', 'FMF', 'AQMIX'])
res = {}
spy = yh('SPY'); sds = sorted(spy)
r20 = {sds[i]: spy[sds[i]]/spy[sds[i-20]]-1 for i in range(20, len(sds))}
for nm, px in cands.items():
    rp = wilder_map(px); com = sorted(set(xlk) & set(km) & set(rp))
    agree = [(xlk[d] > km[d]) == (xlk[d] > rp[d]) for d in com]
    stress = [a for a, d in zip(agree, com) if r20.get(d, 0) < -0.05]
    res[nm] = {'from': sorted(px)[0], 'n': len(com), 'agree': round(sum(agree)/len(agree), 3),
               'agree_stress_spy20d<-5%': (round(sum(stress)/len(stress), 3), len(stress)) if stress else None}
    print(nm, res[nm])
json.dump(res, open(f'{SP}/proxy_fit.json', 'w'))

# ---- decomposition: real KMLM + synthetic SVIX/ZVOL in the real era ---------
P = load_prices(real_synth=True); P['SVIX'] = synth_svix(); P['ZVOL'] = synth_zvol()
sim = SimW(P, rsi_method='wilder'); tk = tree_tickers(trees['KMLM']); days = common_days(P, tk, '2023-04-18', '2026-10-06')
r, h = run_tree(sim, trees['KMLM'], days)
print('KMLM real era: real KMLM flag + synthetic SVIX/ZVOL:', fidelity(r, bt['KMLM_real']['curve']))
for nm in ('COMP3', 'AQMIX', 'WTMF'):
    P['KMLM'] = cands[nm]; sim = SimW(P, rsi_method='wilder'); days = common_days(P, tk, '2023-04-18', '2026-10-06')
    r, h = run_tree(sim, trees['KMLM'], days)
    print(f'KMLM real era: {nm} flag + synthetic SVIX/ZVOL:', fidelity(r, bt['KMLM_real']['curve']))
