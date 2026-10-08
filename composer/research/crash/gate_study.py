"""HG bear-gate study: binary vs graded gates vs macro-conditioned gates, scored on
risk-adjusted metrics, with inverse-signal and placebo tests (house standard).

Mechanics: the HG tree is run ONCE per price panel (decisions never depend on the
gate); a gate is a per-day 'allow' in [0,1] applied at the decision close to the
TREND baskets only (holdings in TQQQ/UPRO/UDOW/SSO/TNA): weight x allow, remainder
to BIL.  Composer-equivalent cost (5.12 bps per unit sum|dw|, trade day) charged on
the variant's own turnover.  Two panels: real tickers 2015-06..2026-10, and a
long-history proxy 1990-01..2026-10 (leveraged legs reconstructed from their
indices; pre-1999 bases are index proxies; see build_lh_prices).
"""
import json, math, sys, random, os
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import SP
sys.path.insert(0, SP)
from replay import yh, rets_of, curve_from, SimW, tree_tickers, run_tree, common_days, load_prices
from hist_replay import recon, splice, bil_from_irx, vix_etp, fits, cash
MAC = f'{SP}/macro'
trees = json.load(open(f'{SP}/trees.json'))
TREND = {'TQQQ', 'UPRO', 'UDOW', 'SSO', 'TNA'}
COST = 5.12e-4

# ---------------------------------------------------------------- prices
def lev_from_index(idx, L, divy=None, alpha=-0.7e-4):
    """synthetic L x index with daily financing at the T-bill and an optional dividend-yield accrual (annual %, monthly dict)."""
    r = rets_of(idx); out = {}
    for d, x in r.items():
        dy = (divy.get(d[:7], 0.0)/100.0/252 if divy else 0.0)
        out[d] = L*(x + dy) - (L-1)*cash.get(d, 0.0) + alpha
    return curve_from(out)

def build_lh_prices():
    divy = json.load(open(f'{MAC}/divyield_multpl.json')) if os.path.exists(f'{MAC}/divyield_multpl.json') else {}
    ndx, gspc, dji, rut, sox, nbi = yh('^NDX'), yh('^GSPC'), yh('^DJI'), yh('^RUT'), yh('^SOX'), yh('^NBI')
    P = {}
    ndx_dy = {k: 0.5 for k in divy} if divy else None          # NDX paid ~0.5%/yr; S&P uses the real monthly yield
    P['TQQQ'] = splice(splice(yh('TQQQ'), recon('TQQQ', 'QQQ', 3)), lev_from_index(ndx, 3, ndx_dy))
    P['QLD'] = splice(splice(yh('QLD'), recon('QLD', 'QQQ', 2)), lev_from_index(ndx, 2, ndx_dy))
    P['UPRO'] = splice(splice(yh('UPRO'), recon('UPRO', 'SPY', 3)), lev_from_index(gspc, 3, divy))
    P['SSO'] = splice(splice(yh('SSO'), recon('SSO', 'SPY', 2)), lev_from_index(gspc, 2, divy))
    P['UDOW'] = splice(splice(splice(yh('UDOW'), recon('UDOW', 'DIA', 3)), lev_from_index(dji, 3, divy)), lev_from_index(gspc, 3, divy))
    P['TNA'] = splice(splice(yh('TNA'), lev_from_index(yh('IWM'), 3)), splice(lev_from_index(rut, 3, {k: 1.5 for k in divy}), lev_from_index(gspc, 3, divy)))
    P['TECL'] = splice(splice(yh('TECL'), recon('TECL', 'XLK', 3)), lev_from_index(ndx, 3, ndx_dy))
    P['SOXL'] = splice(splice(yh('SOXL'), recon('SOXL', '^SOX', 3)), lev_from_index(ndx, 3, ndx_dy))
    P['USD'] = splice(splice(yh('USD'), recon('USD', '^SOX', 2)), lev_from_index(ndx, 2, ndx_dy))
    P['SMH'] = splice(splice(yh('SMH'), sox), ndx)
    P['LABU'] = splice(splice(splice(yh('LABU'), lev_from_index(yh('XBI'), 3)), lev_from_index(nbi, 3)), lev_from_index(ndx, 3, ndx_dy))
    P['BIL'] = splice(yh('BIL'), bil_from_irx())
    for nm in ('VIXY', 'UVXY', 'VIXM'):
        syn, _ = vix_etp(nm); P[nm] = splice(yh(nm), syn)
    P['SPY'] = splice(yh('SPY'), curve_from({d: x + divy.get(d[:7], 0.0)/100/252 for d, x in rets_of(gspc).items()}) if divy else gspc)
    return P

# ---------------------------------------------------------------- base runs
def base_run(P, a, b):
    sim = SimW(P, rsi_method='wilder'); tk = tree_tickers(trees['HG']); days = common_days(P, tk, a, b)
    r, h = run_tree(sim, trees['HG'], days)
    px = {t: P[t] for t in tk if t in P}
    return days, h, px

def variant_returns(days, h, px, allow):
    """apply allow[d0] (decision close) to the trend basket; costed; returns (rets, turnover_per_year, allow_share)."""
    rets = {}; hold = {}
    for i in range(1, len(days)):
        d0, d1 = days[i-1], days[i]; w = dict(h[d1]); a = allow.get(d0, 1.0)
        if a < 1.0 and any(t in TREND for t in w):
            tw = sum(x for t, x in w.items() if t in TREND); moved = tw*(1-a)
            for t in list(w):
                if t in TREND: w[t] *= a
            w['BIL'] = w.get('BIL', 0.0) + moved
        hold[d1] = w
        rets[d1] = sum(x*(px[t][d1]/px[t][d0]-1) for t, x in w.items() if d1 in px[t] and d0 in px[t])
    out = {}; to_total = 0.0
    for i in range(1, len(days)):
        d = days[i]; nxt = days[i+1] if i+1 < len(days) else None
        w, wn = hold[d], (hold[nxt] if nxt else hold[d])
        to = sum(abs(wn.get(k, 0)-w.get(k, 0)) for k in set(w) | set(wn)); to_total += to
        out[d] = rets[d] - COST*to
    return out, to_total/(len(days)/252), hold

def metrics(rets, days, a=None, b=None):
    ds = [d for d in days[1:] if (a is None or d >= a) and (b is None or d <= b) and d in rets]
    if len(ds) < 30: return None
    r = [rets[d] for d in ds]; rf = [cash.get(d, 0.0) for d in ds]
    cum = math.prod(1+x for x in r); yrs = len(ds)/252; cagr = cum**(1/yrs)-1
    ex = [x-f for x, f in zip(r, rf)]; mu = sum(ex)/len(ex); sd = math.sqrt(sum((x-mu)**2 for x in ex)/(len(ex)-1))
    dn = math.sqrt(sum(min(x, 0)**2 for x in ex)/len(ex))
    sharpe = mu/sd*math.sqrt(252) if sd else 0; sortino = mu/dn*math.sqrt(252) if dn else 0
    v = 1; pk = 1; mdd = 0; tuw = 0; tmax = 0
    for x in r:
        v *= 1+x
        if v >= pk: pk = v; tuw = 0
        else: tuw += 1; tmax = max(tmax, tuw)
        mdd = max(mdd, 1-v/pk)
    yr = {}
    for d, x in zip(ds, r): yr[d[:4]] = yr.get(d[:4], 1.0)*(1+x)
    worst_year = min(v-1 for v in yr.values())
    return {'cagr': round(cagr, 4), 'vol': round(sd*math.sqrt(252), 4), 'sharpe': round(sharpe, 3), 'sortino': round(sortino, 3), 'calmar': round(cagr/mdd, 3) if mdd else None,
            'maxdd': round(mdd, 4), 'worst_year': round(worst_year, 4), 'tuw_days': tmax, 'cum': round(cum, 3), 'n': len(ds)}

# ---------------------------------------------------------------- gate signals
def ma_series(px, n):
    ds = sorted(px); out = {}
    s = 0.0; q = []
    for d in ds:
        q.append(px[d]); s += px[d]
        if len(q) > n: s -= q.pop(0)
        if len(q) == n: out[d] = s/n
    return out

def gates_trend(spy):
    ds = sorted(spy); ma50, ma100, ma200 = ma_series(spy, 50), ma_series(spy, 100), ma_series(spy, 200)
    hi252 = {}; q = []
    for d in ds:
        q.append(spy[d]); q = q[-252:]; hi252[d] = max(q)
    G = {'B1 binary SPY<200d': {}, 'G1 ramp +-5% of 200d': {}, 'G2 vote 50/100/200d': {}, 'G3 persistence (tightens over 40d below 200d)': {}, 'G4 drawdown ramp 5%->15%': {}, 'G5 0.5*G3+0.5*G4': {}}
    below = 0
    for d in ds:
        if d not in ma200: continue
        x = spy[d]/ma200[d]-1
        b1 = 0.0 if x < 0 else 1.0
        g1 = min(1.0, max(0.0, (x+0.05)/0.10))
        g2 = (float(spy[d] > ma50[d]) + float(spy[d] > ma100[d]) + float(spy[d] > ma200[d]))/3.0
        below = below+1 if x < 0 else 0
        g3 = 1.0 if x >= 0 else max(0.0, 1-below/40.0)
        dd = 1-spy[d]/hi252[d]; g4 = min(1.0, max(0.0, 1-(dd-0.05)/0.10))
        G['B1 binary SPY<200d'][d] = b1; G['G1 ramp +-5% of 200d'][d] = g1; G['G2 vote 50/100/200d'][d] = g2
        G['G3 persistence (tightens over 40d below 200d)'][d] = g3; G['G4 drawdown ramp 5%->15%'][d] = g4; G['G5 0.5*G3+0.5*G4'][d] = 0.5*g3+0.5*g4
    return G, ma50, ma100, ma200

def monthly_prev(series_m, d):
    """value of a monthly series known at decision date d: the month BEFORE the prior month (two-month lag — multpl posts a month's CAPE after it ends and Shiller earnings arrive later still; counter-agent F7)."""
    y, m = int(d[:4]), int(d[5:7]); m -= 2
    if m <= 0: m += 12; y -= 1
    return series_m.get(f'{y:04d}-{m:02d}')

def rolling_pct(series_m, key, years=20):
    """real-time percentile of series_m[key] within the trailing `years` of monthly values."""
    ks = sorted(series_m); i = ks.index(key); win = [series_m[k] for k in ks[max(0, i-12*years):i+1]]
    return sum(1 for v in win if v <= series_m[key])/len(win)

def macro_flags():
    cape = json.load(open(f'{MAC}/cape_multpl.json'))
    t10y3m = json.load(open(f'{MAC}/fred_T10Y3M.json')); baa = json.load(open(f'{MAC}/fred_BAA10Y.json')); oil = json.load(open(f'{MAC}/fred_DCOILWTICO.json'))
    def daily_prev(ser, d):
        ks = sorted(ser); import bisect
        i = bisect.bisect_left(ks, d)-1; return ser[ks[i]] if i >= 0 else None
    # monthly aggregates (month-end values) for rolling percentiles
    def month_end(ser):
        out = {}
        for k in sorted(ser): out[k[:7]] = ser[k]
        return out
    baa_m = month_end(baa); oil_m = month_end(oil); curve_m = month_end(t10y3m)
    F = {'M1 CAPE pct': {}, 'M1b CAPE high-for-long': {}, 'M2 curve inverted (12m lookback)': {}, 'M3 credit spread pct': {}, 'M4 oil +50% 12m': {}}
    cape_keys = sorted(cape)
    def cape_at(d):
        k = monthly_prev(cape, d); return k
    return cape, baa_m, oil_m, curve_m

def gates_macro(spy_days):
    """macro-conditioned gates: tighten the trend threshold (200d -> 100d -> 50d MA) with the macro state.
    Returns {name: allow}, plus the INVERSE of each (loosen when the flag is on)."""
    cape = json.load(open(f'{MAC}/cape_multpl.json'))
    t10 = json.load(open(f'{MAC}/fred_T10Y3M.json')); baa = json.load(open(f'{MAC}/fred_BAA10Y.json')); oil = json.load(open(f'{MAC}/fred_DCOILWTICO.json'))
    import bisect
    def prev_val(ser, keys, d):
        i = bisect.bisect_left(keys, d)-1; return ser[keys[i]] if i >= 0 else None
    k10, kbaa, koil = sorted(t10), sorted(baa), sorted(oil)
    ckeys = sorted(cape)
    # monthly state series (known with 1-month lag)
    state = {}
    for i, k in enumerate(ckeys):
        win = [cape[x] for x in ckeys[max(0, i-240):i+1]]; pct = sum(1 for v in win if v <= cape[k])/len(win)
        # high-for-long: consecutive months with pct >= 0.8
        state[k] = {'cape_pct': pct}
    run = 0
    for k in ckeys:
        run = run+1 if state[k]['cape_pct'] >= 0.8 else 0; state[k]['cape_run'] = run
    return state, (t10, k10), (baa, kbaa), (oil, koil), prev_val

def build_macro_allows(spy, ma50, ma100, ma200, days):
    state, (t10, k10), (baa, kbaa), (oil, koil), prev_val = gates_macro(days)
    def thr_allow(d, level):
        """level 0: 200d, 1: 100d, 2: 50d (tighter); -1: 300d-ish = never gate (loosest)"""
        if level <= -1: return 1.0
        ma = {0: ma200, 1: ma100, 2: ma50}[min(level, 2)]
        return 0.0 if (d in ma and spy[d] < ma[d]) else 1.0
    out = {}; LEVELS = {}
    names = ['M1 CAPE level (pct>=.8 -> 100d, >=.95 -> 50d)', 'M1b CAPE high-for-long (>=12m at pct>=.8 -> 50d)', 'M2 curve inverted within 12m -> 100d',
             'M3 credit spread pct>=.8 (5y) -> 100d', 'M4 oil +50% yoy -> 100d', 'M5 count of M1-M4 flags -> 200/100/50/50d (near-permanent 50d gate)']
    OWN = {names[0]: 1, names[1]: 2, names[2]: 1, names[3]: 1, names[4]: 1, names[5]: 1}   # the variant's own tightening level, for the mirror inverse
    for n in names: out[n] = {}; out['INV ' + n] = {}; LEVELS[n] = {}
    baa_hist = []
    for d in days:
        if d not in ma200: continue
        st = monthly_prev(state, d) or {'cape_pct': 0.5, 'cape_run': 0}
        f1 = 2 if st['cape_pct'] >= 0.95 else (1 if st['cape_pct'] >= 0.8 else 0)
        f1b = 2 if st['cape_run'] >= 12 else 0
        # curve: inverted at any point in the past 252 trading days (known daily)
        i = bisect_left(k10, d); win = [t10[x] for x in k10[max(0, i-252):i]]
        f2 = 1 if (win and min(win) < 0) else 0
        bv = prev_val(baa, kbaa, d); baa_hist.append(bv)
        hist = [x for x in baa_hist[-1260:] if x is not None]
        f3 = 1 if (bv is not None and hist and sum(1 for x in hist if x <= bv)/len(hist) >= 0.8) else 0
        ov = prev_val(oil, koil, d); j = bisect_left(koil, d)-252; ov1 = oil[koil[j]] if j >= 0 else None
        f4 = 1 if (ov and ov1 and ov/ov1-1 > 0.5) else 0
        cnt = (1 if f1 else 0) + (1 if f1b else 0) + f2 + f3 + f4
        f5 = min(cnt, 2) if cnt else 0
        for n, lvl in zip(names, (f1, f1b, f2, f3, f4, f5)):
            out[n][d] = thr_allow(d, lvl); LEVELS[n][d] = lvl
            out['INV ' + n][d] = thr_allow(d, 0 if lvl else OWN[n])  # mirror image: flag ON -> 200d, flag OFF -> the variant's own level (counter-agent F4)
    build_macro_allows.levels = LEVELS
    return out
from bisect import bisect_left

def placebo_allows(allow, days, rng, k=20):
    """random month-blocks: shuffle the monthly on/off pattern of a macro gate (same count of 'tight' days) 20x."""
    ds = [d for d in days if d in allow]
    # tight = allow < 1 relative to B1? we shuffle the macro LEVEL pattern by month
    months = sorted({d[:7] for d in ds}); outs = []
    for _ in range(k):
        perm = months[:]; rng.shuffle(perm); mp = dict(zip(months, perm))
        # map each day's allow to the allow of a random month's same-index day (approximate by month mean)
        mean = {}
        for d in ds: mean.setdefault(d[:7], []).append(allow[d])
        mean = {m: sum(v)/len(v) for m, v in mean.items()}
        outs.append({d: (allow[d] if mean[mp[d[:7]]] < 1 else 1.0) if True else allow[d] for d in ds})
    return outs

if __name__ == '__main__':
    out = {'panels': {}}
    # ---- panel A: real tickers 2015-06..2026-10 ----
    P = load_prices(real_synth=True); daysA, hA, pxA = base_run(P, '2015-06-01', '2026-10-06')
    # ---- panel B: long-history proxy 1990..2026 ----
    PL = build_lh_prices(); daysB, hB, pxB = base_run(PL, '1990-01-02', '2026-10-06')
    print('panel A', daysA[0], daysA[-1], len(daysA), '| panel B', daysB[0], daysB[-1], len(daysB))
    WIN = {'A': {'2015-06..2026-10': (None, None), '2023-04..2026-10 (live era)': ('2023-04-19', None), '2022 bear': ('2022-01-03', '2022-12-30'), 'COVID 2020-02-19..2021-02-19': ('2020-02-20', '2021-02-19')},
           'B': {'1990-01..2026-10': (None, None), '1990-01..1999-12': (None, '1999-12-31'), '2000-03..2002-10 bear': ('2000-03-11', '2002-10-09'), '2003-01..2007-09': ('2003-01-02', '2007-09-28'),
                 '2007-10..2009-03 bear': ('2007-10-10', '2009-03-09'), '2009-04..2019-12': ('2009-04-01', '2019-12-31'), '2020-01..2026-10': ('2020-01-02', None)}}
    rng = random.Random(3)
    for pan, (days, h, px, PP) in {'A': (daysA, hA, pxA, P), 'B': (daysB, hB, pxB, PL)}.items():
        spy = PP['SPY']; G, ma50, ma100, ma200 = gates_trend(spy)
        allows = {'B0 as built': {}}; allows.update(G)
        allows.update(build_macro_allows(spy, ma50, ma100, ma200, days))
        # inverse of the graded gates too (signal must beat its inverse)
        for n in list(G): allows['INV ' + n] = {d: 1-v for d, v in G[n].items()}
        res = {}
        for name, al in allows.items():
            r, to, hold = variant_returns(days, h, px, al)
            share = sum(al.get(d, 1.0) for d in days)/len(days)
            res[name] = {'turnover_per_year': round(to, 2), 'mean_allow': round(share, 3), 'windows': {w: metrics(r, days, a, b) for w, (a, b) in WIN[pan].items()}}
        out['panels'][pan] = {'days': [days[0], days[-1], len(days)], 'results': res}
        print(f"\n=== panel {pan} ({days[0]}..{days[-1]}) full window: name | CAGR | vol | Sharpe | Sortino | Calmar | maxDD | worst yr | allow")
        full = list(WIN[pan])[0]
        for name, v in res.items():
            m = v['windows'][full]
            print(f"  {name:52s} {m['cagr']:+7.1%} {m['vol']:6.1%} {m['sharpe']:6.2f} {m['sortino']:6.2f} {str(m['calmar']):>6s} {m['maxdd']:6.1%} {m['worst_year']:+7.1%} {v['mean_allow']:.2f} to/yr {v['turnover_per_year']:.0f}")
    json.dump(out, open(f'{SP}/gate_study.json', 'w')); print('saved')
