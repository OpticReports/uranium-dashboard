#!/usr/bin/env python3 -I
"""For each row of data/crises.csv compute DXY and gold behaviour. Output data/crises_metrics.csv.
DXY basis: ICE DXY monthly (Yahoo DX-Y.NYB daily -> monthly close/high/low). Gold basis: World Bank Pink Sheet monthly AVERAGE
($/toz, LBMA PM-based) for all years; COMEX GC=F daily lows (Yahoo) added from 2000-09 for intra-month troughs.
Run from finderA/: python3 -I scripts/crisis_metrics.py"""
import csv, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'data')
dm = {r['month']: r for r in csv.DictReader(open(os.path.join(D, 'dollar_monthly.csv')))}
gm = {r['month']: r for r in csv.DictReader(open(os.path.join(D, 'gold_monthly.csv')))}
months = sorted(dm)
idx = {m: i for i, m in enumerate(months)}
def shift(m, k):
    i = idx[m] + k
    return months[i] if 0 <= i < len(months) else None
def f(x):
    try: return float(x)
    except: return None
def dxy_close(m): return f(dm[m]['dxy_close']) if m in dm else None
def gold(m):
    r = gm.get(m); return f(r['gold_best']) if r else None
def pct(a, b): return None if (a is None or b is None or b == 0) else 100 * (a / b - 1)
def fmt(x, d=1): return '' if x is None else f"{x:.{d}f}"
last_month = max(m for m in months if dm[m]['dxy_close'])
spx = [(r['date'], float(r['close'])) for r in csv.DictReader(open(os.path.join(D, 'spx_daily.csv')))]
def spx_maxdd(m0, m1):
    hi = None; best = (0.0, '', '')
    for d, c in spx:
        if d[:7] < m0 or d[:7] > m1: continue
        if hi is None or c > hi[1]: hi = (d, c)
        dd = 100 * (c / hi[1] - 1)
        if dd < best[0]: best = (dd, hi[0], d)
    return best
rows = []
for c in csv.DictReader(open(os.path.join(D, 'crises.csv'))):
    s, p, e = c['start'], c['peak_stress'], c['end'] or last_month
    pre = shift(s, -1)  # level on the eve of the episode: close of the month before start
    lvl0 = dxy_close(pre)
    chg6 = pct(lvl0, dxy_close(shift(pre, -6))); chg12 = pct(lvl0, dxy_close(shift(pre, -12)))
    span = [m for m in months if s <= m <= e]
    # DXY peak inside the episode (monthly close and intra-month high)
    pk_m = max(span, key=lambda m: f(dm[m]['dxy_close']) or -1)
    pk_hi_m = max(span, key=lambda m: f(dm[m]['dxy_high']) or -1)
    tr_m = min(span, key=lambda m: f(dm[m]['dxy_close']) or 1e9)
    dxy_peak = dxy_close(pk_m); dxy_hi = f(dm[pk_hi_m]['dxy_high'])
    at_peakstress = dxy_close(p)
    peak_before_end = 'yes' if pk_m < e else ('no (peak at end month)' if pk_m == e else '')
    # gold
    g0 = gold(pre); g_series = [(m, gold(m)) for m in span if gold(m) is not None]
    g_tr_m, g_tr = (min(g_series, key=lambda t: t[1]) if g_series else (None, None))
    g_end = gold(e); g_pk = gold(p)
    # gold using daily GC=F lows where available
    gl = [(m, f(gm[m]['gcf_low']), gm[m]['gcf_low_date']) for m in span if f(gm[m]['gcf_low'])]
    gcf_pre = f(gm[pre]['gcf_close']) if pre in gm else None
    gcf_tr = min(gl, key=lambda t: t[1]) if gl else None
    # gold in the 3 months after the DXY peak month
    g_after3 = pct(gold(shift(pk_m, 3)), gold(pk_m))
    # gold max drawdown INSIDE the episode window (peak-to-trough), monthly-average basis and daily GC=F basis (close->low)
    def maxdd(seq):
        best = (0.0, None, None); hi = None
        for m, v in seq:
            if v is None: continue
            if hi is None or v > hi[1]: hi = (m, v)
            dd = 100 * (v / hi[1] - 1)
            if dd < best[0]: best = (dd, hi[0], m)
        return best
    # include the eve month so a drawdown starting at the eve is captured
    g_dd = maxdd([(pre, g0)] + g_series)
    gd = [(m, f(gm[m]['gcf_close'])) for m in [pre] + span if m in gm and f(gm[m]['gcf_close'])]
    # daily-basis: track running max of monthly closes/highs vs monthly lows
    best = (0.0, None, None); hi = None
    for m in [pre] + span:
        r = gm.get(m)
        if not r or not f(r['gcf_high']): continue
        if hi is None or f(r['gcf_high']) > hi[1]: hi = (m, f(r['gcf_high']))
        dd = 100 * (f(r['gcf_low']) / hi[1] - 1)
        if dd < best[0]: best = (dd, hi[0], r['gcf_low_date'])
    g_dd_daily = best
    sdd = spx_maxdd(pre, e)
    rows.append({
        'spx_maxdd_pct': fmt(sdd[0]), 'spx_dd_peak_date': sdd[1], 'spx_dd_trough_date': sdd[2],
        'id': c['id'], 'name': c['name'], 'start': s, 'peak_stress': p, 'end': c['end'] or f'(open; to {last_month})', 'is_crisis': c['is_crisis'], 'type': c['type'],
        'dxy_eve_close': fmt(lvl0, 2), 'dxy_chg_prior_6m_pct': fmt(chg6), 'dxy_chg_prior_12m_pct': fmt(chg12),
        'dxy_at_peak_stress_close': fmt(at_peakstress, 2), 'dxy_chg_eve_to_peak_stress_pct': fmt(pct(at_peakstress, lvl0)),
        'dxy_episode_peak_close': fmt(dxy_peak, 2), 'dxy_episode_peak_month': pk_m, 'dxy_episode_intraday_high': fmt(dxy_hi, 2), 'dxy_intraday_high_date': dm[pk_hi_m]['dxy_high_date'],
        'dxy_chg_eve_to_peak_pct': fmt(pct(dxy_peak, lvl0)), 'dxy_episode_trough_close': fmt(dxy_close(tr_m), 2), 'dxy_episode_trough_month': tr_m,
        'dxy_chg_eve_to_end_pct': fmt(pct(dxy_close(e), lvl0)), 'dxy_peak_before_end': peak_before_end,
        'gold_eve_avg': fmt(g0, 0), 'gold_trough_avg': fmt(g_tr, 0), 'gold_trough_month': g_tr_m or '', 'gold_eve_to_trough_pct': fmt(pct(g_tr, g0)),
        'gold_eve_to_peakstress_pct': fmt(pct(g_pk, g0)), 'gold_eve_to_end_pct': fmt(pct(g_end, g0)),
        'gold_gcf_daily_low': fmt(gcf_tr[1], 0) if gcf_tr else '', 'gold_gcf_daily_low_date': gcf_tr[2] if gcf_tr else '', 'gold_gcf_eve_to_daily_low_pct': fmt(pct(gcf_tr[1], gcf_pre)) if (gcf_tr and gcf_pre) else '',
        'gold_3m_after_dxy_peak_pct': fmt(g_after3),
        'gold_maxdd_in_episode_monthly_pct': fmt(g_dd[0]), 'gold_maxdd_peak_month': g_dd[1] or '', 'gold_maxdd_trough_month': g_dd[2] or '',
        'gold_maxdd_in_episode_daily_pct': fmt(g_dd_daily[0]) if g_dd_daily[1] else '', 'gold_maxdd_daily_peak_month': g_dd_daily[1] or '', 'gold_maxdd_daily_trough_date': g_dd_daily[2] or '',
    })
# move spx cols to the end for readability
rows = [{**{k: v for k, v in r.items() if not k.startswith('spx')}, **{k: v for k, v in r.items() if k.startswith('spx')}} for r in rows]
# rank correlation: DXY eve->peak-stress % vs S&P max drawdown (is-crisis rows only)
def rank(xs):
    o = sorted(range(len(xs)), key=lambda i: xs[i]); r = [0] * len(xs)
    for k, i in enumerate(o): r[i] = k
    return r
sel = [r for r in rows if r['is_crisis'] == '1' and r['dxy_chg_eve_to_peak_stress_pct'] and r['spx_maxdd_pct']]
xs = [float(r['dxy_chg_eve_to_peak_stress_pct']) for r in sel]; ys = [-float(r['spx_maxdd_pct']) for r in sel]
rx, ry = rank(xs), rank(ys); n = len(xs)
rho = 1 - 6 * sum((a - b) ** 2 for a, b in zip(rx, ry)) / (n * (n * n - 1))
xs2 = [float(r['dxy_chg_eve_to_peak_pct']) for r in sel]; rx2 = rank(xs2)
rho2 = 1 - 6 * sum((a - b) ** 2 for a, b in zip(rx2, ry)) / (n * (n * n - 1))
print(f"Spearman rho(DXY eve->peak-stress %, S&P max drawdown depth) = {rho:+.2f}  (n={n});  rho(DXY eve->episode-peak %, S&P DD) = {rho2:+.2f}")
with open(os.path.join(D, 'crises_metrics.csv'), 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
# console summary
print(f"{'id':4} {'start':7} {'peak':7} {'end':7} {'eve':>7} {'6m%':>6} {'12m%':>6} {'->pkS%':>7} {'pk':>7} {'pkMo':7} {'->pk%':>6} {'->end%':>7} {'pk<end':7} | {'g0':>5} {'gTr%':>6} {'gTrMo':7} {'gEnd%':>6} {'gcfLow%':>8} {'g+3mPk%':>8}")
for r in rows:
    print(f"{r['id']:4} {r['start']:7} {r['peak_stress']:7} {r['end'][:7]:7} {r['dxy_eve_close']:>7} {r['dxy_chg_prior_6m_pct']:>6} {r['dxy_chg_prior_12m_pct']:>6} {r['dxy_chg_eve_to_peak_stress_pct']:>7} {r['dxy_episode_peak_close']:>7} {r['dxy_episode_peak_month']:7} {r['dxy_chg_eve_to_peak_pct']:>6} {r['dxy_chg_eve_to_end_pct']:>7} {r['dxy_peak_before_end'][:7]:7} | {r['gold_eve_avg']:>5} {r['gold_eve_to_trough_pct']:>6} {r['gold_trough_month']:7} {r['gold_eve_to_end_pct']:>6} {r['gold_gcf_eve_to_daily_low_pct']:>8} {r['gold_3m_after_dxy_peak_pct']:>8} | DDm {r['gold_maxdd_in_episode_monthly_pct']:>6} {r['gold_maxdd_peak_month']}->{r['gold_maxdd_trough_month']} DDd {r['gold_maxdd_in_episode_daily_pct']:>6} {r['gold_maxdd_daily_peak_month']}->{r['gold_maxdd_daily_trough_date']} | SPX {r['spx_maxdd_pct']:>6}")
