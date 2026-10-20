"""$100k in the current four-engine book on 1996-12-31, run to the latest common close (owner, 2026-10-20).

Engines: the live trees (HG with the SPY 200-day gate, fixtures/hg-live-gated-2026-10-18; KMLM switcher +
VIX sleeve, SLEEVE, HARV from trees.json, verified equal to the live scores 2026-10-20), simulated daily
on the long panel (long_panel.py) from 1995-06-01 for indicator warm-up, Composer-equivalent costs per
engine (replay.composer_equiv, cost_fit.json).  Book: 29/29/27/15, drifting, an engine above 40% reset at
the next close (POLICY Op 5; levgate.book).  Benchmarks: SPY and QQQ total return.
Runs once per VIX mode (ts_synth main; plain and level = sensitivity), caches engine runs in the scratch dir.

usage: book1997.py [--modes ts_synth,plain,level] [--refresh]"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import long_panel as lp   # noqa: E402

lg, gs = lp.lg, lp.gs
from replay import composer_equiv   # noqa: E402

OUT = '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/long1997'
RUN0, BOOK0, START_VALUE = '1995-06-01', '1997-01-02', 100_000.0
HG_GATED = os.path.join(HERE, '..', '..', 'fixtures', 'hg-live-gated-2026-10-18.raw.json')
ENGINES = ('HG', 'KMLM', 'SLEEVE', 'HARV')


def trees():
    T = {e: gs.trees[e] for e in ('KMLM', 'SLEEVE', 'HARV')}
    with open(HG_GATED) as f:
        T['HG'] = json.load(f)
    return T


def run_engines(P, end, tag, refresh=False, T=None):
    cache = os.path.join(OUT, f'engines_{tag}.json')
    if os.path.exists(cache) and not refresh:
        return json.load(open(cache))
    T = T or trees()
    sim = lg.SimW(P, rsi_method='wilder')
    res = {}
    for e in ENGINES:
        tk = lg.tree_tickers(T[e])
        days = lg.common_days(P, tk, RUN0, end)
        r, h = lg.run_tree(sim, T[e], days)
        rc = composer_equiv(r, h, days, e)
        res[e] = {'days': days, 'rets': rc, 'hold': h}
        print(f'  {tag} {e}: {days[0]}..{days[-1]} {len(days)} days', flush=True)
    json.dump(res, open(cache, 'w'))
    return res


def stats(r, ds):
    """CAGR on calendar time, Sharpe/Sortino on daily excess over T-bills, max DD with dates, worst year, TUW"""
    from datetime import date
    x = [r.get(d, 0.0) for d in ds]
    ex = [v - lp.cash.get(d, 0.0) for v, d in zip(x, ds)]
    mu = sum(ex) / len(ex)
    sd = math.sqrt(sum((e - mu) ** 2 for e in ex) / (len(ex) - 1))
    dn = math.sqrt(sum(min(e, 0) ** 2 for e in ex) / len(ex))
    w, pk, pk_d, mdd, mdd_pk, mdd_tr, tuw, tmax, tuw_from = 1.0, 1.0, ds[0], 0.0, None, None, 0, 0, None
    years = {}
    for v, d in zip(x, ds):
        w *= 1 + v
        years[d[:4]] = years.get(d[:4], 1.0) * (1 + v)
        if w >= pk:
            pk, pk_d, tuw = w, d, 0
        else:
            tuw += 1
            if tuw > tmax:
                tmax, tuw_from = tuw, pk_d
        if 1 - w / pk > mdd:
            mdd, mdd_pk, mdd_tr = 1 - w / pk, pk_d, d
    yrs_cal = (date.fromisoformat(ds[-1]) - date.fromisoformat(prev_day(ds[0]))).days / 365.25
    return {'final_multiple': w, 'cagr': w ** (1 / yrs_cal) - 1, 'years': yrs_cal, 'sharpe': mu / sd * math.sqrt(252),
            'sortino': mu / dn * math.sqrt(252) if dn else None, 'vol': sd * math.sqrt(252), 'maxdd': mdd,
            'maxdd_peak': mdd_pk, 'maxdd_trough': mdd_tr, 'worst_year': min((v - 1, y) for y, v in years.items()),
            'best_year': max((v - 1, y) for y, v in years.items()), 'longest_underwater_sessions': tmax, 'underwater_from': tuw_from,
            'by_year': {y: v - 1 for y, v in sorted(years.items())}}


def prev_day(d):
    from datetime import date, timedelta
    return (date.fromisoformat(d) - timedelta(days=1)).isoformat()


def path(r, ds, v0=START_VALUE):
    w, out, pk, dd = v0, [], v0, []
    for d in ds:
        w *= 1 + r.get(d, 0.0)
        pk = max(pk, w)
        out.append(w)
        dd.append(w / pk - 1)
    return out, dd


def bench(px, ds):
    rr = lp.rets_of(px)
    return {d: rr.get(d, 0.0) for d in ds}


def run_mode(mode, refresh=False):
    P, meta = lp.build_long_prices(mode)
    end = min(max(P[t]) for t in ('SPY', 'TQQQ', 'TLT', 'XLK', 'KMLM', 'VXZ'))
    E = run_engines(P, end, mode, refresh)
    eng = {e: E[e]['rets'] for e in ENGINES}
    days = sorted(set().union(*[set(E[e]['days']) for e in ENGINES]))
    days = [d for d in days if BOOK0 <= d <= end]
    book = lg.book(eng, days)
    out = {'mode': mode, 'meta': meta, 'first': days[0], 'last': days[-1], 'n': len(days),
           'book': stats(book, days), 'engines': {e: stats(eng[e], days) for e in ENGINES},
           'bench': {b: stats(bench(P[b], days), days) for b in ('SPY', 'QQQ')}}
    out['paths'] = {'dates': days[::5] + ([days[-1]] if (len(days) - 1) % 5 else []),
                    'book': None}
    sel = list(range(0, len(days), 5)) + ([len(days) - 1] if (len(days) - 1) % 5 else [])
    for k, r in [('book', book)] + [(e, eng[e]) for e in ENGINES] + [(b, bench(P[b], days)) for b in ('SPY', 'QQQ')]:
        v, dd = path(r, days)
        out['paths'][k] = {'value': [round(v[i], 2) for i in sel], 'dd': [round(min(dd[max(0, i - 4):i + 1]), 4) for i in sel]}
    return out, P, E


def fmt(s):
    return (f"${START_VALUE * s['final_multiple']:,.0f}  CAGR {s['cagr']:+.1%}  Sharpe {s['sharpe']:.2f}  Sortino {s['sortino']:.2f}  "
            f"maxDD {s['maxdd']:.1%} ({s['maxdd_peak']}..{s['maxdd_trough']})  worst yr {s['worst_year'][0]:+.1%} {s['worst_year'][1]}  "
            f"underwater {s['longest_underwater_sessions']} sessions from {s['underwater_from']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--modes', default='ts_synth,plain,level')
    ap.add_argument('--refresh', action='store_true')
    a = ap.parse_args()
    res = {}
    for mode in a.modes.split(','):
        print(f'== VIX mode {mode}', flush=True)
        out, P, E = run_mode(mode, a.refresh)
        res[mode] = out
        print(f"book   {out['first']}..{out['last']}: {fmt(out['book'])}")
        for e in ENGINES:
            print(f"  {e:6s} {fmt(out['engines'][e])}")
        for b in ('SPY', 'QQQ'):
            print(f"  {b:6s} {fmt(out['bench'][b])}")
        json.dump(out, open(os.path.join(OUT, f'book1997_{mode}.json'), 'w'))
    print('saved')


if __name__ == '__main__':
    main()
