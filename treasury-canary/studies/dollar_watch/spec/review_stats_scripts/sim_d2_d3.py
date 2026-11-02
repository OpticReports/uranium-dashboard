"""SYNTHETIC ONLY. D-2 (n firings, each its own cluster; PASS T>=.15 & p<=.10; FAIL T<.05) and
D-3 at n=12/24/48 (PASS T>=.15 & p<=.05) on the martingale-null pool of sim_mechanical2, with the
same edge injection as sim_classes_null. No data file is read."""
import sys
import numpy as np
sys.path.insert(0, ".")
import sim_mechanical2 as m2
import sim_power as sp
rng = np.random.default_rng(5)
R = m2.run("garch", 0.006, 150, .08, .90)
S0, P0, M0 = R[:, 1], R[:, 2], R[:, 6]
mixed0 = (P0 > 0) & (P0 < 1)
def draw(n, phi):
    i = rng.integers(0, len(R), n)
    s, p, m, mx = S0[i].copy(), P0[i].copy(), M0[i], mixed0[i]
    fl = mx & (s == 0) & (rng.random(n) < phi); s[fl] = 1; p[fl] += 1 / m[fl]
    return s - p
for phi in (0.0, 0.5, 0.7, 1.0):
    edge = phi * np.mean(S0[mixed0] == 0)
    line = [f"phi {phi:.1f} (mixed-episode edge {edge:+.2f})"]
    for n in (6, 10, 15):
        C = [draw(n, phi) for _ in range(3000)]
        pas = np.mean([(d.mean() >= .15) and (sp.signflip_p(d) <= .10) for d in C])
        fail = np.mean([d.mean() < .05 for d in C])
        line.append(f"D-2 n={n}: PASS {pas:.2f} FAIL {fail:.2f}")
    for n in (12, 24, 48):
        C = [draw(n, phi) for _ in range(2000)]
        line.append(f"D-3 n={n}: PASS {np.mean([(d.mean() >= .15) and (sp.signflip_p(d) <= .05) for d in C]):.2f}")
    print(" | ".join(line))
