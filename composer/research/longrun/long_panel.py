"""Long price panel for all four live engines, 1993-2026, with every fund that did not yet exist rebuilt
from the deepest available proxy (owner request 2026-10-20: "$100k in 1997 in the current set-up").

Base: the add. 40/42 panel B (gate_study.build_lh_prices: HG's legs, SPY total return, BIL, the VIX ETPs,
1990+), then the other engines' legs as in hist_replay.build_prices (panel A), each spliced back further:
  bond ETFs     TLT/IEF/SHY/LQD/HYG <- Vanguard VUSTX/VFITX/VFISX/VFICX/VWEHX, excess return scaled by the
                beta fitted where both exist
  sector ETFs   XLK/XLF/XLP/XLY/VOX/KIE/PEJ <- Ken French daily CRSP industry portfolios (value-weighted);
                IVW/IVE (and VOOG/VOOV/VTV) <- French big-growth / big-value; QQQ/QQQE <- Nasdaq-100 + 0.5%/yr
  leveraged     SQQQ/PSQ before QQQ <- Nasdaq-100 x-3/-1; FAS before XLF <- French finance x3; TMF/TMV on the
                spliced TLT (lev_fits); UGL on gold (GLD <- GC=F <- XAU-index beta)
  KMLM signal   KMLM <- RYMFX (2007) <- MLM-style trend proxy: 12-month MA sign, month-end, inverse-vol,
                1/3 bonds (VUSTX, VFITX) / 1/3 dollar index / 1/3 S&P GSCI, plus T-bills (unfitted)
  VIX funds     real ETP <- vix_etp term-structure model on the real VIX3M/VIX6M (2006-07+) <- before that,
                by vix_mode: 'ts_synth' (main) the same model on a synthetic curve fitted from the VIX alone;
                'plain' (vix_etp's constant-carry regression, as panel B) and 'level' (carry linear in lnVIX)
                as the sensitivity range.  VIX futures did not trade before 2004: every pre-2006 VIX-fund
                return is a model of a market that did not exist.
Downloaded files are data only (CSV/JSON parsed, nothing executed).  fidelity() reports each splice's
overlap correlation and drift."""
import io
import json
import math
import os
import statistics
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'leverage'))
import levgate as lg   # noqa: E402

gs = lg.gs
from hist_replay import recon, vix_etp, fits   # noqa: E402

rets_of, curve_from, splice, cash = lg.rets_of, lg.curve_from, lg.splice, lg.cash
YH = f'{gs.SP}/yh'
RAW = '/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/long1997/raw'


def yh(t):
    with open(f"{YH}/{t.replace('^', '_').replace('=', '_')}.json") as f:
        o = json.load(f)
    return {d: v for d, v in zip(o['dates'], o['adjclose']) if v}


def french(zipname, col, table=0):
    """daily value-weighted returns (decimal) of one column from a Ken French CSV zip (first table)"""
    z = zipfile.ZipFile(os.path.join(RAW, zipname))
    lines = z.read(z.namelist()[0]).decode('latin-1').splitlines()
    out, hdr, t = {}, None, -1
    for ln in lines:
        cells = [c.strip() for c in ln.split(',')]
        if ln.startswith(',') and len(cells) > 2:
            t += 1
            hdr = cells if t == table else None
            continue
        if hdr and cells[0].isdigit() and len(cells[0]) == 8:
            v = float(cells[hdr.index(col)])
            if v > -99:
                out[f'{cells[0][:4]}-{cells[0][4:6]}-{cells[0][6:]}'] = v / 100
        elif hdr and out and not cells[0]:
            break
    return out


def avg_rets(*series):
    ds = sorted(set.intersection(*[set(s) for s in series]))
    return {d: sum(s[d] for s in series) / len(series) for d in ds}


def excess_beta(target, proxy):
    """OLS beta (and alpha, per day) of the target's excess return on the proxy's, where both exist"""
    rt, rp = rets_of(target), rets_of(proxy)
    ds = [d for d in sorted(rt) if d in rp]
    x = [rp[d] - cash.get(d, 0.0) for d in ds]
    y = [rt[d] - cash.get(d, 0.0) for d in ds]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    b = sum((u - mx) * (v - my) for u, v in zip(x, y)) / sum((u - mx) ** 2 for u in x)
    return b, my - b * mx


def scaled(target, proxy):
    """the proxy's path as the target would have run it: cash + beta x proxy excess + alpha"""
    b, a = excess_beta(target, proxy)
    return curve_from({d: cash.get(d, 0.0) + b * (r - cash.get(d, 0.0)) + a for d, r in rets_of(proxy).items()}), (b, a)


def lev_on(base, L, beta=1.0, alpha=0.0):
    """L x a base path's daily return, financed at the T-bill (recon's formula on any series)"""
    return curve_from({d: beta * (L * r - (L - 1) * cash.get(d, 0.0)) + alpha for d, r in rets_of(base).items()})


def lev_fit(name, base, L):
    f = fits.get(name, {})
    return lev_on(base, L, f.get('beta', 1.0), f.get('alpha_bps', 0.0) / 1e4)


def mf_proxy():
    """MLM-style trend proxy (see module doc); unfitted; daily returns incl. T-bills"""
    mk = {'VUSTX': yh('VUSTX'), 'VFITX': yh('VFITX'), 'DXY': yh('DX-Y.NYB'), 'GSCI': yh('^SPGSCI')}
    wt = {'VUSTX': 1 / 6, 'VFITX': 1 / 6, 'DXY': 1 / 3, 'GSCI': 1 / 3}
    R = {k: rets_of(v) for k, v in mk.items()}
    MA = {k: lg.ma_series(v, 252) for k, v in mk.items()}
    base = sorted(set(R['VUSTX']) & set(R['DXY']) & set(R['GSCI']))
    pos, prev, out = {}, None, {}
    for i in range(1, len(base)):
        d0, d1 = base[i - 1], base[i]
        if d0[:7] != prev:
            for k in mk:
                if d0 in MA[k]:
                    hist = [R[k][x] for x in base[max(0, i - 61):i] if x in R[k]]
                    v = statistics.pstdev(hist) * math.sqrt(252) if len(hist) > 20 else None
                    pos[k] = (1 if mk[k][d0] > MA[k][d0] else -1) / v if v else None
            prev = d0[:7]
        av = [k for k in mk if pos.get(k) is not None and d1 in R[k]]
        if av:
            out[d1] = sum(wt[k] * pos[k] * R[k][d1] for k in av) / sum(wt[k] for k in av) * 0.10 + cash.get(d1, 0.0)
    return curve_from(out)


VIX3M_START = '2006-07-18'          # first VIX3M return: vix_etp's term-structure model starts here


def _ols(y, X):
    n = len(X[0])
    A = [[sum(r[i] * r[j] for r in X) for j in range(n)] + [sum(r[i] * t for r, t in zip(X, y))] for i in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(A[r][i]))
        A[i], A[p] = A[p], A[i]
        for r in range(n):
            if r != i:
                f = A[r][i] / A[i][i]
                A[r] = [a - f * b for a, b in zip(A[r], A[i])]
    return [A[i][n] / A[i][i] for i in range(n)]


def synth_curves():
    """synthetic VIX3M and VIX6M from the VIX alone: ln(VIX3M/VIX) and ln(VIX6M/VIX3M) on (1, lnVIX - m, m),
    m = trailing 252-session mean of lnVIX (an adaptive long-run level); fitted 2007-07..2026 / 2008-01..2026
    (R2 0.69 / 0.82)"""
    vix, v3, v6 = yh('^VIX'), yh('^VIX3M'), yh('^VIX6M')
    vd = sorted(vix)
    lv = {d: math.log(vix[d]) for d in vd}
    m, q, s = {}, [], 0.0
    for d in vd:
        q.append(lv[d])
        s += lv[d]
        if len(q) > 252:
            s -= q.pop(0)
        m[d] = s / len(q)
    feat = lambda d: [1.0, lv[d] - m[d], m[d]]   # noqa: E731
    d3 = [d for d in vd if d in v3 and d >= '2007-07-17']
    c3 = _ols([math.log(v3[d] / vix[d]) for d in d3], [feat(d) for d in d3])
    d6 = [d for d in vd if d in v6 and d in v3 and d >= '2008-01-03']
    c6 = _ols([math.log(v6[d] / v3[d]) for d in d6], [feat(d) for d in d6])
    s3 = {d: vix[d] * math.exp(sum(c * x for c, x in zip(c3, feat(d)))) for d in vd}
    s6 = {d: s3[d] * math.exp(sum(c * x for c, x in zip(c6, feat(d)))) for d in vd}
    return vix, s3, s6, (c3, c6)


def vix_pre(name, mode, curves):
    """the ETP's daily path before VIX3M exists, by mode:
    ts_synth  vix_etp's term-structure betas on the synthetic VIX3M/VIX6M (main case)
    level     a + b*dVIX% + c*lnVIX(t-1), fitted on real VIXY (short) / VIXM (mid) 2011-26, x the ETP's leverage
    plain     vix_etp's own pre-2006 constant-carry regression (panel B as reviewed)"""
    Mx = json.load(open(f'{gs.SP}/vix_models.json'))[name]
    lev = Mx['eras'][0][2]          # the ETP's earliest-era leverage, as vix_etp uses before launch
    vix, s3, s6, _ = curves
    rv = rets_of(vix)
    if mode == 'plain':
        bp = Mx['beta_plain']
        return curve_from({d: lev * (bp[0] * r + bp[1]) for d, r in rv.items()})
    if mode == 'level':
        base = 'VIXY' if Mx['kind'] == 'short' else 'VIXM'
        rb = rets_of(yh(base))
        vd = sorted(vix)
        lvl = {vd[i]: math.log(vix[vd[i - 1]]) for i in range(1, len(vd))}
        ds = [d for d in sorted(rb) if '2011-01-04' <= d <= '2026-10-07' and d in rv]
        co = _ols([rb[d] for d in ds], [[1.0, rv[d], lvl[d]] for d in ds])
        return curve_from({d: lev * (co[0] + co[1] * rv[d] + co[2] * lvl[d]) for d in rv if d in lvl})
    b = Mx['beta']
    r3, r6 = rets_of(s3), rets_of(s6)
    ds = sorted(set(rv) & set(r3) & set(r6))
    out = {}
    for i in range(1, len(ds)):
        d, p = ds[i], ds[i - 1]
        if Mx['kind'] == 'short':
            x = [rv[d], r3[d], (s3[p] - vix[p]) / vix[p], 1.0]
        else:
            x = [r3[d], r6[d], (s6[p] - s3[p]) / s3[p], 1.0]
        out[d] = lev * sum(bb * xx for bb, xx in zip(b, x))
    return curve_from(out)


def vix_long(name, mode, curves):
    """real ETP <- vix_etp term-structure model on the real curve (from VIX3M_START) <- vix_pre(mode)"""
    syn, _ = vix_etp(name)
    ts = {d: v for d, v in syn.items() if d >= VIX3M_START}
    return splice(yh(name), splice(ts, vix_pre(name, mode, curves)))


def build_long_prices(vix_mode='ts_synth'):
    P = gs.build_lh_prices()            # HG legs, SPY (TR), BIL: panel B as reviewed (add. 40/42/44)
    meta = {'vix_mode': vix_mode}
    curves = synth_curves()
    meta['synth_curve_coefs'] = [[round(c, 4) for c in cc] for cc in curves[3]]
    for nm in ('VIXY', 'UVXY', 'VIXM'):  # panel B's own VIX legs, rebuilt with the chosen pre-2006 mode
        P[nm] = vix_long(nm, vix_mode, curves)
    ndx = yh('^NDX')
    ndx_tr = curve_from({d: r + 0.005 / 252 for d, r in rets_of(ndx).items()})
    ndx_dy = {k: 0.5 for k in json.load(open(f'{gs.MAC}/divyield_multpl.json'))}
    F12 = '12_Industry_Portfolios_daily_CSV.zip'
    F49 = '49_Industry_Portfolios_daily_CSV.zip'
    F6 = '6_Portfolios_2x3_daily_CSV.zip'
    fc = lambda z, c: curve_from(french(z, c))   # noqa: E731
    # cash-like
    P['PULS'] = P['BOXX'] = P['BIL']
    # equity bases
    P['QQQ'] = splice(yh('QQQ'), ndx_tr)
    P['XLK'] = splice(yh('XLK'), fc(F12, 'BusEq'))
    P['XLF'] = splice(yh('XLF'), fc(F12, 'Money'))
    P['XLP'] = splice(yh('XLP'), fc(F12, 'NoDur'))
    P['XLY'] = splice(yh('XLY'), curve_from(avg_rets(french(F12, 'Shops'), french(F12, 'Durbl'))))
    P['VOX'] = splice(yh('VOX'), fc(F12, 'Telcm'))
    P['KIE'] = splice(yh('KIE'), fc(F49, 'Insur'))
    P['PEJ'] = splice(yh('PEJ'), curve_from(avg_rets(french(F49, 'Meals'), french(F49, 'Fun'))))
    P['IVW'] = splice(yh('IVW'), fc(F6, 'BIG LoBM'))
    P['IVE'] = splice(yh('IVE'), fc(F6, 'BIG HiBM'))
    P['VOOG'] = splice(yh('VOOG'), P['IVW'])
    P['VOOV'] = splice(yh('VOOV'), P['IVE'])
    P['VTV'] = splice(yh('VTV'), P['IVE'])
    P['QQQE'] = splice(yh('QQQE'), P['QQQ'])
    # leveraged / inverse equity
    P['SPXL'] = splice(yh('SPXL'), splice(recon('SPXL', 'SPY', 3), lev_on(P['SPY'], 3, 1.0, -0.7e-4)))
    P['SQQQ'] = splice(yh('SQQQ'), splice(recon('SQQQ', 'QQQ', -3), gs.lev_from_index(ndx, -3, ndx_dy)))
    P['PSQ'] = splice(yh('PSQ'), splice(recon('PSQ', 'QQQ', -1), gs.lev_from_index(ndx, -1, ndx_dy)))
    P['FAS'] = splice(yh('FAS'), lev_fit('FAS', P['XLF'], 3))
    P['SOXS'] = splice(yh('SOXS'), splice(recon('SOXS', '^SOX', -3), gs.lev_from_index(ndx, -3, ndx_dy)))
    xbi = splice(yh('XBI'), yh('^NBI'))
    P['LABD'] = splice(yh('LABD'), curve_from({d: fits['LABD']['beta'] * (-3 * r + 4 * cash.get(d, 0)) + fits['LABD']['alpha_bps'] / 1e4
                                              for d, r in rets_of(xbi).items()}))
    # bonds
    for t, v in (('TLT', 'VUSTX'), ('IEF', 'VFITX'), ('SHY', 'VFISX'), ('LQD', 'VFICX'), ('HYG', 'VWEHX')):
        real = yh(t)
        syn, (b, a) = scaled(real, yh(v))
        P[t] = splice(real, syn)
        meta[t] = {'proxy': v, 'beta': round(b, 3), 'alpha_bp_day': round(a * 1e4, 3)}
    P['CORP'] = splice(yh('CORP'), P['LQD'])
    P['TMF'] = splice(yh('TMF'), lev_fit('TMF', P['TLT'], 3))
    P['TMV'] = splice(yh('TMV'), lev_fit('TMV', P['TLT'], -3))
    # gold (UGL held 0.0% of sessions 2015-26)
    gcf = yh('GC=F')
    xau, (bx, ax) = scaled(gcf, yh('^XAU'))
    meta['GLD'] = {'proxy': 'GC=F <- ^XAU', 'beta_xau': round(bx, 3)}
    P['GLD'] = splice(yh('GLD'), splice(gcf, xau))
    P['UGL'] = splice(yh('UGL'), lev_on(P['GLD'], 2, 1.0, -0.0004))
    # VIX complex (panel A constructions; pre-2006 by vix_mode)
    for nm in ('SVXY', 'VXZ'):
        P[nm] = vix_long(nm, vix_mode, curves)
    P['ZVOL'] = splice(yh('ZVOL'), curve_from({d: -0.971 * r for d, r in rets_of(P['VXZ']).items()}))
    sv = rets_of(P['SVXY'])
    P['SVIX'] = splice(yh('SVIX'), curve_from({d: (2 * r if d >= '2018-02-28' else r) * 0.953 - 0.00036 for d, r in sv.items()}))
    # managed futures signal
    P['RYMFX'] = yh('RYMFX')
    P['MFPROXY'] = mf_proxy()
    P['KMLM'] = splice(yh('KMLM'), splice(P['RYMFX'], P['MFPROXY']))
    return P, meta


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def overlap(real, synth):
    """corr of daily returns and log drift (synth - real, %/yr) where both exist"""
    rr, rs = rets_of(real), rets_of(synth)
    ds = [d for d in sorted(rr) if d in rs]
    if len(ds) < 100:
        return None
    drift = (sum(math.log1p(rs[d]) for d in ds) - sum(math.log1p(rr[d]) for d in ds)) / (len(ds) / 252)
    return {'from': ds[0], 'to': ds[-1], 'n': len(ds), 'corr': round(corr([rr[d] for d in ds], [rs[d] for d in ds]), 3), 'drift_pct_yr': round(drift * 100, 2)}


def rsi(px, n=10):
    ds = sorted(px)
    out, ag, al, q = {}, None, None, []
    for i in range(1, len(ds)):
        x = px[ds[i]] - px[ds[i - 1]]
        q.append(x)
        if len(q) == n:
            ag, al = sum(max(v, 0) for v in q) / n, sum(max(-v, 0) for v in q) / n
        elif len(q) > n:
            ag, al = (ag * (n - 1) + max(x, 0)) / n, (al * (n - 1) + max(-x, 0)) / n
        if ag is not None:
            out[ds[i]] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def fidelity(P, meta):
    F12, F49, F6 = '12_Industry_Portfolios_daily_CSV.zip', '49_Industry_Portfolios_daily_CSV.zip', '6_Portfolios_2x3_daily_CSV.zip'
    ndx_tr = curve_from({d: r + 0.005 / 252 for d, r in rets_of(yh('^NDX')).items()})
    chk = {
        'QQQ <- Nasdaq-100 +0.5%': (yh('QQQ'), ndx_tr),
        'XLK <- French BusEq': (yh('XLK'), curve_from(french(F12, 'BusEq'))),
        'XLF <- French Money': (yh('XLF'), curve_from(french(F12, 'Money'))),
        'XLP <- French NoDur': (yh('XLP'), curve_from(french(F12, 'NoDur'))),
        'XLY <- French Shops+Durbl': (yh('XLY'), curve_from(avg_rets(french(F12, 'Shops'), french(F12, 'Durbl')))),
        'VOX <- French Telcm': (yh('VOX'), curve_from(french(F12, 'Telcm'))),
        'KIE <- French Insur': (yh('KIE'), curve_from(french(F49, 'Insur'))),
        'PEJ <- French Meals+Fun': (yh('PEJ'), curve_from(avg_rets(french(F49, 'Meals'), french(F49, 'Fun')))),
        'IVW <- French big growth': (yh('IVW'), curve_from(french(F6, 'BIG LoBM'))),
        'IVE <- French big value': (yh('IVE'), curve_from(french(F6, 'BIG HiBM'))),
        'GLD <- GC=F': (yh('GLD'), yh('GC=F')),
        'KMLM-ref (KMLM<-RYMFX) <- MF proxy': (splice(yh('KMLM'), yh('RYMFX')), P['MFPROXY']),
        'KMLM <- RYMFX': (yh('KMLM'), yh('RYMFX')),
    }
    for t in ('TLT', 'IEF', 'SHY', 'LQD', 'HYG'):
        chk[f"{t} <- {meta[t]['proxy']} x{meta[t]['beta']}"] = (yh(t), scaled(yh(t), yh(meta[t]['proxy']))[0])
    out = {k: overlap(a, b) for k, (a, b) in chk.items()}
    # the KMLM switcher's decision: RSI10(XLK) > RSI10(KMLM series)
    ref = splice(yh('KMLM'), yh('RYMFX'))
    rx, rr, rp = rsi(yh('XLK')), rsi(ref), rsi(P['MFPROXY'])
    for lab, a, b in (('2007-16', '2007-03-01', '2016-12-30'), ('2017-26', '2017-01-03', '2026-10-07')):
        ds = [d for d in sorted(rr) if a <= d <= b and d in rx and d in rp]
        out[f'KMLM flag agreement, proxy vs real, {lab}'] = round(sum(1 for d in ds if (rx[d] > rr[d]) == (rx[d] > rp[d])) / len(ds), 3)
        out[f'KMLM flag agreement, constant 50 vs real, {lab}'] = round(sum(1 for d in ds if (rx[d] > rr[d]) == (rx[d] > 50)) / len(ds), 3)
    return out


if __name__ == '__main__':
    P, meta = build_long_prices()
    print('splice parameters:', json.dumps(meta, default=str)[:1500])
    for k, v in fidelity(P, meta).items():
        print(f'  {k:45s} {v}')
    need = sorted({t for e in ('KMLM', 'SLEEVE', 'HARV') for t in lg.tree_tickers(gs.trees[e])} | lg.tree_tickers(gs.trees['HG']))
    print('first date per needed ticker:', {t: (min(P[t]) if t in P else 'MISSING') for t in need})
