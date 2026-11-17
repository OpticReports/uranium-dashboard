"""Gate test: vectorized engine == naive loop reference, all families, k grid, cancel on/off."""
import numpy as np, pandas as pd, sys
from engine import run, BAND
def ref(R, ME, w, c, fam, k, cancel=False):
    T, N = R.shape; h = np.array(w, float); pend = -1; trig_t = []
    for t in range(1, T):
        h = h * (1 + R[t])
        if pend > 0: pend -= 1
        if pend == 0:
            pend = -1
            V = h.sum(); br = (np.abs(h / V / w - 1) > BAND).any()
            if not (cancel and fam != 'M' and not br):
                tr = np.abs(w * V - h); h = w * (V - (tr * c).sum())
        V = h.sum(); br = (np.abs(h / V / w - 1) > BAND).any()
        trig = pend < 0 and (ME[t] if fam == 'M' else (br and (ME[t] if fam == 'MB' else True)))
        if trig:
            trig_t.append(t)
            if k == 0:
                tr = np.abs(w * V - h); h = w * (V - (tr * c).sum())
            else: pend = k
    return np.log(h.sum()), trig_t
D = sys.argv[1]
A = pd.read_pickle(f'{D}/A.pkl').iloc[:3000]
R = A.values; ME = (A.index.to_period('M') != A.index.to_period('M').shift(-1) if False else pd.Series(A.index.to_period('M')).ne(pd.Series(A.index.to_period('M')).shift(-1)).values)
w = np.array([.235, .235, .153, .141, .177, .059]); c = np.array([5, 8, 3, 10, 10, 12]) / 1e4
bad = 0
for fam in ['D', 'M', 'MB']:
    for cancel in [False, True]:
        o = run(R, ME, w, c, fam, cancel=cancel, record=True)
        for k in range(11):
            lv, tt = ref(R, ME, w, c, fam, k, cancel)
            ok = abs(lv - o['logV'][0, k]) < 1e-10 and tt == [x[0] for x in o['trig'][k]]
            bad += not ok
            if not ok: print('MISMATCH', fam, cancel, k, lv, o['logV'][0, k], len(tt), len(o['trig'][k]))
        print(fam, cancel, 'events k=1:', len(o['trig'][1]), 'fills', o['nfill'][0, :4])
# batch == single
o1 = run(R, ME, w, c, 'D'); ob = run(np.stack([R, R]), np.stack([ME, ME]), w, c, 'D')
assert np.allclose(o1['logV'][0], ob['logV'][1])
print('FAILURES', bad); sys.exit(1 if bad else 0)
