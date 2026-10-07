"""Regime bootstrap along the ACTUAL regime sequence of a historical crash
(house method, regime_boot.py / addendum 13), both lenses, with the book-level
guards (cap-40, sleeve band) applied at month-ends.  Reports the distribution
of the account balance at 3/6/9/12(+) months from a $303,140 start and the
max drawdown over the sequence.
"""
import json, random, math, sys
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import SP
B = json.load(open(f'{SP}/boot_inputs.json'))
START_VALUE = 303140.0
IBKR = 346000.0
W = {'HG': .29, 'KMLM': .29, 'SLEEVE': .27, 'HARV': .15}

def monthly_from_curve(curve):
    me = {}
    for d in sorted(curve): me[d[:7]] = curve[d]
    yms = sorted(me); return {yms[i]: me[yms[i]]/me[yms[i-1]]-1 for i in range(1, len(yms))}

# regimes from S&P dailies (same rule as regime_boot)
spx = B['spx']; sd = sorted(spx); by_m = {}
for i, d in enumerate(sd):
    by_m.setdefault(d[:7], []).append((spx[d], spx[sd[i-1]] if i else spx[d]))
regime, spx_m = {}, {}
for ym, rows in sorted(by_m.items()):
    mret = rows[-1][0]/rows[0][1]-1; worst = min(a/b-1 for a, b in rows)
    regime[ym] = 'CRASH' if (mret < -0.05 or worst < -0.03) else 'TREND-UP' if mret > 0.025 else 'CHOP'
    spx_m[ym] = mret
THIS_M = '2026-10'
eng = {k: monthly_from_curve(v) for k, v in B['engines'].items()}
for ym, r in B['harv_guard_sim'].items(): eng['HARV'].setdefault(ym, r)
buckets = {k: {'TREND-UP': [], 'CHOP': [], 'CRASH': []} for k in eng}
for k, m in eng.items():
    for ym, ret in m.items():
        if ym in regime and ym < THIS_M: buckets[k][regime[ym]].append((ym, ret))
donor = {r: sorted({ym for ym, _ in buckets['HG'][r]}) for r in ('TREND-UP', 'CHOP', 'CRASH')}
print({k: {r: len(v) for r, v in b.items()} for k, b in buckets.items()})

def draw(regm, rng, conservative):
    m_star = rng.choice(donor[regm]); out = {}
    for k in eng:
        if conservative and k == 'KMLM' and regm in ('CRASH', 'CHOP'):
            hit = dict(buckets['HG'][regm]).get(m_star)
            out[k] = hit if hit is not None else rng.choice(buckets['HG'][regm])[1]; continue
        hit = dict(buckets[k][regm]).get(m_star)
        out[k] = hit if hit is not None else rng.choice(buckets[k][regm])[1]
    return out

def step_guards(v, log):
    """v: {engine: $}. Cap-40 (any engine > 40% of book -> reset all to target);
    sleeve band (S/(E+IBKR+S) outside 7-15% -> S := 10% x (E+IBKR), diff to/from
    the engine furthest below/above target among HG/KMLM/HARV)."""
    tot = sum(v.values())
    if max(v.values())/tot > 0.40:
        for k in v: v[k] = W[k]*tot
        log['cap'] += 1; return
    E = tot - v['SLEEVE']; w = v['SLEEVE']/(E + IBKR + v['SLEEVE'])
    if w > 0.15 or w < 0.07:
        target = 0.10*(E + IBKR); diff = v['SLEEVE'] - target   # >0: trim sleeve, buy engine
        others = {k: v[k]/tot - W[k] for k in ('HG', 'KMLM', 'HARV')}
        k = min(others, key=others.get) if diff > 0 else max(others, key=others.get)
        v['SLEEVE'] = target; v[k] += diff; log['band'] += 1

def run_seq(seq, K, conservative, guards=True, seed=7, horizons=(3, 6, 9, 12, 18, 24, 36)):
    rng = random.Random(seed); n = len(seq)
    H = [h for h in horizons if h <= n]
    vals = {h: [] for h in H}; mdds = []; eng_h = {h: {k: [] for k in W} for h in H}; worst_m = []
    fires = {'cap': 0, 'band': 0}
    for _ in range(K):
        v = {k: W[k]*START_VALUE for k in W}; curve = [START_VALUE]; eng_cum = {k: 1.0 for k in W}
        for i, regm in enumerate(seq):
            d = draw(regm, rng, conservative)
            for k in v: v[k] *= (1 + d[k]); eng_cum[k] *= (1 + d[k])
            if guards: step_guards(v, fires)
            curve.append(sum(v.values()))
            if (i+1) in vals:
                vals[i+1].append(curve[-1])
                for k in W: eng_h[i+1][k].append(eng_cum[k]-1)
        peak = curve[0]; mdd = 0
        for x in curve: peak = max(peak, x); mdd = max(mdd, 1-x/peak)
        mdds.append(mdd); worst_m.append(min(curve[i+1]/curve[i]-1 for i in range(len(curve)-1)))
    q = lambda a, p: sorted(a)[int(p*(len(a)-1))]
    out = {'n_months': n, 'K': K, 'fires_per_path': {k: round(x/K, 2) for k, x in fires.items()},
           'maxdd': {p: round(q(mdds, p), 4) for p in (.05, .25, .5, .75, .95)},
           'worst_month': {p: round(q(worst_m, p), 4) for p in (.05, .5, .95)},
           'balance': {h: {p: round(q(vals[h], p)) for p in (.05, .25, .5, .75, .95)} for h in H},
           'p_loss': {h: round(sum(x < START_VALUE for x in vals[h])/K, 3) for h in H},
           'engine_median_cum': {h: {k: round(q(eng_h[h][k], .5), 4) for k in W} for h in H}}
    return out

SCEN = {
    'COVID 2020 (from 2020-02)':   ('2020-02', 12),
    'GFC from peak (2007-10)':     ('2007-10', 18),
    'GFC from Lehman (2008-09)':   ('2008-09', 12),
    'Dotcom from NDX peak (2000-03)': ('2000-03', 36),
    'Dotcom acute (2000-09)':      ('2000-09', 12),
}
months_all = sorted(regime)
res = {}
for name, (start, n) in SCEN.items():
    i0 = months_all.index(start); seq_m = months_all[i0:i0+n]; seq = [regime[m] for m in seq_m]
    res[name] = {'months': seq_m, 'regimes': seq, 'spx_cum': round(math.prod(1+spx_m[m] for m in seq_m)-1, 4),
                 'spx_path': [round(math.prod(1+spx_m[m] for m in seq_m[:h])-1, 4) for h in (3, 6, 9, 12) if h <= n]}
    for lens, cons in (('as_measured', False), ('conservative', True)):
        res[name][lens] = run_seq(seq, 4000, cons)
        res[name][lens+'_noguards'] = run_seq(seq, 4000, cons, guards=False)
    r = res[name]
    print(f"\n{name}: {n}m, regimes {''.join(x[0] for x in seq)}  SPX {r['spx_cum']:+.1%}")
    for lens in ('as_measured', 'conservative'):
        b = r[lens]['balance']; print(f"  {lens:13s} 12m p05 ${b[12][.05]:,} p50 ${b[12][.5]:,} p95 ${b[12][.95]:,}  maxDD p50 {r[lens]['maxdd'][.5]:.1%} p95 {r[lens]['maxdd'][.95]:.1%}  P(loss@12m) {r[lens]['p_loss'][12]:.0%}  fires {r[lens]['fires_per_path']}")
        bn = r[lens+'_noguards']; print(f"  {'  no guards':13s} 12m p50 ${bn['balance'][12][.5]:,}  maxDD p50 {bn['maxdd'][.5]:.1%} p95 {bn['maxdd'][.95]:.1%}")
json.dump({'buckets': {k: {r: len(v) for r, v in b.items()} for k, b in buckets.items()}, 'scenarios': res,
           'regime_rule': 'CRASH if month<-5% or worst day<-3%; TREND-UP if >+2.5%; else CHOP'}, open(f'{SP}/boot_scen.json', 'w'))
print('saved')
