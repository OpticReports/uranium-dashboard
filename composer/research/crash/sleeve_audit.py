#!/usr/bin/env python3
"""Crash Convexity Sleeve audit, 2026-11-05 (report-only; nothing traded, nothing on Composer touched).

Owner question (11-05): the sleeve (nNdBk7hc5NiBzeRvbI5T, $81.7k, POLICY Op 1 = 10% of the family's
crash-exposed assets, owner decision 2026-07-16) sat 100% in BOXX through a SPY -4.4% / SOXL -39% / VIX 28
session and the pre-close preview called it "firm: no change".
  (a) what its triggers need to leave BOXX, and how far each was from firing at the 11-05 close;
  (b) what it did on every SPY <= -3% (and <= -4%) day since 2015-06 and on the synthetic path since 1995,
      and across the known episodes;
  (c) is it convex: downside vs upside beta to SPY, crash-day payoff, calm-period carry, share of days parked.

Inputs (read-only):
  fixtures/approved/manifest.json + sleeve-yHJkdePZ.json   the approved tree, evaluated by scripts/shadow_runner.py
  <SC>/study3/yh2y.json          Yahoo adjusted closes, 2 years, every tree ticker (+SPY, BIL, VIXM, VXZ, ^VIX,
                                 ^VIX3M), fetched 2026-11-05 16:50 ET with shadow_runner.fetch_prices; refetched
                                 with --refresh-yahoo. This is the basis of the 11-05 trigger table.
  <SC>/overnight/daily.json      SPY / BOXX / BIL / VIXM / VXZ bars 2006..2026-11-05 (its 11-05 row is an 11:45 ET
                                 snapshot, not the close: SPY 744.45 there vs 733.00 at 16:00; replaced by yh2y)
  <SC>/crash/yh/*.json           Yahoo histories: SPY 1993+ (the pre-2006 SPY days), ^IRX / BIL / BOXX (the cash
                                 line), the held funds' own returns (edge section), RYMFX
  <SC>/long1997/engines_ts_synth.json   the sleeve's daily path 1995-06..2026-11-04 from research/longrun/book1997.py
                                 (the live tree on the long panel of long_panel.py, Composer-equivalent costs):
                                 rets[d] = return earned on d, hold[d] = weights earning on d (decided at close d-1)
  results/monitor/shadow-ledger.jsonl   Composer's live holdings per session (path validation)
Writes composer/results/sleeve-audit-2026-11-05.json. Chart: make_sleeve_chart.py.

usage: sleeve_audit.py [--refresh-yahoo]
"""
import datetime
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'scripts'))
import shadow_runner as sr  # noqa: E402

SC = os.environ.get('STUDY_DATA', '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad')
YH2Y = f'{SC}/study3/yh2y.json'
DAILY = f'{SC}/overnight/daily.json'
YH = f'{SC}/crash/yh'
ENGINES = f'{SC}/long1997/engines_ts_synth.json'
LEDGER = os.path.join(HERE, '..', '..', 'results', 'monitor', 'shadow-ledger.jsonl')
OUT = os.path.join(HERE, '..', '..', 'results', 'sleeve-audit-2026-11-05.json')
D_LIVE = '2026-11-05'
REAL_FROM = '2015-06-01'            # "since 2015-06": LABD exists; KMLM <- RYMFX until 2020-12-02; BOXX = BIL
PATH_FROM = '1995-06-02'
CASH = ('BOXX', 'BIL')
FRONTRUN = {'UVXY', 'SVXY', 'SOXL', 'SOXS', 'UGL', 'TQQQ', 'SPXL', 'KIE', 'TMF'}    # the FrontrunBonds half's legs
INVERSE = {'LABD', 'TMV'}                                                           # the InverseHold half's legs
EPISODES = [  # (label, first return day, last return day): returns compound from the close before the first day
    ('2015-08-24 flash crash', '2015-08-18', '2015-08-25'),
    ('2018-02-05 Volmageddon', '2018-01-29', '2018-02-08'),
    ('2018-12 selloff', '2018-12-03', '2018-12-24'),
    ('2020 COVID 02-19..03-23', '2020-02-20', '2020-03-23'),
    ('2022 bear 01-03..10-12', '2022-01-04', '2022-10-12'),
    ('2024-08-05 yen unwind', '2024-08-01', '2024-08-05'),
    ('2025-04-02..04-08 tariffs', '2025-04-03', '2025-04-08'),
    ('2026-11-05', '2026-11-05', '2026-11-05'),
]
WORDS = [
    "Two halves of 50%, re-evaluated at every close (daily rebalance). Nothing in the tree reads VIX, VIX3M, SPY or any "
    "equity index: the triggers are one-day shocks in bond and credit ETFs and RSI extremes in a few sector ETFs.",
    "InverseHold (50%): gate RSI(IEF,8) < RSI(PSQ,45): the 7-10y Treasury ETF must be weaker on an 8-day RSI than the "
    "45-day RSI of the inverse-Nasdaq fund, i.e. bonds selling off while the inverse-equity trend is strong (a 2022-type "
    "tape). Gate open: 25% LABD (-3x biotech) if RSI(LABD,20) < RSI(KMLM,10) else BOXX, and 25% TMV (-3x long Treasuries) "
    "if RSI(TMV,20) < RSI(KMLM,10) else BOXX. Gate closed: 50% BOXX. A flight-to-quality crash (bonds up) pushes IEF's RSI "
    "up and the gate further from opening.",
    "FrontrunBonds (50%): a cascade tested in order, the first true condition picks the leg, usually the WORST one-day "
    "performer of a short list (a mean-reversion buy), and the next close re-tests everything: HYG 1d > +1.75% or TLT 1d "
    "> +6% or TLT 1d < -3.5% -> worst-1d of UVXY/SVXY/SOXL; HYG 1d < -1.75% -> worst of SVXY/SOXS/UGL; SHY 1d < -0.33% -> "
    "UVXY; SHY 1d > +0.5% -> UVXY (SVXY above +0.6%); TMF 1d > +10.5% -> UVXY; TMF 1d < -7.5% -> SVXY; RSI(CORP,15) < 23 "
    "or RSI(CORP,16) > 80 -> worst of SVXY/SOXL; RSI(PEJ,14) > 75.6 -> worst of UVXY/TQQQ/SPXL; RSI(KIE,10) > 78 -> worst "
    "of UVXY/SOXL/TQQQ; RSI(KIE,10) < 21 -> worst of SOXL/TQQQ; KIE 1d < -6% -> worst of KIE/SOXL/TQQQ; KIE 1d > +3.45% -> "
    "UVXY+SOXS; RSI(KIE,14) < 27 -> KIE+SOXL; LQD 1d > +1.5% or < -4% -> worst of UVXY/SOXL; RSI(LQD,12) > 79.5 -> SOXL; "
    "RSI(LQD,14) < 25 -> worst of SVXY/TMF; else BOXX.",
    "So the sleeve leaves BOXX when BONDS move, not when stocks do. On an equity crash day with calm Treasuries and "
    "credit (11-05: HYG -0.3%, TLT +0.2%, SHY +0.2%, LQD +0.2%) every condition reads false and both halves stay in "
    "BOXX; had a FrontrunBonds trigger fired at the 11-05 close, most branches would have bought SOXL (the worst "
    "one-day performer, -39%), a dip-buy, not a hedge.",
]


# ------------------------------------------------------------------ helpers
def yh(t):
    with open(f"{YH}/{t.replace('^', '_').replace('=', '_')}.json") as f:
        o = json.load(f)
    return {d: v for d, v in zip(o['dates'], o['adjclose']) if v}


def rets_of(px):
    ds = sorted(px)
    return {ds[i]: px[ds[i]] / px[ds[i - 1]] - 1 for i in range(1, len(ds))}


def curve_from(r):
    out, v = {}, 1.0
    for d in sorted(r):
        v *= 1 + r[d]
        out[d] = v
    return out


def splice(real, synth):
    """real where it exists, synthetic (rescaled) before its first date"""
    first = min(real)
    out = {d: v for d, v in synth.items() if d < first}
    if out:
        k = real[first] / synth[first] if first in synth else real[first] / synth[max(out)]
        out = {d: v * k for d, v in out.items()}
    out.update(real)
    return out


def prod(xs):
    v = 1.0
    for x in xs:
        v *= 1 + x
    return v - 1


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def sd(xs):
    if len(xs) < 2:
        return None
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def tstat(xs):
    s = sd(xs)
    return mean(xs) / s * math.sqrt(len(xs)) if s else None


def tdiff(a, b):
    sa, sb = sd(a), sd(b)
    if sa is None or sb is None:
        return None
    se = math.sqrt(sa ** 2 / len(a) + sb ** 2 / len(b))
    return (mean(a) - mean(b)) / se if se else None


def median(xs):
    s = sorted(xs)
    n = len(s)
    return None if not n else (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)


def ols(x, y):
    """y = a + b x: (a, b, t_b, r, n)"""
    n = len(x)
    if n < 3:
        return None
    mx, my = mean(x), mean(y)
    sxx = sum((u - mx) ** 2 for u in x)
    sxy = sum((u - mx) * (v - my) for u, v in zip(x, y))
    syy = sum((v - my) ** 2 for v in y)
    b = sxy / sxx
    a = my - b * mx
    res = sum((v - a - b * u) ** 2 for u, v in zip(x, y))
    se = math.sqrt(res / (n - 2) / sxx) if n > 2 and sxx else None
    return {'alpha': a, 'beta': b, 't': b / se if se else None, 'r': sxy / math.sqrt(sxx * syy) if syy else None, 'n': n}


def fmt_w(w):
    return sr.fmt_w(w)


def is_cash(w):
    return all(t in CASH for t in w)


def cagr(r, ds):
    v = prod([r.get(d, 0.0) for d in ds])
    yrs = (datetime.date.fromisoformat(ds[-1]) - datetime.date.fromisoformat(ds[0])).days / 365.25
    return (1 + v) ** (1 / yrs) - 1 if yrs > 0 else None


def maxdd(r, ds):
    v = pk = 1.0
    dd = 0.0
    for d in ds:
        v *= 1 + r.get(d, 0.0)
        pk = max(pk, v)
        dd = max(dd, 1 - v / pk)
    return dd


# ------------------------------------------------------------------ data
def load_yahoo(refresh=False):
    if os.path.exists(YH2Y) and not refresh:
        with open(YH2Y) as f:
            return json.load(f)
    cfg = sr.load_manifest()['SLEEVE']
    tk = sorted(sr.tree_tickers(sr.load_tree(cfg['eras'][-1])) | {'SPY', 'BIL', '^VIX', '^VIX3M', 'VIXM', 'VXZ'})
    now = datetime.datetime.now(datetime.timezone.utc)
    adj, raw, bad = sr.fetch_prices(tk, now, '2y')
    if bad:
        raise RuntimeError(f'Yahoo failed for {bad}')
    os.makedirs(os.path.dirname(YH2Y), exist_ok=True)
    out = {'fetched': now.isoformat(), 'adj': adj, 'raw': raw, 'bad': bad}
    with open(YH2Y, 'w') as f:
        json.dump(out, f)
    return out


def spy_returns(y2):
    """SPY daily total returns: Yahoo adjusted closes; daily.json 2006..11-04, crash/yh before 2006, yh2y for 11-05"""
    with open(DAILY) as f:
        dj = json.load(f)
    r_old = rets_of(yh('SPY'))
    px = {d: v['a'] for d, v in dj['SPY']['rows'].items() if d <= '2026-11-04'}
    r_new = rets_of(px)
    r = {d: v for d, v in r_old.items() if d < min(r_new)}
    r.update(r_new)
    p = y2['adj']['SPY']
    r[D_LIVE] = p[D_LIVE] / p['2026-11-04'] - 1
    return r, dj


def cash_line(y2):
    """BOXX (2022-12-28+) <- BIL (2007-05-30+) <- 13-week T-bill accrual (^IRX): the engine's own BOXX stand-in"""
    with open(f'{YH}/_IRX.json') as f:
        irx = json.load(f)
    acc = curve_from({d: (c / 100) / 252 for d, c in zip(irx['dates'], irx['close']) if c is not None})
    boxx = yh('BOXX')
    boxx[D_LIVE] = y2['adj']['BOXX'][D_LIVE] * boxx['2026-11-04'] / y2['adj']['BOXX']['2026-11-04']
    return rets_of(splice(boxx, splice(yh('BIL'), acc)))


def launch_dates(tickers):
    out = {}
    for t in tickers:
        try:
            out[t] = min(yh(t))
        except FileNotFoundError:
            out[t] = None
    return out


# ------------------------------------------------------------------ 1. the rules and the 11-05 trigger table
def cond_label(node):
    fn, t, w = node['lhs-fn'], node['lhs-val'], sr.window(node, 'lhs')
    lhs = f"{t} 1-day return" if fn == 'cumulative-return' and w == 1 else f"{sr.SHORT[fn]}({t},{w})"
    op = '>' if node['comparator'] == 'gt' else '<'
    if node.get('rhs-fixed-value?'):
        thr = float(node['rhs-val'])
        rhs = f"{thr:+g}%" if fn == 'cumulative-return' else f"{thr:g}"
    else:
        rhs = f"{sr.SHORT[node['rhs-fn']]}({node['rhs-val']},{sr.window(node, 'rhs')})"
    return f"{lhs} {op} {rhs}"


def branch_weights(sim, if_child, d):
    out = {}
    for c in if_child.get('children') or []:
        sim.weights(c, d, 1.0, out)
    return sr.norm(out)


def flip_move(sim, node, d, ticker, limit=0.6):
    """smallest fractional move of `ticker`'s close on d that makes the condition true (None within +-limit)"""
    p0 = sim.p[ticker][d]

    def test(x):
        sim.p[ticker][d] = p0 * (1 + x)
        sim.cache = {}
        try:
            return sim.cond(node, d)
        finally:
            sim.p[ticker][d] = p0
    best = None
    for sign in (1, -1):
        lo, hi, x = 0.0, None, 0.0005
        while x <= limit:
            if test(sign * x):
                hi = x
                break
            lo, x = x, x * 1.2
        if hi is not None:
            for _ in range(30):
                mid = (lo + hi) / 2
                if test(sign * mid):
                    hi = mid
                else:
                    lo = mid
            if best is None or hi < abs(best):
                best = sign * hi
    sim.cache = {}
    return best


def indicator_series(px, fn, w):
    """{date: indicator} over a whole price series: 1-day/w-day cumulative return in %, or Wilder RSI seeded on the
    first w changes (as the long panel's simulator and shadow_runner.indicator read it over all history)"""
    ds = sorted(px)
    s = [px[d] for d in ds]
    out = {}
    if fn == 'cumulative-return':
        for i in range(w, len(ds)):
            out[ds[i]] = (s[i] / s[i - w] - 1) * 100
        return out
    if fn != 'relative-strength-index':
        raise ValueError(fn)
    dd = [s[i] - s[i - 1] for i in range(1, len(s))]
    if len(dd) < w:
        return out
    ag = sum(max(x, 0) for x in dd[:w]) / w
    al = sum(max(-x, 0) for x in dd[:w]) / w
    out[ds[w]] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(w, len(dd)):
        ag = (ag * (w - 1) + max(dd[i], 0)) / w
        al = (al * (w - 1) + max(-dd[i], 0)) / w
        out[ds[i + 1]] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def fire_counts(rows, P2, r_spy, lo=REAL_FROM, hi=D_LIVE):
    """how often each condition of the trigger table read TRUE on its own (cascade order ignored) 2015-06..11-05, on
    the real series (KMLM <- RYMFX before 2020-12-02), and on the SPY <= -3% / -4% days of that window"""
    px = {}

    def series(t):
        if t not in px:
            p = yh(t)
            if t == 'KMLM':
                p = splice(p, yh('RYMFX'))
            if t in P2 and D_LIVE in P2[t] and '2026-11-04' in p:
                p[D_LIVE] = P2[t][D_LIVE] * p['2026-11-04'] / P2[t]['2026-11-04']
            px[t] = p
        return px[t]
    crash3 = {d for d in r_spy if lo <= d <= hi and r_spy[d] <= -0.03}
    crash4 = {d for d in crash3 if r_spy[d] <= -0.04}
    for r in rows:
        fn, t, w = r['lhs']
        a = indicator_series(series(t), fn, w)
        if r['rhs']:
            fn2, t2, w2 = r['rhs']
            b = indicator_series(series(t2), fn2, w2)
        ds = [d for d in a if lo <= d <= hi and (not r['rhs'] or d in b)]
        op = sr.OPS['gt' if r['op'] == '>' else 'lt']
        fired = [d for d in ds if op(a[d], b[d] if r['rhs'] else r['threshold'])]
        by_year = {}
        for d in fired:
            by_year[d[:4]] = by_year.get(d[:4], 0) + 1
        r['fires'] = {'from': ds[0] if ds else None, 'n_days': len(ds), 'n_true': len(fired), 'share': len(fired) / len(ds) if ds else None,
                      'last': fired[-1] if fired else None, 'by_year': by_year,
                      'on_crash3': sum(1 for d in fired if d in crash3), 'of_crash3': sum(1 for d in ds if d in crash3),
                      'on_crash4': sum(1 for d in fired if d in crash4), 'of_crash4': sum(1 for d in ds if d in crash4),
                      'crash3_dates': [d for d in fired if d in crash3]}
    return rows


def trigger_table(prices, tree, d):
    """every condition on the evaluated path at the close of d: live value, threshold, distance, the one-day move
    of the left-hand ticker that flips it, and what the sleeve would hold had it fired (all else as it closed)"""
    sim, target, trace = sr.run_engine(prices, tree, d)
    if target is None:
        raise RuntimeError(f'engine unavailable on {d}: {trace}')
    rows = []

    def walk(node, w, half):
        step = node['step']
        kids = node.get('children') or []
        if step == 'if':
            fired = None
            for k in kids:
                if k.get('is-else-condition?'):
                    continue
                res = sim.cond(k, d)
                lhs = (k['lhs-fn'], k['lhs-val'], sr.window(k, 'lhs'))
                l = sim.ind(*lhs, d)
                if k.get('rhs-fixed-value?'):
                    rhs, r = None, float(k['rhs-val'])
                else:
                    rhs = (k['rhs-fn'], k['rhs-val'], sr.window(k, 'rhs'))
                    r = sim.ind(*rhs, d)
                gt = k['comparator'] == 'gt'
                dist = (r - l) if gt else (l - r)          # how far the left side must move, in indicator units
                bw = branch_weights(sim, k, d)
                half_now = {}
                sim.weights(half[0], d, 1.0, half_now)
                half_now = sr.norm(half_now)
                would = {t: x for t, x in target.items()}
                for t, x in half_now.items():
                    would[t] = would.get(t, 0.0) - x * half[1]
                for t, x in bw.items():
                    would[t] = would.get(t, 0.0) + x * half[1]
                would = {t: round(x, 4) for t, x in would.items() if x > 1e-6}
                row = {'half': half[2], 'half_weight': half[1], 'label': cond_label(k), 'lhs': lhs, 'rhs': rhs,
                       'op': '>' if gt else '<', 'value': l, 'threshold': r, 'distance': dist, 'fired': bool(res),
                       'flip_move': flip_move(sim, k, d, k['lhs-val']), 'would_hold': would,
                       'unit': 'pp' if k['lhs-fn'] == 'cumulative-return' else ('RSI pts' if 'relative' in k['lhs-fn'] else 'x')}
                if rhs:
                    row['flip_move_rhs'] = flip_move(sim, k, d, k['rhs-val'])
                rows.append(row)
                if res:
                    fired = k
                    break
            if fired is None:
                fired = next((k for k in kids if k.get('is-else-condition?')), {})
            for k in fired.get('children') or []:
                walk(k, w, half)
        elif step in ('root', 'group'):
            for k in kids:
                walk(k, w, half)
        elif step == 'wt-cash-equal':
            for k in kids:
                walk(k, w / len(kids), half)
        elif step == 'wt-cash-specified':
            ws = [sr.weight_of(k) for k in kids]
            tot = sum(ws)
            for k, x in zip(kids, ws):
                walk(k, w * x / tot, (k, x / tot, k.get('name') or k['id'][:8]))
    walk(tree, 1.0, (tree, 1.0, 'root'))
    # the InverseHold gate's inner tests, read with the gate forced open (not on the path today)
    inner = []
    for t, w in (('LABD', 20), ('TMV', 20)):
        a, b = sim.ind('relative-strength-index', t, w, d), sim.ind('relative-strength-index', 'KMLM', 10, d)
        inner.append({'label': f'RSI({t},{w}) < RSI(KMLM,10)', 'value': a, 'threshold': b, 'fired': a < b,
                      'holds': t if a < b else 'BOXX'})
    return rows, inner, target, trace


# ------------------------------------------------------------------ main
def main():
    refresh = '--refresh-yahoo' in sys.argv
    y2 = load_yahoo(refresh)
    P2 = y2['adj']
    cfg = sr.load_manifest()['SLEEVE']
    era = cfg['eras'][-1]
    tree = sr.load_tree(era)
    rows, inner, target, trace = trigger_table(P2, tree, D_LIVE)
    r_spy, dj = spy_returns(y2)
    rows = fire_counts(rows, P2, r_spy)
    r_cash = cash_line(y2)
    live = {t: P2[t][D_LIVE] / P2[t]['2026-11-04'] - 1 for t in P2 if D_LIVE in P2[t] and '2026-11-04' in P2[t]}
    vix, v3 = P2['^VIX'][D_LIVE], P2['^VIX3M'][D_LIVE]

    # the sleeve's path, plus the live 11-05 row (BOXX 100%, decided at the 11-04 close: run_engine and Composer agree)
    with open(ENGINES) as f:
        E = json.load(f)['SLEEVE']
    days, rets, hold = list(E['days']), dict(E['rets']), dict(E['hold'])
    _, t1104, _ = sr.run_engine(P2, tree, '2026-11-04')
    assert t1104 == {'BOXX': 1.0}, t1104
    hold[D_LIVE] = {'BOXX': 1.0}
    rets[D_LIVE] = live['BOXX']
    days.append(D_LIVE)
    hold_days = [d for d in days if d in hold]
    idx = {d: i for i, d in enumerate(hold_days)}
    next_hold = {hold_days[i]: hold[hold_days[i + 1]] for i in range(len(hold_days) - 1)}
    next_hold[D_LIVE] = target

    def fwd(d, k):
        i = idx[d]
        ds = hold_days[i + 1:i + 1 + k]
        return prod([rets[x] for x in ds]) if len(ds) == k else None

    held = sorted({t for w in hold.values() for t in w})
    launch = launch_dates(held + ['KMLM', 'HYG', 'IEF', 'PSQ', 'CORP', 'PEJ', 'KIE', 'LQD', 'SHY', 'TLT', 'BIL', 'BOXX'])

    def proxies(d, w):
        out = [t for t in w if t not in CASH and launch.get(t) and d < launch[t]]
        if d < launch['KMLM']:
            out.append('KMLM-signal')
        return out

    # ---- 2. crash days
    def row(d):
        w = hold[d]
        return {'date': d, 'spy': r_spy[d], 'hold': w, 'ret': rets[d], 'f1': fwd(d, 1), 'f5': fwd(d, 5), 'f10': fwd(d, 10),
                'f20': fwd(d, 20), 'next_hold': next_hold[d], 'parked': is_cash(w), 'parked_next': is_cash(next_hold[d]),
                'proxies': proxies(d, w), 'era': 'live' if d == D_LIVE else ('real-era' if d >= REAL_FROM else 'synthetic')}
    spy_days = [d for d in hold_days if d in r_spy and d >= PATH_FROM]
    crash = [row(d) for d in spy_days if r_spy[d] <= -0.03]
    ups = sorted(spy_days, key=lambda d: -r_spy[d])

    def summary(rs):
        if not rs:
            return {'n': 0}
        g = lambda k: [x[k] for x in rs if x[k] is not None]   # noqa: E731
        pos = lambda k: (sum(1 for v in g(k) if v > 0) / len(g(k))) if g(k) else None   # noqa: E731
        parked = [x for x in rs if x['parked']]
        return {'n': len(rs), 'spy_mean': mean(g('spy')), 'ret_mean': mean(g('ret')), 'ret_median': median(g('ret')),
                'hit': sum(1 for x in rs if x['ret'] > 0) / len(rs), 'ret_t': tstat(g('ret')) if len(rs) > 2 else None,
                'ret_sum': sum(g('ret')), 'ret_min': min(g('ret')), 'ret_max': max(g('ret')),
                'f1': mean(g('f1')), 'f5': mean(g('f5')), 'f10': mean(g('f10')), 'f20': mean(g('f20')),
                'f5_median': median(g('f5')), 'f20_median': median(g('f20')), 'f5_pos': pos('f5'), 'f20_pos': pos('f20'),
                'parked_share': sum(x['parked'] for x in rs) / len(rs), 'parked_next_share': sum(x['parked_next'] for x in rs) / len(rs),
                'entered_at_close': sum(1 for x in parked if not x['parked_next']), 'parked_at_open': len(parked),
                'best': max(rs, key=lambda x: x['ret'])['date'], 'worst': min(rs, key=lambda x: x['ret'])['date']}
    crash_summary = {}
    for lab, lo in (('2015-06+', REAL_FROM), ('1995-06+', PATH_FROM), ('2024-06+ (both halves OOS, add. 4b)', '2024-06-01')):
        for thr in (-0.03, -0.04):
            crash_summary[f'{lab} SPY<={thr:.0%}'] = summary([x for x in crash if x['date'] >= lo and x['spy'] <= thr])
        if lab == '2015-06+':
            crash_summary[f'{lab} SPY<=-3% ex-2020'] = summary([x for x in crash if x['date'] >= lo and x['date'][:4] != '2020'])
            crash_summary[f'{lab} SPY<=-3% ex-2020-2022'] = summary([x for x in crash if x['date'] >= lo and x['date'][:4] not in ('2020', '2022')])
        if lab.startswith('2024'):
            continue
        crash_summary[f'{lab} SPY>=+3%'] = summary([row(d) for d in spy_days if d >= lo and r_spy[d] >= 0.03])
        top = [row(d) for d in [x for x in ups if x >= lo][:10]]
        crash_summary[f'{lab} top-10 up-days'] = summary(top)
        crash_summary[f'{lab} top-10 up-days']['days'] = [{'date': x['date'], 'spy': x['spy'], 'ret': x['ret'], 'hold': x['hold']} for x in top]
        crash_summary[f'{lab} all days'] = summary([row(d) for d in spy_days if d >= lo])

    # ---- 3. episodes
    episodes = []
    for lab, a, b in EPISODES:
        ds = [d for d in hold_days if a <= d <= b]
        ia, ib = idx[ds[0]], idx[ds[-1]]
        v = pk = 1.0
        mdd, best, worst = 0.0, None, None
        for d in ds:
            v *= 1 + rets[d]
            pk = max(pk, v)
            mdd = max(mdd, 1 - v / pk)
            if best is None or rets[d] > rets[best]:
                best = d
            if worst is None or rets[d] < rets[worst]:
                worst = d
        legs = {}
        for d in ds:
            for t, x in hold[d].items():
                if t not in CASH and (t not in legs or x > legs[t][0]):
                    legs[t] = (x, d)
        out_day = next((i for i in range(ia, ib + 1) if not is_cash(hold[hold_days[i]])), None)
        after = next((i for i in range(ib + 1, min(ib + 21, len(hold_days))) if not is_cash(hold[hold_days[i]])), None)
        episodes.append({'label': lab, 'from': ds[0], 'to': ds[-1], 'sessions': len(ds), 'spy': prod([r_spy[d] for d in ds]),
                         'sleeve': v - 1, 'sleeve_maxdd': mdd, 'best_day': {'date': best, 'ret': rets[best], 'hold': hold[best]},
                         'worst_day': {'date': worst, 'ret': rets[worst], 'hold': hold[worst]},
                         'max_leg': max(((x, t, d) for t, (x, d) in legs.items()), default=None),
                         'legs': {t: {'max_w': x, 'on': d} for t, (x, d) in legs.items()},
                         'days_to_leave_cash': None if out_day is None else out_day - ia,
                         'first_out_after_episode': None if out_day is not None or after is None else after - ib,
                         'parked_share': sum(is_cash(hold[d]) for d in ds) / len(ds),
                         'next20': prod([rets[x] for x in hold_days[ib + 1:ib + 21]]) if ib + 20 < len(hold_days) else None,
                         'spy_next20': prod([r_spy[x] for x in hold_days[ib + 1:ib + 21] if x in r_spy]) if ib + 20 < len(hold_days) else None,
                         'proxies': sorted({p for d in ds for p in proxies(d, hold[d])}),
                         'path': [[d, round(prod([rets[x] for x in ds[:k + 1]]), 5), round(prod([r_spy[x] for x in ds[:k + 1]]), 5)] for k, d in enumerate(ds)]})

    # ---- 4. convexity
    conv = {}
    for lab, lo in (('2015-06+', REAL_FROM), ('1995-06+', PATH_FROM), ('2020-12+ (all legs real)', '2020-12-02')):
        ds = [d for d in spy_days if d >= lo]
        dn = [d for d in ds if r_spy[d] < 0]
        up = [d for d in ds if r_spy[d] > 0]
        c2 = [d for d in ds if r_spy[d] <= -0.02]
        buckets = [(-1, -0.03), (-0.03, -0.02), (-0.02, -0.01), (-0.01, 0), (0, 0.01), (0.01, 0.02), (0.02, 0.03), (0.03, 1)]
        bk = []
        for a, b in buckets:
            sel = [d for d in ds if a <= r_spy[d] < b] if a < 0 else [d for d in ds if a < r_spy[d] <= b]
            bk.append({'lo': a, 'hi': b, 'n': len(sel), 'sleeve': mean([rets[d] for d in sel]) if sel else None,
                       'spy': mean([r_spy[d] for d in sel]) if sel else None, 'hit': (sum(1 for d in sel if rets[d] > 0) / len(sel)) if sel else None})
        conv[lab] = {'from': ds[0], 'to': ds[-1], 'n': len(ds),
                     'down': ols([r_spy[d] for d in dn], [rets[d] for d in dn]), 'up': ols([r_spy[d] for d in up], [rets[d] for d in up]),
                     'all': ols([r_spy[d] for d in ds], [rets[d] for d in ds]), 'spy_le_2pct': ols([r_spy[d] for d in c2], [rets[d] for d in c2]),
                     'buckets': bk, 'cagr': cagr(rets, ds), 'spy_cagr': cagr(r_spy, ds), 'cash_cagr': cagr(r_cash, ds),
                     'maxdd': maxdd(rets, ds), 'spy_maxdd': maxdd(r_spy, ds),
                     'parked_share': sum(is_cash(hold[d]) for d in ds) / len(ds),
                     'frontrun_out_share': sum(any(t in FRONTRUN for t in hold[d]) for d in ds) / len(ds),
                     'inverse_out_share': sum(any(t in INVERSE for t in hold[d]) for d in ds) / len(ds),
                     'corr_with_spy': ols([r_spy[d] for d in ds], [rets[d] for d in ds])['r']}
    years = {}
    for d in spy_days:
        y = d[:4]
        yy = years.setdefault(y, {'sleeve': 1.0, 'spy': 1.0, 'cash': 1.0, 'crash_days': 0, 'crash4_days': 0, 'min_spy': 0.0, 'parked': 0, 'n': 0})
        yy['sleeve'] *= 1 + rets[d]
        yy['spy'] *= 1 + r_spy[d]
        yy['cash'] *= 1 + r_cash.get(d, 0.0)
        yy['crash_days'] += r_spy[d] <= -0.03
        yy['crash4_days'] += r_spy[d] <= -0.04
        yy['min_spy'] = min(yy['min_spy'], r_spy[d])
        yy['parked'] += is_cash(hold[d])
        yy['n'] += 1
    for y, v in years.items():
        v['sleeve'] -= 1
        v['spy'] -= 1
        v['cash'] -= 1
        v['parked'] /= v['n']
        v['calm'] = v['crash_days'] == 0
    carry = {}
    for lab, lo in (('2015-06+', '2015'), ('1995-06+', '1995')):
        ys = {y: v for y, v in years.items() if y >= lo}
        calm = [v['sleeve'] for v in ys.values() if v['calm']]
        rough = [v['sleeve'] for v in ys.values() if not v['calm']]
        carry[lab] = {'calm_years': sorted(y for y, v in ys.items() if v['calm']), 'calm_mean': mean(calm), 'calm_median': median(calm),
                      'calm_min': min(calm) if calm else None, 'calm_geo': (prod(calm)) ** (1 / len(calm)) - 1 if calm else None,
                      'calm_spy_mean': mean([v['spy'] for v in ys.values() if v['calm']]),
                      'calm_cash_mean': mean([v['cash'] for v in ys.values() if v['calm']]),
                      'rough_years': sorted(y for y, v in ys.items() if not v['calm']), 'rough_mean': mean(rough), 'rough_median': median(rough),
                      'rough_spy_mean': mean([v['spy'] for v in ys.values() if not v['calm']])}
    # equity curves (every 5th session + the last), scatter points for the chart
    curves = {}
    for lab, lo in (('2015-06+', REAL_FROM), ('1995-06+', PATH_FROM)):
        ds = [d for d in spy_days if d >= lo]
        vs, vp, vc, pts = 1.0, 1.0, 1.0, []
        for i, d in enumerate(ds):
            vs *= 1 + rets[d]
            vp *= 1 + r_spy[d]
            vc *= 1 + r_cash.get(d, 0.0)
            if i % 5 == 0 or i == len(ds) - 1 or r_spy[d] <= -0.03:
                pts.append([d, round(vs, 5), round(vp, 5), round(vc, 5)])
        curves[lab] = pts
    sc = [d for d in spy_days if d >= REAL_FROM]
    scatter = [[round(r_spy[d], 5), round(rets[d], 5), d] for d in sc]

    # ---- 5. comparator: a static long mid-term-vol sleeve (VIXM; VXZ) on the same crash days and in calm years
    comp = {}
    for t in ('VIXM', 'VXZ'):
        px = {d: v['a'] for d, v in dj[t]['rows'].items() if d <= '2026-11-04'}
        r = rets_of(px)
        r[D_LIVE] = live[t]
        ds = [d for d in spy_days if d in r]
        cd = [d for d in ds if r_spy[d] <= -0.03]
        calm_y = [y for y, v in years.items() if v['calm'] and y >= ds[0][:4] and y != ds[0][:4]]
        by_year = {}
        for d in ds:
            by_year[d[:4]] = by_year.get(d[:4], 1.0) * (1 + r[d])
        comp[t] = {'from': ds[0], 'to': ds[-1], 'cagr': cagr(r, ds), 'maxdd': maxdd(r, ds), 'sleeve_cagr_same_window': cagr(rets, ds),
                   'crash_days': {'n': len(cd), 'mean': mean([r[d] for d in cd]), 'hit': sum(1 for d in cd if r[d] > 0) / len(cd) if cd else None,
                                  'sleeve_mean_same_days': mean([rets[d] for d in cd]), 'sleeve_hit_same_days': sum(1 for d in cd if rets[d] > 0) / len(cd) if cd else None,
                                  'f5_mean': mean([prod([r[x] for x in ds[ds.index(d) + 1:ds.index(d) + 6]]) for d in cd if ds.index(d) + 5 < len(ds)])},
                   'calm_year_mean': mean([by_year[y] - 1 for y in calm_y]) if calm_y else None, 'calm_years': calm_y,
                   'sleeve_calm_year_mean': mean([years[y]['sleeve'] for y in calm_y]) if calm_y else None,
                   'down_beta': ols([r_spy[d] for d in ds if r_spy[d] < 0], [r[d] for d in ds if r_spy[d] < 0])['beta'],
                   'up_beta': ols([r_spy[d] for d in ds if r_spy[d] > 0], [r[d] for d in ds if r_spy[d] > 0])['beta'],
                   'd1105': live[t]}

    # ---- 6. path validation: Composer's live holdings (ledger) vs the path's decision at the same close
    val = {'n': 0, 'agree': 0, 'misses': []}
    if os.path.exists(LEDGER):
        led = {r['date']: r for r in sr.read_ledger(LEDGER) if r.get('engine') == 'SLEEVE' and r.get('live')}
        for d, r in sorted(led.items()):
            if d not in next_hold or d == D_LIVE:
                continue
            lv = {('BOXX' if t == 'BIL' else t): x for t, x in r['live'].items()}
            w = next_hold[d]
            val['n'] += 1
            if sr.distance(w, lv)[0] <= 0.03:
                val['agree'] += 1
            else:
                val['misses'].append({'date': d, 'status': r.get('status'), 'live': r['live'], 'path': w})

    # ---- 7. by-products: what the sleeve's states say about the legs and about SPY (candidate edges, with mirrors)
    R = {}
    for t in held:
        if t in CASH:
            continue
        px = yh(t)
        if t in P2 and D_LIVE in P2[t]:
            px[D_LIVE] = P2[t][D_LIVE] * px['2026-11-04'] / P2[t]['2026-11-04']
        R[t] = rets_of(px)
    states = []
    OOS = '2023-04-01'      # add. 4: InverseHold's record is out of sample from ~2023-04; FrontrunBonds' from before 2024-06 (add. 4b)
    for t in sorted(R):
        lo = max(REAL_FROM, launch[t] or REAL_FROM)
        for lab, a, b in (('2015-06..2023-03 (in sample)', lo, OOS), ('2023-04+ (OOS)', OOS, '2099'), ('all', lo, '2099')):
            ds = [d for d in spy_days if a <= d < b and d >= lo and d in R[t]]
            on = [R[t][d] for d in ds if hold[d].get(t, 0) > 0]
            off = [R[t][d] for d in ds if hold[d].get(t, 0) == 0]
            if len(on) < 5:
                continue
            states.append({'ticker': t, 'window': lab, 'from': ds[0], 'to': ds[-1], 'n_on': len(on), 'mean_on': mean(on), 'hit_on': sum(1 for x in on if x > 0) / len(on), 't_on': tstat(on),
                           'n_off': len(off), 'mean_off': mean(off), 't_diff': tdiff(on, off), 'sleeve_days_share': len(on) / len(ds),
                           'leg_total': prod(on)})
    # transitions: the sleeve leaving cash (decided at close d) vs SPY's next 5 / 20 sessions; mirror: returning to cash
    def spy_fwd(d, k):
        i = idx[d]
        ds = hold_days[i + 1:i + 1 + k]
        return prod([r_spy[x] for x in ds if x in r_spy]) if len(ds) == k else None
    trans = {}
    for lab, lo in (('2015-06+', REAL_FROM), ('1995-06+', PATH_FROM)):
        ds = [d for d in spy_days if d >= lo and d != D_LIVE]
        ev = {'leave cash (any leg)': [d for d in ds if is_cash(hold[d]) and not is_cash(next_hold[d])],
              'FrontrunBonds leg on': [d for d in ds if not any(t in FRONTRUN for t in hold[d]) and any(t in FRONTRUN for t in next_hold[d])],
              'InverseHold leg on': [d for d in ds if not any(t in INVERSE for t in hold[d]) and any(t in INVERSE for t in next_hold[d])],
              'MIRROR: back to cash': [d for d in ds if not is_cash(hold[d]) and is_cash(next_hold[d])],
              'MIRROR: FrontrunBonds leg off': [d for d in ds if any(t in FRONTRUN for t in hold[d]) and not any(t in FRONTRUN for t in next_hold[d])]}
        base5 = [spy_fwd(d, 5) for d in ds]
        base20 = [spy_fwd(d, 20) for d in ds]
        base5 = [x for x in base5 if x is not None]
        base20 = [x for x in base20 if x is not None]
        out = {'unconditional': {'n': len(base5), 'spy_f5': mean(base5), 'spy_f20': mean(base20)}}
        for k, evd in ev.items():
            f5 = [spy_fwd(d, 5) for d in evd]
            f20 = [spy_fwd(d, 20) for d in evd]
            f5 = [x for x in f5 if x is not None]
            f20 = [x for x in f20 if x is not None]
            s5 = [fwd(d, 5) for d in evd]
            s5 = [x for x in s5 if x is not None]
            out[k] = {'n': len(evd), 'spy_f5': mean(f5), 'spy_f5_t_vs_uncond': tdiff(f5, base5) if len(f5) > 2 else None,
                      'spy_f20': mean(f20), 'spy_f20_t_vs_uncond': tdiff(f20, base20) if len(f20) > 2 else None,
                      'sleeve_f5': mean(s5), 'sleeve_f5_hit': (sum(1 for x in s5 if x > 0) / len(s5)) if s5 else None,
                      'spy_same_day': mean([r_spy[d] for d in evd]) if evd else None}
        trans[lab] = out
    # the crash-day signal itself: does a SPY <= -3% day say anything about the sleeve's next sessions vs any day
    crash_sig = {}
    for lab, lo in (('2015-06+', REAL_FROM), ('1995-06+', PATH_FROM)):
        cd = [x for x in crash if x['date'] >= lo and x['f5'] is not None]
        alld = [row(d) for d in spy_days if d >= lo]
        alld = [x for x in alld if x['f5'] is not None]
        crash_sig[lab] = {'n': len(cd), 'sleeve_f5_after_crash': mean([x['f5'] for x in cd]), 'sleeve_f5_any_day': mean([x['f5'] for x in alld]),
                          't': tdiff([x['f5'] for x in cd], [x['f5'] for x in alld]) if len(cd) > 2 else None,
                          'sleeve_f20_after_crash': mean([x['f20'] for x in cd if x['f20'] is not None]),
                          'sleeve_f20_any_day': mean([x['f20'] for x in alld if x['f20'] is not None])}
    edges = []
    for s in states:
        if s['window'] == 'all' and s['n_on'] >= 30 and s['t_diff'] is not None and abs(s['t_diff']) >= 2:
            oos = next((x for x in states if x['ticker'] == s['ticker'] and x['window'].endswith('(OOS)')), None)
            edges.append({'kind': 'held-leg conditional return', 'ticker': s['ticker'], 'n': s['n_on'], 'mean_on': s['mean_on'], 'mean_off': s['mean_off'],
                          't_diff': s['t_diff'], 'hit_on': s['hit_on'], 'from': s['from'], 'in_sample_to': OOS,
                          'oos': {k: oos[k] for k in ('n_on', 'mean_on', 'hit_on', 't_diff', 'mean_off')} if oos else None})
    for lab, o in trans.items():
        for k, v in o.items():
            if k == 'unconditional' or k.startswith('MIRROR') or v['n'] < 30:
                continue
            for h in ('f5', 'f20'):
                t = v.get(f'spy_{h}_t_vs_uncond')
                if t is not None and abs(t) >= 2:
                    edges.append({'kind': f'SPY after "{k}" ({lab})', 'horizon': h, 'n': v['n'], 'spy_fwd': v[f'spy_{h}'], 'uncond': o['unconditional'][f'spy_{h}'], 't': t})

    # ---- counterfactual legs on 11-05: what the sleeve would have earned had it held each leg into the session
    cf = {}
    for t in sorted(FRONTRUN | INVERSE):
        if t in live:
            w = 0.25 if t in INVERSE else 0.5
            cf[t] = {'leg_ret': live[t], 'weight': w, 'sleeve_ret': w * live[t] + (1 - w) * live['BOXX']}

    out = {
        'generated': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'symphony': cfg['symphony'], 'era': era, 'tree_name': tree.get('name'),
        'inputs': {'yahoo_2y': {'path': YH2Y, 'fetched': y2.get('fetched')}, 'daily_json': DAILY, 'engine_path': ENGINES, 'yh_cache': YH, 'ledger': LEDGER},
        'live_1105': {'spy': live['SPY'], 'soxl': live['SOXL'], 'vix': vix, 'vix3m': v3, 'vix3m_over_vix_minus_1': v3 / vix - 1,
                      'hyg': live['HYG'], 'tlt': live['TLT'], 'shy': live['SHY'], 'lqd': live['LQD'], 'tmf': live['TMF'], 'ief': live['IEF'],
                      'boxx': live['BOXX'], 'uvxy': live['UVXY'], 'svxy': live['SVXY'], 'soxs': live['SOXS'], 'labd': live['LABD'], 'tmv': live['TMV'],
                      'target_1105': target, 'decided_1104': t1104, 'sleeve_value': 81707.36, 'sleeve_holdings_live': {'BOXX': 0.999},
                      'closest_calls': sr.explain(trace, 6), 'daily_json_1105_spy': dj['SPY']['rows'][D_LIVE]['c'], 'daily_json_mtime_utc': datetime.datetime.fromtimestamp(os.path.getmtime(DAILY), tz=datetime.timezone.utc).isoformat(timespec='minutes')},
        'rules_words': WORDS, 'trigger_table': rows, 'inverse_inner': inner, 'counterfactual_legs_1105': cf,
        'crash_days': crash, 'crash_summary': crash_summary, 'episodes': episodes,
        'convexity': conv, 'years': years, 'carry': carry, 'curves': curves, 'scatter': scatter,
        'comparator': comp, 'validation': val, 'states': states, 'transitions': trans, 'crash_signal': crash_sig, 'edges': edges,
        'launch_dates': launch, 'path': {'from': hold_days[0], 'to': hold_days[-1], 'n': len(hold_days), 'held_tickers': held},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=0, default=str)
    # ---- console
    L = out['live_1105']
    print(f"11-05 close: SPY {L['spy']:+.2%}  SOXL {L['soxl']:+.1%}  VIX {L['vix']:.2f}  VIX3M {L['vix3m']:.2f} ({L['vix3m_over_vix_minus_1']:+.1%})  "
          f"HYG {L['hyg']:+.2%} TLT {L['tlt']:+.2%} SHY {L['shy']:+.2%} LQD {L['lqd']:+.2%} TMF {L['tmf']:+.2%} IEF {L['ief']:+.2%}")
    print(f"target at the 11-05 close: {fmt_w(target)}; at 11-04: {fmt_w(t1104)}; daily.json 11-05 SPY print {L['daily_json_1105_spy']} (file {L['daily_json_mtime_utc']})")
    print('\nTRIGGER TABLE (11-05 close)')
    for r in rows:
        fm, fc = r['flip_move'], r['fires']
        print(f"  [{r['half'][:12]:12s}] {r['label']:34s} live {r['value']:8.2f}  need {r['op']} {r['threshold']:7.2f}  distance {r['distance']:7.2f} {r['unit']:7s} "
              f"flip by {('%+.2f%%' % (fm * 100)) if fm is not None else 'no 1-day move':>14s}  -> {fmt_w(r['would_hold']):26s} | true {fc['n_true']:4d}/{fc['n_days']} days since {fc['from']}, "
              f"last {fc['last']}, on {fc['on_crash3']}/{fc['of_crash3']} crash days ({fc['on_crash4']}/{fc['of_crash4']} <=-4%)")
    for r in inner:
        print(f"  [inside gate ] {r['label']:34s} live {r['value']:8.2f}  vs {r['threshold']:7.2f}  -> {r['holds']}")
    print('  counterfactual 11-05 legs: ' + '; '.join(f"{t} {v['leg_ret']:+.1%} -> sleeve {v['sleeve_ret']:+.1%}" for t, v in cf.items()))
    print(f"  validation misses: " + '; '.join(f"{m['date']} {m['status']}: live {fmt_w(m['live'])} vs path {fmt_w(m['path'])}" for m in val['misses']))
    print('\nCRASH DAYS')
    for k, v in crash_summary.items():
        if v.get('n'):
            print(f"  {k:44s} n {v['n']:3d}  sleeve same-day {v['ret_mean']:+.2%} (median {v['ret_median']:+.2%}, hit {v['hit']:.0%}, min {v['ret_min']:+.1%} max {v['ret_max']:+.1%})  next 1/5/20: "
                  f"{v['f1']:+.2%} / {v['f5']:+.2%} (med {v['f5_median']:+.2%}, pos {v['f5_pos']:.0%}) / {(v['f20'] or 0):+.2%} (med {(v['f20_median'] or 0):+.2%})  "
                  f"parked at open {v['parked_share']:.0%}, after close {v['parked_next_share']:.0%}, entered at the close {v['entered_at_close']}/{v['parked_at_open']}")
    print('\nEPISODES')
    for e in episodes:
        ml = e['max_leg']
        print(f"  {e['label']:28s} {e['from']}..{e['to']} SPY {e['spy']:+.1%}  sleeve {e['sleeve']:+.1%} (maxDD {e['sleeve_maxdd']:.1%})  max leg "
              f"{(ml[1] + ' %.0f%% on %s' % (ml[0] * 100, ml[2])) if ml else 'none'}  left cash after {e['days_to_leave_cash']} sessions  parked {e['parked_share']:.0%}  next20 {e['next20'] if e['next20'] is None else '%+.1f%%' % (e['next20'] * 100)}")
    print('\nCONVEXITY')
    for k, v in conv.items():
        print(f"  {k:26s} beta down {v['down']['beta']:+.3f} (t {v['down']['t']:+.1f}, n {v['down']['n']})  up {v['up']['beta']:+.3f} (t {v['up']['t']:+.1f}, n {v['up']['n']})  "
              f"SPY<=-2% {v['spy_le_2pct']['beta']:+.3f} (n {v['spy_le_2pct']['n']})  corr {v['corr_with_spy']:+.3f}  CAGR {v['cagr']:+.1%} vs SPY {v['spy_cagr']:+.1%} cash {v['cash_cagr']:+.1%}  "
              f"maxDD {v['maxdd']:.1%}  parked {v['parked_share']:.0%} (FB out {v['frontrun_out_share']:.0%}, IH out {v['inverse_out_share']:.0%})")
        print('     buckets: ' + '; '.join(f"{b['lo']:+.0%}..{b['hi']:+.0%}: {b['sleeve']:+.2%} (n {b['n']})" for b in v['buckets'] if b['n']))
    for k, v in carry.items():
        print(f"  carry {k}: calm years {v['calm_years']} mean {v['calm_mean']:+.1%} median {v['calm_median']:+.1%} min {v['calm_min']:+.1%}; rough years mean {v['rough_mean']:+.1%}")
    print('\nCOMPARATOR')
    for t, v in comp.items():
        c = v['crash_days']
        print(f"  {t}: {v['from']}..{v['to']} CAGR {v['cagr']:+.1%} (sleeve {v['sleeve_cagr_same_window']:+.1%}) maxDD {v['maxdd']:.0%}; crash days n {c['n']} mean {c['mean']:+.2%} hit {c['hit']:.0%} "
              f"(sleeve {c['sleeve_mean_same_days']:+.2%}, hit {c['sleeve_hit_same_days']:.0%}); calm-year mean {v['calm_year_mean']:+.1%} (sleeve {v['sleeve_calm_year_mean']:+.1%}); betas down {v['down_beta']:+.2f} up {v['up_beta']:+.2f}; 11-05 {v['d1105']:+.1%}")
    print(f"\nVALIDATION vs ledger: {val['agree']}/{val['n']} agree; misses {[(m['date'], m['status']) for m in val['misses']]}")
    print('\nSTATES (held leg, its own return on days held vs not)')
    for s in states:
        print(f"  {s['ticker']:5s} {s['window']:30s} {s['from']}..{s['to']} n_on {s['n_on']:4d} mean {s['mean_on']:+.2%} hit {s['hit_on']:.0%} t {s['t_on']:+.1f} | off mean {s['mean_off']:+.2%} | t_diff {s['t_diff']:+.1f} | leg total {s['leg_total']:+.0%}")
    print('\nTRANSITIONS')
    for lab, o in trans.items():
        for k, v in o.items():
            print(f"  {lab} {k:30s} " + (f"n {v['n']:4d} SPY f5 {v['spy_f5']:+.2%} (t {v['spy_f5_t_vs_uncond']}) f20 {v['spy_f20']:+.2%} (t {v['spy_f20_t_vs_uncond']}) sleeve f5 {v['sleeve_f5']:+.2%}" if k != 'unconditional' else f"n {v['n']} SPY f5 {v['spy_f5']:+.2%} f20 {v['spy_f20']:+.2%}"))
    print('\nEDGES:', json.dumps(edges, default=str)[:2000] or 'none')
    print('wrote', OUT)


if __name__ == '__main__':
    main()
