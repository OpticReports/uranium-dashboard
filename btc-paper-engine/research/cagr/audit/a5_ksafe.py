"""k_safe audit: constant-leverage scaling of k=1 per-bar returns vs the
exact fixed-qty simulate() at the same k, on the same (full) path."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import harness as H, baseline as B
d = lambda t: time.strftime("%Y-%m-%d", time.gmtime(int(t)))
bars = H.load_bars("btcusd"); closes = {"btcusd": H.closes_of(bars)}; inds = H.compute_indicators(bars, 20)
t0, t1 = H.ts_of("2013-01-01"), H.ts_of("2026-12-31")+86399
legs = B.legs_for(bars, t0, t1, inds=inds)
r1 = H.simulate(legs, closes, k=1.0, start_ts=t0, end_ts=t1)
u = np.diff(r1.equity)/r1.equity[:-1]
print("unit-ret bars", len(u), "(note: first bar's return vs start_equity dropped; r1.equity[0]=%.2f)" % r1.equity[0])
W = 2*H.BARS_PER_YEAR
def win_breach(eq, target=0.30, step=30):
    hits = tot = 0
    for s in range(0, len(eq)-W, step):
        e = eq[s:s+W]; pk = np.maximum.accumulate(e); tot += 1
        hits += ((e/pk-1).min() < -target)
    return hits/tot
def ddpath(eq):
    pk = np.maximum.accumulate(eq); x = eq/pk-1; i = x.argmin(); j = eq[:i+1].argmax(); return x[i], i, j
ks = [0.2, 0.3, 0.3958, 0.4338, 0.5, 0.75, 1.0, 1.5]
print(f"{'k':>6} | exact maxDD  scaled maxDD | exact P(2y win DD>30%)  scaled  bootstrap")
rng_paths = None
for k in ks:
    ex = H.simulate(legs, closes, k=k, start_ts=t0, end_ts=t1).equity
    sc = np.concatenate([[1.0], np.cumprod(1+k*u)])
    dex, i, j = ddpath(np.concatenate([[ex[0]], ex])); dsc, _, _ = ddpath(sc)
    # bootstrap p at k (reuse k_safe internals with same seed)
    rng = np.random.default_rng(7)
    paths = np.stack([u[H._stationary_bootstrap_idx(len(u), W, 180.0, rng)] for _ in range(1000)])
    g = np.clip(1+k*paths, 1e-12, None); eq = np.cumprod(g, axis=1)
    pk = np.maximum.accumulate(np.concatenate([np.ones((1000,1)), eq], axis=1), axis=1)[:,1:]
    pb = ((eq/pk-1).min(axis=1) < -0.30).mean()
    print(f"{k:6.4f} | {dex*100:8.2f}%  {dsc*100:8.2f}%   | {win_breach(ex):8.3f}  {win_breach(sc):8.3f}  {pb:8.3f}   trough {d(r1.ts[max(i-1,0)])} peak {d(r1.ts[max(j-1,0)])}")
