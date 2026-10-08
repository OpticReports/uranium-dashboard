"""55y regime bootstrap (house method) with HG replaced by a gate variant, both lenses.
HG buckets come from the SIM (real tickers 2015-06..2026-10, Composer-equivalent cost)
for every variant incl. 'as built', so the comparison is apples to apples; the other
three engines' buckets are the study's (boot_inputs.json).  K=2000 paths over the real
1971-2026 regime sequence (like research/regime_boot.py); reports book CAGR p05/p50,
maxDD p50/p95, monthly Sharpe p50, and the 12-month-horizon stats on the crash sequences."""
import os, json, math, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate_study as gs
from replay import load_prices
SP = gs.SP
B = json.load(open(f'{SP}/boot_inputs.json'))
W = {'HG': .29, 'KMLM': .29, 'SLEEVE': .27, 'HARV': .15}
def monthly_from_curve(curve):
    me = {}
    for d in sorted(curve): me[d[:7]] = curve[d]
    yms = sorted(me); return {yms[i]: me[yms[i]]/me[yms[i-1]]-1 for i in range(1, len(yms))}
spx = B['spx']; sd = sorted(spx); by_m = {}
for i, d in enumerate(sd): by_m.setdefault(d[:7], []).append((spx[d], spx[sd[i-1]] if i else spx[d]))
regime = {}
for ym, rows in sorted(by_m.items()):
    mret = rows[-1][0]/rows[0][1]-1; worst = min(a/b-1 for a, b in rows)
    regime[ym] = 'CRASH' if (mret < -0.05 or worst < -0.03) else 'TREND-UP' if mret > 0.025 else 'CHOP'
THIS_M = '2026-10'; months = [ym for ym in sorted(regime) if '1971-01' <= ym < THIS_M]
others = {k: monthly_from_curve(v) for k, v in B['engines'].items() if k != 'HG'}
for ym, r in B['harv_guard_sim'].items(): others['HARV'].setdefault(ym, r)

P = load_prices(real_synth=True); days, h, px = gs.base_run(P, '2015-06-01', '2026-10-06')
spy = P['SPY']; G, ma50, ma100, ma200 = gs.gates_trend(spy); M = gs.build_macro_allows(spy, ma50, ma100, ma200, days)
variants = {'B0 as built (sim)': {}, 'B1 binary SPY<200d': G['B1 binary SPY<200d'], 'G2 vote 50/100/200d': G['G2 vote 50/100/200d'], 'G4 drawdown ramp 5%->15%': G['G4 drawdown ramp 5%->15%'], 'M4 oil +50% yoy -> 100d': M['M4 oil +50% yoy -> 100d']}
res = {}
for name, al in variants.items():
    r, _, _ = gs.variant_returns(days, h, px, al); curve = gs.curve_from(r); hg_m = monthly_from_curve(curve)
    eng = dict(others); eng['HG'] = hg_m
    buckets = {k: {'TREND-UP': [], 'CHOP': [], 'CRASH': []} for k in eng}
    for k, m in eng.items():
        for ym, ret in m.items():
            if ym in regime and ym < THIS_M: buckets[k][regime[ym]].append((ym, ret))
    donor = {rg: sorted({ym for ym, _ in buckets['HG'][rg]}) for rg in ('TREND-UP', 'CHOP', 'CRASH')}
    def draw(regm, rng, conservative):
        m_star = rng.choice(donor[regm]); out = {}
        for k in eng:
            if conservative and k == 'KMLM' and regm in ('CRASH', 'CHOP'):
                hit = dict(buckets['HG'][regm]).get(m_star); out[k] = hit if hit is not None else rng.choice(buckets['HG'][regm])[1]; continue
            hit = dict(buckets[k][regm]).get(m_star); out[k] = hit if hit is not None else rng.choice(buckets[k][regm])[1]
        return out
    def run(seq, K, conservative, seed=5):
        rng = random.Random(seed); cagrs, mdds, sharpes = [], [], []
        for _ in range(K):
            v = {k: W[k] for k in W}; cur = 1.0; peak = 1.0; mdd = 0.0; rets = []
            for regm in seq:
                d = draw(regm, rng, conservative)
                for k in v: v[k] *= 1+d[k]
                tot = sum(v.values())
                if max(v.values())/tot > 0.40: v = {k: W[k]*tot for k in W}     # cap-40
                rets.append(tot/cur-1); cur = tot; peak = max(peak, cur); mdd = max(mdd, 1-cur/peak)
            cagrs.append(cur**(12/len(seq))-1); mdds.append(mdd)
            mu = sum(rets)/len(rets); sdv = math.sqrt(sum((x-mu)**2 for x in rets)/(len(rets)-1)); sharpes.append(mu/sdv*math.sqrt(12) if sdv else 0)
        q = lambda a, p: sorted(a)[int(p*(len(a)-1))]
        return {'cagr_p05': round(q(cagrs, .05), 4), 'cagr_p50': round(q(cagrs, .5), 4), 'maxdd_p50': round(q(mdds, .5), 4), 'maxdd_p95': round(q(mdds, .95), 4), 'sharpe_p50': round(q(sharpes, .5), 3)}
    seq = [regime[m] for m in months]
    res[name] = {'hg_buckets': {rg: len(v) for rg, v in buckets['HG'].items()}, 'hg_bucket_means': {rg: round(sum(x for _, x in v)/len(v), 4) for rg, v in buckets['HG'].items()}}
    for lens, cons in (('as_measured', False), ('conservative', True)):
        res[name][lens] = run(seq, 2000, cons)
        # crash sequences (12m) for reference
        for sname, start in (('GFC 2007-10', '2007-10'), ('dotcom 2000-03', '2000-03'), ('COVID 2020-02', '2020-02')):
            i0 = months.index(start); res[name][lens][sname+' 12m'] = run([regime[m] for m in months[i0:i0+12]], 2000, cons)
    a, c = res[name]['as_measured'], res[name]['conservative']
    print(f"{name:28s} HG CRASH-bucket mean {res[name]['hg_bucket_means']['CRASH']:+.1%} | 55y as-measured CAGR p05/p50 {a['cagr_p05']:+.1%}/{a['cagr_p50']:+.1%} DD p50/p95 {a['maxdd_p50']:.0%}/{a['maxdd_p95']:.0%} Sh {a['sharpe_p50']:.2f} | conservative {c['cagr_p05']:+.1%}/{c['cagr_p50']:+.1%} DD {c['maxdd_p50']:.0%}/{c['maxdd_p95']:.0%} Sh {c['sharpe_p50']:.2f} | GFC12m cons p05/p50 {c['GFC 2007-10 12m']['cagr_p05']:+.0%}/{c['GFC 2007-10 12m']['cagr_p50']:+.0%}")
json.dump(res, open(f'{SP}/boot_gate.json', 'w')); print('saved')
