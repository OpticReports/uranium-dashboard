"""Moving-block bootstrap (252-day blocks, 10,000 resamples, seed 20261116) of the joint daily sleeve-return
matrix; month-end flags travel with their rows; full strategy rerun for every k on each resample (PREREG sec 4)."""
import sys, json, numpy as np, time
from multiprocessing import Pool
from engine import run, KS
from common import *
D = sys.argv[1]; NB = int(sys.argv[2]) if len(sys.argv) > 2 else 10_000
BL = 252; BATCH = 400

def cell(args):
    U, fam, sg = args
    R, rf = load(D, U); a, b = segments(R.index)[sg]; Rs, _ = seg_slice(R, rf, a, b)
    X = Rs.values[1:].astype(np.float64); ME = me_flags(Rs.index)[1:]; T = len(X)
    w = np.array(UNIV[U]['w']); c = np.full(len(w), 5e-4)
    rng = np.random.default_rng(SEED); nbk = int(np.ceil(T / BL))
    starts = rng.integers(0, T - BL + 1, size=(NB, nbk))
    idx = (starts[:, :, None] + np.arange(BL)[None, None, :]).reshape(NB, -1)[:, :T]
    out = np.empty((NB, len(KS))); t0 = time.time()
    for s in range(0, NB, BATCH):
        ii = idx[s:s + BATCH]
        Rb = np.concatenate([np.zeros((len(ii), 1, X.shape[1])), X[ii]], 1)
        MEb = np.concatenate([np.zeros((len(ii), 1), bool), ME[ii]], 1)
        out[s:s + BATCH] = cagr(run(Rb, MEb, w, c, fam)['logV'], T + 1)
    diff = (out - out[:, [1]]) * 1e4
    res = dict(n=NB, mean_bps=diff.mean(0).tolist(), lo_bps=np.percentile(diff, 2.5, 0).tolist(),
               hi_bps=np.percentile(diff, 97.5, 0).tolist(), frac_pos=(diff > 0).mean(0).tolist(), secs=time.time() - t0)
    print(U, fam, sg, 'k4', round(res['mean_bps'][4], 1), [round(res['lo_bps'][4], 1), round(res['hi_bps'][4], 1)], f"{res['secs']:.0f}s", flush=True)
    return f'{U}|{fam}|{sg}', res

if __name__ == '__main__':
    jobs = []
    for U in ['A', 'B']:
        R, _ = load(D, U)
        for fam in ['D', 'M', 'MB']:
            for sg in segments(R.index): jobs.append((U, fam, sg))
    with Pool(int(sys.argv[3]) if len(sys.argv) > 3 else 4) as p:
        res = dict(p.imap_unordered(cell, jobs))
    json.dump(res, open(f'{D}/out_bootstrap{"" if NB == 10000 else "_" + str(NB)}.json', 'w'))
