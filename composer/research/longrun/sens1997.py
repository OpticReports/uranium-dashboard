"""Sensitivity of the 1997 book backtest (book1997.py) to the proxy and rule choices the counter-agent
flagged (2026-10-20), each a single change against the main case (VIX mode ts_synth):
  pregate     HG without its 200-day gate (the gate was chosen on this same history, add. 40)
  const50     the KMLM switcher's managed-futures RSI pinned at 50 before RYMFX exists (2007-02-22)
  mfall       the trend proxy in place of RYMFX through 2020 (KMLM itself from 2020-12)
  uvxy15pre   UVXY at today's 1.5x (not its original 2x) before its 2011 launch
  uvxy15      UVXY at 1.5x through 2018-02-27 (today's terms throughout)
plus, for every variant, the book rule: the 40% cap reset at the next close (POLICY Op 5, main), two closes
later, a 39.5% / 41% cap, no cap (pure drift), and daily rebalancing to 29/29/27/15.
2x -> 1.5x on a daily-reset fund: r' = 0.75 r + 0.25 T-bill.
usage: sens1997.py VARIANT    (writes long1997/sens_<variant>.json; 'report' combines them)"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import book1997 as bk   # noqa: E402

lp, lg = bk.lp, bk.lg
OUT = bk.OUT
TARGET = lg.TARGET
PRE_GATE = os.path.join(HERE, '..', '..', 'fixtures', 'hg-live-pre-gate-2026-10-18.raw.json')
BOOK_RULES = [('cap 40%, reset next close (main)', 0.40, 1), ('cap 40%, reset two closes later', 0.40, 2), ('cap 39.5%', 0.395, 1),
              ('cap 41%', 0.41, 1), ('no cap (pure drift)', None, 1), ('daily rebalance to targets', 'daily', 0)]


class SimConst(lg.SimW):
    """the KMLM fund's RSI pinned at 50 before RYMFX exists"""
    def ind(self, fn, tick, window, day):
        if tick == 'KMLM' and fn == 'relative-strength-index' and day < '2007-02-22':
            return 50.0
        return lg.SimW.ind(self, fn, tick, window, day)


def book(eng, days, cap=0.40, lag=1):
    if cap == 'daily':
        return {d: sum(TARGET[e] * eng[e].get(d, 0.0) for e in TARGET) for d in days}
    w, out, pending = dict(TARGET), {}, None
    for d in days:
        r = sum(w[e] * eng[e].get(d, 0.0) for e in w)
        out[d] = r
        w = {e: w[e] * (1 + eng[e].get(d, 0.0)) / (1 + r) for e in w}
        if pending is not None:
            pending -= 1
            if pending == 0:
                w, pending = dict(TARGET), None
        if cap is not None and pending is None and max(w.values()) > cap:
            pending = lag
    return out


def summary(eng, days):
    rows = {}
    for lab, cap, lag in BOOK_RULES:
        b = book(eng, days, cap, lag)
        m = math.prod(1 + b[d] for d in days)
        m1 = math.prod(1 + b[d] for d in days if d <= '2014-12-31')
        w, pk, mdd = 1.0, 1.0, 0.0
        for d in days:
            w *= 1 + b[d]
            pk = max(pk, w)
            mdd = max(mdd, 1 - w / pk)
        rows[lab] = {'final': bk.START_VALUE * m, 'end2014': bk.START_VALUE * m1, 'cagr_9714': m1 ** (1 / 18) - 1, 'maxdd': mdd}
    return rows


def run_variant(v):
    E0 = json.load(open(os.path.join(OUT, 'engines_ts_synth.json')))
    eng = {e: E0[e]['rets'] for e in bk.ENGINES}
    end = E0['HG']['days'][-1]
    if v != 'baseline':
        P, _ = lp.build_long_prices('ts_synth')
        T = bk.trees()
        sim, rerun = lg.SimW, []
        if v == 'pregate':
            with open(PRE_GATE) as f:
                T['HG'] = json.load(f)
            rerun = ['HG']
        elif v == 'const50':
            sim, rerun = SimConst, ['KMLM', 'SLEEVE']
        elif v == 'mfall':
            P['KMLM'] = lp.splice(lp.yh('KMLM'), P['MFPROXY'])
            rerun = ['KMLM', 'SLEEVE']
        elif v in ('uvxy15pre', 'uvxy15'):
            cut = '2011-10-04' if v == 'uvxy15pre' else '2018-02-28'
            ru = lp.rets_of(P['UVXY'])
            P['UVXY'] = lp.curve_from({d: (0.75 * r + 0.25 * lp.cash.get(d, 0.0) if d < cut else r) for d, r in ru.items()})
            rerun = list(bk.ENGINES)
        s = sim(P, rsi_method='wilder')
        for e in rerun:
            tk = lg.tree_tickers(T[e])
            days = lg.common_days(P, tk, bk.RUN0, end)
            r, h = lg.run_tree(s, T[e], days)
            eng[e] = bk.composer_equiv(r, h, days, e)
            print(f'  {v} {e} rerun {days[0]}..{days[-1]}', flush=True)
    days = sorted(set().union(*[set(x) for x in eng.values()]))
    days = [d for d in days if bk.BOOK0 <= d <= end]
    res = {'variant': v, 'rules': summary(eng, days),
           'engine_cagr_9714': {e: math.prod(1 + eng[e].get(d, 0.0) for d in days if d <= '2014-12-31') ** (1 / 18) - 1 for e in bk.ENGINES}}
    json.dump(res, open(os.path.join(OUT, f'sens_{v}.json'), 'w'), indent=1)
    m = res['rules']['cap 40%, reset next close (main)']
    print(f"{v:10s} final ${m['final'] / 1e9:6.1f}B  end-2014 ${m['end2014'] / 1e6:5.1f}M  1997-2014 {m['cagr_9714']:+.1%}  maxDD {m['maxdd']:.1%}", flush=True)


def report():
    out = {}
    for v in ('baseline', 'pregate', 'const50', 'mfall', 'uvxy15pre', 'uvxy15'):
        p = os.path.join(OUT, f'sens_{v}.json')
        if os.path.exists(p):
            out[v] = json.load(open(p))
    for v, r in out.items():
        print(v.ljust(10), ' | '.join(f"{lab[:14]}: ${x['final'] / 1e9:.1f}B {x['cagr_9714']:+.1%}" for lab, x in r['rules'].items()))
    json.dump(out, open(os.path.join(OUT, 'sens1997.json'), 'w'), indent=1)


if __name__ == '__main__':
    report() if sys.argv[1] == 'report' else run_variant(sys.argv[1])
