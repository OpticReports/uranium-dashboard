import numpy as np, pandas as pd, json
SEED = 20261116
UNIV = {
 'A': dict(w=[.235, .235, .153, .141, .177, .059], yaml=[5, 8, 3, 10, 10, 12]),
 'A_veiex': dict(w=[.235, .235, .153, .141, .118, .059, .059], yaml=[5, 8, 3, 10, 10, 8, 12]),
 'A_long': dict(w=[.412, .235, .153, .141, .059], yaml=[5, 8, 3, 10, 12]),
 'A_asfyx': dict(w=[.235, .235, .153, .141, .177, .059], yaml=[5, 8, 3, 10, 10, 12]),
 'A_pput': dict(w=[.235, .235, .153, .141, .177, .059], yaml=[5, 8, 3, 10, 10, 12]),
 'B': dict(w=[.4, .4, .2], yaml=[1, 10, 8]),
}
def load(D, name):
    R = pd.read_pickle(f'{D}/data/{name}.pkl'); rf = pd.read_pickle(f'{D}/data/{name}_rf.pkl')
    return R, rf
def me_flags(idx):
    p = pd.Series(idx.to_period('M')); return p.ne(p.shift(-1)).values
def segments(idx):
    s, e = idx[0], idx[-1]; mid = s + (e - s) / 2
    segs = {'full': (s, e), 'H1': (s, mid), 'H2': (mid + pd.Timedelta(days=1), e)}
    if s < pd.Timestamp('2013-01-01'): segs['pre2013'] = (s, pd.Timestamp('2012-12-31'))
    return segs
def seg_slice(R, rf, a, b):
    m = (R.index >= a) & (R.index <= b); return R[m], rf[m]
def cagr(logV, n_days):
    return np.expm1(logV * 252.0 / (n_days - 1))
