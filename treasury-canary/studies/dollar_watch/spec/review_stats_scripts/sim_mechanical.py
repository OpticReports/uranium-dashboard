"""SYNTHETIC ONLY: does the SPEC's matched benchmark leave a MECHANICAL edge when the series is a
martingale (no economics at all)? D-1 rule as SPEC 3.2/3.5: s = clip(sd(756 log changes ending k-61)
/ sigma_B, .25, 8); gate max roc20[k-60..k] >= .04 s; decel roc20 <= .5 max; near-high X >= (1-.03 s)
* max X[k-60..k]; cooling 120; no yield condition. S1: max X(k, k+250] <= X[k] (1 + .03 s).
E_f: gate-on & near-high days of f's episode, > 120 days after the previous firing, firing day incl.
Null models: constant-vol Gaussian RW; GARCH(1,1)-t(5) with persistence .98 (alpha .08, beta .90).
Also reports episodes/yr, firing share of episodes, |E_f|, and the share of homogeneous E_f
(p_f in {0,1} => D_f = 0 by construction). No data file is read."""
import sys
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

SIG_B = 0.00341
rng = np.random.default_rng(int(sys.argv[2]) if len(sys.argv) > 2 else 11)


def path(N, model, sig_u=0.006):
    if model == "rw":
        r = sig_u * rng.standard_normal(N)
    else:
        a, b, nu = 0.08, 0.90, 5.0
        w = sig_u ** 2 * (1 - a - b)
        z = rng.standard_t(nu, N) / np.sqrt(nu / (nu - 2))
        r = np.empty(N); h = sig_u ** 2
        for t in range(N):
            r[t] = np.sqrt(h) * z[t]
            h = w + a * r[t] ** 2 + b * h
    return np.exp(np.concatenate([[0.0], np.cumsum(r)])), r


def analyse(X, r):
    n = len(X)
    roc = np.full(n, np.nan); roc[20:] = X[20:] / X[:-20] - 1
    k0 = 817
    # trailing sd of the 756 log changes r[k-61-756 .. k-62] (r[i] = log X[i+1]/X[i]); ends at day k-61
    cs = np.concatenate([[0], np.cumsum(r)]); cs2 = np.concatenate([[0], np.cumsum(r ** 2)])
    s = np.full(n, np.nan)
    k = np.arange(k0, n)
    hi = k - 61; lo = hi - 756
    m1 = (cs[hi] - cs[lo]) / 756; m2 = (cs2[hi] - cs2[lo]) / 756
    s[k0:] = np.clip(np.sqrt(np.maximum(m2 - m1 ** 2, 0) * 756 / 755) / SIG_B, 0.25, 8)
    mx = np.full(n, np.nan); mx[80:] = swv(roc[20:], 61).max(axis=1)[:n - 80]
    hx = np.full(n, np.nan); hx[60:] = swv(X, 61).max(axis=1)
    fmax = np.full(n, np.nan); fmax[:n - 250] = swv(X[1:], 250).max(axis=1)[:n - 250]
    valid = np.zeros(n, bool); valid[k0:n - 250] = True
    gate = valid & (mx >= 0.04 * s)
    dec = roc <= 0.5 * mx
    near = X >= (1 - 0.03 * s) * hx
    S1 = fmax <= X * (1 + 0.03 * s)
    cand = np.where(gate & dec & near)[0]
    fires = []; last = -10 ** 9
    for c in cand:
        if c - last > 120:
            fires.append(c); last = c
    # episodes
    g = gate.astype(int); d = np.diff(np.concatenate([[0], g, [0]]))
    st = np.where(d == 1)[0]; en = np.where(d == -1)[0] - 1
    eps = []
    for a_, b_ in zip(st, en):
        if eps and a_ - eps[-1][1] - 1 < 20:
            eps[-1][1] = b_
        else:
            eps.append([a_, b_])
    out = []; prev = -10 ** 9
    for f in fires:
        e = next(ep for ep in eps if ep[0] <= f <= ep[1])
        idx = np.arange(e[0], e[1] + 1)
        idx = idx[gate[idx] & near[idx] & (idx - prev > 120)]
        pf = S1[idx].mean()
        # decomposition: benchmark restricted to decel-eligible days only ("any decel day" vs "first")
        idd = idx[dec[idx]]
        pdec = S1[idd].mean() if len(idd) else np.nan
        out.append((S1[f] - pf, len(idx), pf in (0.0, 1.0), pf, S1[f], S1[f] - pdec))
        prev = f
    nfire_eps = sum(1 for ep in eps if any(ep[0] <= f <= ep[1] for f in fires))
    yrs = valid.sum() / 250.0
    return out, len(eps), nfire_eps, yrs, S1[valid].mean()


if __name__ == "__main__":
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    N = 12000
    for model in ("rw", "garch"):
        D, M, H, PF, S, DD = [], [], [], [], [], []
        E = F = 0; Y = 0.0; S1all = []
        for _ in range(reps):
            X, r = path(N, model)
            out, ne, nfe, yrs, s1m = analyse(X, r)
            E += ne; F += nfe; Y += yrs; S1all.append(s1m)
            for o in out:
                D.append(o[0]); M.append(o[1]); H.append(o[2]); PF.append(o[3]); S.append(o[4]); DD.append(o[5])
        D = np.array(D); M = np.array(M); H = np.array(H); DD = np.array(DD)
        se = D.std(ddof=1) / np.sqrt(len(D))
        print(f"\n[{model}] paths {reps}, eval years {Y:.0f}: episodes {E} ({E/Y:.2f}/yr), "
              f"episodes with a firing {F/E:.0%}, firings {len(D)}")
        print(f"   unconditional S1 rate {np.mean(S1all):.3f}; mean p_f {np.mean(PF):.3f}; rule hit rate {np.mean(S):.3f}")
        print(f"   mean D_f (rule - matched random) = {D.mean():+.4f}  (SE {se:.4f}; naive iid SE)")
        print(f"   share homogeneous E_f (D_f = 0 by construction) {H.mean():.2f}; |E_f| median {np.median(M):.0f}, "
              f"share |E_f|<=5 {np.mean(M <= 5):.2f}")
        ok = ~np.isnan(DD)
        print(f"   rule vs random DECEL-eligible day only: mean {DD[ok].mean():+.4f} (SE {DD[ok].std(ddof=1)/np.sqrt(ok.sum()):.4f})")
        print(f"   sd of D_f over non-homogeneous firings {D[~H].std(ddof=1):.3f}; over all {D.std(ddof=1):.3f}")
