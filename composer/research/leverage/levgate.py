"""Leverage-gate lab (research pass; no live change).

Owner question (2026-10-16): is there a factor, or a small set, that times WHEN a leg should be held
leveraged and when as its 1x version — same signals, same trades, only the leverage switches — and
how should such a gate be blended and applied across the engines?

Core: every leveraged leg t has a 1x twin (TQQQ->QQQ, UDOW->DIA, SQQQ->PSQ, UVXY->VIXY ...).  A gate
is a per-day allowance lam[d0] in [0,1], decided at the close d0 from data up to d0; on d1 the leg
earns lam*r_lev + (1-lam)*r_1x (1 = as built, 0 = fully de-levered, 0.5 ~ a 2x blend).  Switching
leverage is a trade: cost at the engine's measured bps (add. 38) on the effective holdings
{t, '1x:'+t}.  Decisions, dip-buys, hedges and cash legs are untouched; a gate applies to the leg
CLASSES named (default: the long trend legs only).

Panels: B = HG on the 1990-2026 proxy panel (gate_study.build_lh_prices; out of sample for HG's
rules; synthetic legs before the ETFs exist).  A = all four engines on hist_replay.build_prices,
2015-06..2026-10 (real tickers where they exist; KMLM's regime flag read from RYMFX before 2020-12,
PULS<-BIL before 2018, BOXX=BIL; in sample for KMLM/SLEEVE/HARV, designed July 2026).
Tests: full-window metrics; by-window (B); inverse gate (1-lam); monthly re-dated placebos and a
paired block bootstrap for a shortlist; book-level application blends (A).
Extend: one line in FACTORS (name -> builder) or LEG (ticker -> class, L).  Output: OUT/levgate.json.
"""
import bisect
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', 'crash')))
import gate_study as gs                                   # noqa: E402
from gate_study import metrics, ma_series, lev_from_index, trees, cash   # noqa: E402
from hist_replay import build_prices, splice               # noqa: E402
from replay import yh, rets_of, curve_from, SimW, tree_tickers, run_tree, common_days   # noqa: E402

OUT = os.environ.get('LEVGATE_DATA', os.path.join(os.path.dirname(gs.SP), 'levgate'))
os.makedirs(OUT, exist_ok=True)
MAC = gs.MAC

LEG = {  # ticker: (class, daily leverage)
    'TQQQ': ('trend', 3), 'QLD': ('trend', 2), 'UPRO': ('trend', 3), 'SPXL': ('trend', 3), 'SSO': ('trend', 2),
    'UDOW': ('trend', 3), 'TNA': ('trend', 3), 'TECL': ('trend', 3), 'SOXL': ('trend', 3), 'USD': ('trend', 2),
    'LABU': ('trend', 3), 'FAS': ('trend', 3), 'UGL': ('gold', 2), 'TMF': ('bond', 3), 'UVXY': ('longvol', 1.5),
    'SQQQ': ('inverse', -3), 'TMV': ('inverse', -3), 'LABD': ('inverse', -3), 'SOXS': ('inverse', -3)}
ALL_CLASSES = ('trend', 'gold', 'bond', 'longvol', 'inverse')
COST = {'HG': 5.12e-4, 'KMLM': 5.86e-4, 'SLEEVE': 2.25e-4, 'HARV': 5.21e-4}
B_WIN, A_WIN = ('1990-01-02', '2026-10-15'), ('2015-06-01', '2026-10-15')
WINDOWS_B = {'1990-99': (None, '1999-12-31'), '2000-02 bear': ('2000-03-11', '2002-10-09'), '2003-07': ('2003-01-02', '2007-09-28'),
             '2007-09 bear': ('2007-10-10', '2009-03-09'), '2009-19': ('2009-04-01', '2019-12-31'), '2020-26': ('2020-01-02', None)}
TARGET = {'HG': 0.29, 'KMLM': 0.29, 'SLEEVE': 0.27, 'HARV': 0.15}


# ------------------------------------------------------------------ 1x twins
def inv1x(base):
    """-1x daily-reset fund on `base` (financing at the T-bill, 25 bp/yr fee)."""
    return curve_from({d: -r + 2 * cash.get(d, 0.0) - 1e-5 for d, r in rets_of(base).items()})


def one_x_B(P):
    divy = json.load(open(f'{MAC}/divyield_multpl.json'))
    ndx_dy = {k: 0.5 for k in divy}
    ndx, gspc, dji, rut, nbi = yh('^NDX'), yh('^GSPC'), yh('^DJI'), yh('^RUT'), yh('^NBI')
    qqq = splice(yh('QQQ'), lev_from_index(ndx, 1, ndx_dy, alpha=-1e-5))
    return {'TQQQ': qqq, 'QLD': qqq, 'TECL': splice(yh('XLK'), qqq), 'UPRO': P['SPY'], 'SSO': P['SPY'],
            'UDOW': splice(splice(yh('DIA'), lev_from_index(dji, 1, divy, alpha=-1e-5)), lev_from_index(gspc, 1, divy, alpha=-1e-5)),
            'TNA': splice(yh('IWM'), splice(lev_from_index(rut, 1, {k: 1.5 for k in divy}, alpha=-1e-5), lev_from_index(gspc, 1, divy, alpha=-1e-5))),
            'SOXL': P['SMH'], 'USD': P['SMH'],
            'LABU': splice(splice(yh('XBI'), lev_from_index(nbi, 1, alpha=-1e-5)), lev_from_index(ndx, 1, ndx_dy, alpha=-1e-5)),
            'UVXY': P['VIXY']}


def one_x_A(P):
    soxx = splice(yh('SOXX'), P['SOXI'])
    return {'TQQQ': P['QQQ'], 'QLD': P['QQQ'], 'TECL': P['XLK'], 'UPRO': P['SPY'], 'SPXL': P['SPY'], 'SSO': P['SPY'],
            'UDOW': P['DIA'], 'TNA': P['IWM'], 'SOXL': soxx, 'USD': soxx, 'LABU': P['XBI'], 'FAS': P['XLF'], 'UGL': yh('GLD'),
            'TMF': P['TLT'], 'UVXY': P['VIXY'], 'SQQQ': P['PSQ'], 'TMV': splice(yh('TBF'), inv1x(P['TLT'])),
            'LABD': inv1x(P['XBI']), 'SOXS': inv1x(soxx)}


# ------------------------------------------------------------------ the gate engine
def gate_run(days, hold, P, P1, lam, classes, cost):
    """lam: {d0: float} or {d0: {ticker: float}} (missing -> 1).  Returns (costed daily returns,
    turnover/yr, mean allowance over leveraged-leg weight)."""
    rets, eff, lsum, lw = {}, {}, 0.0, 0.0
    for i in range(1, len(days)):
        d0, d1 = days[i - 1], days[i]
        L = lam.get(d0, 1.0)
        h, r = {}, 0.0
        for t, x in hold[d1].items():
            leg = LEG.get(t)
            if leg and leg[0] in classes and t in P1 and d0 in P1[t] and d1 in P1[t]:
                lt = L.get(t, 1.0) if isinstance(L, dict) else L
                h[t] = h.get(t, 0.0) + x * lt
                h['1x:' + t] = h.get('1x:' + t, 0.0) + x * (1 - lt)
                r += x * (lt * (P[t][d1] / P[t][d0] - 1) + (1 - lt) * (P1[t][d1] / P1[t][d0] - 1))
                lsum += x * lt
                lw += x
            else:
                h[t] = h.get(t, 0.0) + x
                if d0 in P[t] and d1 in P[t]:
                    r += x * (P[t][d1] / P[t][d0] - 1)
        eff[d1], rets[d1] = h, r
    out, to_tot = {}, 0.0
    for i in range(1, len(days)):
        d = days[i]
        nxt = days[i + 1] if i + 1 < len(days) else None
        w, wn = eff[d], (eff[nxt] if nxt else eff[d])
        to = sum(abs(wn.get(k, 0.0) - w.get(k, 0.0)) for k in set(w) | set(wn))
        to_tot += to
        out[d] = rets[d] - cost * to
    return out, to_tot / (len(days) / 252), (lsum / lw if lw else 1.0)


# ------------------------------------------------------------------ factor library
def vol_series(px, n):
    ds = sorted(px)
    out, q = {}, []
    for i in range(1, len(ds)):
        q.append(px[ds[i]] / px[ds[i - 1]] - 1)
        if len(q) > n:
            q.pop(0)
        if len(q) == n:
            m = sum(q) / n
            out[ds[i]] = math.sqrt(sum((x - m) ** 2 for x in q) / (n - 1) * 252)
    return out


def dd_series(px, n=252):
    ds = sorted(px)
    out, q = {}, []
    for d in ds:
        q.append(px[d])
        q = q[-n:]
        out[d] = px[d] / max(q) - 1
    return out


def rank_series(s, n=252):
    ds = sorted(s)
    out = {}
    for i, d in enumerate(ds):
        win = [s[x] for x in ds[max(0, i - n + 1):i + 1]]
        out[d] = sum(1 for v in win if v <= s[d]) / len(win)
    return out


def asof(ser):
    ks = sorted(k for k, v in ser.items() if v is not None)

    def f(d):
        i = bisect.bisect_right(ks, d) - 1
        return ser[ks[i]] if i >= 0 else None
    return f


def hyst(x, lo, hi, ds):
    out, on = {}, True
    for d in ds:
        v = x.get(d)
        if v is None:
            out[d] = 1.0
            continue
        if on and v < lo:
            on = False
        elif (not on) and v > hi:
            on = True
        out[d] = 1.0 if on else 0.0
    return out


def build_factors(P, P1, days, eng_rets, legs_held):
    """Returns {name: lam} for the decision days `days`.  Every series is point-in-time (<= d0)."""
    spy = P['SPY']
    ma = {n: ma_series(spy, n) for n in (50, 100, 200)}
    v20, v10 = vol_series(spy, 20), vol_series(spy, 10)
    vrank = rank_series({d: v for d, v in v20.items() if d >= '1989-01-01'}, 252)
    sdd = dd_series(spy)
    vix = yh('^VIX')
    vix3m = yh('^VIX3M')
    vixma = ma_series(vix, 50)
    ecurve = curve_from(eng_rets)
    ema = {n: ma_series(ecurve, n) for n in (100, 200)}
    ev20 = vol_series(ecurve, 20)
    edd = dd_series(ecurve)
    baa = asof(json.load(open(f'{MAC}/fred_BAA10Y.json')))
    baa_rank = rank_series({d: baa(d) for d in days if baa(d) is not None}, 252)
    t10 = asof(json.load(open(f'{MAC}/fred_T10Y3M.json')))
    cape_m = json.load(open(f'{MAC}/cape_multpl.json'))
    legvol = {t: vol_series(P1[t], 20) for t in legs_held if t in P1}

    def rf(d):
        return cash.get(d, 0.0) * 252

    cape_keys = sorted(cape_m)
    cape_cache = {}

    def cape_pct(d):   # 20y percentile of CAPE, two-month lag (add. 40 convention)
        y, m = int(d[:4]), int(d[5:7]) - 2
        if m < 1:
            y, m = y - 1, m + 12
        k = f'{y:04d}-{m:02d}'
        if k not in cape_m:
            return None
        if k not in cape_cache:
            i = bisect.bisect_right(cape_keys, k)
            win = cape_keys[max(0, i - 240):i]
            cape_cache[k] = sum(1 for x in win if cape_m[x] <= cape_m[k]) / len(win)
        return cape_cache[k]

    def curve_inv_recent(d):   # inverted at any point in the prior 252 sessions
        i = bisect.bisect_left(days, d)
        return any((t10(x) or 0) < 0 for x in days[max(0, i - 252):i + 1])

    g = lambda cond: {d: (1.0 if cond(d) else 0.0) for d in days}   # noqa: E731
    sv = lambda s, d: s.get(d)   # noqa: E731
    F = {}
    F['A0 always levered (as built)'] = {}
    F['A1 never levered'] = {d: 0.0 for d in days}
    F['A2 fixed 1/3'] = {d: 1 / 3 for d in days}
    F['A3 fixed 1/2 (~2x)'] = {d: 0.5 for d in days}
    F['A4 fixed 2/3'] = {d: 2 / 3 for d in days}
    F['T200 SPY>200d'] = g(lambda d: d not in ma[200] or spy[d] > ma[200][d])
    F['T100 SPY>100d'] = g(lambda d: d not in ma[100] or spy[d] > ma[100][d])
    F['T50 SPY>50d'] = g(lambda d: d not in ma[50] or spy[d] > ma[50][d])
    F['Tvote 50/100/200'] = {d: sum(1.0 for n in (50, 100, 200) if d in ma[n] and spy[d] > ma[n][d]) / 3 if d in ma[200] else 1.0 for d in days}
    F['T200h hysteresis +-2%'] = hyst({d: spy[d] / ma[200][d] - 1 for d in days if d in ma[200]}, -0.02, 0.02, days)
    F['T200half 0.5 below 200d'] = {d: (1.0 if F['T200 SPY>200d'][d] else 0.5) for d in days}
    for k in (15, 20, 25, 30):
        F[f'V20<{k} SPY 20d vol'] = g(lambda d, k=k: sv(v20, d) is None or v20[d] < k / 100)
    F['V10<25 SPY 10d vol'] = g(lambda d: sv(v10, d) is None or v10[d] < 0.25)
    F['Vrank<80 (1y pct of 20d vol)'] = g(lambda d: sv(vrank, d) is None or vrank[d] < 0.8)
    for k in (12, 16, 20, 25):
        F[f'VT{k} vol target {k}% on SPY vol'] = {d: (min(1.0, k / 100 / v20[d]) if d in v20 and v20[d] > 0 else 1.0) for d in days}
    for k in (30, 40, 50):
        F[f'ET{k} vol target {k}% on own vol'] = {d: (min(1.0, k / 100 / ev20[d]) if d in ev20 and ev20[d] > 0 else 1.0) for d in days}
    F['E100 own equity>100d'] = g(lambda d: d not in ema[100] or ecurve[d] > ema[100][d])
    F['E200 own equity>200d'] = g(lambda d: d not in ema[200] or ecurve[d] > ema[200][d])
    F['EDD10 own DD<10%'] = g(lambda d: sv(edd, d) is None or edd[d] > -0.10)
    F['EDD20 own DD<20%'] = g(lambda d: sv(edd, d) is None or edd[d] > -0.20)
    F['D10 SPY DD<10% (1y high)'] = g(lambda d: sv(sdd, d) is None or sdd[d] > -0.10)
    for k in (20, 25, 30):
        F[f'X{k} VIX<{k}'] = g(lambda d, k=k: sv(vix, d) is None or vix[d] < k)
    F['Xma VIX<50d MA'] = g(lambda d: sv(vixma, d) is None or vix[d] < vixma[d])
    F['Xts VIX<VIX3M (pre-06: VIX<50d)'] = g(lambda d: (vix[d] < vix3m[d]) if (d in vix3m and d in vix) else (sv(vixma, d) is None or vix[d] < vixma[d]))
    F['R4 T-bill<4%'] = g(lambda d: rf(d) < 0.04)
    F['C80 credit spread 1y pct<80'] = g(lambda d: sv(baa_rank, d) is None or baa_rank[d] < 0.8)
    F['Y curve not inverted in 1y'] = g(lambda d: not curve_inv_recent(d))
    F['K80 CAPE 20y pct<80'] = g(lambda d: (cape_pct(d) or 0) < 0.8)
    for k in (25, 35, 45):
        F[f'L{k} leg base vol<{k}%'] = {d: {t: (1.0 if (d not in legvol[t] or legvol[t][d] < k / 100) else 0.0) for t in legvol} for d in days}
    legma = {t: ma_series(P1[t], 200) for t in legs_held if t in P1}
    F['R1 leg base>200d (per leg)'] = {d: {t: (1.0 if (d not in legma[t] or P1[t][d] > legma[t][d]) else 0.0) for t in legma} for d in days}
    legma100 = {t: ma_series(P1[t], 100) for t in legs_held if t in P1}
    F['R1b leg base>100d (per leg)'] = {d: {t: (1.0 if (d not in legma100[t] or P1[t][d] > legma100[t][d]) else 0.0) for t in legma100} for d in days}
    train = [v20[d] for d in days[:2520] if d in v20]          # first ten years of the panel = training window, frozen
    if len(train) > 250:
        q50, q85 = sorted(train)[len(train) // 2], sorted(train)[int(len(train) * 0.85)]
        F[f'R2 RV buckets q50/q85 frozen ({q50:.0%}/{q85:.0%})'] = {d: (1.0 if d not in v20 or v20[d] < q50 else (0.5 if v20[d] < q85 else 0.0)) for d in days}
    legdd = {t: dd_series(P1[t]) for t in legs_held if t in P1}
    legvr = {t: rank_series(legvol[t], 252) for t in legvol}
    F['R4 inverse-leg panic (base DD>10% & vol pct>80)'] = {d: {t: (0.0 if (LEG[t][0] == 'inverse' and legdd[t].get(d, 0) < -0.10 and legvr[t].get(d, 0) > 0.8) else 1.0) for t in legvol} for d in days}
    F['T200&V25 both on'] = {d: min(F['T200 SPY>200d'][d], F['V20<25 SPY 20d vol'][d]) for d in days}
    F['T200|V25 either on'] = {d: max(F['T200 SPY>200d'][d], F['V20<25 SPY 20d vol'][d]) for d in days}
    F['vote2of3 T200,V25,X25'] = {d: (1.0 if F['T200 SPY>200d'][d] + F['V20<25 SPY 20d vol'][d] + F['X25 VIX<25'][d] >= 2 else 0.0) for d in days}
    F['VT16xT200'] = {d: F['VT16 vol target 16% on SPY vol'][d] * F['T200 SPY>200d'][d] for d in days}
    F['VT20 floor 1/3'] = {d: max(1 / 3, F['VT20 vol target 20% on SPY vol'][d]) for d in days}
    return F


def inverse(lam, days):
    return {d: (1 - lam.get(d, 1.0)) if not isinstance(lam.get(d, 1.0), dict) else lam[d] for d in days}


def placebo(lam, days, rng):
    """Monthly mean allowance pattern, months randomly re-dated (gate_study/placebo2 convention)."""
    mean = {}
    for d in days:
        mean.setdefault(d[:7], []).append(lam.get(d, 1.0))
    mean = {m: sum(v) / len(v) for m, v in mean.items()}
    months = sorted(mean)
    perm = months[:]
    rng.shuffle(perm)
    mp = dict(zip(months, perm))
    return {d: mean[mp[d[:7]]] for d in days}


def fmt(m, extra=''):
    return (f"{m['cagr']:+7.1%} vol {m['vol']:5.1%} Sh {m['sharpe']:5.2f} So {m['sortino']:5.2f} Ca {m['calmar'] if m['calmar'] is not None else 0:5.2f} "
            f"DD {m['maxdd']:5.1%} worst {m['worst_year']:+6.1%}{extra}")


def engine_runs(panel):
    """Base holdings per engine: B -> HG on the long proxy panel; A -> four engines on build_prices.
    The tree runs are cached in OUT/base_<panel>.json (delete to force a rerun)."""
    cache = f'{OUT}/base_{panel}.json'
    if panel == 'B':
        P = gs.build_lh_prices()
        P1 = one_x_B(P)
    else:
        P, _ = build_prices()
        P1 = one_x_A(P)
    if os.path.exists(cache):
        runs = {e: (v['days'], v['hold']) for e, v in json.load(open(cache)).items()}
        return P, P1, runs
    runs = {}
    if panel == 'B':
        days, h, px = gs.base_run(P, *B_WIN)
        runs['HG'] = (days, h)
    else:
        sim = SimW(P, rsi_method='wilder')
        for e in ('HG', 'KMLM', 'SLEEVE', 'HARV'):
            tk = tree_tickers(trees[e])
            days = common_days(P, tk, *A_WIN)
            _, h = run_tree(sim, trees[e], days)
            runs[e] = (days, h)
    json.dump({e: {'days': d, 'hold': h} for e, (d, h) in runs.items()}, open(cache, 'w'))
    return P, P1, runs


def book(eng, days):
    """29/29/27/15, drifting, reset to target the close after any engine >40% (POLICY Op 5)."""
    w, out = dict(TARGET), {}
    for d in days:
        r = sum(w[e] * eng[e].get(d, 0.0) for e in w)
        out[d] = r
        w = {e: w[e] * (1 + eng[e].get(d, 0.0)) / (1 + r) for e in w}
        if max(w.values()) > 0.40:
            w = dict(TARGET)
    return out


def main(seed=11, n_placebo=100, n_boot=400):
    rng = random.Random(seed)
    res = {'panels': {}, 'notes': []}
    shortlist_B = []
    for panel in ('B', 'A'):
        P, P1, runs = engine_runs(panel)
        res['panels'][panel] = {}
        for e, (days, h) in runs.items():
            legs_held = sorted({t for d in h for t in h[d] if t in LEG})
            base, to0, _ = gate_run(days, h, P, P1, {}, ALL_CLASSES, COST[e])
            F = build_factors(P, P1, days, base, legs_held)
            rows, series = {}, {}
            for name, lam in F.items():
                cls = ('inverse',) if name.startswith('R4') else ('trend',)
                r, to, mean_l = gate_run(days, h, P, P1, lam, cls, COST[e])
                m = metrics(r, days)
                rows[name] = {'full': m, 'turnover': round(to, 1), 'mean_allow': round(mean_l, 3)}
                series[name] = r
                if panel == 'B':
                    rows[name]['windows'] = {w: gs.metrics(r, days, a, b) for w, (a, b) in WINDOWS_B.items()}
            # class application blends for a few shapes
            for name in ('A1 never levered', 'T200 SPY>200d', 'V20<25 SPY 20d vol', 'VT16 vol target 16% on SPY vol'):
                for cls_name, cls in (('all legs', ALL_CLASSES), ('trend+inverse', ('trend', 'inverse')), ('longvol only', ('longvol',))):
                    r, to, mean_l = gate_run(days, h, P, P1, F[name], cls, COST[e])
                    rows[f'{name} [{cls_name}]'] = {'full': metrics(r, days), 'turnover': round(to, 1), 'mean_allow': round(mean_l, 3)}
                    series[f'{name} [{cls_name}]'] = r
            res['panels'][panel][e] = {'rows': rows, 'legs_held': legs_held, 'n_days': len(days), 'first': days[0], 'last': days[-1]}
            print(f"\n== panel {panel} / {e}: {days[0]}..{days[-1]} ({len(days)} d); leveraged legs held: {' '.join(legs_held)}")
            print(f"   {'variant':40s} {'allow':>5s} {'TO/yr':>5s}  CAGR     vol   Sharpe Sortino Calmar  maxDD  worst yr")
            for name, row in rows.items():
                m = row['full']
                print(f"   {name[:40]:40s} {row['mean_allow']:5.2f} {row['turnover']:5.0f} {fmt(m)}")
            if panel == 'B':
                base_sh = rows['A0 always levered (as built)']['full']['sharpe']
                cands = [n for n in F if not n.startswith('A') and rows[n]['full']['sharpe'] > base_sh]
                cands.sort(key=lambda n: -rows[n]['full']['sharpe'])
                shortlist_B = cands[:8]
                for must in ('T200 SPY>200d', 'VT16 vol target 16% on SPY vol', 'V20<25 SPY 20d vol', 'A1 never levered'):
                    if must not in shortlist_B:
                        shortlist_B.append(must)
                print('\n   by window (CAGR/yr), panel B:')
                print(f"   {'variant':40s} " + ' '.join(f'{w:>13s}' for w in WINDOWS_B))
                for name in ['A0 always levered (as built)'] + shortlist_B:
                    print(f"   {name[:40]:40s} " + ' '.join(f"{rows[name]['windows'][w]['cagr']:+8.1%} {rows[name]['windows'][w]['maxdd']:4.0%}" for w in WINDOWS_B))
                # inverse + placebo + paired bootstrap for the shortlist
                print(f'\n   nulls, panel B ({n_placebo} placebos; paired {n_boot}x 20d-block bootstrap of Sharpe vs as built):')
                base_r = series['A0 always levered (as built)']
                ds = days[1:]
                nb = len(ds) // 20
                for name in shortlist_B:
                    lam = F[name]
                    if any(isinstance(v, dict) for v in lam.values()):
                        print(f"   {name[:40]:40s} per-leg gate: inverse/placebo skipped")
                        continue
                    inv_r, _, _ = gate_run(days, h, P, P1, inverse(lam, days), ('trend',), COST[e])
                    mi = metrics(inv_r, days)
                    draws = []
                    for _ in range(n_placebo):
                        pr, _, _ = gate_run(days, h, P, P1, placebo(lam, days, rng), ('trend',), COST[e])
                        draws.append(metrics(pr, days))
                    real = rows[name]['full']
                    pct = {k: sum(1 for x in draws if x[k] < real[k]) / n_placebo for k in ('cagr', 'sharpe', 'sortino')}
                    pct['dd_better'] = sum(1 for x in draws if x['maxdd'] > real['maxdd']) / n_placebo
                    r_v = series[name]
                    gaps = []   # paired block bootstrap (20-day blocks)
                    for _ in range(n_boot):
                        blocks = [rng.randrange(0, len(ds) - 20) for _ in range(nb)]
                        sel = [ds[s + k] for s in blocks for k in range(20)]
                        a = [r_v[d] - cash.get(d, 0.0) for d in sel]
                        b = [base_r[d] - cash.get(d, 0.0) for d in sel]
                        sh = lambda x: (sum(x) / len(x)) / math.sqrt(sum((v - sum(x) / len(x)) ** 2 for v in x) / (len(x) - 1)) * math.sqrt(252)   # noqa: E731
                        gaps.append(sh(a) - sh(b))
                    gaps.sort()
                    ci = (gaps[int(0.05 * n_boot)], gaps[int(0.95 * n_boot)])
                    p_gt = sum(1 for x in gaps if x > 0) / n_boot
                    rows[name]['nulls'] = {'inverse': mi, 'placebo_pct': pct, 'sharpe_gap_ci90': [round(ci[0], 3), round(ci[1], 3)], 'p_gap_gt0': p_gt}
                    print(f"   {name[:40]:40s} inverse {mi['cagr']:+6.1%}/Sh {mi['sharpe']:4.2f}/DD {mi['maxdd']:4.0%} | placebo pct CAGR {pct['cagr']:.2f} Sh {pct['sharpe']:.2f} DD-better {pct['dd_better']:.2f} | Sharpe gap vs built 90% [{ci[0]:+.2f},{ci[1]:+.2f}] P>0 {p_gt:.2f}")
            res['panels'][panel][e]['series_keep'] = {k: series[k] for k in ('A0 always levered (as built)', 'A1 never levered', 'T200 SPY>200d', 'V20<25 SPY 20d vol', 'VT16 vol target 16% on SPY vol') if k in series}
        if panel == 'A':
            # book-level application blends: which engines get the gate
            days_all = sorted(set.intersection(*[set(runs[e][0][1:]) for e in runs]))
            S = {e: res['panels']['A'][e]['series_keep'] for e in runs}
            combos = {}
            for gate in ('A1 never levered', 'T200 SPY>200d', 'V20<25 SPY 20d vol', 'VT16 vol target 16% on SPY vol'):
                for app, engs in (('HG only', {'HG'}), ('HG+KMLM', {'HG', 'KMLM'}), ('all engines', set(runs))):
                    eng = {e: (S[e][gate] if e in engs else S[e]['A0 always levered (as built)']) for e in runs}
                    combos[f'{gate} -> {app}'] = metrics(book(eng, days_all), ['x'] + days_all)
            combos['as built'] = metrics(book({e: S[e]['A0 always levered (as built)'] for e in runs}, days_all), ['x'] + days_all)
            res['book_A'] = {'window': [days_all[0], days_all[-1]], 'rows': combos}
            print(f"\n== book level, panel A {days_all[0]}..{days_all[-1]} (29/29/27/15 drift, cap-40):")
            for k, m in combos.items():
                print(f"   {k[:52]:52s} {fmt(m)}")
    res['shortlist_B'] = shortlist_B
    json.dump(res, open(f'{OUT}/levgate.json', 'w'))
    print('\nsaved', f'{OUT}/levgate.json')


if __name__ == '__main__':
    main()
