"""YTD 2026 leverage attribution: how much of the Composer account's return came from leverage?

COUNTERFACTUAL ("unlevered"): the SAME signals, the SAME trades on the SAME days; every ETF the
symphonies held with |leverage| > 1 is swapped, at the holding step only, for its 1x version in the
same direction:
    3x/2x long  -> the 1x ETF on the same index      (TQQQ -> QQQ, UDOW -> DIA, SOXL -> SOXX ...)
    -3x inverse -> the -1x inverse                    (SQQQ -> PSQ, TMV -> TBF)
    UVXY (1.5x) -> VIXY (1x)
Where no real 1x ETF tracks the same index (USD, LABD, SOXS) the product's own daily return is
de-levered:  r_1x = (r_L + (|L|-1) * rf) / |L|   (a daily-reset L-x fund earns L*index - (L-1)*rf;
the same identity with |L| gives the same-direction 1x return for an inverse fund).
ROBUSTNESS: the whole study is re-run with that self-de-levering applied to EVERY leveraged ticker.
Products at or below 1x (bonds, cash, sector ETFs, SVIX -1x, SVXY -0.5x, ZVOL, VXZ, VIXM) are untouched.
Decisions are NOT re-run with 1x tickers in the conditions: the symphonies' thresholds (RSI etc.)
are tuned on the leveraged tickers, so that would be a different strategy, not "the same one unlevered".

TWO VIEWS
  A. ACCOUNT (live, what actually happened): the account's own time-weighted return (Composer
     portfolio-history), minus each day's leverage contribution
         c_t = sum_s  w_s,t-1  *  sum_i h_s,i,t-1 * (r_i,t - r_1x(i),t)
     w_s = live symphony value / account value at the prior close (cash and pending deposits carry
     no leverage); h = the Composer model holdings of the symphony VERSION live on that decision
     date.  Fills, slippage, cash drag and deposit timing stay exactly as they happened.
  B. BOOK AS BUILT TODAY (model): the four current versions from 2025-12-31 at 29/29/27/15,
     drifting, with the POLICY Op 5 cap-40 reset; levered vs unlevered on identical holdings.
     KMLM, SLEEVE and HARV were designed in July 2026 on data that includes H1 2026: in sample.

Model convention (add. 38): holdings dated d are decided at d's close and earn d+1's adjclose
return; trading cost = per-engine bps x sum|h(d1) - h(d0)| charged on the trade day.  The cost is
identical in both legs (same weights), so it cancels in the leverage contribution.

Inputs (fetch_*.py, all under LEV_DATA): yh/<T>.json, backtests.json, portfolio_history.json,
live_symphonies.json.  Output: LEV_DATA/lev_study.json and a printed summary.
"""
import json
import math
import os

D = os.environ.get('LEV_DATA', '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/lev')
YTD0, YTD1 = '2025-12-31', '2026-10-15'      # base close, last complete close

# ------------------------------------------------------------------ leverage map
# ticker: (leverage, real 1x ETF on the same index or None -> self-de-lever)
MAP = {
    'TQQQ': (3, 'QQQ'), 'QLD': (2, 'QQQ'), 'UPRO': (3, 'SPY'), 'SPXL': (3, 'SPY'), 'SSO': (2, 'SPY'),
    'UDOW': (3, 'DIA'), 'TNA': (3, 'IWM'), 'TECL': (3, 'XLK'), 'SOXL': (3, 'SOXX'), 'LABU': (3, 'XBI'),
    'UGE': (2, 'XLP'), 'UGL': (2, 'GLD'), 'TMF': (3, 'TLT'), 'UVXY': (1.5, 'VIXY'),
    'SQQQ': (-3, 'PSQ'), 'TMV': (-3, 'TBF'),
    'USD': (2, None), 'LABD': (-3, None), 'SOXS': (-3, None),
}
UNLEVERED = {'ANGL', 'BIL', 'BOXX', 'BSV', 'KIE', 'LQD', 'PULS', 'SMH', 'SPAB', 'SVIX', 'SVXY', 'TLT', 'VBF',
             'VCIT', 'VIXM', 'VIXY', 'VXZ', 'XLP', 'XLU', 'XLV', 'ZVOL'}
COST_BPS = {'HG': 5.12, 'KMLM': 5.86, 'ORIG': 5.86, 'SLEEVE': 2.25, 'HARV': 5.21}   # add. 38 fits

# version live for each decision date (created_at vs the ~15:50 ET rebalance; see versions.json)
SCHEDULE = {
    'HG': [('0000-00-00', 'HG:0DeB193gVf6uIq2osLmL'),          # 2025-12-05 original, live until the 07-30 update:
           # the 06-30 saves (6jq2...) were never deployed — on 2026-07-02 live HG earned XLV's +2.63% to 1 bp,
           # a leaf the 06-30 version no longer has (counter-agent, 2026-10-16)
           ('2026-07-31', 'HG:bP4mvRy6YHHejuPGUBNY')],         # saved 07-30 23:30 ET, after the close
    'ORIG': [('0000-00-00', 'ORIG:wt3G61qcuOZ8MVYJ64v4')],
    'KMLM': [('0000-00-00', 'KMLM:MVfHI8OgKae5EaC3W9oE')],
    'SLEEVE': [('0000-00-00', 'SLEEVE:GtCP9qywDB4E5kxj6ScN'),  # 07-06 13:11 ET; live from 07-07
               ('2026-07-31', 'SLEEVE:yHJkdePZUWBT6eMCgO9m')], # 07-30 23:31 ET
    'HARV': [('0000-00-00', 'HARV:XVtsDTV1R6iuYDEg8XZK')],     # 07-21 17:34 ET; live from 07-22
}
CURRENT = {'HG': 'HG:bP4mvRy6YHHejuPGUBNY', 'KMLM': 'KMLM:MVfHI8OgKae5EaC3W9oE',
           'SLEEVE': 'SLEEVE:yHJkdePZUWBT6eMCgO9m', 'HARV': 'HARV:XVtsDTV1R6iuYDEg8XZK'}
TARGET = {'HG': 0.29, 'KMLM': 0.29, 'SLEEVE': 0.27, 'HARV': 0.15}
# ORIG (KMLM switcher original, liquidated 2026-07-07) has no live series left; its value is the
# account residual on 06-30..07-02, and on 07-06 the residual less the $49,075.85 HG withdrawal
# that sat in cash that night (CHANGELOG 2026-07-06).
ORIG_DAYS = ('2026-06-30', '2026-07-01', '2026-07-02', '2026-07-06')
HG_WITHDRAWAL_CASH = {'2026-07-06': 49075.85}


def epoch_ms_to_iso(ms):
    import datetime
    return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).date().isoformat()


def load_px(t):
    o = json.load(open(f"{D}/yh/{t.replace('^', '_')}.json"))
    return dict(zip(o['dates'], o['close'] if t == '^IRX' else o['adjclose']))


def returns(p):
    ds = sorted(p)
    return {ds[i]: p[ds[i]] / p[ds[i - 1]] - 1 for i in range(1, len(ds))}


SPY_PX = load_px('SPY')
DAYS = sorted(SPY_PX)
IRX = load_px('^IRX')
RF = {DAYS[i]: IRX[DAYS[i - 1]] / 100 / 252 for i in range(1, len(DAYS))}   # rate locked at the prior close
YTD = [d for d in DAYS if YTD0 < d <= YTD1]
_R = {}


def R(t):
    if t not in _R:
        _R[t] = returns(load_px(t))
    return _R[t]


def r1x(t, d, method):
    """Same-direction 1x return of ticker t on day d.  method: 'real' (real 1x ETF where one tracks
    the same index) or 'self' (self-de-levered for every leveraged ticker)."""
    if t not in MAP:
        if t not in UNLEVERED:
            raise KeyError(f'{t}: not classified as leveraged or unlevered')
        return R(t)[d]
    L, real = MAP[t]
    if method == 'real' and real:
        return R(real)[d]
    return (R(t)[d] + (abs(L) - 1) * RF[d]) / abs(L)


def model_path(hold, method, cost_bps):
    """Levered and unlevered daily returns of one version's model holdings, plus the leverage
    contribution c = gross levered - gross unlevered (cost cancels)."""
    rL, rU, c = {}, {}, {}
    for i in range(1, len(DAYS)):
        d0, d1 = DAYS[i - 1], DAYS[i]
        h0, h1 = hold.get(d0), hold.get(d1)
        if not h0:
            continue
        gL = sum(w * R(t)[d1] for t, w in h0.items())
        gU = sum(w * r1x(t, d1, method) for t, w in h0.items())
        cost = cost_bps / 1e4 * sum(abs(h1.get(t, 0) - h0.get(t, 0)) for t in set(h0) | set(h1)) if h1 else 0.0
        rL[d1], rU[d1], c[d1] = gL - cost, gU - cost, gL - gU
    return rL, rU, c


def metrics(r, ds):
    x = [r[d] for d in ds]
    ex = [a - RF[d] for a, d in zip(x, ds)]
    n = len(ex)
    mu = sum(ex) / n
    sd = math.sqrt(sum((e - mu) ** 2 for e in ex) / (n - 1))
    dn = math.sqrt(sum(min(e, 0.0) ** 2 for e in ex) / n)
    v = pk = 1.0
    mdd = 0.0
    for a in x:
        v *= 1 + a
        pk = max(pk, v)
        mdd = max(mdd, 1 - v / pk)
    return {'ytd': round(v - 1, 4), 'vol': round(sd * math.sqrt(252), 4),
            'sharpe': round(mu / sd * math.sqrt(252), 3) if sd else None,
            'sortino': round(mu / dn * math.sqrt(252), 3) if dn else None,
            'maxdd': round(mdd, 4), 'n': n}


def cum_path(r, ds):
    v, out = 1.0, {}
    for d in ds:
        v *= 1 + r[d]
        out[d] = v
    return out


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sab = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    saa = sum((x - ma) ** 2 for x in a)
    sbb = sum((y - mb) ** 2 for y in b)
    return sab / math.sqrt(saa * sbb)


def version_for(sym, d0):
    key = None
    for start, k in SCHEDULE[sym]:
        if d0 >= start:
            key = k
    return key


def main():
    B = json.load(open(f'{D}/backtests.json'))
    ph = json.load(open(f'{D}/portfolio_history.json'))
    live = json.load(open(f'{D}/live_symphonies.json'))
    out = {'window': [YTD0, YTD1], 'n_days': len(YTD), 'map': {t: list(v) for t, v in MAP.items()}}

    # ---- 1. model paths for every version, both methods; validate vs Composer's own equity
    paths, val = {}, {}
    for key, bt in B.items():
        sym = bt['sym']
        eq = bt['equity']
        comp = {d1: eq[d1] / eq[d0] - 1 for d0, d1 in zip(DAYS, DAYS[1:]) if d0 in eq and d1 in eq}
        for method in ('real', 'self'):
            mL, mU, c = model_path(bt['holdings'], method, COST_BPS[sym])
            # levered = Composer's own backtest (exact); unlevered = Composer's backtest minus the
            # leverage contribution of the same holdings.  mL (our reproduction) is kept only as a check.
            paths[(key, method)] = ({d: comp[d] for d in c if d in comp},
                                    {d: comp[d] - c[d] for d in c if d in comp}, c, mL)
        mL = paths[(key, 'real')][3]
        ds = [d for d in YTD if d in mL and d in comp]
        val[key] = {'corr_vs_composer': round(corr([mL[d] for d in ds], [comp[d] for d in ds]), 5),
                    'ytd_composer': round(math.prod(1 + comp[d] for d in ds) - 1, 4),
                    'ytd_reproduced': round(math.prod(1 + mL[d] for d in ds) - 1, 4), 'n': len(ds)}
    out['model_validation'] = val

    # ---- 2. view A: the account's live path
    A = {epoch_ms_to_iso(ms): v for ms, v in zip(ph['epoch_ms'], ph['series'])}
    TW = {epoch_ms_to_iso(ms): v for ms, v in zip(ph['epoch_ms'], ph['cumulative_twr_series'])}
    V = {s: {epoch_ms_to_iso(ms): v for ms, v in zip(p['epoch_ms'], p['series'])} for s, p in live.items() if p['epoch_ms']}
    adays = sorted(d for d in TW if d <= YTD1)
    missing = [d for d in YTD if d not in TW]
    extra = [d for d in adays if d > YTD0 and d not in set(DAYS)]
    out['account_calendar'] = {'missing_trading_days': missing, 'non_trading_days_in_series': extra}
    ORIG_V = {}
    for d in ORIG_DAYS:
        resid = A[d] - sum(V[s].get(d, 0.0) for s in V)
        ORIG_V[d] = resid - HG_WITHDRAWAL_CASH.get(d, 0.0)
    out['orig_value_used'] = {d: round(v, 2) for d, v in ORIG_V.items()}
    # ORIG was cash at the 06-30 close (bought at the 07-01 window) and still held its 07-02 basket on 07-07
    # until the 15:50 liquidation (live -10.2% vs the basket -10.8%; the model had rotated to UVXY)
    ORIG_HOLD = {'2026-07-01': {}, '2026-07-07': B['ORIG:wt3G61qcuOZ8MVYJ64v4']['holdings']['2026-07-02']}
    # Composer's deposit-adjusted series per symphony: V1 = (V0 + F) * (1 + r), deposit counted at the start of the day
    DA = {s: {epoch_ms_to_iso(ms): v for ms, v in zip(p['epoch_ms'], p['deposit_adjusted_series'])} for s, p in live.items() if p['epoch_ms']}
    # HG's live holdings where they differ from the model (infer_live.py; run it first)
    inf_path = f'{D}/hg_inferred.json'
    HG_INF = json.load(open(inf_path))['rows'] if os.path.exists(inf_path) else {}
    out['hg_inference_counts'] = json.load(open(inf_path))['counts'] if HG_INF else None

    def hold_of(s, d0, d1, method):
        """holdings that earned d1's return (decided at d0)"""
        if s == 'ORIG' and d1 in ORIG_HOLD:
            return ORIG_HOLD[d1]
        if s == 'HG' and d1 in HG_INF and method != 'real_no_inference':
            row = HG_INF[d1]
            if method == 'real_openbest' and row['class'] == 'open' and row.get('best_hold'):
                return row['best_hold']
            return row['inferred_hold']
        return B[version_for(s, d0)]['holdings'][d0]

    def ret_of(h, d1):
        return sum(w * R(t)[d1] for t, w in h.items())

    def c_of(h, d1, method):
        return sum(w * (R(t)[d1] - r1x(t, d1, method)) for t, w in h.items())

    def lev_share(h, d1):
        """share of a return earned by holdings h that is leverage: sum_i a_i (1 - 1/|L_i|), a_i = the leg's
        share of the day's close-to-close move (weight x |L| when the day is flat); clipped to [0, 1]."""
        contrib = {t: w * R(t)[d1] for t, w in h.items()}
        tot = sum(contrib.values())
        if abs(tot) >= 0.001:
            a = {t: c / tot for t, c in contrib.items()}
        else:
            z = sum(w * (abs(MAP[t][0]) if t in MAP else 1.0) for t, w in h.items())
            a = {t: w * (abs(MAP[t][0]) if t in MAP else 1.0) / z for t, w in h.items()} if z else {}
        return max(0.0, min(1.0, sum(a[t] * (1 - 1 / abs(MAP[t][0])) for t in a if t in MAP)))

    # methods: real (central: real 1x twins, inferred HG holdings), self (every ETF self-de-levered),
    # real_no_inference (model holdings throughout), real_openbest (unresolved HG days -> best-fitting leaf),
    # real_nodeposit (no intraday leverage effect on deposit dollars)
    acct, flows, FS, bys = {}, {}, {}, {}
    for method in ('real', 'self', 'real_no_inference', 'real_openbest', 'real_nodeposit'):
        mth = 'self' if method == 'self' else 'real'
        rA, rAU, cA, wsum = {}, {}, {}, {}
        for d1 in YTD:
            d0 = DAYS[DAYS.index(d1) - 1]
            r = (1 + TW[d1]) / (1 + TW[d0]) - 1
            F = A[d1] / (1 + r) - A[d0]                  # external flow, Composer's start-of-day convention
            F = F if abs(F) > 100 else 0.0
            base = A[d0] + F
            flows[d1] = F
            c, ws = 0.0, 0.0
            for s in ('HG', 'KMLM', 'SLEEVE', 'HARV', 'ORIG'):
                if s == 'ORIG':
                    v0, fs, rl = ORIG_V.get(d0, 0.0), 0.0, None
                else:
                    v0 = V.get(s, {}).get(d0, 0.0)
                    da0, da1 = DA.get(s, {}).get(d0), DA.get(s, {}).get(d1)
                    rl = (da1 / da0 - 1) if (da0 and da1) else None
                    fs = (V[s][d1] / (1 + rl) - v0) if (rl is not None and d1 in V[s]) else 0.0
                    fs = fs if abs(fs) > 100 else 0.0
                    FS.setdefault(s, {})[d1] = fs
                if v0 <= 0 and fs <= 0:
                    continue
                h = hold_of(s, d0, d1, method)
                if not h:
                    continue
                w_hold = max(v0 + min(fs, 0.0), 0.0) / base      # a withdrawal leaves at the open
                cs = w_hold * c_of(h, d1, mth)
                ws += w_hold
                if fs > 0 and rl is not None and method != 'real_nodeposit':
                    # the deposit's own return from fill to close, from the symphony's deposit-adjusted return
                    rF = ((v0 + fs) * (1 + rl) - v0 * (1 + ret_of(h, d1))) / fs - 1
                    rF = max(-0.15, min(0.15, rF))
                    cs += fs / base * rF * lev_share(h, d1)
                    ws += fs / base
                c += cs
                if method == 'real':
                    bys[s] = bys.get(s, 0.0) + cs
            rA[d1], rAU[d1], cA[d1], wsum[d1] = r, r - c, c, ws
        acct[method] = {'actual': rA, 'unlevered': rAU, 'contribution': cA, 'invested_share': wsum}
    out['flows_recovered'] = {d: round(f, 2) for d, f in flows.items() if f}
    # E2: the model (Composer backtests of the live versions) at the live weights; cash earns 0
    mod = {}
    for d1 in YTD:
        d0 = DAYS[DAYS.index(d1) - 1]
        r = 0.0
        for s in ('HG', 'KMLM', 'SLEEVE', 'HARV', 'ORIG'):
            val_s = ORIG_V.get(d0, 0.0) if s == 'ORIG' else V.get(s, {}).get(d0, 0.0)
            if val_s > 0:
                r += val_s / (A[d0] + flows[d1]) * paths[(version_for(s, d0), 'real')][0][d1]
        mod[d1] = r
    acct['real']['model_levered'] = mod
    acct['real']['model_unlevered'] = {d: mod[d] - acct['real']['contribution'][d] for d in YTD}
    if HG_INF:
        ds_ = sorted(HG_INF)
        out['hg_cost_check'] = {
            'live': round(math.prod(1 + HG_INF[d]['live'] for d in ds_) - 1, 4),
            'model_frictionless': round(math.prod(1 + HG_INF[d]['model_ret'] for d in ds_) - 1, 4),
            'model_composer_costed': round(math.prod(B[version_for('HG', DAYS[DAYS.index(d) - 1])]['equity'][d]
                                                      / B[version_for('HG', DAYS[DAYS.index(d) - 1])]['equity'][DAYS[DAYS.index(d) - 1]] for d in ds_) - 1, 4)}
    out['account_model_check'] = {'corr_live_vs_model_daily': round(corr([acct['real']['actual'][d] for d in YTD], [mod[d] for d in YTD]), 4),
                                  'ytd_live': round(math.prod(1 + acct['real']['actual'][d] for d in YTD) - 1, 4),
                                  'ytd_model_same_weights': round(math.prod(1 + mod[d] for d in YTD) - 1, 4)}

    # ---- 3. view B: the book as built today (model)
    def book(eng_paths):
        w, res, resets = dict(TARGET), {}, []
        for d1 in YTD:
            r = sum(w[e] * eng_paths[e][d1] for e in w)
            res[d1] = r
            w = {e: w[e] * (1 + eng_paths[e][d1]) / (1 + r) for e in w}
            if max(w.values()) > 0.40:
                w, _ = dict(TARGET), resets.append(d1)
        return res, resets
    bookv = {}
    for method in ('real', 'self'):
        L = {e: paths[(CURRENT[e], method)][0] for e in CURRENT}
        U = {e: paths[(CURRENT[e], method)][1] for e in CURRENT}
        bL, rsL = book(L)
        bU, rsU = book(U)
        bookv[method] = {'levered': bL, 'unlevered': bU, 'resets_levered': rsL, 'resets_unlevered': rsU, 'eng_L': L, 'eng_U': U}

    # ---- 4. benchmarks
    bench = {t: {d: R(t)[d] for d in YTD} for t in ('SPY', 'QQQ', 'SSO', 'UPRO')}

    # ---- 5. metrics
    M = {}
    for method in ('real', 'self'):
        m = {}
        m['ACCOUNT actual (live)'] = metrics(acct[method]['actual'], YTD)
        m['ACCOUNT unlevered'] = metrics(acct[method]['unlevered'], YTD)
        if method == 'real':
            m['ACCOUNT unlevered, model holdings (no HG inference)'] = metrics(acct['real_no_inference']['unlevered'], YTD)
            m['ACCOUNT unlevered, unresolved HG days -> best-fit leaf'] = metrics(acct['real_openbest']['unlevered'], YTD)
            m['ACCOUNT unlevered, no deposit-day intraday effect'] = metrics(acct['real_nodeposit']['unlevered'], YTD)
            ku = metrics(acct['real']['unlevered'], YTD)
            k = m['ACCOUNT actual (live)']['vol'] / ku['vol']
            m['ACCOUNT unlevered scaled to actual vol (constant %.2fx)' % k] = metrics({d: RF[d] + k * (acct['real']['unlevered'][d] - RF[d]) for d in YTD}, YTD)
            m['DIAG costed Composer model at live weights, levered'] = metrics(acct['real']['model_levered'], YTD)
            m['DIAG costed Composer model at live weights, unlevered'] = metrics(acct['real']['model_unlevered'], YTD)
        m['BOOK as built, levered (model)'] = metrics(bookv[method]['levered'], YTD)
        m['BOOK as built, unlevered (model)'] = metrics(bookv[method]['unlevered'], YTD)
        for e in CURRENT:
            m[f'{e} levered (model)'] = metrics(bookv[method]['eng_L'][e], YTD)
            m[f'{e} unlevered (model)'] = metrics(bookv[method]['eng_U'][e], YTD)
            if method == 'real' and e in ('HG', 'KMLM'):   # same holdings with no trading cost: how much of the Sharpe drop is cost
                fl, c_ = paths[(CURRENT[e], 'real')][3], paths[(CURRENT[e], 'real')][2]
                m[f'{e} levered (frictionless)'] = metrics({d: fl[d] for d in YTD}, YTD)
                m[f'{e} unlevered (frictionless)'] = metrics({d: fl[d] - c_[d] for d in YTD}, YTD)
        M[method] = m
    for t, r in bench.items():
        M['real'][f'{t} buy & hold'] = metrics(r, YTD)
    out['metrics'] = M
    out['book_resets'] = {m: {'levered': bookv[m]['resets_levered'], 'unlevered': bookv[m]['resets_unlevered']} for m in bookv}

    # leverage contribution by symphony: sum of the weighted daily contributions (not compounded)
    out['account_contribution_by_symphony_sum_of_daily'] = {s_: round(v, 4) for s_, v in bys.items()}
    # contribution by half: H1 (HG only) vs Jul-Oct
    for lab, (a, b) in {'Jan-Jun': ('2026-01-02', '2026-06-30'), 'Jul-Oct15': ('2026-07-01', YTD1)}.items():
        ds = [d for d in YTD if a <= d <= b]
        out.setdefault('account_by_period', {})[lab] = {
            'actual': metrics(acct['real']['actual'], ds), 'unlevered': metrics(acct['real']['unlevered'], ds)}

    def dd_dates(r, ds):
        v = pk = 1.0
        pkd, best = ds[0], (0.0, None, None)
        for d in ds:
            v *= 1 + r[d]
            if v > pk:
                pk, pkd = v, d
            if 1 - v / pk > best[0]:
                best = (1 - v / pk, pkd, d)
        return {'maxdd': round(best[0], 4), 'peak': best[1], 'trough': best[2]}
    out['dd_dates'] = {'account actual': dd_dates(acct['real']['actual'], YTD),
                       'account unlevered': dd_dates(acct['real']['unlevered'], YTD),
                       'SPY': dd_dates(bench['SPY'], YTD), 'UPRO': dd_dates(bench['UPRO'], YTD)}
    tiers_out = {}
    for e in ('HG', 'KMLM'):
        key = CURRENT[e]
        h = B[key]['holdings']
        groups = {}
        for d1 in YTD:
            d0 = DAYS[DAYS.index(d1) - 1]
            lw = sum(w for t, w in h[d0].items() if t in MAP)
            Lw = sum(w * abs(MAP[t][0]) for t, w in h[d0].items() if t in MAP)
            g = 'no leverage' if lw == 0 else ('3x' if Lw / lw > 2.5 else ('2x' if Lw / lw > 1.75 else '1.5x'))
            groups.setdefault(g, []).append(d1)
        res = {}
        for lab, path in (('levered', paths[(key, 'real')][0]), ('unlevered', paths[(key, 'real')][1])):
            ex = {d: path[d] - RF[d] for d in YTD}
            n = len(ex)
            mu = sum(ex.values()) / n
            var = sum((x - mu) ** 2 for x in ex.values()) / (n - 1)
            res[lab] = {g: {'days': len(ds), 'ann_excess_contrib': round(sum(ex[d] for d in ds) / n * 252, 4),
                            'variance_share': round(sum((ex[d] - mu) ** 2 for d in ds) / (n - 1) / var, 3)} for g, ds in groups.items()}
        tiers_out[e] = res
    out['tiers'] = tiers_out

    # dollar view: the recovered external flows (start-of-day) replayed through each path (same deposits)
    T = len(YTD)
    paths_d = {'actual': acct['real']['actual'], 'unlevered': acct['real']['unlevered'], 'SPY': bench['SPY'], 'QQQ': bench['QQQ'], 'UPRO': bench['UPRO']}
    dollars = {}
    for lab, rr in paths_d.items():
        v, fsum, wsum = A[YTD0], 0.0, 0.0
        for k_, d1 in enumerate(YTD):
            f = flows[d1]
            v = (v + f) * (1 + rr[d1])
            fsum += f
            wsum += f * (T - k_) / T
        pnl = v - A[YTD0] - fsum
        dollars[lab] = {'end_value': round(v, 2), 'gain': round(pnl, 2), 'modified_dietz': round(pnl / (A[YTD0] + wsum), 4)}
    dollars['recovered_net_flows'] = round(sum(flows.values()), 2)
    ts = json.load(open(f'{D}/total_stats.json'))
    dollars['recorded_2026_deposits'] = ts['net_deposits'] - live['HG']['deposit_adjusted_series'][0]
    dollars['leverage_dollars'] = round(dollars['actual']['gain'] - dollars['unlevered']['gain'], 2)
    since = [d for d in YTD if d >= '2026-04-07']
    out['since_money_arrived'] = {'window': [since[0], since[-1]], **{lab: metrics(rr, since) for lab, rr in paths_d.items()}}
    out['dollars'] = dollars

    # daily series for the chart
    out['series'] = {
        'dates': YTD,
        'acct_actual': [round(x, 6) for x in cum_path(acct['real']['actual'], YTD).values()],
        'acct_unlev': [round(x, 6) for x in cum_path(acct['real']['unlevered'], YTD).values()],
        'acct_unlev_self': [round(x, 6) for x in cum_path(acct['self']['unlevered'], YTD).values()],
        'acct_model_unlev': [round(x, 6) for x in cum_path(acct['real']['model_unlevered'], YTD).values()],
        'upro': [round(x, 6) for x in cum_path(bench['UPRO'], YTD).values()],
        'book_lev': [round(x, 6) for x in cum_path(bookv['real']['levered'], YTD).values()],
        'book_unlev': [round(x, 6) for x in cum_path(bookv['real']['unlevered'], YTD).values()],
        'spy': [round(x, 6) for x in cum_path(bench['SPY'], YTD).values()],
        'invested_share': [round(acct['real']['invested_share'][d], 4) for d in YTD],
        'eng': {e: {'L': [round(x, 6) for x in cum_path(bookv['real']['eng_L'][e], YTD).values()],
                    'U': [round(x, 6) for x in cum_path(bookv['real']['eng_U'][e], YTD).values()]} for e in CURRENT},
    }
    json.dump(out, open(f'{D}/lev_study.json', 'w'), indent=1)

    # ---- print
    print(f"window {YTD0} close -> {YTD1} close, {len(YTD)} sessions; account calendar gaps: {missing or 'none'}")
    print('our reproduction vs Composer equity (a check only; the levered rows ARE Composer):')
    for k, v in val.items():
        print(f"  {k:30s} corr {v['corr_vs_composer']:.5f}  YTD composer {v['ytd_composer']:+.2%}  reproduced {v['ytd_reproduced']:+.2%}")
    print('account live vs model at live weights:', out['account_model_check'])
    print('ORIG value used:', out['orig_value_used'])
    print('HG inference classes:', out['hg_inference_counts'], '| HG cost check:', out.get('hg_cost_check'))
    for method in ('real', 'self'):
        print(f"\n== method: {method} ==")
        for k, m in M[method].items():
            print(f"  {k:36s} YTD {m['ytd']:+8.2%}  vol {m['vol']:6.1%}  Sharpe {m['sharpe']:5.2f}  Sortino {m['sortino']:5.2f}  maxDD {m['maxdd']:6.1%}")
    print('\nbook cap-40 resets:', out['book_resets'])
    print('account leverage contribution by symphony (sum of daily, real):', out['account_contribution_by_symphony_sum_of_daily'])
    print('dollars (recovered flows through each path):', out['dollars'])
    print('since money arrived:', {k: (v if k == 'window' else f"{v['ytd']:+.1%}/Sh {v['sharpe']:.2f}/DD {v['maxdd']:.1%}") for k, v in out['since_money_arrived'].items()})
    print('drawdown dates:', out['dd_dates'])
    for e, res in out['tiers'].items():
        print(f'{e} by leverage tier:', res)
    for lab, v in out['account_by_period'].items():
        print(f"  {lab}: actual {v['actual']['ytd']:+.2%} (DD {v['actual']['maxdd']:.1%})  unlevered {v['unlevered']['ytd']:+.2%} (DD {v['unlevered']['maxdd']:.1%})")


if __name__ == '__main__':
    main()
