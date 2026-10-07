"""Leg-level attribution of the replays + sleeve GFC sensitivity (VIX-ETP legs -> BIL)."""
import os, json, math, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from replay import *
from hist_replay import build_prices
H = json.load(open(f'{SP}/hist_replay.json')); C = json.load(open(f'{SP}/covid_replay.json')); trees = json.load(open(f'{SP}/trees.json'))

def attrib(run, P, a, b):
    """per-ticker sum of w*r and days held inside [a,b]; plus state (holding-set) P&L."""
    hold = run['hold']; days = [d for d in sorted(hold) if a <= d <= b]
    tick, state = {}, {}
    prevd = {d: run['days'][run['days'].index(d)-1] for d in days}
    for d in days:
        d0 = prevd[d]; key = '+'.join(sorted(hold[d]))
        for t, w in hold[d].items():
            r = P[t][d]/P[t][d0]-1 if d in P[t] and d0 in P[t] else 0.0
            tick.setdefault(t, [0.0, 0]); tick[t][0] += w*r; tick[t][1] += 1
            state.setdefault(key, [0.0, 0]); state[key][0] += w*r
        state[key][1] += 1
    return ({t: (round(v[0], 4), v[1]) for t, v in sorted(tick.items(), key=lambda x: x[1][0])},
            {k: (round(v[0], 4), v[1]) for k, v in sorted(state.items(), key=lambda x: x[1][0])})

P, _ = build_prices()
out = {}
for key, a, b in (('SLEEVE_gfc', '2008-09-15', '2009-09-14'), ('SLEEVE_gfc', '2007-10-09', '2009-03-09'), ('HG_gfc', '2007-10-09', '2009-03-09'),
                  ('HG_dotcom', '2000-03-10', '2002-10-09'), ('HG_dotcom', '2000-03-10', '2001-03-09'), ('HG_gfc', '2008-09-15', '2009-09-14')):
    t, s = attrib(H['runs'][key], P, a, b)
    out[f'{key} {a}..{b}'] = {'ticker': t, 'state': s}
    print(f"\n{key} {a}..{b}\n  tickers (sum w*r, days):", t, "\n  states:", s)
# COVID sleeve attribution (DBMF proxy), real prices
Pc = load_prices(kmlm_proxy='DBMF')
for eng in ('SLEEVE', 'HG', 'HARV'):
    t, s = attrib(C['covid']['DBMF'][eng], Pc, '2020-02-20', '2020-03-23')
    out[f'{eng}_covid 2020-02-20..03-23'] = {'ticker': t, 'state': s}; print(f"\n{eng} COVID crash:", t, s)
for proxy in ('AQMIX', 'DBC'):
    t, s = attrib(C['covid'][proxy]['KMLM'], load_prices(kmlm_proxy=proxy), '2020-02-20', '2020-03-23')
    out[f'KMLM_covid_{proxy} 2020-02-20..03-23'] = {'ticker': t, 'state': s}; print(f"\nKMLM COVID crash ({proxy}):", t, s)
    # flag path: share of days risk-on during the crash
    hold = C['covid'][proxy]['KMLM']['hold']; ds = [d for d in sorted(hold) if '2020-02-20' <= d <= '2020-03-23']
    print('   holdings path:', [(d[5:], '/'.join(f'{k}{int(v*100)}' for k, v in hold[d].items())) for d in ds])

# sleeve GFC sensitivity: VIX-ETP legs replaced by BIL
P2 = dict(P); P2['SVXY'] = P['BIL']; P2['UVXY'] = P['BIL']
sim = SimW(P2, rsi_method='wilder'); tk = tree_tickers(trees['SLEEVE']); days = common_days(P2, tk, '2007-06-01', '2010-12-31')
r, h = run_tree(sim, trees['SLEEVE'], days); rc = composer_equiv(r, h, days, 'SLEEVE'); ds = sorted(rc)
seg = lambda x, y: math.prod(1+rc[d] for d in ds if x <= d <= y)-1
print(f"\nSLEEVE gfc with SVXY/UVXY->BIL: peak-trough {seg('2007-10-10','2009-03-09'):+.1%} | 2008 {seg('2008-01-01','2008-12-31'):+.1%} | 12m Lehman {seg('2008-09-15','2009-09-14'):+.1%} | 12m peak {seg('2007-10-10','2008-10-09'):+.1%}")
out['SLEEVE_gfc_vixlegs_to_BIL'] = {'rets': rc, 'hold': h, 'days': days}
json.dump(out, open(f'{SP}/attrib.json', 'w')); print('saved')
