"""Term-structure VIX-ETP model: r_ETP = b1*dVIX% + b2*dVIX3M% + g*slope + a,
slope = (VIX3M - VIX)/VIX at the prior close (contango > 0 -> long-vol roll loss).
Fit 2011-2018 (UVXY 2x->1.5x handled by era), test OOS 2019-2026 incl. COVID.
Compared with the plain dVIX regression used so far."""
import os, json, math, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from replay import yh, rets_of, curve_from, SP, corr
subprocess.run([sys.executable, f'{SP}/yh_fetch.py', '^VIX6M'], check=False)
vix = yh('^VIX'); v3 = yh('^VIX3M'); rv = rets_of(vix); rv3 = rets_of(v3)
try:
    v6 = yh('^VIX6M'); rv6 = rets_of(v6)
except Exception:
    v6 = {}; rv6 = {}
ds_all = sorted(set(rv) & set(rv3))
prev = {ds_all[i]: ds_all[i-1] for i in range(1, len(ds_all))}
slope = {d: (v3[prev[d]]-vix[prev[d]])/vix[prev[d]] for d in ds_all if d in prev}
slope6 = {d: (v6[prev[d]]-v3[prev[d]])/v3[prev[d]] for d in ds_all if d in prev and prev[d] in v6 and prev[d] in v3}

def ols_multi(y, X):
    """least squares via normal equations (small k)."""
    n = len(y); k = len(X[0])
    A = [[sum(X[i][a]*X[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    B = [sum(X[i][a]*y[i] for i in range(n)) for a in range(k)]
    # gaussian elimination
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(A[r][c])); A[c], A[p] = A[p], A[c]; B[c], B[p] = B[p], B[c]
        for r in range(k):
            if r != c and A[c][c]:
                f = A[r][c]/A[c][c]; A[r] = [A[r][j]-f*A[c][j] for j in range(k)]; B[r] -= f*B[c]
    beta = [B[c]/A[c][c] for c in range(k)]
    res = [y[i]-sum(beta[j]*X[i][j] for j in range(k)) for i in range(n)]
    return beta, res

SPEC = {  # etp: (features, leverage eras)
    'UVXY': ('short', [('2011-10-04', '2018-02-27', 2.0), ('2018-02-28', '2099', 1.5)]),
    'VIXY': ('short', [('2011-01-04', '2099', 1.0)]),
    'SVXY': ('short', [('2011-10-04', '2018-02-27', -1.0), ('2018-02-28', '2099', -0.5)]),
    'VIXM': ('mid', [('2011-01-04', '2099', 1.0)]),
    'VXZ':  ('mid', [('2018-01-25', '2099', 1.0)]),
}
def feats(d, kind):
    if kind == 'short': return [rv[d], rv3[d], slope[d], 1.0]
    f = [rv3[d], rv6.get(d, rv3[d]), slope6.get(d, slope[d]), 1.0]; return f
models = {}
for etp, (kind, eras) in SPEC.items():
    re = rets_of(yh(etp)); lev_of = lambda d: next((L for a, b, L in eras if a <= d <= b), None)
    com = [d for d in ds_all if d in re and d in slope and lev_of(d) and (kind == 'short' or d in rv3)]
    # normalise by leverage: y = r_etp / lev
    y_all = {d: re[d]/lev_of(d) for d in com}
    fit_d = [d for d in com if d < '2019-01-01']; oos_d = [d for d in com if d >= '2019-01-01']
    if len(fit_d) < 300: fit_d = com[:int(len(com)*0.6)]; oos_d = com[int(len(com)*0.6):]
    beta, res = ols_multi([y_all[d] for d in fit_d], [feats(d, kind) for d in fit_d])
    # plain dVIX model for comparison
    bp, resp = ols_multi([y_all[d] for d in fit_d], [[rv[d] if kind == 'short' else rv3[d], 1.0] for d in fit_d])
    def pred(d, b, plain=False):
        x = [rv[d] if kind == 'short' else rv3[d], 1.0] if plain else feats(d, kind); return sum(bb*xx for bb, xx in zip(b, x))
    oy = [y_all[d] for d in oos_d]; op = [pred(d, beta) for d in oos_d]; opp = [pred(d, bp, True) for d in oos_d]
    cum = lambda a: math.prod(1+v for v in a)
    covid = [d for d in oos_d if '2020-02-19' <= d <= '2020-03-18']
    cov = (round(cum([y_all[d] for d in covid]), 3), round(cum([pred(d, beta) for d in covid]), 3), round(cum([pred(d, bp, True) for d in covid]), 3)) if covid else None
    models[etp] = {'kind': kind, 'beta': [round(b, 5) for b in beta], 'beta_plain': [round(b, 5) for b in bp], 'eras': eras,
                   'fit': [fit_d[0], fit_d[-1]], 'oos_corr': round(corr(oy, op), 4), 'oos_corr_plain': round(corr(oy, opp), 4),
                   'oos_cum_real': round(cum(oy), 3), 'oos_cum_model': round(cum(op), 3), 'oos_cum_plain': round(cum(opp), 3),
                   'covid_real_model_plain (per-unit-lev)': cov}
    print(etp, models[etp])
json.dump(models, open(f'{SP}/vix_models.json', 'w')); print('saved')
