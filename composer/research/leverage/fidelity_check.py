"""Fidelity gate for the HG 200-day gate draft: Composer's own backtest (v2, reg+TAF fees, 5 bp slippage) of
the draft tree and of the live tree, 2015-06-01 on, against the gate lab's panel-A model (levgate.json:
'A0 always levered (as built)' and 'T200 SPY>200d -> cash [trend only]'; holdings from base_A.json).
Reports daily-return correlation, drift, CAGR / Sharpe / max DD, the day-by-day holdings match, and the
agreement of the gate's off days.  Backtests are cached in the scratch dir; nothing is saved to Composer.

usage: fidelity_check.py [--refresh]"""
import argparse
import json
import math
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'scripts'))
sys.path.insert(0, HERE)
import composerlib as cl   # noqa: E402
import levgate as lg       # noqa: E402

D = '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/draft'
START, END = '2015-06-01', '2026-10-17'
TREND = {'TQQQ', 'UPRO', 'UDOW', 'SSO', 'TNA'}
MODEL = {'live': 'A0 always levered (as built)', 'draft': 'T200 SPY>200d -> cash [trend only]'}


def composer_bt(name, tree, refresh):
    p = os.path.join(D, f'bt_{name}.json')
    if os.path.exists(p) and not refresh:
        return json.load(open(p))
    t = dict(tree)
    t.setdefault('id', str(uuid.uuid4()))
    bt = cl.backtest_tree(t, start=START, end=END)
    json.dump(bt, open(p, 'w'))
    return bt


def parse_bt(bt):
    days, vals = cl.equity_curve(bt)
    eq = {cl.epoch_day_to_date(d).isoformat(): v for d, v in zip(days, vals)}
    raw = bt.get('tdvm_weights') or {}
    hold = {}
    if raw:
        first = next(iter(raw))
        if first.isdigit():                       # {day: {ticker: w}}
            for d, m in raw.items():
                hold[cl.epoch_day_to_date(int(d)).isoformat()] = {t: x for t, x in m.items() if x}
        else:                                     # {ticker: {day: w}}
            for t, m in raw.items():
                for d, x in m.items():
                    if x:
                        hold.setdefault(cl.epoch_day_to_date(int(d)).isoformat(), {})[t] = x
    return eq, hold


def rets(eq):
    ds = sorted(eq)
    return {ds[i]: eq[ds[i]] / eq[ds[i - 1]] - 1 for i in range(1, len(ds)) if eq[ds[i - 1]] > 0}


def stats(r, ds):
    x = [r[d] for d in ds]
    cum = math.prod(1 + v for v in x)
    ex = [v - lg.gs.cash.get(d, 0.0) for v, d in zip(x, ds)]
    mu = sum(ex) / len(ex)
    sd = math.sqrt(sum((e - mu) ** 2 for e in ex) / (len(ex) - 1))
    w = pk = 1.0
    mdd = 0.0
    for v in x:
        w *= 1 + v
        pk = max(pk, w)
        mdd = max(mdd, 1 - w / pk)
    return {'cagr': cum ** (252 / len(x)) - 1, 'sharpe': mu / sd * math.sqrt(252), 'maxdd': mdd, 'cum': cum, 'n': len(x)}


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def top(h):
    """HG holds one asset at a time; the ticker with the largest weight."""
    return max(h, key=h.get) if h else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refresh', action='store_true')
    a = ap.parse_args()
    trees = {'live': json.load(open(os.path.join(D, 'hg_live_tree_at_build.json'))),
             'draft': json.load(open(os.path.join(D, 'hg_gate_draft_tree.json')))}
    C = {}
    for k, t in trees.items():
        bt = composer_bt(k, t, a.refresh)
        eq, hold = parse_bt(bt)
        C[k] = {'eq': eq, 'hold': hold, 'stats': bt.get('stats', {}), 'warn': bt.get('data_warnings')}
        ds = sorted(eq)
        print(f'Composer {k:5s} {ds[0]}..{ds[-1]} {len(ds)} days; holdings days {len(hold)}; '
              f"stats CAGR {bt['stats'].get('annualized_rate_of_return')} sharpe {bt['stats'].get('sharpe_ratio')} "
              f"maxDD {bt['stats'].get('max_drawdown')}; warnings {bt.get('data_warnings')}")
    # model
    J = json.load(open(os.path.join(lg.OUT, 'levgate.json')))
    A = J['panels']['A']['HG']['series_keep']
    M = {k: A[v] for k, v in MODEL.items()}
    base = json.load(open(os.path.join(lg.OUT, 'base_A.json')))['HG']
    days, hold = base['days'], base['hold']
    # model holdings hold[d] earn day d (decided at the prior close); the gate for them is read at that prior close.
    # Composer's tdvm_weights[d] are the holdings decided at the close of d, so Composer day d pairs with hold[d+1].
    spy = lg.gs.yh('SPY')
    ma = lg.ma_series(spy, 200)
    gate_on = {d: spy[d] > ma[d] for d in days if d in ma}
    prev = {days[i]: days[i - 1] for i in range(1, len(days))}
    m_hold = {'live': {d: hold[d] for d in days[1:]},
              'draft': {d: ({'BIL': 1.0} if (not gate_on[prev[d]] and top(hold[d]) in TREND) else hold[d]) for d in days[1:]}}
    # diagnostic: the same gate on the unadjusted close (Composer's price convention is not documented)
    o = json.load(open(f"{lg.gs.SP}/yh/SPY.json"))
    close = dict(zip(o['dates'], o['close']))
    ma_c = lg.ma_series(close, 200)
    gate_on_close = {d: close[d] > ma_c[d] for d in days if d in ma_c}
    out = {'start': START, 'end': END}
    for k in ('live', 'draft'):
        cr, mr = rets(C[k]['eq']), M[k]
        ds = sorted(set(cr) & set(mr))
        ds = [d for d in ds if d >= '2015-06-02']
        sc, sm = stats(cr, ds), stats(mr, ds)
        c = corr([cr[d] for d in ds], [mr[d] for d in ds])
        drift = (math.log(sc['cum']) - math.log(sm['cum'])) / (len(ds) / 252)
        # holdings match at offsets -1, 0, +1 (Composer day d vs model decision day d+off)
        ch, mh = C[k]['hold'], m_hold[k]
        match = {}
        for off in (-1, 0, 1):
            pairs = [(d, days[days.index(d) + off]) for d in sorted(ch) if d in days and 0 <= days.index(d) + off < len(days) and days[days.index(d) + off] in mh]
            same = sum(1 for d, e in pairs if top(ch[d]) == top(mh[e]))
            match[off] = (same, len(pairs))
        best = max(match, key=lambda o: match[o][0] / max(1, match[o][1]))
        mism = [(d, top(ch[d]), top(mh[days[days.index(d) + best]])) for d in sorted(ch)
                if d in days and 0 <= days.index(d) + best < len(days) and days[days.index(d) + best] in mh
                and top(ch[d]) != top(mh[days[days.index(d) + best]])]
        out[k] = {'common_days': len(ds), 'first': ds[0], 'last': ds[-1], 'corr': c, 'drift': drift,
                  'composer': sc, 'model': sm, 'composer_stats': C[k]['stats'], 'match': {str(o): v for o, v in match.items()},
                  'best_offset': best, 'mismatch_days': mism[:400], 'n_mismatch': len(mism)}
        print(f"\n{k}: {len(ds)} common days {ds[0]}..{ds[-1]}  corr {c:.4f}  drift Composer-model {drift * 100:+.2f}%/yr")
        print(f"  Composer CAGR {sc['cagr']:+.1%} Sharpe {sc['sharpe']:.2f} DD {sc['maxdd']:.1%} | model CAGR {sm['cagr']:+.1%} Sharpe {sm['sharpe']:.2f} DD {sm['maxdd']:.1%}")
        print('  holdings match by offset:', {o: f'{s}/{n} = {s / max(1, n):.3%}' for o, (s, n) in match.items()}, 'best', best)
        print('  first mismatches:', mism[:12])
    # gate days: Composer draft in BIL while Composer live holds a trend basket, vs the model's gate
    ch_l, ch_d = C['live']['hold'], C['draft']['hold']
    comp_off = sorted(d for d in ch_d if d in ch_l and top(ch_l[d]) in TREND and top(ch_d[d]) == 'BIL')
    comp_trend = sorted(d for d in ch_l if top(ch_l[d]) in TREND)
    nxt = {days[i - 1]: days[i] for i in range(1, len(days))}
    model_trend = sorted(d for d in days[:-1] if top(hold[nxt[d]]) in TREND)          # decision days
    model_off = sorted(d for d in model_trend if not gate_on[d])
    model_off_close = sorted(d for d in model_trend if not gate_on_close[d])
    both = set(comp_off) & set(model_off)
    print(f"\ngate: Composer draft de-levers on {len(comp_off)} of {len(comp_trend)} trend days; model on {len(model_off)} of {len(model_trend)}; "
          f"in both {len(both)}; Composer only {sorted(set(comp_off) - set(model_off))[:15]}; model only {sorted(set(model_off) - set(comp_off))[:15]}")
    print(f"      with the gate on the unadjusted close: model off {len(model_off_close)}, in both {len(set(comp_off) & set(model_off_close))}")
    out['gate'] = {'composer_off': comp_off, 'model_off': model_off, 'model_off_close': model_off_close,
                   'composer_trend_days': len(comp_trend), 'model_trend_days': len(model_trend),
                   'spy_vs_200d': {d: round(spy[d] / ma[d] - 1, 5) for d in days if d in ma}}
    # chart data: cumulative curves on the common calendar
    ds = sorted(set(rets(C['live']['eq'])) & set(M['live']) & set(rets(C['draft']['eq'])) & set(M['draft']))
    curves = {}
    for lab, r in (('composer live', rets(C['live']['eq'])), ('model live', M['live']), ('composer draft', rets(C['draft']['eq'])), ('model draft', M['draft'])):
        v, w = 1.0, []
        for d in ds:
            v *= 1 + r[d]
            w.append(round(v, 4))
        curves[lab] = w
    out['chart'] = {'dates': ds, 'curves': curves}
    json.dump(out, open(os.path.join(D, 'fidelity.json'), 'w'))
    print('\nsaved', os.path.join(D, 'fidelity.json'))


if __name__ == '__main__':
    main()
