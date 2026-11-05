#!/usr/bin/env python3
"""Leg sizing on the KMLM switcher's own path: what capping or vol-scaling the 75% leveraged leg costs in CAGR per
point of max drawdown saved (owner question 2026-11-05; research only, nothing changes live).

The symphony "KMLM switcher + VIX sleeve 75/25" (YPTSJFJwD2ZKfAeYJUbW) runs one leveraged leg at 75% of the symphony
and a 25% VIX sleeve. On 2026-11-05 it held SOXL at 75% into a -33% SOXL session (Composer's ~15:50 exit; the 16:00
close printed -38.7%), lost 26.7% in a day and sits 31.7% below its 2026-08-17 peak.

Path: the add. 47 pipeline's KMLM run (research/longrun/book1997.py --modes ts_synth -> engines_ts_synth.json: per
session the holdings earning that session and the Composer-equivalent costed return), 1995-06-02..2026-11-04, synthetic
before each fund's launch (long_panel), the rules' own years after 2015-06 (in sample). GATE TEST first: the path's
daily return is rebuilt here from holdings x per-ticker returns (long_panel.build_long_prices) minus the engine's own
cost (cost_fit.json: 5.856 bps per unit sum|dw|, add. 38) and must match to 1e-9 before anything else runs.

The leg = the 75% group's risk holdings: TECL/SOXL/SPXL/LABU (3x longs: dip-buys at 75%, or the switcher's bottom-2 of
TECL/SOXL/SVIX at 37.5% each), SQQQ (-3x, 75%), UVXY (overbought pops, 75%), SVIX (-1x VIX, 37.5% in pairs). TLT is the
group's defensive leg and the 25% sleeve (PULS/VXZ/ZVOL) is never touched. The leg is 75% on 6,279 of 7,894 sessions and
never above it (no branch holds more). Variants, decided at the prior close from data through it; released weight goes
to PULS, the tree's own cash asset (= BIL in the panel):
  cap C          every leg holding x min(1, C/0.75), C = 60 / 50 / 37.5 / 25%
  cap 37.5 -> 1x the released half in the holding's 1x twin instead of cash (SVIX, no twin: unchanged)
  single-name    a lone leg holding (a dip-buy, a UVXY pop, SQQQ) capped at 37.5%; pair days untouched
  vol-target k   each leg holding x min(1, k / (0.75 x its realized 20-session vol, annualized)): the leg's vol
                 contribution capped at k; k solved so the mean leg weight equals each cap's, plus fixed k
  VIX gate       the whole leg halved when the prior close of ^VIX > 25 / > 30
  2x             SOXL -> USD, SPXL -> SSO; TECL / LABU / SQQQ -> 2/3 of the 3x fund's daily return (ROM, a 2x biotech
                 fund and QID are not in the panel: stated proxy); UVXY (1.5x) and SVIX unchanged
  1x             TECL -> XLK, SOXL -> SMH, SPXL -> SPY, LABU -> XBI, SQQQ -> PSQ, UVXY -> VIXY; SVIX unchanged
Costs: the engine's own, on each variant's own turnover. Metrics on 1995-06-02..2026-11-04 and 2015-06-01..2026-11-04:
CAGR (calendar time), max DD, Sharpe (daily, rf 0), Calmar, worst day / month, time under water, episode returns, the
2026-11-05 session from the live holding (SOXL 75 / PULS 16 / VXZ 9) at Composer's ~15:50 prints and at the 16:00
closes, "CAGR given up per point of max DD saved" vs as built, and the book (HG / KMLM / SLEEVE / HARV at the
2026-11-05 dollar weights, drifting, cap-40 reset at the next close, POLICY Op 5) with the KMLM variant swapped in.
Plus the by-products the EDGE rule asks for: the leg's return by prior-close vol quartile, by VIX bucket and by branch,
with t, hit rate, a mirrored bucket and a block-permutation placebo.

Counter-agent fixes (review1, 2026-11-05): (1) the SOXL dip-buy by-product is the REAL counterfactual: the live tree with
its RSI10(SOXL) < 30 condition disabled, replayed by the engine's own simulator (replay.SimW, Wilder RSI) on the same panel
and sessions, gated on identical holdings on every non-branch session; (2) leave-one-year-out ranges on every ratio (that
year's sessions set flat for base and variant), the 2015-26 max-DD episode and 2022's share of the 2015-26 growth; (3) the
longest time-under-water end date, SOXL's own 10-30 session; (4) the cap-37.5 -> 1x leg weight counts the SVIX halves that
stay in SVIX; (5) PULS = BIL on the whole path. Edge 1 gets its within-branch, 1x-twin, era and since-2015 checks.

Output: results/leg-sizing-2026-11-05.json (every frozen number the exhibit shows).
usage: leg_sizing.py [--engines PATH] [--out PATH] [--placebo N]
"""
import argparse
import copy
import datetime
import json
import math
import os
import random
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', 'longrun')))
import long_panel as lp   # noqa: E402
import book1997 as b97    # noqa: E402

RES = os.path.normpath(os.path.join(HERE, '..', '..', 'results'))
ENGINES = os.path.join(b97.OUT, 'engines_ts_synth.json')
OUT = os.path.join(RES, 'leg-sizing-2026-11-05.json')
SNAPSHOT = os.path.join(RES, 'monitor', 'last-snapshot.json')
COST_FIT = os.path.join(lp.gs.SP, 'cost_fit.json')

LEG = {'TECL': 3, 'SOXL': 3, 'SPXL': 3, 'LABU': 3, 'SQQQ': -3, 'UVXY': 1.5, 'SVIX': -1}   # ticker: daily leverage
BASE_LEG = 0.75
CASH = 'PULS'                       # the tree's own cash asset (the sleeve's); BIL in the panel
TWO_X = {'SOXL': ('USD', 1.0), 'SPXL': ('SSO', 1.0), 'TECL': ('TECL', 2 / 3), 'LABU': ('LABU', 2 / 3), 'SQQQ': ('SQQQ', 2 / 3)}
ONE_X = {'TECL': 'XLK', 'SOXL': 'SMH', 'SPXL': 'SPY', 'LABU': 'XBI', 'SQQQ': 'PSQ', 'UVXY': 'VIXY'}
WINDOWS = {'full': ('1995-06-02', '2026-11-04'), 'since2015': ('2015-06-01', '2026-11-04')}
EPISODES = {'2020-02-19..03-23 (COVID)': ('2020-02-19', '2020-03-23'), '2025-04-02..04-08 (tariffs)': ('2025-04-02', '2025-04-08'),
            '2022 full year': ('2022-01-01', '2022-12-31')}
VOL_N = 20
CAPS = (0.60, 0.50, 0.375, 0.25)
K_FIXED = (0.30, 0.45, 0.60, 0.90)
VIX_THR = (25, 30)
CAP40 = 0.40
PLACEBO_N = 1000
# 2026-11-05 (the path ends at the 11-04 close): the live holding into the session (Composer's 11-04 close: SOXL 75.5 / PULS
# 15.6 / VXZ 8.8, the tree's own 75 / 16 / 9) and the prints. 'as_traded' = Composer's ~15:50 rebalance: SOXL 44.50 per the
# owner's brief (5-minute bars printed 43.95-44.65 from 15:25 to 15:55), USD/SMH at the 15:50 bar; VXZ/PULS at the close.
# 'close' = the 16:00 closes (Yahoo, fetched 2026-11-05 21:50 UTC): SOXL slid 7% in the last five minutes. TECL (the
# edited tree's other half on 11-05): close only, no ~15:50 print on file.
LIVE_1105 = {'SOXL': 0.75, 'PULS': 0.16, 'VXZ': 0.09}
PX_1104 = {'SOXL': 66.68, 'USD': 65.28, 'SMH': 504.27, 'VXZ': 45.21, 'PULS': 49.50, '^VIX': 16.61, 'TECL': 163.69}
PX_1105 = {'as_traded': {'SOXL': 44.50, 'USD': 51.50, 'SMH': 452.37, 'VXZ': 48.21, 'PULS': 49.50},
           'close': {'SOXL': 40.87, 'USD': 50.27, 'SMH': 447.73, 'VXZ': 48.21, 'PULS': 49.50, 'TECL': 124.62}}
# the edited tree's holding into 11-05: with the dip-buy gone, the switcher's bottom-2 of TECL / SOXL / SVIX at the 11-04
# close AND at the 15:5x prices = SOXL / TECL (the engine's own close decision under both trees)
FT_LEG_1105 = {'SOXL': 0.375, 'TECL': 0.375}
SLEEVE = {'PULS', 'VXZ', 'ZVOL'}        # the 25% sleeve's assets: never in the 75% group
COMPOSER_1105 = {'value_1104': 99677.37, 'value_1105': 73020.64}   # monitor snapshots: the symphony's realized session
# the book into 11-05: the 11-04 close values (snapshot-20261104T213559Z) and the other engines' realized sessions
# (last-snapshot last_percent_change): HG held USD (-1.7%), SLEEVE BOXX (+0.0%), HARV ZVOL/PULS (+2.0%)
BOOK_1104 = {'HG': 89500.68, 'KMLM': 99677.37, 'SLEEVE': 81695.60, 'HARV': 37310.44}
OTHERS_1105 = {'HG': -0.0170, 'SLEEVE': 0.0001, 'HARV': 0.0202}


# ------------------------------------------------------------------ data
def load_engines(path):
    if not os.path.exists(path):
        print('engine cache missing: rebuilding via book1997.run_mode(ts_synth)', flush=True)
        b97.run_mode('ts_synth')
    return json.load(open(path))


def build_prices():
    P, meta = lp.build_long_prices('ts_synth')
    P['XBI'] = lp.splice(lp.yh('XBI'), lp.yh('^NBI'))        # LABU's 1x twin, panel A's construction
    return P, lp.yh('^VIX'), meta


def day_returns(P, days, tickers):
    """{ticker: {d1: P[d1]/P[d0] - 1}} on consecutive engine sessions; a missing price leaves the day out"""
    R, missing = {}, {}
    for t in tickers:
        px, r = P[t], {}
        for i in range(1, len(days)):
            d0, d1 = days[i - 1], days[i]
            if d0 in px and d1 in px:
                r[d1] = px[d1] / px[d0] - 1
            else:
                missing[t] = missing.get(t, 0) + 1
        R[t] = r
    return R, missing


def rolling_vol(r, days, n=VOL_N):
    """annualized population std of the last n session returns through each session (inclusive)"""
    out, q, s, s2 = {}, [], 0.0, 0.0
    for d in days[1:]:
        x = r.get(d)
        if x is None:
            continue
        q.append(x)
        s += x
        s2 += x * x
        if len(q) > n:
            y = q.pop(0)
            s -= y
            s2 -= y * y
        if len(q) == n:
            m = s / n
            out[d] = math.sqrt(max(s2 / n - m * m, 0.0) * 252)
    return out


def vol_through(px, end, n=VOL_N):
    """the same measure on a ticker's own dates, through `end`"""
    ds = [d for d in sorted(px) if d <= end][-(n + 1):]
    r = [px[ds[i]] / px[ds[i - 1]] - 1 for i in range(1, len(ds))]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / len(r) * 252)


# ------------------------------------------------------------------ the variant engine
def run_variant(days, hold, R, c, rule=None, sub=None, to_1x=False):
    """Daily returns of the path with the leg re-sized or re-instrumented, costed on the variant's own turnover.
    rule(d0, h) -> {leg ticker: factor in [0, 1]} (missing = 1), read at the decision close d0 for the holdings h that
    earn on d1; the released weight goes to CASH, or to the holding's 1x twin when to_1x. sub: {leg ticker: (proxy,
    scale)} replaces a holding's return by scale x the proxy's (weights unchanged)."""
    eff, gross, legw_sum = {}, {}, 0.0
    for i in range(1, len(days)):
        d0, d1 = days[i - 1], days[i]
        h = hold[d1]
        f = rule(d0, h) if rule else {}
        w, r = {}, 0.0
        for t, x in h.items():
            if t in LEG:
                ft = f.get(t, 1.0)
                w[t] = w.get(t, 0.0) + x * ft
                legw_sum += x * ft
                pt, sc = sub.get(t, (t, 1.0)) if sub else (t, 1.0)
                r += x * ft * sc * R[pt].get(d1, 0.0)
                rel = x * (1 - ft)
                if rel > 1e-12:
                    if to_1x:
                        k, src = ('1x:' + t, ONE_X[t]) if t in ONE_X else (t, t)
                        w[k] = w.get(k, 0.0) + rel
                        r += rel * R[src].get(d1, 0.0)
                        if t not in ONE_X:
                            legw_sum += rel      # SVIX has no twin: the released half stays in the leg (counter-agent fix 4)
                    else:
                        w[CASH] = w.get(CASH, 0.0) + rel
                        r += rel * R[CASH].get(d1, 0.0)
            else:
                w[t] = w.get(t, 0.0) + x
                r += x * R[t].get(d1, 0.0)
        eff[d1], gross[d1] = w, r
    out, to_tot = {}, 0.0
    for i in range(1, len(days)):
        d = days[i]
        nxt = days[i + 1] if i + 1 < len(days) else None
        w, wn = eff[d], (eff[nxt] if nxt else eff[d])
        to = sum(abs(wn.get(k, 0.0) - w.get(k, 0.0)) for k in set(w) | set(wn))
        to_tot += to
        out[d] = gross[d] - c * to
    n = len(days) - 1
    return out, {'avg_leg_weight': legw_sum / n, 'turnover_yr': to_tot / (n / 252)}


def cap_rule(C):
    def rule(d0, h):
        legw = sum(x for t, x in h.items() if t in LEG)
        return {t: C / legw for t in h if t in LEG} if legw > C + 1e-12 else {}
    return rule


def single_name_rule(S, only=None):
    """a lone leg holding above S is capped at S (pairs untouched); only: restrict to one ticker's lone days"""
    def rule(d0, h):
        L = [(t, x) for t, x in h.items() if t in LEG]
        if len(L) == 1 and L[0][1] > S + 1e-12 and (only is None or L[0][0] == only):
            return {L[0][0]: S / L[0][1]}
        return {}
    return rule


def vt_rule(k, VOL):
    def rule(d0, h):
        f = {}
        for t in h:
            if t in LEG:
                s = VOL[t].get(d0)
                if s:
                    f[t] = min(1.0, (k / s) / BASE_LEG)
        return f
    return rule


def vix_rule(thr, vix):
    def rule(d0, h):
        v = vix.get(d0)
        return {t: 0.5 for t in h if t in LEG} if v is not None and v > thr else {}
    return rule


def solve_k(target_avg, days, hold, VOL):
    """k whose mean leg weight over the path equals target_avg (monotone in k: bisection)"""
    rows = []
    for i in range(1, len(days)):
        d0 = days[i - 1]
        for t, x in hold[days[i]].items():
            if t in LEG:
                rows.append((x, VOL[t].get(d0)))
    n = len(days) - 1

    def avg(k):
        return sum(x * (min(1.0, (k / v) / BASE_LEG) if v else 1.0) for x, v in rows) / n
    lo, hi = 1e-3, 10.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if avg(mid) < target_avg:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ------------------------------------------------------------------ metrics
def prev_day(d):
    return (datetime.date.fromisoformat(d) - datetime.timedelta(days=1)).isoformat()


def stats(r, days, a, b):
    ds = [d for d in days if a <= d <= b and d in r]
    x = [r[d] for d in ds]
    n = len(x)
    cum, pk, pk_d, mdd, mdd_pk, mdd_tr = 1.0, 1.0, ds[0], 0.0, None, None
    tuw, tmax, tuw_from, tuw_to, under = 0, 0, None, None, 0
    months, years, worst_day = {}, {}, (0.0, None)
    for v, d in zip(x, ds):
        cum *= 1 + v
        months[d[:7]] = months.get(d[:7], 1.0) * (1 + v)
        years[d[:4]] = years.get(d[:4], 1.0) * (1 + v)
        if v < worst_day[0]:
            worst_day = (v, d)
        if cum >= pk:
            if tuw and tuw == tmax:
                tuw_to = d          # the longest stretch so far ends here (a new peak)
            pk, pk_d, tuw = cum, d, 0
        else:
            tuw += 1
            under += 1
            if tuw > tmax:
                tmax, tuw_from = tuw, pk_d
        dd = 1 - cum / pk
        if dd > mdd:
            mdd, mdd_pk, mdd_tr = dd, pk_d, d
    if tuw and tuw == tmax:
        tuw_to = 'open'
    yrs = (datetime.date.fromisoformat(ds[-1]) - datetime.date.fromisoformat(prev_day(ds[0]))).days / 365.25
    cagr = cum ** (1 / yrs) - 1
    mu = sum(x) / n
    sd = math.sqrt(sum((v - mu) ** 2 for v in x) / (n - 1))
    dn = math.sqrt(sum(min(v, 0.0) ** 2 for v in x) / n)
    wm = min((v - 1, m) for m, v in months.items())
    wy = min((v - 1, y) for y, v in years.items())
    return {'from': ds[0], 'to': ds[-1], 'n': n, 'years': round(yrs, 3), 'final_multiple': cum, 'cagr': cagr,
            'vol': sd * math.sqrt(252), 'sharpe': mu / sd * math.sqrt(252), 'sortino': mu / dn * math.sqrt(252) if dn else None,
            'maxdd': mdd, 'maxdd_peak': mdd_pk, 'maxdd_trough': mdd_tr, 'calmar': cagr / mdd if mdd else None,
            'worst_day': worst_day[0], 'worst_day_date': worst_day[1], 'worst_month': wm[0], 'worst_month_id': wm[1],
            'worst_year': wy[0], 'worst_year_id': wy[1], 'tuw_longest_sessions': tmax, 'tuw_longest_from': tuw_from, 'tuw_longest_to': tuw_to,
            'tuw_share': under / n, 'by_year': {y: v - 1 for y, v in sorted(years.items())}}


def cagr_dd(r, days, a, b, flat_year=None):
    """CAGR (calendar time, unchanged) and max DD on the window with one calendar year's sessions set flat: the
    counter-agent's leave-one-year-out"""
    ds = [d for d in days if a <= d <= b and d in r]
    cum, pk, mdd = 1.0, 1.0, 0.0
    for d in ds:
        if flat_year is None or d[:4] != flat_year:
            cum *= 1 + r[d]
            if cum > pk:
                pk = cum
            elif 1 - cum / pk > mdd:
                mdd = 1 - cum / pk
    yrs = (datetime.date.fromisoformat(ds[-1]) - datetime.date.fromisoformat(prev_day(ds[0]))).days / 365.25
    return cum ** (1 / yrs) - 1, mdd


def loyo(rb, rv, days, a, b):
    """the ratio (pp CAGR given up per pp max DD saved) with each calendar year left out (set flat for base and variant):
    its range and the years at the ends"""
    out = {}
    for y in sorted({d[:4] for d in days if a <= d <= b}):
        cb, db = cagr_dd(rb, days, a, b, y)
        cv, dv = cagr_dd(rv, days, a, b, y)
        dd = db - dv
        out[y] = ((cb - cv) / dd) if dd > 1e-9 else None
    vals = {y: v for y, v in out.items() if v is not None}
    mn = min(vals.items(), key=lambda kv: kv[1]) if vals else None
    mx = max(vals.items(), key=lambda kv: kv[1]) if vals else None
    return {'by_year': out, 'min': list(mn) if mn else None, 'max': list(mx) if mx else None, 'n_years': len(out)}


def mstat(x):
    n = len(x)
    mu = sum(x) / n if n else None
    sd = math.sqrt(sum((v - mu) ** 2 for v in x) / (n - 1)) if n > 1 else 0.0
    return {'n': n, 'mean': mu, 'sd': sd, 't': (mu / sd * math.sqrt(n)) if sd else None, 'hit': (sum(1 for v in x if v > 0) / n) if n else None}


def welch(a, b):
    """Welch t of mean(b) - mean(a) from two mstat dicts"""
    se = math.sqrt(a['sd'] ** 2 / a['n'] + b['sd'] ** 2 / b['n']) if a['n'] > 1 and b['n'] > 1 else 0.0
    return (b['mean'] - a['mean']) / se if se else None


def leg_kind(h):
    """what the 75% group holds: 'pair A+B', 'dip-buy X', 'UVXY', 'SQQQ', 'TLT'"""
    L = {t: x for t, x in h.items() if t in LEG}
    if not L:
        return 'TLT' if h.get('TLT') else 'none'
    if len(L) == 2:
        return 'pair ' + '+'.join(sorted(L))
    t = next(iter(L))
    return 'dip-buy ' + t if t in ('TECL', 'SOXL', 'SPXL', 'LABU') else t


# ------------------------------------------------------------------ the edited tree (counter-agent fix 1)
def edit_tree_no_soxl_dip(tree):
    """the live tree with its RSI10(SOXL) < 30 dip-buy disabled: the condition can never fire (rhs -1), so that 'if'
    falls through to its else-branch, the approved tree's next checks (SPXL RSI10 < 30, LABU RSI10 < 25, then the
    XLK-vs-KMLM switcher). Returns (edited deep copy, number of conditions changed: must be exactly 1)."""
    T = copy.deepcopy(tree)
    hits = []

    def walk(n):
        if (n.get('step') == 'if-child' and not n.get('is-else-condition?') and n.get('lhs-fn') == 'relative-strength-index'
                and n.get('lhs-val') == 'SOXL' and n.get('comparator') == 'lt' and n.get('rhs-fixed-value?') and float(n['rhs-val']) == 30):
            n['rhs-val'] = '-1'
            hits.append(n)
        for k in n.get('children') or []:
            walk(k)
    walk(T)
    return T, len(hits)


def fallthrough(P, days, hold, R, first_real):
    """Replay the edited tree with the engine's own simulator (replay.SimW, Wilder RSI) on the same panel and sessions.
    GATE: its holdings must equal the engine's on every session the SOXL dip-buy did not fire. Returns the edited holdings
    (what the fall-through variant earns) and the day-level comparison on the branch's sessions, symphony-level: the 75%
    group's contribution as built (SOXL 75) vs the fall-through holdings vs the released-to-PULS alternative."""
    T2, nhit = edit_tree_no_soxl_dip(lp.gs.trees['KMLM'])
    if nhit != 1:
        sys.exit(f'tree edit: expected one RSI10(SOXL) < 30 condition, found {nhit}')
    sim = lp.lg.SimW(P, rsi_method='wilder')
    _, h2 = lp.lg.run_tree(sim, T2, days)
    branch = [d for d in days[1:] if hold[d].get('SOXL') == BASE_LEG]
    bset = set(branch)
    mism = [d for d in days[1:] if d not in bset and h2[d] != hold[d]]
    print(f'fall-through gate: edited tree vs engine holdings on {len(days) - 1 - len(branch)} non-branch sessions: {len(mism)} mismatches', flush=True)
    if mism:
        sys.exit(f'FALL-THROUGH GATE FAILED: the edited tree differs from the engine on non-branch sessions, e.g. {mism[:3]}; stop')
    rows = []
    for d in branch:
        ab = sum(x * R[t].get(d, 0.0) for t, x in hold[d].items() if t not in SLEEVE)
        ft = sum(x * R[t].get(d, 0.0) for t, x in h2[d].items() if t not in SLEEVE)
        rows.append((d, ab, ft, BASE_LEG * R[CASH].get(d, 0.0), leg_kind(h2[d])))
    kinds = Counter(r[4] for r in rows)
    eras = {'all': rows, 'synthetic (before SOXL launch)': [r for r in rows if r[0] < first_real['SOXL']],
            'real (since SOXL launch)': [r for r in rows if r[0] >= first_real['SOXL']],
            'since 2015-06': [r for r in rows if r[0] >= WINDOWS['since2015'][0]]}

    def comp(rs):
        a, b, p, dd = mstat([r[1] for r in rs]), mstat([r[2] for r in rs]), mstat([r[3] for r in rs]), mstat([r[2] - r[1] for r in rs])
        return {'n': len(rs), 'as_built': a, 'fall_through': b, 'puls': p, 'diff': dd,
                'compounded_as_built': math.prod(1 + r[1] for r in rs), 'compounded_fall_through': math.prod(1 + r[2] for r in rs)}
    in_pair = sum(v for k, v in kinds.items() if k.startswith('pair') and 'SOXL' in k)
    return h2, {'edit': 'the live tree with its RSI10(SOXL) < 30 condition disabled (rhs -1): that if falls through to its else-branch (SPXL RSI10 < 30, LABU RSI10 < 25, the XLK-vs-KMLM switcher)',
                'gate': {'non_branch_sessions': len(days) - 1 - len(branch), 'mismatches': len(mism), 'simulator': "replay.SimW (Wilder RSI), the engine's own, same panel and sessions"},
                'branch_sessions': len(branch), 'holdings': dict(kinds.most_common()),
                'soxl_in_pair': {'n': in_pair, 'share': in_pair / len(branch)}, 'sqqq_or_tlt': {'n': kinds['SQQQ'] + kinds['TLT'], 'share': (kinds['SQQQ'] + kinds['TLT']) / len(branch)},
                'day_level': {k: comp(v) for k, v in eras.items() if len(v) > 2},
                'basis': "symphony-level: the 75% group's contribution to the session (SOXL 75% as built vs the fall-through holdings vs 75% in PULS), before costs; " +
                         f"synthetic / real split at SOXL's launch {first_real['SOXL']}"}


def episode(r, days, a, b):
    g = 1.0
    for d in days:
        if a <= d <= b and d in r:
            g *= 1 + r[d]
    return g - 1


def tradeoff(base, s):
    """CAGR given up per point of max DD saved vs as built (pp per pp; None when no DD is saved)"""
    dc, dd = s['cagr'] - base['cagr'], base['maxdd'] - s['maxdd']
    return {'d_cagr': dc, 'dd_saved': dd, 'cagr_per_dd': (-dc / dd) if dd > 1e-9 else None,
            'd_sharpe': s['sharpe'] - base['sharpe'], 'd_calmar': (s['calmar'] or 0) - (base['calmar'] or 0)}


def book(eng, days, target):
    """drifting from target; an engine above 40% at a close is reset to target at the NEXT close (POLICY Op 5)"""
    w, out, pending = dict(target), {}, False
    for d in days:
        r = sum(w[e] * eng[e].get(d, 0.0) for e in w)
        out[d] = r
        w = {e: w[e] * (1 + eng[e].get(d, 0.0)) / (1 + r) for e in w}
        if pending:
            w, pending = dict(target), False
        if max(w.values()) > CAP40:
            pending = True
    return out


def path_sample(r, days, a, b, step=5):
    ds = [d for d in days if a <= d <= b and d in r]
    v, pk, vals, dds = 1.0, 1.0, [], []
    for d in ds:
        v *= 1 + r[d]
        pk = max(pk, v)
        vals.append(v)
        dds.append(v / pk - 1)
    sel = list(range(0, len(ds), step)) + ([len(ds) - 1] if (len(ds) - 1) % step else [])
    return {'dates': [ds[i] for i in sel], 'value': [round(vals[i], 5) for i in sel],
            'dd': [round(min(dds[max(0, i - step + 1):i + 1]), 4) for i in sel]}


# ------------------------------------------------------------------ edge by-products
def bucket_stats(rows, key):
    out = {}
    for row in rows:
        out.setdefault(key(row), []).append(row)
    res = {}
    for k, rs in out.items():
        x = [r[1] for r in rs]
        n = len(x)
        mu = sum(x) / n
        sd = math.sqrt(sum((v - mu) ** 2 for v in x) / (n - 1)) if n > 1 else 0.0
        ru = [r[1] / (r[2] / math.sqrt(252)) for r in rs if r[2]]
        res[k] = {'n': n, 'mean': mu, 'sd': sd, 't': mu / sd * math.sqrt(n) if sd else None, 'hit': sum(1 for v in x if v > 0) / n,
                  'mean_ret_per_daily_sigma': sum(ru) / len(ru) if ru else None, 'worst': min(x), 'best': max(x),
                  'log_growth_at_75pct': sum(math.log1p(BASE_LEG * v) for v in x), 'mean_sigma': sum(r[2] for r in rs) / n,
                  'per_year_pct': None}
    return res


def draw_placebo(rows, n_pick, observed, n_draw, seed=13, block=21):
    """the mean of n_pick leg days drawn as random 21-session blocks of the leg-day sequence, n_draw times: where the
    observed branch mean sits in that distribution (the branch's days vs any days of the same count)"""
    rets = [r[1] for r in rows]
    rng = random.Random(seed)
    nb = max(1, round(n_pick / block))
    draws = []
    for _ in range(n_draw):
        pick = []
        for _ in range(nb):
            i = rng.randrange(0, max(1, len(rets) - block))
            pick.extend(rets[i:i + block])
        draws.append(sum(pick) / len(pick))
    draws.sort()
    return {'p05': draws[int(0.05 * len(draws))], 'p50': draws[len(draws) // 2], 'p95': draws[int(0.95 * len(draws))],
            'percentile_of_observed': sum(1 for g in draws if g < observed) / len(draws), 'draws': len(draws), 'block_sessions': block}


def block_placebo(rows, label_of, group_a, group_b, n_draw, seed=11, block=21):
    """observed mean(a) - mean(b) vs the same statistic with the labels re-dated in 21-session blocks"""
    labs = [label_of(r) for r in rows]
    rets = [r[1] for r in rows]

    def gap(lb):
        a = [v for v, l in zip(rets, lb) if l == group_a]
        b = [v for v, l in zip(rets, lb) if l == group_b]
        return (sum(a) / len(a) - sum(b) / len(b)) if a and b else None
    obs = gap(labs)
    rng = random.Random(seed)
    blocks = [labs[i:i + block] for i in range(0, len(labs), block)]
    draws = []
    for _ in range(n_draw):
        bl = list(blocks)
        rng.shuffle(bl)
        lb = [l for bb in bl for l in bb][:len(labs)]
        g = gap(lb)
        if g is not None:
            draws.append(g)
    draws.sort()
    pct = sum(1 for g in draws if g < obs) / len(draws) if draws else None
    return {'observed_gap': obs, 'placebo_p05': draws[int(0.05 * len(draws))], 'placebo_p50': draws[len(draws) // 2],
            'placebo_p95': draws[int(0.95 * len(draws))], 'percentile_of_observed': pct, 'draws': len(draws), 'block_sessions': block}


def edge_section(days, hold, R, VOL, vix, n_draw, first_real):
    rows = []       # (d1, leg return at base weights / 0.75, weighted prior-close sigma, prior-close VIX, branch, the 1x twins' return)
    for i in range(1, len(days)):
        d0, d1 = days[i - 1], days[i]
        L = {t: x for t, x in hold[d1].items() if t in LEG}
        if not L:
            continue
        rl = sum(x * R[t].get(d1, 0.0) for t, x in L.items()) / BASE_LEG
        sig = sum(x * VOL[t].get(d0, 0.0) for t, x in L.items()) / BASE_LEG
        tw = sum(x * R[ONE_X.get(t, t)].get(d1, 0.0) for t, x in L.items()) / BASE_LEG     # the same names' 1x twins (SVIX: none, stays)
        rows.append((d1, rl, sig, vix.get(d0), leg_kind(hold[d1]), tw))
    sig_sorted = sorted(r[2] for r in rows)
    q = [sig_sorted[int(len(sig_sorted) * p)] for p in (0.25, 0.5, 0.75)]
    QL = ('Q1 lowest vol', 'Q2', 'Q3', 'Q4 highest vol')

    def qlab(r):
        return QL[0] if r[2] <= q[0] else QL[1] if r[2] <= q[1] else QL[2] if r[2] <= q[2] else QL[3]

    def vlab(r):
        v = r[4 - 1]
        return 'n/a' if v is None else 'VIX <= 20' if v <= 20 else 'VIX 20-25' if v <= 25 else 'VIX 25-30' if v <= 30 else 'VIX > 30'
    yrs = (datetime.date.fromisoformat(days[-1]) - datetime.date.fromisoformat(days[1])).days / 365.25
    by_sig, by_vix, by_kind = bucket_stats(rows, qlab), bucket_stats(rows, vlab), bucket_stats(rows, lambda r: r[4])
    for b in (by_sig, by_vix, by_kind):
        for v in b.values():
            v['per_year_pct'] = (math.exp(v['log_growth_at_75pct'] / yrs) - 1)
    # the same by-branch split in the live-rule years only
    rows15 = [r for r in rows if r[0] >= '2015-06-01']
    by_kind15 = bucket_stats(rows15, lambda r: r[4])
    yrs15 = (datetime.date.fromisoformat(days[-1]) - datetime.date.fromisoformat('2015-05-31')).days / 365.25
    for v in by_kind15.values():
        v['per_year_pct'] = (math.exp(v['log_growth_at_75pct'] / yrs15) - 1)
    for k, v in by_kind.items():
        v['placebo'] = draw_placebo(rows, v['n'], v['mean'], n_draw)
        # synthetic / real split at the latest launch among the branch's funds (counter-agent, review1)
        tks = k.split(' ', 1)[1].split('+') if k.startswith(('pair', 'dip-buy')) else [k]
        launch = max(first_real[t] for t in tks)
        rs = [r for r in rows if r[4] == k]
        v['eras'] = {'launch': launch, 'synthetic': mstat([r[1] for r in rs if r[0] < launch]), 'real': mstat([r[1] for r in rs if r[0] >= launch])}
    allx = [r[1] for r in rows]
    mu = sum(allx) / len(allx)
    sd = math.sqrt(sum((v - mu) ** 2 for v in allx) / (len(allx) - 1))
    # --- counter-agent (review1) checks on edge 1: the gradient within each branch (its own sigma quartiles), in the 1x
    # twins on the same days with the same labels, the Q4 bucket's composition by year, and since 2015 on its own quartiles
    q1s, q4s = mstat([r[1] for r in rows if qlab(r) == QL[0]]), mstat([r[1] for r in rows if qlab(r) == QL[3]])

    def own_quartiles(rs):
        e = sorted(r[2] for r in rs)
        lo, hi = e[int(len(e) * 0.25)], e[int(len(e) * 0.75)]
        a, b = mstat([r[1] for r in rs if r[2] <= lo]), mstat([r[1] for r in rs if r[2] > hi])
        return {'n': len(rs), 'Q1': a, 'Q4': b, 'welch_t_Q4_minus_Q1': welch(a, b)}
    within = {k: own_quartiles([r for r in rows if r[4] == k]) for k, v in by_kind.items() if v['n'] >= 150}
    mirror = {k: mstat([r[5] for r in rows if qlab(r) == k]) for k in QL}
    ysum = {}
    for r in rows:
        if qlab(r) == QL[3]:
            ysum[r[0][:4]] = ysum.get(r[0][:4], 0.0) + r[1]
    tot4 = sum(ysum.values())
    q4comp = {'sum_of_daily_returns': tot4, 'top_years_share': {y: v / tot4 for y, v in sorted(ysum.items(), key=lambda kv: -kv[1])[:6]},
              'pre_2010_share': sum(v for y, v in ysum.items() if y < '2010') / tot4, 'share_2022': ysum.get('2022', 0.0) / tot4}
    e15 = sorted(r[2] for r in rows15)
    q15 = [e15[int(len(e15) * p)] for p in (0.25, 0.5, 0.75)]
    since15 = bucket_stats(rows15, lambda r: QL[0] if r[2] <= q15[0] else QL[1] if r[2] <= q15[1] else QL[2] if r[2] <= q15[2] else QL[3])
    p_soxl = by_kind['dip-buy SOXL']['placebo']['percentile_of_observed']
    return {'leg_days': len(rows), 'leg_mean': mu, 'leg_sd': sd, 'leg_t': mu / sd * math.sqrt(len(allx)),
            'sigma_quartile_edges': q, 'by_sigma_quartile': by_sig, 'by_vix': by_vix, 'by_branch': by_kind, 'by_branch_since2015': by_kind15,
            'placebo_sigma_Q4_minus_Q1': block_placebo(rows, qlab, QL[3], QL[0], n_draw),
            'placebo_vix_gt25_minus_le25': block_placebo(rows, lambda r: 'hi' if (r[3] or 0) > 25 else 'lo', 'hi', 'lo', n_draw, seed=12),
            'welch_t_Q4_minus_Q1': welch(q1s, q4s), 'within_branch_own_quartiles': within, 'mirror_1x_twins_same_days': mirror,
            'q4_composition': q4comp, 'since2015_own_quartiles': since15, 'since2015_sigma_quartile_edges': q15,
            'worst_of_branches_placebo': {'n_branches': len(by_kind), 'soxl_dip_percentile': p_soxl,
                                          'p_some_branch_at_or_below': 1 - (1 - p_soxl) ** len(by_kind),
                                          'note': 'the SOXL dip-buy is the minimum of the branch t-stats; a placebo percentile this low for the worst of n branches is expected 1 - (1 - p)^n of the time'},
            'note': 'leg return = the leveraged holdings\' return at their base weights / 0.75 (the leg at 100%); sigma = the holdings\' '
                    'weighted realized 20-session vol at the prior close; VIX = prior close; in sample on the engine\'s own path; '
                    'mirror = the same names\' 1x twins (XLK, SMH, SPY, XBI, PSQ, VIXY; SVIX itself) on the same days with the same vol labels'}


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--engines', default=ENGINES)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--placebo', type=int, default=PLACEBO_N)
    a = ap.parse_args()
    E = load_engines(a.engines)
    days, rets, hold = E['KMLM']['days'], E['KMLM']['rets'], E['KMLM']['hold']
    P, vix, meta = build_prices()
    c = json.load(open(COST_FIT))['KMLM']['cost_bps_per_unit_sum_abs_dw'] / 1e4
    held = sorted({t for h in hold.values() for t in h})
    twins = sorted({v[0] for v in TWO_X.values()} | set(ONE_X.values()))
    R, missing = day_returns(P, days, sorted(set(held) | set(twins)))
    # --- gate test: the path's return = holdings x returns - cost on the path's own turnover
    base, info0 = run_variant(days, hold, R, c)
    diffs = [abs(base[d] - rets[d]) for d in days[1:]]
    gate = {'max_abs_diff': max(diffs), 'n': len(diffs), 'cost_bps_per_unit_sum_abs_dw': c * 1e4, 'missing_returns': missing}
    print(f"gate test: rebuilt KMLM path vs engines_ts_synth rets: max |diff| {gate['max_abs_diff']:.2e} over {gate['n']} sessions", flush=True)
    if gate['max_abs_diff'] > 1e-9:
        sys.exit('GATE FAILED: the rebuilt path does not match the engine path; stop')
    # --- leg structure
    kinds = Counter()
    for h in hold.values():
        kinds[', '.join(f'{t} {x:g}' for t, x in sorted(h.items()) if t in LEG) or 'none (TLT)'] += 1
    legw = Counter(round(sum(x for t, x in h.items() if t in LEG), 4) for h in hold.values())
    # --- vol series and matched k
    VOL = {t: rolling_vol(R[t], days) for t in LEG}
    n = len(days) - 1
    base_avg = sum(x for h in hold.values() for t, x in h.items() if t in LEG) / n
    k_matched = {C: solve_k(C * legw[BASE_LEG] / n, days, hold, VOL) for C in CAPS}
    print('matched k:', {C: round(k, 4) for C, k in k_matched.items()}, flush=True)
    # --- variants
    V = [('base', 'as built (75% leg)', 'base', {}, None, None, False)]
    for C in CAPS:
        V.append((f'cap{C * 100:g}', f'cap {C * 100:g}% -> PULS', 'cap', {'cap': C}, cap_rule(C), None, False))
    V.append(('cap37.5_1x', 'cap 37.5%, released half in the 1x twin', 'cap1x', {'cap': 0.375}, cap_rule(0.375), None, True))
    V.append(('sn37.5', 'single-name cap 37.5% (pairs untouched)', 'single', {'cap': 0.375}, single_name_rule(0.375), None, False))
    for C in CAPS:
        V.append((f'vt_m{C * 100:g}', f'vol-target k {k_matched[C]:.2f} (mean leg weight = cap {C * 100:g}%)', 'vt', {'k': k_matched[C], 'matched_cap': C}, vt_rule(k_matched[C], VOL), None, False))
    for k in K_FIXED:
        V.append((f'vt_k{k:g}', f'vol-target k {k:.2f}', 'vt', {'k': k}, vt_rule(k, VOL), None, False))
    for thr in VIX_THR:
        V.append((f'vix{thr}', f'leg halved when prior VIX > {thr}', 'vix', {'vix': thr}, vix_rule(thr, vix), None, False))
    V.append(('two_x', '2x substitution (USD, SSO; 2/3 of TECL, LABU, SQQQ)', 'sub', {}, None, TWO_X, False))
    V.append(('one_x', '1x reference (XLK, SMH, SPY, XBI, PSQ, VIXY)', 'sub', {}, None, {t: (p, 1.0) for t, p in ONE_X.items()}, False))
    # by-product (EDGE rule), not a sizing option: the real counterfactual for the SOXL dip-buy branch (counter-agent fix 1):
    # the edited tree replayed by the engine's own simulator; its holdings replace the path's on the branch's sessions
    first_real = {t: min(lp.yh(t)) for t in ('SOXL', 'TECL', 'SPXL', 'LABU', 'SQQQ', 'UVXY', 'SVIX', 'VXZ', 'ZVOL', 'PULS', 'BIL', 'KMLM', 'RYMFX', 'TLT', 'USD', 'SSO', 'SMH', 'XLK', 'PSQ', 'VIXY', 'XBI')}
    hold_ft, FT = fallthrough(P, days, hold, R, first_real)
    print(f"fall-through: {FT['branch_sessions']} branch sessions -> {FT['holdings']}; SOXL 37.5 in a pair on {FT['soxl_in_pair']['n']}", flush=True)
    V.append(('soxl_dip_ft', 'by-product: SOXL dip-buy branch removed (the edited tree falls through to its next checks)', 'byprod',
              {'edit': 'RSI10(SOXL) < 30 disabled'}, None, None, False))
    HOLD_OVERRIDE = {'soxl_dip_ft': hold_ft}
    # --- book inputs
    snap = json.load(open(SNAPSHOT))
    sym = {'HG': 'mbkiXcuNDjueXpiox5Av', 'KMLM': 'YPTSJFJwD2ZKfAeYJUbW', 'SLEEVE': 'nNdBk7hc5NiBzeRvbI5T', 'HARV': 'ORQNCfZnA18wmsMWVhf8'}
    dollars = {e: snap['symphonies'][s]['value'] for e, s in sym.items()}
    tot = sum(dollars.values())
    target = {e: v / tot for e, v in dollars.items()}
    eng = {e: E[e]['rets'] for e in sym}
    bdays = {w: [d for d in sorted(set().union(*[set(E[e]['days']) for e in sym])) if a0 <= d <= b0] for w, (a0, b0) in WINDOWS.items()}
    # --- 11-05 inputs
    sig_soxl = vol_through(P['SOXL'], '2026-11-04')
    vix_1104 = PX_1104['^VIX']
    out_v, paths, series = {}, {}, {}
    base_stats = {}
    btot = sum(BOOK_1104.values())
    for vid, label, fam, params, rule, sub, to1x in V:
        r, info = run_variant(days, HOLD_OVERRIDE.get(vid, hold), R, c, rule, sub, to1x)
        series[vid] = r
        S = {w: stats(r, days, *WINDOWS[w]) for w in WINDOWS}
        if vid == 'base':
            base_stats = S
        row = {'label': label, 'family': fam, 'params': params, 'avg_leg_weight': info['avg_leg_weight'], 'turnover_yr': info['turnover_yr'],
               'windows': S, 'episodes': {k: episode(r, days, *v) for k, v in EPISODES.items()},
               'tradeoff': {w: tradeoff(base_stats[w], S[w]) for w in WINDOWS}}
        # the 11-05 session from the live holding
        d11 = {}
        for ps, px in PX_1105.items():
            rr = {t: px[t] / PX_1104[t] - 1 for t in px}
            sleeve = LIVE_1105['PULS'] * rr['PULS'] + LIVE_1105['VXZ'] * rr['VXZ']
            if vid == 'soxl_dip_ft':
                # the edited tree holds the engine's own close decision, SOXL / TECL 37.5 each; TECL has a close but no ~15:50 print
                if 'TECL' not in px:
                    d11[ps] = None
                    continue
                leg_ret = sum(x * rr[t] for t, x in FT_LEG_1105.items())
                d11[ps] = {'leg_weight': sum(FT_LEG_1105.values()), 'leg_instrument': '+'.join(FT_LEG_1105), 'leg_contrib': leg_ret, 'sleeve_contrib': sleeve,
                           'day': leg_ret + sleeve, 'book_day': sum(BOOK_1104[e] / btot * OTHERS_1105[e] for e in OTHERS_1105) + BOOK_1104['KMLM'] / btot * (leg_ret + sleeve),
                           'note': 'the edited tree\'s holding into 11-05 (SOXL 37.5 / TECL 37.5, the engine\'s own close decision under both trees); at the 16:00 closes only'}
                continue
            f = 1.0
            if fam in ('cap', 'cap1x', 'single'):
                f = min(1.0, params['cap'] / BASE_LEG)
            elif fam == 'vt':
                f = min(1.0, (params['k'] / sig_soxl) / BASE_LEG)
            elif fam == 'vix':
                f = 0.5 if vix_1104 > params['vix'] else 1.0
            leg_src = 'SOXL'
            if vid == 'two_x':
                leg_src = 'USD'
            if vid == 'one_x':
                leg_src = 'SMH'
            leg_ret = LIVE_1105['SOXL'] * f * rr[leg_src] + LIVE_1105['SOXL'] * (1 - f) * (rr['SMH'] if to1x else rr['PULS'])
            bday = sum(BOOK_1104[e] / btot * OTHERS_1105[e] for e in OTHERS_1105) + BOOK_1104['KMLM'] / btot * (leg_ret + sleeve)
            d11[ps] = {'leg_weight': LIVE_1105['SOXL'] * f, 'leg_instrument': leg_src, 'leg_contrib': leg_ret, 'sleeve_contrib': sleeve, 'day': leg_ret + sleeve,
                       'book_day': bday}
        row['day_2026_11_05'] = d11
        # book
        bk = {}
        for w in WINDOWS:
            e2 = dict(eng)
            e2['KMLM'] = r
            br = book(e2, bdays[w], target)
            bs = stats(br, bdays[w], *WINDOWS[w])
            bk[w] = {k: bs[k] for k in ('cagr', 'maxdd', 'sharpe', 'calmar', 'worst_day', 'worst_day_date', 'maxdd_peak', 'maxdd_trough', 'final_multiple')}
        row['book'] = bk
        out_v[vid] = row
        paths[vid] = {w: path_sample(r, days, *WINDOWS[w]) for w in WINDOWS}
        d11p = d11['as_traded'] or d11['close']
        print(f"{vid:12s} full CAGR {S['full']['cagr']:+.1%} DD {S['full']['maxdd']:.1%} Sh {S['full']['sharpe']:.2f} | 2015 CAGR {S['since2015']['cagr']:+.1%} "
              f"DD {S['since2015']['maxdd']:.1%} Sh {S['since2015']['sharpe']:.2f} | 11-05 {d11p['day']:+.1%}{'' if d11['as_traded'] else ' (closes)'} | leg {info['avg_leg_weight']:.3f} to/yr {info['turnover_yr']:.0f}", flush=True)
    # --- leave-one-year-out on every ratio (counter-agent fix 2): that year's sessions set flat for base and variant
    for vid in out_v:
        if vid != 'base':
            out_v[vid]['loyo'] = {w: loyo(series['base'], series[vid], days, *WINDOWS[w]) for w in WINDOWS}
    for vid in ('cap37.5', 'cap60', 'vt_m60', 'vix30'):
        L = out_v[vid]['loyo']
        print(f"LOYO {vid:8s} " + ' | '.join(f"{w}: as is {out_v[vid]['tradeoff'][w]['cagr_per_dd']:.2f}, {L[w]['min'][1]:.2f} (no {L[w]['min'][0]}) .. {L[w]['max'][1]:.2f} (no {L[w]['max'][0]})" for w in WINDOWS), flush=True)
    # the fall-through's largest day-level differences (full costed daily returns) and the concentration of the windows
    rb, rf = series['base'], series['soxl_dip_ft']
    bdays_ft = [d for d in days[1:] if hold[d].get('SOXL') == BASE_LEG]
    for key, lo_d, keyf in (('largest_day_differences', '0000', lambda d: -abs(rf[d] - rb[d])), ('largest_day_differences_since2015', WINDOWS['since2015'][0], lambda d: -abs(rf[d] - rb[d])),
                            ('worst_for_fall_through_since2015', WINDOWS['since2015'][0], lambda d: rf[d] - rb[d])):
        diffs = sorted((d for d in bdays_ft if d >= lo_d), key=keyf)[:6]
        FT[key] = [{'date': d, 'as_built': rb[d], 'fall_through': rf[d], 'held': leg_kind(hold_ft[d])} for d in diffs]
    FT['edited_tree'] = {w: {k: out_v['soxl_dip_ft']['windows'][w][k] for k in ('cagr', 'maxdd', 'sharpe', 'calmar', 'tuw_longest_sessions', 'worst_day', 'worst_day_date')} for w in WINDOWS}
    FT['episodes'] = {k: {'as_built': out_v['base']['episodes'][k], 'fall_through': out_v['soxl_dip_ft']['episodes'][k]} for k in EPISODES}
    print('fall-through largest day diffs:', [(x['date'], round(x['as_built'] * 100, 1), round(x['fall_through'] * 100, 1), x['held']) for x in FT['largest_day_differences']], flush=True)
    bs = base_stats['since2015']
    conc = {'share_2022_of_log_growth_since2015': math.log1p(bs['by_year']['2022']) / math.log(bs['final_multiple']),
            'maxdd_since2015_episode': [bs['maxdd_peak'], bs['maxdd_trough']], 'maxdd_full_episode': [base_stats['full']['maxdd_peak'], base_stats['full']['maxdd_trough']],
            'maxdd_since2015_not_2020': {vid: [v['windows']['since2015']['maxdd_peak'], v['windows']['since2015']['maxdd_trough']] for vid, v in out_v.items()
                                         if v['windows']['since2015']['maxdd_trough'][:4] != '2020'},
            'dd_saved_full_pp': {vid: v['tradeoff']['full']['dd_saved'] * 100 for vid, v in out_v.items() if vid != 'base'},
            'note': 'every since-2015 ratio divides by the Feb-Mar 2020 drawdown; a full-window ratio that divides by < 3 pp of DD saved is ill-conditioned'}
    print(f"2022 share of 2015-26 log growth {conc['share_2022_of_log_growth_since2015']:.3f}; since-2015 max DD {conc['maxdd_since2015_episode']}; variants whose own since-2015 max DD is not 2020: {sorted(conc['maxdd_since2015_not_2020'])}", flush=True)
    # base book for reference (same as out_v['base']['book'])
    bench = {}
    for bname in ('SPY', 'QQQ'):
        rb_ = {d: v for d, v in lp.rets_of(P[bname]).items()}
        bench[bname] = {w: {k: stats(rb_, days, *WINDOWS[w])[k] for k in ('cagr', 'maxdd', 'sharpe')} for w in WINDOWS}
    edge = edge_section(days, hold, R, VOL, vix, a.placebo, first_real)
    composer_day = COMPOSER_1105['value_1105'] / COMPOSER_1105['value_1104'] - 1
    soxl_1030 = P['SOXL']['2026-10-30'] / P['SOXL']['2026-10-29'] - 1

    def lo(vid, w):
        L = out_v[vid]['loyo'][w]
        return f"{out_v[vid]['tradeoff'][w]['cagr_per_dd']:.2f} as is, {L['min'][1]:.2f} (no {L['min'][0]}) .. {L['max'][1]:.2f} (no {L['max'][0]})"
    no20 = {vid: out_v[vid]['loyo']['since2015']['by_year'].get('2020') for vid in ('cap60', 'cap37.5', 'vt_m60', 'vix30')}
    ft_s = FT['day_level']
    res = {'generated': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
           'question': 'KMLM switcher + VIX sleeve 75/25: what capping or vol-scaling the 75% leveraged leg costs in CAGR per point of max DD saved, on the engine\'s own path',
           'inputs': {'engine_path': a.engines, 'days': [days[1], days[-1]], 'sessions': n, 'vix_mode': meta.get('vix_mode'), 'cost_bps_per_unit_sum_abs_dw': c * 1e4,
                      'cost_source': 'cost_fit.json (Composer-equivalent, add. 38), applied to each variant\'s own turnover', 'leg': LEG, 'cash': CASH,
                      'two_x_map': {t: f'{p} x {s:.3g}' for t, (p, s) in TWO_X.items()}, 'one_x_map': ONE_X, 'vol_window_sessions': VOL_N,
                      'leg_weight_distribution': {str(k): v for k, v in sorted(legw.items())}, 'branch_days': dict(kinds.most_common()),
                      'first_real_date': first_real, 'book_dollars_2026_11_05': dollars, 'book_weights': target, 'cap40': CAP40,
                      'live_holding_1105': LIVE_1105, 'px_1104': PX_1104, 'px_1105': PX_1105, 'sigma20_soxl_1104': sig_soxl, 'vix_1104': vix_1104,
                      'soxl_1030': soxl_1030, 'path_1030': rets['2026-10-30'], 'ft_leg_1105': FT_LEG_1105,
                      'composer_realized_1105': composer_day, 'composer_values_1105': COMPOSER_1105, 'matched_k': {f'{C:g}': k for C, k in k_matched.items()},
                      'book_1104_dollars': BOOK_1104, 'book_1104_weights': {e: v / sum(BOOK_1104.values()) for e, v in BOOK_1104.items()}, 'others_1105': OTHERS_1105,
                      'book_realized_1105': sum(BOOK_1104[e] / sum(BOOK_1104.values()) * OTHERS_1105[e] for e in OTHERS_1105) + BOOK_1104['KMLM'] / sum(BOOK_1104.values()) * composer_day},
           'gate_test': gate, 'windows': WINDOWS, 'episodes': EPISODES, 'variants': out_v, 'order': [v[0] for v in V], 'paths': paths, 'bench': bench, 'edge': edge,
           'fallthrough': FT, 'concentration': conc,
           'honesty': [
               'All variants are in-sample re-sizings of a live rule on its own reconstructed path: the KMLM rules were built on 2015-26, and every variant is a function of the same holdings; the 1995-2015 years are out of sample for the rules but synthetic for most legs.',
               f'Synthetic data before each fund\'s launch (long_panel, ts_synth VIX mode): SOXL real from {first_real["SOXL"]}, TECL {first_real["TECL"]}, SPXL {first_real["SPXL"]}, LABU {first_real["LABU"]}, SQQQ {first_real["SQQQ"]}, UVXY {first_real["UVXY"]}, SVIX {first_real["SVIX"]}, VXZ {first_real["VXZ"]}, ZVOL {first_real["ZVOL"]}; PULS = BIL on the whole path, 2018-26 included (long_panel sets PULS to BIL; BIL real from {first_real["BIL"]}, T-bills before), so released weight earns T-bills throughout; the KMLM signal from RYMFX before {first_real["KMLM"]} and a trend proxy before {first_real["RYMFX"]}; VIX funds before 2006 model a market that did not exist.',
               f'The 2015-26 ratios are one episode: the as-built max DD since 2015, every ratio\'s starting point, is {conc["maxdd_since2015_episode"][0]} → {conc["maxdd_since2015_episode"][1]} (COVID), as is every cap\'s; the {len(conc["maxdd_since2015_not_2020"])} vol-target and VIX variants cut COVID below their own 2015-16 or 2018-Q4 drawdowns. So "pp of CAGR per pp of DD saved" since 2015 is priced on Feb-Mar 2020 alone. Leave-one-year-out (that year set flat for base and variant): cap 37.5 {lo("cap37.5", "since2015")}; vol-target k {k_matched[0.60]:.2f} {lo("vt_m60", "since2015")}; VIX > 30 {lo("vix30", "since2015")}. "VIX gates are the cheapest DD since 2015" and "vol-targeting beats caps since 2015" are statements about Feb-Mar 2020: without 2020 the vol-target costs more per pp than the cap at the same mean leg weight ({no20["vt_m60"]:.2f} vs cap 60 {no20["cap60"]:.2f}). The full-window vol-target and VIX ratios divide by < 3 pp of DD saved ({conc["dd_saved_full_pp"]["vt_m60"]:.1f} and {conc["dd_saved_full_pp"]["vix30"]:.1f} pp) and are ill-conditioned (vt k {k_matched[0.60]:.2f}: {lo("vt_m60", "full")}). 2022 (+{bs["by_year"]["2022"]:,.0%}) is {conc["share_2022_of_log_growth_since2015"]:.0%} of the 2015-26 log growth.',
               f'Costs: the engine\'s own Composer-equivalent assumption only ({c * 1e4:.3f} bps per unit of sum|dw|, i.e. {2 * c * 1e4:.1f} bps per full switch, add. 38), charged on each variant\'s own turnover; the vol-target\'s daily resizing pays it every day. No financing, borrow or tax beyond what the funds\' (synthetic) returns embed.',
               'Not modeled: Composer\'s 10pp threshold corridor (the path rebalances to target daily; live KMLM trades only when a holding drifts 10pp off target), taxes, the sleeve\'s own rebalancing and its interaction with a smaller leg (the sleeve stays at its path weights; released weight sits in PULS beside it). Cap 37.5 → 1x keeps the SVIX halves in SVIX (no twin), so its mean leg weight is '
               f'{out_v["cap37.5_1x"]["avg_leg_weight"]:.1%}, not the cap\'s {out_v["cap37.5"]["avg_leg_weight"]:.1%}.',
               '2x and 1x legs are substitutions on the same decisions: the decisions (RSI thresholds on the 3x funds) are unchanged, only the instrument earning the day changes; ROM, QID and a 2x biotech fund are proxied as 2/3 of the 3x fund\'s daily return.',
               'The 2026-11-05 session is outside the path (which ends at the 11-04 close): it is the live holding (SOXL 75%, PULS 16%, VXZ 9%) priced at Composer\'s ~15:50 prints (SOXL 44.50 per the brief; the 15:50 bar printed 44.03) and at the 16:00 closes (SOXL 40.87 after a 7% slide in the final five minutes). Composer\'s realized session was '
               f'{composer_day:+.1%} (its own fills, then TECL into the close). The engine\'s closing-price decision on 11-04 was SOXL 37.5 / TECL 37.5; Composer held SOXL 75.5 (a knife-edge at 15:5x prices, shadow ledger): the day is shown on the live holding, as the question asks.',
               'Vol-target and VIX rules read the decision close (d0) and earn d1, as the engine does; Composer decides at ~15:50, not the close. The matched k is solved on the full path, so the 2015-26 mean leg weight differs slightly from the cap\'s.',
               f'The by-product row is the real counterfactual for the SOXL dip-buy branch: the live tree with its RSI10(SOXL) < 30 condition disabled, replayed by the engine\'s own simulator (Wilder RSI) on the same panel; identical holdings on every one of the {FT["gate"]["non_branch_sessions"]:,} non-branch sessions (checked), the fall-through holdings on the {FT["branch_sessions"]} branch sessions ({", ".join(f"{k} {v}" for k, v in FT["holdings"].items())}: SOXL 37.5 in a pair on only {FT["soxl_in_pair"]["share"]:.0%}), costed on its own turnover. The branch\'s sessions are {ft_s["synthetic (before SOXL launch)"]["n"] / FT["branch_sessions"]:.0%} synthetic. Its 11-05 is at the 16:00 closes only: the edited tree holds the engine\'s own close decision (SOXL 37.5 / TECL 37.5, the same under both trees) and no ~15:50 TECL print is on file; the as-built figure is Composer\'s knife-edge at 15:5x prices.']}
    json.dump(res, open(a.out, 'w'), default=lambda o: float(o))
    print('wrote', a.out, f'({os.path.getsize(a.out) // 1024} KB)')


if __name__ == '__main__':
    main()
