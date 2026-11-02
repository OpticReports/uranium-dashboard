"""SYNTHETIC ONLY. D-1 class probabilities when the firing-level (S1_f, p_f, |E_f|) come from the
martingale-null pipeline (sim_mechanical2.run), i.e. a series with NO information, then with an
injected edge: each mixed-episode miss of the rule is turned into a hit with prob phi (p_f updated,
since the firing day is in E_f). Clusters: mixed sizes as sim_power.py, firings drawn independently
(ignores within-cluster correlation -> optimistic for power). No data file is read."""
import sys
import numpy as np
sys.path.insert(0, ".")
import sim_mechanical2 as m2
import sim_power as sp

rng = np.random.default_rng(99)
pool = {}
for tag, model, sig_u, a, b in (("RW", "rw", 0.006, 0, 0), ("GARCH", "garch", 0.006, .08, .90)):
    R = m2.run(model, sig_u, 150, a, b)
    pool[tag] = R   # cols: path, S1_f, p_all, p_pre, p_post, uncond, |E_f|

def draw_cluster_values(R, K, phi):
    S = R[:, 1].copy(); P = R[:, 2].copy(); M = R[:, 6]
    mixed = (P > 0) & (P < 1)
    Dc = np.empty(K)
    for c, n in enumerate(sp.cluster_sizes(K, "mixed")):
        i = rng.integers(0, len(R), n)
        s, p, m, mx = S[i].copy(), P[i].copy(), M[i], mixed[i]
        flip = mx & (s == 0) & (rng.random(n) < phi)
        s[flip] = 1; p[flip] += 1 / m[flip]
        Dc[c] = (s - p).mean()
    return Dc

print("pool | phi | mean edge in mixed eps | E[T] | P(PASS) P(INC) P(FAIL) P(INVERSE)")
for tag, R in pool.items():
    P = R[:, 2]; mixed = (P > 0) & (P < 1)
    print(f"{tag}: firings {len(R)}, homogeneous share {1-mixed.mean():.2f}, mean D (null) {np.mean(R[:,1]-R[:,2]):+.3f}")
    for K in (25, 35):
        for phi in (0.0, 0.3, 0.5, 0.7):
            edge = phi * np.mean(R[mixed, 1] == 0)
            C = [sp.classify(draw_cluster_values(R, K, phi)) for _ in range(1500)]
            g = lambda k: np.mean([c[k] for c in C])
            print(f"  {tag} K={K} phi={phi:.1f} | edge_mixed {edge:+.2f} | E[T] {g('T'):+.3f} | PASS {g('PASS'):.2f}  INC {g('INC'):.2f}  FAIL {g('FAIL'):.2f}  INVERSE {g('INVERSE'):.2f}")
