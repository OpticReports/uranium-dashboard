"""Deterministic runs, per-event tests, placebos, mirrored check, sensitivities (PREREG sec 2,4)."""
import sys, json, numpy as np, pandas as pd
from scipy import stats
from engine import run, event_paths, KS
from common import *
D = sys.argv[1]
H = 11; NPERM = 100_000

def holm(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p); adj = np.empty(n); m = 0
    for r, i in enumerate(o):
        m = max(m, min(1, (n - r) * p[i])); adj[i] = m
    return adj

def signflip(d, n=NPERM):
    rng = np.random.default_rng(SEED); obs = d.mean(); ge = 0; ge2 = 0; done = 0
    while done < n:
        b = min(10_000, n - done); s = rng.choice([-1.0, 1.0], size=(b, len(d)))
        pm = (s * d).mean(1); ge += (pm >= obs - 1e-15).sum(); ge2 += (np.abs(pm) >= abs(obs) - 1e-15).sum(); done += b
    return (1 + ge) / (1 + n), (1 + ge2) / (1 + n)

def metrics(out, rf, nd):
    V = out['Vpath']; r = V[:, 1:] / V[:, :-1] - 1; ex = r - rf.values[None, 1:]
    yrs = (nd - 1) / 252
    dd = (V / np.maximum.accumulate(V, 1) - 1).min(1)
    return dict(cagr=cagr(out['logV'][0], nd), sharpe=ex.mean(1) / r.std(1) * np.sqrt(252), maxdd=dd,
                turnover_pa=out['traded'][0] / yrs, costdrag_bps_pa=out['costs'][0] / yrs * 1e4, fills=out['nfill'][0])

def one_cell(R, rf, w, c, fam, cancel=False, events=True):
    nd = len(R); ME = me_flags(R.index)
    out = run(R.values, ME, w, c, fam, cancel=cancel, record=True)
    m = metrics(out, rf, nd)
    res = {k: (v.tolist() if hasattr(v, 'tolist') else v) for k, v in m.items()}
    res['cagr_diff_bps'] = ((m['cagr'] - m['cagr'][1]) * 1e4).tolist()
    res['n_days'] = nd; res['start'] = str(R.index[0].date()); res['end'] = str(R.index[-1].date())
    if not events: return res, out, None
    ev = out['trig'][1]
    ts = np.array([t for t, _ in ev if t + H <= nd - 1], int)
    devs = np.array([dv for t, dv in ev if t + H <= nd - 1])
    Hk1 = out['Hk1']
    lv = event_paths(R.values, Hk1, ts, w, c) if len(ts) else np.zeros((0, 11))
    d = lv - lv[:, [1]]
    # direction: breaching sleeve (largest |dev| among breaching; T-M: largest |dev| overall)
    if len(ts):
        dv = np.where(np.abs(devs) > 0.2, np.abs(devs), 0) if fam != 'M' else np.abs(devs)
        j = dv.argmax(1); direction = np.sign(devs[np.arange(len(ts)), j])
    else: direction = np.zeros(0); j = np.zeros(0, int)
    E = dict(n=int(len(ts)), dates=[str(R.index[t].date()) for t in ts], direction=direction.tolist(), sleeve=j.tolist(),
             d=d.tolist())
    per_k = {}
    for k in KS:
        if k == 1 or len(ts) < 2: continue
        x = d[:, k]
        p1, p2 = signflip(x)
        tt = stats.ttest_1samp(x, 0)
        try: wil = stats.wilcoxon(x, alternative='greater').pvalue
        except ValueError: wil = float('nan')
        side = {}
        for nm, sg in [('up', 1), ('down', -1)]:
            y = x[direction == sg]
            if len(y) >= 2:
                se = y.std(ddof=1) / np.sqrt(len(y)); q = stats.t.ppf(.975, len(y) - 1)
                side[nm] = dict(n=int(len(y)), mean_bps=y.mean() * 1e4, ci95_bps=[(y.mean() - q * se) * 1e4, (y.mean() + q * se) * 1e4],
                                p_signflip_1s=signflip(y)[0])
            else: side[nm] = dict(n=int(len(y)), mean_bps=(y.mean() * 1e4 if len(y) else None))
        per_k[int(k)] = dict(mean_bps=x.mean() * 1e4, median_bps=float(np.median(x) * 1e4), t=tt.statistic, p_t_2s=tt.pvalue,
                             p_wilcoxon_1s=wil, p_signflip_1s=p1, p_signflip_2s=p2, hit_rate=float((x > 0).mean()), mirrored=side)
    if per_k:
        pk = [per_k[k]['p_signflip_1s'] for k in (3, 4, 5)]
        for k, a in zip((3, 4, 5), holm(pk)): per_k[k]['holm_primary'] = a
        ks2 = [k for k in KS if k != 1]
        for k, a in zip(ks2, holm([per_k[k]['p_signflip_1s'] for k in ks2])): per_k[k]['holm_secondary'] = a
    # placebos
    plac = {}
    if len(ts) >= 2:
        allt = np.array([t for t, _ in ev]); cand = np.arange(1, nd - H)
        dist = np.min(np.abs(cand[:, None] - allt[None, :]), 1)
        mind = 11; pool = cand[dist >= mind]
        if len(pool) < len(ts):
            mind = 6; pool = cand[dist >= mind]
        lvp = event_paths(R.values, Hk1, pool, w, c); dp = lvp - lvp[:, [1]]
        rng = np.random.default_rng(SEED); rep = len(pool) < len(ts)
        draws = np.array([rng.choice(len(pool), len(ts), replace=rep) for _ in range(1000)])
        rng2 = np.random.default_rng(SEED + 1)
        kd = rng2.integers(1, 11, size=(1000, len(ts)))
        p2m = d[np.arange(len(ts))[None, :], kd].mean(1)
        for k in (3, 4, 5):
            p1m = dp[draws, k].mean(1); real = d[:, k].mean()
            plac[k] = dict(real_bps=real * 1e4, p1_95_bps=np.percentile(p1m, 95) * 1e4, p1_mean_bps=p1m.mean() * 1e4,
                           p1_pctile_of_real=float((p1m < real).mean()), p1_pool=int(len(pool)), p1_min_dist=mind,
                           p2_95_bps=np.percentile(p2m, 95) * 1e4, p2_mean_bps=p2m.mean() * 1e4, p2_pctile_of_real=float((p2m < real).mean()),
                           beats_p1=bool(real > np.percentile(p1m, 95)), beats_p2=bool(real > np.percentile(p2m, 95)))
            if k == 4: E['placebo1_k4_bps'] = (p1m * 1e4).tolist(); E['placebo2_bps'] = (p2m * 1e4).tolist()
    return res, out, dict(events=E, per_k=per_k, placebo=plac)

def main():
    results = dict(meta=dict(seed=SEED, nperm=NPERM, horizon_days=H, cost_primary_bps=5), cells={}, sens={}, equity={})
    # gate: event_paths consistency vs naive single-event loop
    R, rf = load(D, 'A'); w = np.array(UNIV['A']['w']); c = np.full(len(w), 5e-4)
    Hh = np.abs(np.random.default_rng(1).normal(1, .3, size=(len(R), len(w))))
    lv = event_paths(R.values, Hh, [100, 2000], w, c)
    for ii, t in enumerate([100, 2000]):
        for k in range(11):
            h = Hh[t] / Hh[t].sum()
            if k == 0: V = h.sum(); h = w * (V - (np.abs(w * V - h) * c).sum())
            for j in range(1, 12):
                h = h * (1 + R.values[t + j])
                if j == k: V = h.sum(); h = w * (V - (np.abs(w * V - h) * c).sum())
            assert abs(np.log(h.sum()) - lv[ii, k]) < 1e-12, (t, k)
    print('event_paths gate OK', flush=True)
    for U in ['A', 'B']:
        R, rf = load(D, U); w = np.array(UNIV[U]['w']); c5 = np.full(len(w), 5e-4)
        for fam in ['D', 'M', 'MB']:
            for sg, (a, b) in segments(R.index).items():
                Rs, rfs = seg_slice(R, rf, a, b)
                res, out, ev = one_cell(Rs, rfs, w, c5, fam)
                key = f'{U}|{fam}|{sg}'; results['cells'][key] = dict(det=res, **ev)
                if sg == 'full':
                    V = out['Vpath']; step = 5
                    results['equity'][f'{U}|{fam}'] = dict(dates=[str(x.date()) for x in Rs.index[::step]],
                                                            V={int(k): V[k, ::step].tolist() for k in KS})
                pk = ev['per_k']
                print(key, 'n_ev', ev['events']['n'], 'cagr_diff k3-5', np.round(res['cagr_diff_bps'][3:6], 1),
                      'ev mean k3-5', [round(pk[k]['mean_bps'], 2) for k in (3, 4, 5)] if pk else None,
                      'holm', [round(pk[k]['holm_primary'], 3) for k in (3, 4, 5)] if pk else None, flush=True)
            # sensitivities on full segment
            Rf, rff = R, rf
            for nm, c in [('cost2', np.full(len(w), 2e-4)), ('cost10', np.full(len(w), 1e-3)),
                          ('yaml', np.array(UNIV[U]['yaml']) / 1e4), ('yaml2x', 2 * np.array(UNIV[U]['yaml']) / 1e4)]:
                res, _, ev = one_cell(Rf, rff, w, c, fam, events=(nm in ('cost10', 'yaml2x')))
                results['sens'][f'{U}|{fam}|{nm}'] = dict(cagr_diff_bps=res['cagr_diff_bps'], fills=res['fills'],
                    ev_mean_bps={k: ev['per_k'][k]['mean_bps'] for k in (3, 4, 5)} if ev and ev['per_k'] else None)
            if fam != 'M':
                res, _, ev = one_cell(Rf, rff, w, c5, fam, cancel=True, events=False)
                results['sens'][f'{U}|{fam}|cancel_if_uncrossed'] = dict(cagr_diff_bps=res['cagr_diff_bps'], fills=res['fills'])
    for U in ['A_long', 'A_veiex', 'A_asfyx', 'A_pput']:
        R, rf = load(D, U); w = np.array(UNIV[U]['w']); c5 = np.full(len(w), 5e-4)
        for fam in ['D', 'M', 'MB']:
            res, _, ev = one_cell(R, rf, w, c5, fam)
            pk = ev['per_k']
            results['sens'][f'{U}|{fam}|cost5'] = dict(start=res['start'], end=res['end'], cagr_diff_bps=res['cagr_diff_bps'], fills=res['fills'],
                n_events=ev['events']['n'],
                ev={k: dict(mean_bps=pk[k]['mean_bps'], p_signflip_1s=pk[k]['p_signflip_1s'], holm=pk[k]['holm_primary']) for k in (3, 4, 5)} if pk else None)
            print(U, fam, ev['events']['n'], np.round(res['cagr_diff_bps'][3:6], 1), flush=True)
    json.dump(results, open(f'{D}/out_analysis.json', 'w'), default=float)
main()
