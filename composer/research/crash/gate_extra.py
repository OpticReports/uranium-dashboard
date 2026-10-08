"""Three more trend-gate shapes suggested by the first pass (fast exit / slow re-entry / hysteresis):
G6 off below 200d; above it, the 50/100/200 vote (stricter than B1)
G7 off below 200d; after a recross, re-enter linearly over 20 sessions (slow re-entry)
G8 hysteresis: off when SPY < 200d MA x 0.98, on again only when SPY > 200d MA x 1.02
Both panels, same metrics; plus their inverses.  Saves gate_extra.json."""
import os, json, math, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate_study as gs
from replay import load_prices
out = {}
P = load_prices(real_synth=True); daysA, hA, pxA = gs.base_run(P, '2015-06-01', '2026-10-06')
PL = gs.build_lh_prices(); daysB, hB, pxB = gs.base_run(PL, '1990-01-02', '2026-10-06')
WIN = {'A': {'2015-06..2026-10': (None, None), '2023-04..2026-10 (live era)': ('2023-04-19', None), '2022 bear': ('2022-01-03', '2022-12-30'), 'COVID 2020-02-19..2021-02-19': ('2020-02-20', '2021-02-19')},
       'B': {'1990-01..2026-10': (None, None), '1990-01..1999-12': (None, '1999-12-31'), '2000-03..2002-10 bear': ('2000-03-11', '2002-10-09'), '2003-01..2007-09': ('2003-01-02', '2007-09-28'),
             '2007-10..2009-03 bear': ('2007-10-10', '2009-03-09'), '2009-04..2019-12': ('2009-04-01', '2019-12-31'), '2020-01..2026-10': ('2020-01-02', None)}}
for pan, (days, h, px, PP) in {'A': (daysA, hA, pxA, P), 'B': (daysB, hB, pxB, PL)}.items():
    spy = PP['SPY']; G, ma50, ma100, ma200 = gs.gates_trend(spy); ds = sorted(d for d in spy if d in ma200)
    g6, g7, g8 = {}, {}, {}
    above = 0; on8 = True
    for d in ds:
        x = spy[d]/ma200[d]-1
        vote = (float(spy[d] > ma50[d]) + float(spy[d] > ma100[d]) + float(spy[d] > ma200[d]))/3.0
        g6[d] = 0.0 if x < 0 else vote
        above = above+1 if x >= 0 else 0
        g7[d] = 0.0 if x < 0 else min(1.0, above/20.0)
        if on8 and x < -0.02: on8 = False
        elif (not on8) and x > 0.02: on8 = True
        g8[d] = 1.0 if on8 else 0.0
    allows = {'G6 off<200d, vote above': g6, 'G7 off<200d, 20d ramp-in after recross': g7, 'G8 hysteresis 200d +-2%': g8}
    for n in list(allows): allows['INV ' + n] = {d: 1-v for d, v in allows[n].items()}
    res = {}
    for name, al in allows.items():
        r, to, hold = gs.variant_returns(days, h, px, al)
        res[name] = {'turnover_per_year': round(to, 2), 'mean_allow': round(sum(al.get(d, 1.0) for d in days)/len(days), 3), 'windows': {w: gs.metrics(r, days, a, b) for w, (a, b) in WIN[pan].items()}}
        m = res[name]['windows'][list(WIN[pan])[0]]
        print(pan, f"{name:44s} {m['cagr']:+7.1%} vol {m['vol']:5.1%} Sh {m['sharpe']:5.2f} So {m['sortino']:5.2f} Ca {m['calmar']} DD {m['maxdd']:5.1%} worst {m['worst_year']:+6.1%} allow {res[name]['mean_allow']:.2f}")
    out[pan] = res
json.dump(out, open(f'{gs.SP}/gate_extra.json', 'w')); print('saved')
