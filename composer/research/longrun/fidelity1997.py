"""Fidelity checks for book1997.py.
1. Real era: each engine's long-panel run against Composer's own backtest of the live symphony (HG 2015-06+,
   the others 2023+): daily-return correlation, CAGR / max DD on common days, holdings agreement (Composer's
   weights at close d pair with the simulator's hold[d+1]).
2. KMLM signal: the KMLM and SLEEVE engines 2007-03..2026-10 with the managed-futures proxy in place of
   RYMFX/KMLM, against the main run (what the pre-2007 proxy does to the engines' results).
3. HG consistency: the long-panel HG (plain VIX mode = panel B's VIX legs) against the reviewed panel-B gated
   series (levgate 'T200 SPY>200d -> cash [trend only]'), 1997-2026."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '..', 'scripts'))
import book1997 as bk   # noqa: E402
import composerlib as cl   # noqa: E402

lp, lg = bk.lp, bk.lg
OUT = bk.OUT


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def cagr_dd(r, ds):
    w, pk, mdd = 1.0, 1.0, 0.0
    for d in ds:
        w *= 1 + r[d]
        pk = max(pk, w)
        mdd = max(mdd, 1 - w / pk)
    return w ** (252 / len(ds)) - 1, mdd


def composer_series(e):
    bt = json.load(open(os.path.join(OUT, f'composer_bt_{e}.json')))
    days, vals = cl.equity_curve(bt)
    eq = {cl.epoch_day_to_date(d).isoformat(): v for d, v in zip(days, vals)}
    raw = bt.get('tdvm_weights') or {}
    hold = {}
    for t, m in raw.items():
        for d, x in m.items():
            if x:
                hold.setdefault(cl.epoch_day_to_date(int(d)).isoformat(), {})[t] = x
    ds = sorted(eq)
    return {ds[i]: eq[ds[i]] / eq[ds[i - 1]] - 1 for i in range(1, len(ds))}, hold


def real_era(E):
    out = {}
    for e in bk.ENGINES:
        cr, ch = composer_series(e)
        mr, mh, mdays = E[e]['rets'], E[e]['hold'], E[e]['days']
        ds = [d for d in sorted(cr) if d in mr][1:]
        c = corr([cr[d] for d in ds], [mr[d] for d in ds])
        (cc, cd), (mc, md) = cagr_dd(cr, ds), cagr_dd(mr, ds)
        nxt = {mdays[i]: mdays[i + 1] for i in range(len(mdays) - 1)}
        pairs = [(d, nxt[d]) for d in sorted(ch) if d in nxt and nxt[d] in mh and d >= ds[0]]
        l1 = [sum(abs(ch[d].get(t, 0.0) - mh[n].get(t, 0.0)) for t in set(ch[d]) | set(mh[n])) for d, n in pairs]
        same = sum(1 for x in l1 if x < 0.02) / len(l1)
        out[e] = {'from': ds[0], 'to': ds[-1], 'n': len(ds), 'corr': round(c, 4), 'composer_cagr': round(cc, 4), 'model_cagr': round(mc, 4),
                  'composer_maxdd': round(cd, 4), 'model_maxdd': round(md, 4), 'same_holdings_share': round(same, 4), 'mean_l1': round(sum(l1) / len(l1), 4)}
    return out


def kmlm_signal(P, E):
    P2 = dict(P)
    P2['KMLM'] = P['MFPROXY']
    T = bk.trees()
    sim = lg.SimW(P2, rsi_method='wilder')
    out = {}
    for e in ('KMLM', 'SLEEVE'):
        tk = lg.tree_tickers(T[e])
        days = lg.common_days(P2, tk, '2006-01-03', E[e]['days'][-1])
        r, h = lg.run_tree(sim, T[e], days)
        rc = bk.composer_equiv(r, h, days, e)
        ds = [d for d in days if d >= '2007-03-01' and d in E[e]['rets']]
        (pc, pd), (mc, md) = cagr_dd(rc, ds), cagr_dd(E[e]['rets'], ds)
        same = sum(1 for d in ds if h.get(d) == E[e]['hold'].get(d)) / len(ds)
        out[e] = {'from': ds[0], 'to': ds[-1], 'main_cagr': round(mc, 4), 'proxy_cagr': round(pc, 4), 'main_maxdd': round(md, 4),
                  'proxy_maxdd': round(pd, 4), 'corr': round(corr([rc[d] for d in ds], [E[e]['rets'][d] for d in ds]), 4), 'same_holdings_share': round(same, 4)}
    return out


def hg_vs_panel_b():
    E = json.load(open(os.path.join(OUT, 'engines_plain.json')))
    J = json.load(open(os.path.join(lg.OUT, 'levgate.json')))
    s = J['panels']['B']['HG']['series_keep']['T200 SPY>200d -> cash [trend only]']
    m = E['HG']['rets']
    ds = [d for d in sorted(s) if d in m and '1997-01-02' <= d]
    (a, ad), (b, bd) = cagr_dd(m, ds), cagr_dd(s, ds)
    big = sorted(((abs(m[d] - s[d]), d) for d in ds), reverse=True)[:5]
    return {'from': ds[0], 'to': ds[-1], 'n': len(ds), 'corr': round(corr([m[d] for d in ds], [s[d] for d in ds]), 5),
            'long_panel_cagr': round(a, 4), 'panel_b_cagr': round(b, 4), 'long_panel_maxdd': round(ad, 4), 'panel_b_maxdd': round(bd, 4),
            'largest_daily_gaps': [(d, round(x, 4)) for x, d in big]}


def main():
    E = json.load(open(os.path.join(OUT, 'engines_ts_synth.json')))
    res = {'real_era': real_era(E)}
    for k, v in res['real_era'].items():
        print('real era', k, v)
    P, _ = lp.build_long_prices('ts_synth')
    res['kmlm_signal'] = kmlm_signal(P, E)
    for k, v in res['kmlm_signal'].items():
        print('KMLM signal proxy', k, v)
    if os.path.exists(os.path.join(OUT, 'engines_plain.json')):
        res['hg_vs_panel_b'] = hg_vs_panel_b()
        print('HG long panel (plain) vs panel B', res['hg_vs_panel_b'])
    json.dump(res, open(os.path.join(OUT, 'fidelity1997.json'), 'w'), indent=1)
    print('saved')


if __name__ == '__main__':
    main()
