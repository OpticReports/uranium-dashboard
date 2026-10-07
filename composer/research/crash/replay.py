"""In-kind daily replay of the four live trees through COVID (and fidelity checks).

Uses composer/research/synth/tree_sim.py (validated 0.999-1.000 vs Composer on the
live trees, Wilder RSI) with a warm-up fix: Wilder RSI uses up to 250 closes but
accepts as few as 60 when a series is young (DBMF, 2019-05+).  Missing data ->
condition False (never flat-filled).
"""
import json, math, sys, copy, datetime as dt
from _paths import SP
sys.path.insert(0, '/home/user/uranium-dashboard/composer/research/synth')
from tree_sim import Sim

def yh(t):
    o = json.load(open(f"{SP}/yh/{t.replace('^','_')}.json"))
    return dict(zip(o['dates'], o['adjclose']))

def rets_of(px):
    ds = sorted(px); return {ds[i]: px[ds[i]]/px[ds[i-1]]-1 for i in range(1, len(ds))}

def curve_from(rets, start=1.0):
    out = {}; v = start
    for d in sorted(rets):
        v *= 1 + rets[d]; out[d] = v
    return out

# ---- synthetic / substitute instruments ----------------------------------
SVIX_BETA, SVIX_ALPHA = 0.953, -0.00036     # fit vs 2xSVXY 2022-03..2026-10 (corr .993)
ZVOL_BETA, ZVOL_ALPHA = 0.971, 0.0          # fit vs -VXZ 2023-04..2026-10 (corr .973); alpha measured +1.9bp/d, set 0 (conservative)

def synth_svix():
    svxy = rets_of(yh('SVXY')); out = {}
    for d, r in svxy.items():
        lev = 1.0 if d < '2018-02-28' else 0.5          # SVXY went -1x -> -0.5x on 2018-02-28
        out[d] = SVIX_BETA * (r/lev) + SVIX_ALPHA
    return curve_from(out)

def synth_zvol(alpha=ZVOL_ALPHA):
    vxz = rets_of(yh('VXZ'))
    return curve_from({d: ZVOL_BETA*(-r) + alpha for d, r in vxz.items()})

def load_prices(kmlm_proxy='DBMF', zvol_alpha=ZVOL_ALPHA, real_synth=False):
    """real_synth=True keeps real SVIX/ZVOL/KMLM/BOXX (real-era fidelity check)."""
    tick = ['BIL','LABU','QLD','SMH','SSO','TECL','TNA','TQQQ','UDOW','UPRO','USD','UVXY','VIXM','VIXY',
            'PULS','SOXL','SPXL','SQQQ','TLT','VXZ','QQQE','VTV','VOX','VOOG','VOOV','XLP','XLY','FAS','SPY','XLK',
            'KIE','LABD','SOXS','SVXY','TMF','TMV','UGL','IEF','PSQ','HYG','SHY','CORP','PEJ','LQD','DBMF','DBC','KMLM','BOXX','SVIX','ZVOL']
    P = {t: yh(t) for t in tick}
    if real_synth:
        return P
    P['SVIX'] = synth_svix()
    P['ZVOL'] = synth_zvol(zvol_alpha)
    P['KMLM'] = yh(kmlm_proxy)
    P['BOXX'] = yh('BIL')
    return P

class SimW(Sim):
    """Wilder RSI with a bounded warm-up (>=60 closes) instead of a hard 250."""
    def ind(self, fn, tick, window, day):
        if fn != 'relative-strength-index' or self.rsi_method != 'wilder':
            return Sim.ind(self, fn, tick, window, day)
        key = (fn, tick, window, day)
        if key in self._cache: return self._cache[key]
        w = int(window or 10)
        i = self.idx[tick].get(day) if tick in self.idx else None
        v = None
        if i is not None:
            n = min(250, i)
            if n >= max(60, w+1):
                s = [self.p[tick][d] for d in self.days[tick][i-n:i+1]]
                r = [s[k]-s[k-1] for k in range(1, len(s))]
                g = [max(x,0) for x in r]; l = [max(-x,0) for x in r]
                ag, al = sum(g[:w])/w, sum(l[:w])/w
                for x in r[w:]:
                    ag = (ag*(w-1) + max(x,0))/w; al = (al*(w-1) + max(-x,0))/w
                v = 100.0 if al == 0 else 100 - 100/(1 + ag/al)
        self._cache[key] = v
        return v

def tree_tickers(tree):
    s = set()
    def walk(n):
        if n.get('step') == 'asset': s.add(n['ticker'])
        if n.get('lhs-fn'):
            s.add(n['lhs-val'])
            if not n.get('rhs-fixed-value?') and isinstance(n.get('rhs-val'), str): s.add(n['rhs-val'])
        for c in n.get('children') or []: walk(c)
    walk(tree); return s

def run_tree(sim, tree, days, w0=None):
    """Daily returns + holdings.  holdings[d1] = weights that EARN d1's return
    (decided at close d0).  w0 overrides the day-0 holdings (from-today variant)."""
    rets, hold = {}, {}
    subs = sim._find_filter_groups(tree)
    sim.sub = {sid: [(days[0], 1.0)] for sid in subs}
    for i in range(1, len(days)):
        d0, d1 = days[i-1], days[i]
        for sid, st in subs.items():
            sw = sim.weights(st, d0); tot = sum(sw.values()); sr = 0.0
            for t, x in sw.items():
                p0, p1 = sim.p[t].get(d0), sim.p[t].get(d1)
                if p0 and p1: sr += (x/tot if tot else 0)*(p1/p0-1)
            sim.sub[sid].append((d1, sim.sub[sid][-1][1]*(1+sr)))
        w = sim.weights(tree, d0) if not (w0 and i == 1) else dict(w0)
        tot = sum(w.values()); r = 0.0
        for t, x in w.items():
            p0, p1 = sim.p[t].get(d0), sim.p[t].get(d1)
            if p0 and p1: r += (x/tot if tot else 0)*(p1/p0-1)
        rets[d1] = r; hold[d1] = {t: round(x/tot, 4) for t, x in w.items() if tot and x/tot > 1e-6}
    return rets, hold

def corr(a, b):
    n = len(a); ma = sum(a)/n; mb = sum(b)/n
    sa = math.sqrt(sum((x-ma)**2 for x in a)); sb = math.sqrt(sum((y-mb)**2 for y in b))
    return sum((x-ma)*(y-mb) for x, y in zip(a, b))/(sa*sb) if sa and sb else float('nan')

def fidelity(sim_rets, comp_curve):
    cr = rets_of(comp_curve); com = sorted(set(sim_rets) & set(cr))
    a = [sim_rets[d] for d in com]; b = [cr[d] for d in com]
    ca = math.prod(1+x for x in a); cb = math.prod(1+x for x in b)
    return {'n': len(com), 'corr': round(corr(a, b), 4), 'sim_cum': round(ca, 3), 'composer_cum': round(cb, 3),
            'window': [com[0], com[-1]] if com else None}

def composer_equiv(rets, hold, days, eng):
    """Composer-equivalent daily returns: frictionless sim minus Composer's 5bps
    slippage-setting drag, fitted per engine in the real era (cost_fit.json:
    intercept bps/day + slope bps per unit sum|dw|).  Live has run ABOVE the
    Composer model on every engine (add. 38), so this is the conservative level."""
    import os
    cf = json.load(open(f'{SP}/cost_fit.json')) if os.path.exists(f'{SP}/cost_fit.json') else {}
    c = cf.get(eng, {}); a = c.get('intercept_bps', -2.7)/1e4; b = c.get('bps_per_unit_sum_abs_dw', -0.7)/1e4
    out = {}; prev = {}
    for d in days[1:]:
        w = hold.get(d, {}); to = sum(abs(w.get(k, 0)-prev.get(k, 0)) for k in set(w) | set(prev)); prev = w
        out[d] = rets[d] + a + b*to          # a, b are negative (composer - sim)
    return out

LIVE_W0 = {'HG': {'TQQQ': 1.0}, 'KMLM': {'VXZ': .13, 'PULS': .12, 'SOXL': .37, 'SVIX': .38},
           'SLEEVE': {'BOXX': .75, 'LABD': .25}, 'HARV': {'VXZ': .60, 'PULS': .40}}   # live holdings 2026-10-06 close

def common_days(P, tickers, start, end):
    ds = None
    for t in tickers:
        s = {d for d in P[t] if start <= d <= end}
        ds = s if ds is None else ds & s
    return sorted(ds)

if __name__ == '__main__':
    trees = json.load(open(f'{SP}/trees.json'))
    bt = json.load(open(f'{SP}/composer_bt.json'))
    out = {'fidelity': {}}
    # ---- (iii)/(iv) real-era simulator fidelity, real tickers --------------
    P = load_prices(real_synth=True)
    sim = SimW(P, rsi_method='wilder')
    for eng in ('HG', 'KMLM', 'SLEEVE', 'HARV'):
        tk = tree_tickers(trees[eng])
        days = common_days(P, tk, '2023-04-18', '2026-10-06')
        r, _ = run_tree(sim, trees[eng], days)
        out['fidelity'][f'{eng}_real_realtickers'] = fidelity(r, bt[f'{eng}_real']['curve'])
        print(eng, 'real era, real tickers:', out['fidelity'][f'{eng}_real_realtickers'])
    # ---- real era with synthetics (measures synthetic error) ---------------
    for proxy in ('DBMF', 'DBC'):
        P = load_prices(kmlm_proxy=proxy)
        sim = SimW(P, rsi_method='wilder')
        for eng in ('KMLM', 'HARV', 'SLEEVE'):
            tk = tree_tickers(trees[eng])
            days = common_days(P, tk, '2023-04-18', '2026-10-06')
            r, _ = run_tree(sim, trees[eng], days)
            out['fidelity'][f'{eng}_real_synth_{proxy}'] = fidelity(r, bt[f'{eng}_real']['curve'])
            print(eng, f'real era, synthetics ({proxy}):', out['fidelity'][f'{eng}_real_synth_{proxy}'])
    # ---- COVID window, all four, two KMLM proxies --------------------------
    out['covid'] = {}
    for proxy in ('AQMIX', 'FMF', 'DBMF', 'DBC'):
        P = load_prices(kmlm_proxy=proxy)
        sim = SimW(P, rsi_method='wilder')
        res = {}
        for eng in ('HG', 'KMLM', 'SLEEVE', 'HARV'):
            tk = tree_tickers(trees[eng])
            days = common_days(P, tk, '2019-09-03', '2021-03-31')
            r, h = run_tree(sim, trees[eng], days)
            res[eng] = {'rets': r, 'hold': h, 'days': days, 'rets_costed': composer_equiv(r, h, days, eng)}
            # from-today variant: live 2026-10-06 holdings earn the first crash day (2020-02-20)
            d0 = days.index('2020-02-19'); days2 = days[d0:]
            r2, h2 = run_tree(sim, trees[eng], days2, w0=LIVE_W0[eng])
            res[eng]['from_today'] = {'rets': r2, 'hold_day1': h2[days2[1]], 'natural_hold_day1': h[days2[1]],
                                      'rets_costed': composer_equiv(r2, h2, days2, eng)}
            if eng == 'HG' and proxy == 'DBMF':
                out['fidelity']['HG_covid_vs_composer'] = fidelity(r, bt['HG_covid']['curve']); print('HG covid fidelity', out['fidelity']['HG_covid_vs_composer'])
            if eng == 'SLEEVE':
                out['fidelity'][f'SLEEVE_covid_vs_composer_{proxy}'] = fidelity(r, bt['SLEEVE_covid_sub']['curve']); print('SLEEVE covid fidelity', proxy, out['fidelity'][f'SLEEVE_covid_vs_composer_{proxy}'])
        out['covid'][proxy] = res
        for eng in res:
            rr = res[eng]['rets']; ds = sorted(rr)
            seg = lambda a, b: math.prod(1+rr[d] for d in ds if a <= d <= b) - 1
            print(f"  {proxy} {eng:6s} 2020-02-19..03-23 {seg('2020-02-20','2020-03-23'):+7.1%}  03-24..06-30 {seg('2020-03-24','2020-06-30'):+7.1%}  12m from 02-19 {seg('2020-02-20','2021-02-19'):+7.1%}")
    json.dump(out, open(f'{SP}/covid_replay.json', 'w'))
    print('saved')
