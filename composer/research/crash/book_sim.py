"""Book-level daily simulation with the POLICY guards, from today's balance.

Engines' daily returns in -> book path with: concentration cap (any engine >40%
of book -> reset all four to 29/29/27/15, executed next close), sleeve band
(sleeve/(others+IBKR+sleeve) outside 7-15% -> sleeve to 10% x (others+IBKR),
difference to/from the engine furthest below/above target; next close), IBKR
equities held constant at $346k (owner-reported).  Alerts (DD tiers, book DD
17%) are logged, never traded.
"""
import json, math
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import SP
START = 303140.0; IBKR = 346000.0
W = {'HG': .29, 'KMLM': .29, 'SLEEVE': .27, 'HARV': .15}
LIVE = {'HG': 88088.0, 'KMLM': 98073.0, 'SLEEVE': 79885.0, 'HARV': 37094.0}   # 2026-10-06 close (sum 303,140)
TIERS = {'HG': (0.15, 0.40), 'KMLM': (0.15, 0.39), 'SLEEVE': (0.15, 0.20), 'HARV': (0.12, 0.12)}

def simulate(rets, days, guards=True, start_alloc='live', log_alerts=True):
    """rets: {engine: {day: ret}}; days: ordered list (day 0 = start, no return)."""
    v = dict(LIVE) if start_alloc == 'live' else {k: W[k]*START for k in W}
    scale = START/sum(v.values()); v = {k: x*scale for k, x in v.items()}
    path = [{'day': days[0], 'book': START, **{k: v[k] for k in v}}]
    pending = None; fires = []; peak = {k: v[k] for k in v}; book_peak = START; alerts = set()
    for d in days[1:]:
        for k in v: v[k] *= 1 + rets[k].get(d, 0.0)
        if pending:                                  # execute yesterday's decision at today's close
            kind, moves = pending
            for k, dx in moves.items(): v[k] += dx
            fires.append({'day': d, 'kind': kind, 'moves': {k: round(x) for k, x in moves.items()}}); pending = None
        tot = sum(v.values())
        if guards:
            if max(v.values())/tot > 0.40:
                pending = ('cap-40', {k: W[k]*tot - v[k] for k in v})
            else:
                E = tot - v['SLEEVE']; w = v['SLEEVE']/(E + IBKR + v['SLEEVE'])
                if w > 0.15 or w < 0.07:
                    target = 0.10*(E + IBKR); diff = v['SLEEVE'] - target
                    others = {k: v[k]/tot - W[k] for k in ('HG', 'KMLM', 'HARV')}
                    k = min(others, key=others.get) if diff > 0 else max(others, key=others.get)
                    pending = ('band-trim' if diff > 0 else 'band-reenter', {'SLEEVE': -diff, k: diff})
        for k in v:
            peak[k] = max(peak[k], v[k]); dd = 1 - v[k]/peak[k]
            for tier, lvl in zip(('tier1', 'tier2'), TIERS[k]):
                if dd >= lvl: alerts.add((k, tier))
        book_peak = max(book_peak, tot)
        if 1 - tot/book_peak >= 0.17: alerts.add(('BOOK', 'dd17'))
        path.append({'day': d, 'book': tot, **{k: v[k] for k in v}})
    return path, fires, sorted(alerts)

def summarize(path, d0, horizons_days=(63, 126, 189, 252)):
    """balances at +3/6/9/12 months of trading days from d0 (index of day 0), maxDD, TUW, worst day/week."""
    i0 = next(i for i, p in enumerate(path) if p['day'] >= d0)
    b = [p['book'] for p in path[i0:]]; ds = [p['day'] for p in path[i0:]]
    out = {'start': ds[0], 'start_value': round(b[0])}
    for h in horizons_days:
        if h < len(b): out[f'm{h//21}'] = {'day': ds[h], 'value': round(b[h]), 'ret': round(b[h]/b[0]-1, 4)}
    peak = b[0]; mdd = 0; mdd_day = ds[0]; tuw = 0; tuw_max = 0; trough_i = 0; peak_i = 0
    for i, x in enumerate(b):
        if x >= peak: peak = x; tuw = 0; peak_i = i
        else:
            tuw += 1; tuw_max = max(tuw_max, tuw)
        if 1-x/peak > mdd: mdd = 1-x/peak; mdd_day = ds[i]; trough_i = i
    out['maxdd'] = round(mdd, 4); out['maxdd_trough'] = mdd_day; out['tuw_max_days'] = tuw_max
    out['worst_day'] = round(min(b[i]/b[i-1]-1 for i in range(1, len(b))), 4)
    out['worst_5d'] = round(min(b[i]/b[i-5]-1 for i in range(5, len(b))), 4) if len(b) > 5 else None
    out['end'] = {'day': ds[-1], 'value': round(b[-1]), 'ret': round(b[-1]/b[0]-1, 4)}
    per = {}
    for k in W:
        s = [p[k] for p in path[i0:]]
        pk = s[0]; m = 0
        for x in s: pk = max(pk, x); m = max(m, 1-x/pk)
        per[k] = {'maxdd': round(m, 4)}
    out['engine_maxdd'] = per
    return out

if __name__ == '__main__':
    C = json.load(open(f'{SP}/covid_replay.json')); H = json.load(open(f'{SP}/hist_replay.json')); A = json.load(open(f'{SP}/attrib.json'))
    out = {'covid': {}, 'gfc': {}, 'dotcom': {}}
    # ---- COVID: day 0 = 2020-02-19, horizons to 2021-02-19 -----------------
    for proxy, res in C['covid'].items():
        for variant in ('historical_state', 'from_today'):
            for basis in ('rets_costed', 'rets'):
                if variant == 'historical_state':
                    rets = {k: res[k][basis] for k in W}; days = [d for d in res['HG']['days'] if d >= '2020-02-19']
                else:
                    rets = {k: res[k]['from_today'][basis] for k in W}; days = ['2020-02-19'] + sorted(rets['HG'])
                days = [d for d in days if d <= '2021-02-19']
                for g in (True, False):
                    path, fires, alerts = simulate(rets, days, guards=g)
                    key = f'{proxy}|{variant}|{"composer" if basis=="rets_costed" else "frictionless"}|{"guards" if g else "noguards"}'
                    out['covid'][key] = {'summary': summarize(path, '2020-02-19'), 'fires': fires, 'alerts': alerts,
                                         'path': [(p['day'], round(p['book']), round(p['HG']), round(p['KMLM']), round(p['SLEEVE']), round(p['HARV'])) for p in path]}
    for key in sorted(out['covid']):
        if 'composer' in key:
            s = out['covid'][key]['summary']
            print(f"COVID {key:52s} 3m {s.get('m3',{}).get('ret',0):+7.1%} 6m {s.get('m6',{}).get('ret',0):+7.1%} 9m {s.get('m9',{}).get('ret',0):+7.1%} 12m {s.get('m12',{}).get('ret',0):+7.1%} maxDD {s['maxdd']:.1%} ({s['maxdd_trough']}) worst5d {s['worst_5d']:+.1%} fires {len(out['covid'][key]['fires'])} alerts {out['covid'][key]['alerts']}")
    # ---- GFC hybrid: HG + SLEEVE daily recon; KMLM conservative (= HG path) or exhibit; HARV exhibit or flat ----
    hg = H['runs']['HG_gfc']['rets']; sl = H['runs']['SLEEVE_gfc']['rets']; hv = H['runs']['HARV_gfc_exhibit']['rets']; km = H['runs']['KMLM_gfc_exhibit']['rets']
    sl_bil = A['SLEEVE_gfc_vixlegs_to_BIL']['rets']
    cashish = {d: 0.02/252 for d in hg}
    for start, label in (('2007-10-09', 'from_peak'), ('2008-09-12', 'from_lehman')):
        days = [d for d in sorted(hg) if d >= start and d in sl and d in hv and d in km][:400]
        days = [start] + [d for d in days if d > start] if start in hg else days
        for kml, kname in ((hg, 'KMLM=HG(conservative)'), (km, 'KMLM=exhibit')):
            for hvv, hname in ((hv, 'HARV=exhibit'), (cashish, 'HARV=cash2%')):
                for slv, sname in ((sl, 'SLEEVE=recon'), (sl_bil, 'SLEEVE=recon,vol-legs->BIL')):
                    rets = {'HG': hg, 'KMLM': kml, 'SLEEVE': slv, 'HARV': hvv}
                    for g in (True, False):
                        path, fires, alerts = simulate(rets, days, guards=g)
                        key = f'{label}|{kname}|{hname}|{sname}|{"guards" if g else "noguards"}'
                        out['gfc'][key] = {'summary': summarize(path, start), 'fires': fires, 'alerts': alerts,
                                           'path': [(p['day'], round(p['book']), round(p['HG']), round(p['KMLM']), round(p['SLEEVE']), round(p['HARV'])) for p in path]}
                        s = out['gfc'][key]['summary']
                        if g and hname == 'HARV=exhibit' and sname == 'SLEEVE=recon':
                            print(f"GFC {key:75s} 3m {s.get('m3',{}).get('ret',0):+7.1%} 6m {s.get('m6',{}).get('ret',0):+7.1%} 9m {s.get('m9',{}).get('ret',0):+7.1%} 12m {s.get('m12',{}).get('ret',0):+7.1%} maxDD {s['maxdd']:.1%} fires {len(fires)} alerts {alerts}")
    # ---- dotcom: HG daily recon + conservative companions (KMLM=HG, SLEEVE=cash, HARV=cash) and bootstrap for the rest ----
    hgd = H['runs']['HG_dotcom']['rets']
    for start, label in (('2000-03-10', 'from_ndx_peak'), ('2000-09-01', 'acute')):
        days = [d for d in sorted(hgd) if d >= start][:400]
        rets = {'HG': hgd, 'KMLM': hgd, 'SLEEVE': {d: 0.06/252 for d in hgd}, 'HARV': {d: 0.06/252 for d in hgd}}
        for g in (True, False):
            path, fires, alerts = simulate(rets, days, guards=g)
            key = f'{label}|KMLM=HG(conservative)|SLEEVE,HARV=cash6%|{"guards" if g else "noguards"}'
            out['dotcom'][key] = {'summary': summarize(path, start), 'fires': fires, 'alerts': alerts,
                                  'path': [(p['day'], round(p['book']), round(p['HG']), round(p['KMLM']), round(p['SLEEVE']), round(p['HARV'])) for p in path]}
            s = out['dotcom'][key]['summary']
            print(f"DOTCOM {key:70s} 3m {s.get('m3',{}).get('ret',0):+7.1%} 6m {s.get('m6',{}).get('ret',0):+7.1%} 12m {s.get('m12',{}).get('ret',0):+7.1%} maxDD {s['maxdd']:.1%} fires {len(fires)} alerts {alerts}")
    json.dump(out, open(f'{SP}/book_sim.json', 'w')); print('saved')
