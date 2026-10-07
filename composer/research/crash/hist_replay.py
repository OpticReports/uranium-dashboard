"""Daily in-kind-as-possible replays of HG (2000-02 dotcom, 2007-09 GFC) and the
SLEEVE (GFC) using validated leveraged-ETF reconstructions on their real base
indices.  VIX-ETP legs use a crude VIX-index regression (flagged).  KMLM/HARV
are NOT replayed here (their vol legs are unmeasurable pre-2009; bootstrap
lens only).
"""
import os, json, math, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from replay import *
subprocess.run([sys.executable, f'{SP}/yh_fetch.py', 'RYMFX', 'IVW', 'IVE'], check=False)
trees = json.load(open(f'{SP}/trees.json')); fits = json.load(open(f'{SP}/lev_fits.json'))
irx = json.load(open(f'{SP}/yh/_IRX.json')); cash = {d: (c/100)/252 for d, c in zip(irx['dates'], irx['close']) if c is not None}
def ols(y, x):
    n = len(x); mx = sum(x)/n; my = sum(y)/n
    b = sum((xi-mx)*(yi-my) for xi, yi in zip(x, y))/sum((xi-mx)**2 for xi in x); return my-b*mx, b

def recon(lev, base, L, beta=None, alpha=None, start=None):
    """synthetic leveraged series: r = beta*(L*r_base - (L-1)*cash) + alpha"""
    f = fits.get(lev, {}); beta = f.get('beta', 1.0) if beta is None else beta
    alpha = f.get('alpha_bps', 0)/1e4 if alpha is None else alpha
    rb = rets_of(yh(base)); out = {}
    for d, r in rb.items():
        if start and d < start: continue
        out[d] = beta*(L*r - (L-1)*cash.get(d, 0.0)) + alpha
    return curve_from(out)

def splice(real, synth):
    """real series where it exists, synthetic (rescaled) before its first date."""
    rd = sorted(real); first = rd[0]; sd = sorted(synth)
    out = {d: synth[d] for d in sd if d < first}
    if out:
        last = max(out); k = real[first]/synth[first] if first in synth else real[first]/synth[last]
        out = {d: v*k for d, v in out.items()}
    out.update(real); return out

def vix_etp(name, src='^VIX'):
    """Term-structure VIX-ETP model (vix_models.json): r/lev = b1*dVIX + b2*dVIX3M + g*slope + a
    (mid-term: dVIX3M, dVIX6M, 3M-6M slope); OOS 2019-26 corr .96-.97 short / .89-.90 mid;
    COVID spike captured ~77% (plain dVIX regression: 41%).  Before VIX3M exists (2006-07)
    the plain dVIX regression is spliced underneath (pre-2006 = cruder, flagged)."""
    M = json.load(open(f'{SP}/vix_models.json'))[name]
    vix = yh('^VIX'); v3 = yh('^VIX3M'); v6 = yh('^VIX6M') if M['kind'] == 'mid' else {}
    rv = rets_of(vix); rv3 = rets_of(v3); rv6 = rets_of(v6) if v6 else {}
    lev_of = lambda d: next((L for a_, b_, L in M['eras'] if a_ <= d <= b_), M['eras'][0][2] if d < M['eras'][0][0] else M['eras'][-1][2])
    bp = M['beta_plain']; plain = curve_from({d: lev_of(d)*(bp[0]*r + bp[1]) for d, r in rv.items()})
    ds = sorted(set(rv) & set(rv3)); prev = {ds[i]: ds[i-1] for i in range(1, len(ds))}
    b = M['beta']; out = {}
    for d in ds[1:]:
        p = prev[d]
        if M['kind'] == 'short':
            x = [rv[d], rv3[d], (v3[p]-vix[p])/vix[p], 1.0]
        else:
            s6 = (v6[p]-v3[p])/v3[p] if (p in v6 and p in v3) else (v3[p]-vix[p])/vix[p]
            x = [rv3[d], rv6.get(d, rv3[d]), s6, 1.0]
        out[d] = lev_of(d)*sum(bb*xx for bb, xx in zip(b, x))
    return splice(curve_from(out), plain), tuple(b)

def bil_from_irx():
    return curve_from({d: c for d, c in cash.items()})

def build_prices():
    P = {}
    P['QQQ'] = yh('QQQ'); P['SPY'] = yh('SPY'); P['DIA'] = yh('DIA'); P['XLK'] = yh('XLK'); P['XLF'] = yh('XLF')
    P['IWM'] = splice(yh('IWM'), yh('^RUT')); P['XBI'] = splice(yh('XBI'), yh('^NBI'))
    P['SOXI'] = yh('^SOX')
    P['TQQQ'] = splice(yh('TQQQ'), recon('TQQQ', 'QQQ', 3)); P['QLD'] = splice(yh('QLD'), recon('QLD', 'QQQ', 2))
    P['UPRO'] = splice(yh('UPRO'), recon('UPRO', 'SPY', 3)); P['SSO'] = splice(yh('SSO'), recon('SSO', 'SPY', 2))
    P['UDOW'] = splice(yh('UDOW'), recon('UDOW', 'DIA', 3))
    P['TNA'] = splice(yh('TNA'), curve_from({d: fits['TNA']['beta']*(3*r-2*cash.get(d, 0))+fits['TNA']['alpha_bps']/1e4 for d, r in rets_of(P['IWM']).items()}))
    P['TECL'] = splice(yh('TECL'), recon('TECL', 'XLK', 3))
    P['SOXL'] = splice(yh('SOXL'), recon('SOXL', '^SOX', 3)); P['SOXS'] = splice(yh('SOXS'), recon('SOXS', '^SOX', -3))
    P['USD'] = splice(yh('USD'), recon('USD', '^SOX', 2)); P['SMH'] = splice(yh('SMH'), yh('^SOX'))
    P['LABU'] = splice(yh('LABU'), curve_from({d: fits['LABU']['beta']*(3*r-2*cash.get(d, 0))+fits['LABU']['alpha_bps']/1e4 for d, r in rets_of(P['XBI']).items()}))
    P['LABD'] = splice(yh('LABD'), curve_from({d: fits['LABD']['beta']*(-3*r+4*cash.get(d, 0))+fits['LABD']['alpha_bps']/1e4 for d, r in rets_of(P['XBI']).items()}))
    P['SPXL'] = splice(yh('SPXL'), recon('SPXL', 'SPY', 3)); P['FAS'] = splice(yh('FAS'), recon('FAS', 'XLF', 3))
    P['SQQQ'] = splice(yh('SQQQ'), recon('SQQQ', 'QQQ', -3)); P['PSQ'] = splice(yh('PSQ'), recon('PSQ', 'QQQ', -1))
    P['TLT'] = yh('TLT'); P['TMF'] = splice(yh('TMF'), recon('TMF', 'TLT', 3)); P['TMV'] = splice(yh('TMV'), recon('TMV', 'TLT', -3))
    P['UGL'] = splice(yh('UGL'), recon('UGL', 'GLD', 2, beta=1.0, alpha=-0.0004))
    P['BIL'] = splice(yh('BIL'), bil_from_irx()); P['BOXX'] = P['BIL']
    for t in ('HYG', 'LQD', 'IEF', 'SHY', 'KIE', 'PEJ', 'SVXY', 'UVXY', 'VIXY', 'VIXM'): P[t] = yh(t)
    P['CORP'] = splice(yh('CORP'), yh('LQD'))
    models = {}
    for nm in ('VIXY', 'UVXY', 'VIXM', 'SVXY'):
        syn, fit = vix_etp(nm); models[nm] = fit; P[nm] = splice(yh(nm), syn)
    P['KMLM'] = splice(yh('KMLM'), yh('RYMFX'))
    # mechanism-exhibit legs (artifact-grade pre-2018): VXZ from VIX3M model, ZVOL = -0.971 VXZ, SVIX from SVXY model (-1x era)
    syn, fit = vix_etp('VXZ'); models['VXZ'] = fit; P['VXZ'] = splice(yh('VXZ'), syn)
    P['ZVOL'] = splice(yh('ZVOL'), curve_from({d: -0.971*r for d, r in rets_of(P['VXZ']).items()}))
    svix_syn = curve_from({d: 2*r*0.953-0.00036 for d, r in rets_of(P['SVXY']).items() if d >= '2018-02-28'} | {d: r*0.953-0.00036 for d, r in rets_of(P['SVXY']).items() if d < '2018-02-28'})
    P['SVIX'] = splice(yh('SVIX'), svix_syn)
    P['PULS'] = splice(yh('PULS'), P['BIL']); P['QQQE'] = splice(yh('QQQE'), yh('QQQ'))
    P['VOOG'] = splice(yh('VOOG'), yh('IVW')); P['VOOV'] = splice(yh('VOOV'), yh('IVE'))
    for t in ('VTV', 'VOX', 'XLP', 'XLY'): P[t] = yh(t)
    return P, models

if __name__ == '__main__':
    P, models = build_prices(); print('VIX ETP models (beta, alpha bps/d):', models)
    cost = json.load(open(f'{SP}/cost_fit.json')) if __import__('os').path.exists(f'{SP}/cost_fit.json') else {}
    sim = SimW(P, rsi_method='wilder')
    out = {'vix_models': models, 'runs': {}}
    runs = [('HG', 'dotcom', '1999-06-01', '2003-12-31'), ('HG', 'gfc', '2007-01-03', '2010-12-31'), ('SLEEVE', 'gfc', '2007-06-01', '2010-12-31'),
            ('HG', 'covid_recon', '2019-09-03', '2021-03-31'),
            ('HARV', 'gfc_exhibit', '2007-06-01', '2010-12-31'), ('KMLM', 'gfc_exhibit', '2007-06-01', '2010-12-31'),
            ('SLEEVE', 'covid_recon', '2019-09-03', '2021-03-31')]
    for eng, tag, a, b in runs:
        tk = tree_tickers(trees[eng]); missing = [t for t in tk if t not in P]
        days = common_days(P, tk, a, b)
        if len(days) < 50:
            print(eng, tag, 'SKIPPED: only', len(days), 'common days; first dates:', {t: sorted(P[t])[0] for t in tk if t in P}); continue
        r, h = run_tree(sim, trees[eng], days)
        rc = composer_equiv(r, h, days, eng)
        out['runs'][f'{eng}_{tag}'] = {'days': days, 'rets': rc, 'rets_frictionless': r, 'hold': h, 'missing': missing}
        ds = sorted(rc); cum = math.prod(1+rc[d] for d in ds)
        seg = lambda x, y: math.prod(1+rc[d] for d in ds if x <= d <= y)-1
        peak = 1; v = 1; mdd = 0
        for d in ds: v *= 1+rc[d]; peak = max(peak, v); mdd = max(mdd, 1-v/peak)
        print(f"{eng} {tag} {days[0]}..{days[-1]} n={len(days)} cum {cum:.2f}x maxDD {mdd:.1%} missing {missing}")
        if tag == 'dotcom': print(f"   2000-03-10..2000-12-29 {seg('2000-03-11','2000-12-29'):+.1%} | 2001 {seg('2001-01-01','2001-12-31'):+.1%} | 2002 {seg('2002-01-01','2002-12-31'):+.1%} | 12m from 2000-03-10 {seg('2000-03-11','2001-03-09'):+.1%}")
        if tag == 'gfc': print(f"   2007-10-09..2009-03-09 {seg('2007-10-10','2009-03-09'):+.1%} | 2008 {seg('2008-01-01','2008-12-31'):+.1%} | 12m from Lehman {seg('2008-09-15','2009-09-14'):+.1%} | 12m from peak {seg('2007-10-10','2008-10-09'):+.1%}")
    json.dump(out, open(f'{SP}/hist_replay.json', 'w')); print('saved')
