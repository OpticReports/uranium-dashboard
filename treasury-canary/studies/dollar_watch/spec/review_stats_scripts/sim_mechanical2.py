"""SYNTHETIC ONLY. Extends sim_mechanical.py: decomposes the martingale-null bias of D_f by which part
of E_f the benchmark uses (all = SPEC; pre = days <= f; post = days >= f), varies the vol level
(s ~ 0.9 / 1.8 / 3.5) and the GARCH persistence. Path-clustered SE (by path). No data file is read."""
import sys
import numpy as np
sys.path.insert(0, ".")
import sim_mechanical as sm

def run(model, sig_u, reps, a=0.08, b=0.90):
    rows = []
    for p in range(reps):
        if model == "rw":
            r = sig_u * sm.rng.standard_normal(12000)
        else:
            nu = 5.0; w = sig_u ** 2 * (1 - a - b)
            z = sm.rng.standard_t(nu, 12000) / np.sqrt(nu / (nu - 2))
            r = np.empty(12000); h = sig_u ** 2
            for t in range(12000):
                r[t] = np.sqrt(h) * z[t]; h = w + a * r[t] ** 2 + b * h
        X = np.exp(np.concatenate([[0.0], np.cumsum(r)]))
        res = analyse_split(X, r)
        for row in res:
            rows.append((p,) + row)
    R = np.array(rows, dtype=float)
    return R

def analyse_split(X, r):
    # reuse sm.analyse internals by re-deriving the arrays (copy of the logic, returns split benchmarks)
    n = len(X)
    from numpy.lib.stride_tricks import sliding_window_view as swv
    roc = np.full(n, np.nan); roc[20:] = X[20:] / X[:-20] - 1
    k0 = 817
    cs = np.concatenate([[0], np.cumsum(r)]); cs2 = np.concatenate([[0], np.cumsum(r ** 2)])
    s = np.full(n, np.nan); k = np.arange(k0, n); hi = k - 61; lo = hi - 756
    m1 = (cs[hi] - cs[lo]) / 756; m2 = (cs2[hi] - cs2[lo]) / 756
    s[k0:] = np.clip(np.sqrt(np.maximum(m2 - m1 ** 2, 0) * 756 / 755) / sm.SIG_B, 0.25, 8)
    mx = np.full(n, np.nan); mx[80:] = swv(roc[20:], 61).max(axis=1)[:n - 80]
    hx = np.full(n, np.nan); hx[60:] = swv(X, 61).max(axis=1)
    fmax = np.full(n, np.nan); fmax[:n - 250] = swv(X[1:], 250).max(axis=1)[:n - 250]
    valid = np.zeros(n, bool); valid[k0:n - 250] = True
    gate = valid & (mx >= 0.04 * s); dec = roc <= 0.5 * mx; near = X >= (1 - 0.03 * s) * hx
    S1 = fmax <= X * (1 + 0.03 * s)
    cand = np.where(gate & dec & near)[0]; fires = []; last = -10 ** 9
    for c in cand:
        if c - last > 120:
            fires.append(c); last = c
    g = gate.astype(int); d = np.diff(np.concatenate([[0], g, [0]]))
    st = np.where(d == 1)[0]; en = np.where(d == -1)[0] - 1; eps = []
    for a_, b_ in zip(st, en):
        if eps and a_ - eps[-1][1] - 1 < 20: eps[-1][1] = b_
        else: eps.append([a_, b_])
    out = []; prev = -10 ** 9; uncond = S1[valid].mean()
    for f in fires:
        e = next(ep for ep in eps if ep[0] <= f <= ep[1])
        idx = np.arange(e[0], e[1] + 1); idx = idx[gate[idx] & near[idx] & (idx - prev > 120)]
        pre = idx[idx <= f]; post = idx[idx >= f]
        out.append((S1[f], S1[idx].mean(), S1[pre].mean(), S1[post].mean(), uncond, len(idx)))
        prev = f
    return out

def summarize(tag, R):
    paths = np.unique(R[:, 0])
    def mse(v):
        # path-clustered SE of the mean of v
        m = v.mean(); g = np.array([v[R[:, 0] == p].sum() - m * (R[:, 0] == p).sum() for p in paths])
        return m, np.sqrt((g ** 2).sum()) / len(v)
    S, pall, ppre, ppost, unc = R[:, 1], R[:, 2], R[:, 3], R[:, 4], R[:, 5]
    out = [tag, f"firings {len(R)}"]
    for name, v in (("rule-uncond", S - unc), ("D_SPEC(all E_f)", S - pall), ("D_pre(E_f<=f)", S - ppre), ("D_post(E_f>=f)", S - ppost)):
        m, se = mse(v); out.append(f"{name} {m:+.3f}±{se:.3f}")
    print(" | ".join(out))

if __name__ == "__main__":
  reps = int(sys.argv[1])
  for model, sig_u, a, b in (("rw", 0.006, 0, 0), ("garch", 0.003, .08, .90), ("garch", 0.006, .08, .90), ("garch", 0.012, .08, .90), ("garch", 0.006, .05, .90), ("garch", 0.006, .10, .89)):
    R = run(model, sig_u, reps, a, b)
    summarize(f"[{model} sig_u={sig_u} a={a} b={b}]", R)
