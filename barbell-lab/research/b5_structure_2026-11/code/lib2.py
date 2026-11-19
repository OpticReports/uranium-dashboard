"""Shared pieces for the structure study: extended tape, book simulation, risk-balance maths, bootstrap.
The overlay study's verified engine (simulate, metrics) and tape builder are imported unchanged."""
import os, pickle, sys
import numpy as np, pandas as pd
from numba import njit, prange
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.abspath(__file__)); STUDY = os.path.dirname(HERE)
OV = os.path.join(os.path.dirname(STUDY), "b5_overlay_2026-11", "code"); sys.path.insert(0, OV)
os.environ.setdefault("B5_CACHE", os.path.join(os.path.dirname(STUDY), "b5_overlay_2026-11", "_cache"))
import common as C, engine as E  # noqa: E402

LEGS = C.LEGS                                                   # AVUV PHYS QUAL KMLM AVDV AVEM TAIL
EXTRA = ["BTAL", "DBMFc", "IEF", "TIP", "USMV", "AVLVc", "UUP", "CLLZ", "PPUT"]
COLS = LEGS + EXTRA + ["BIL"]; IX = {c: i for i, c in enumerate(COLS)}; N = len(COLS)
LIVE = np.zeros(N); LIVE[:7] = C.BASE[:7]
EQ = ["AVUV", "QUAL", "AVDV", "AVEM"]; EQW = np.array([LIVE[IX[l]] for l in EQ]); EQP = EQW / EQW.sum()
COST = np.array([C.BT["costs_bps"][l] for l in LEGS] + [10, 10, 2, 3, 3, 5, 5, 3, 3, 1.0]) / 1e4
SPREAD = 0.005
EXT0, CONF0 = C.EXT0, C.CONF0


def load():
    return pickle.load(open(os.path.join(STUDY, "_cache", "panel2.pkl"), "rb"))


def build(p, variant="T1"):
    """Overlay tape (legs + BIL) plus the new instruments. A column is 0.0 before its first usable return;
    `first` records that date so no arm holds it earlier."""
    t = C.build_tape(p, variant); cal = t["cal"]; r = p["ret"]; R = pd.DataFrame(index=cal, columns=COLS, dtype=float)
    for l in LEGS + ["BIL"]:
        R[l] = t["R"][l].values
    kchain = t["R"]["KMLM"]
    d = r["DBMF"].reindex(cal); a = r["AQMIX"].reindex(cal)
    R["DBMFc"] = np.where(d.notna(), d, np.where(a.notna(), a, kchain))          # DBMF <- AQMIX <- the KMLM chain (RYMFX/cash)
    av = r["AVLV"].reindex(cal); R["AVLVc"] = np.where(av.notna(), av, r["DFLVX"].reindex(cal))
    first = {}
    for c, src in (("BTAL", "BTAL"), ("IEF", "IEF"), ("TIP", "TIP"), ("USMV", "USMV"), ("UUP", "UUP"), ("CLLZ", "CLLZ"), ("PPUT", "PPUT")):
        x = r[src].reindex(cal); first[c] = x.first_valid_index(); R[c] = x.fillna(0.0).values
    first["DBMFc"] = cal[0]; first["AVLVc"] = cal[0]
    if R.isna().any().any():
        raise RuntimeError(f"NaN in tape2: {R.isna().sum()[R.isna().sum() > 0].to_dict()}")
    return dict(cal=cal, R=R, me=t["me"], first=first, variant=variant, kmlm_real_from=t["S"]["KMLM"].ne("cash").idxmax())


def vec(**kw):
    w = np.zeros(N)
    for k, v in kw.items():
        w[IX[k]] = v
    return w


def path(cal, base, changes=None):
    """Target-weight path: `base` everywhere, then each (date, weights) in `changes` from that date on."""
    W = np.repeat(np.asarray(base, float)[None, :], len(cal), 0)
    for d, w in sorted(changes or [], key=lambda x: x[0]):
        W[int(cal.searchsorted(pd.Timestamp(d))):] = w
    return W


def sim(tape, W, cost=COST, spread=None):
    """Run the verified engine. spread=None: cash earns BIL. spread=x: the cash column is a LOAN costing BIL + x/yr
    (only valid when the cash weight is never positive)."""
    R = np.ascontiguousarray(tape["R"].values.copy())
    if spread is not None:
        if W[:, -1].max() > 1e-12:
            raise RuntimeError("loan column used with positive cash weight")
        R[:, -1] = R[:, -1] + spread / 252.0
    T = len(R)
    return E.simulate(R, np.ascontiguousarray(W), cost, tape["me"], C.BAND, C.CAL_DAYS, 1e-9, False, np.zeros(N, bool), 0.0, 0, T)[0]


def lever(r_unlev, c, g, spread, reset_cost=5e-4):
    """Constant-gross leverage, reset daily (what a stacked ETF, a futures overlay or a managed loan does; D15):
    g x the unlevered book, the borrowed (g-1) pays T-bills + spread, and the daily reset trade g(g-1)|r| pays reset_cost."""
    g = np.asarray(g, float) if not np.isscalar(g) else np.full(len(r_unlev), g)
    return g * r_unlev - (g - 1) * (c + spread / 252.0) - g * (g - 1) * np.abs(r_unlev) * reset_cost


# ---------- risk balance
def erc(cov, cap=1.0):
    """Equal risk contribution; a per-asset cap is enforced inside the solver (D3). With a binding cap the
    contributions cannot all be equal: the solver then minimises their squared spread."""
    n = len(cov); b = np.full(n, 1.0 / n)
    def f(w):
        rc = w * (cov @ w); rc = rc / rc.sum(); return ((rc - b) ** 2).sum() * 1e4
    best = None
    for x0 in (np.full(n, 1.0 / n), np.minimum(1 / np.sqrt(np.diag(cov)) / (1 / np.sqrt(np.diag(cov))).sum(), cap)):
        res = minimize(f, x0 / x0.sum(), bounds=[(1e-6, cap)] * n, constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}], method="SLSQP",
                       options={"ftol": 1e-15, "maxiter": 1000})
        if best is None or res.fun < best.fun:
            best = res
    w = np.clip(best.x, 0, cap)
    for _ in range(50):                                            # exact sum-to-one without breaching the cap
        gap = 1.0 - w.sum(); free = w < cap - 1e-12
        if abs(gap) < 1e-14 or not free.any():
            break
        w[free] += gap * w[free] / w[free].sum(); w = np.clip(w, 0, cap)
    rc = w * (cov @ w); rc /= rc.sum()
    if w.max() < cap - 1e-6 and np.abs(rc - b).max() > 2e-3:
        raise RuntimeError(f"ERC did not converge: {rc}")
    return w


def semicov(X):
    D = np.minimum(X, 0.0); return D.T @ D / len(D)


# ---------- statistics
def chunks21(ex):
    """Consecutive 21-trading-day compounded excess returns (the 'monthly' returns of D8); a trailing partial chunk is dropped."""
    ex = np.asarray(ex, float); n = len(ex) // 21
    return np.prod(1 + ex[:n * 21].reshape(n, 21), 1) - 1


def sortino(ex):
    """Sortino on 21-day chunks: annualised mean over annualised downside deviation (target 0 excess)."""
    m = chunks21(ex); return float(m.mean() * 12 / (np.sqrt((np.minimum(m, 0) ** 2).mean()) * np.sqrt(12)))


@njit(parallel=True, cache=True)
def boot2(A, B, V, idx):
    """A: T x K arm excess returns, B: T x K control excess returns, V: T x K validity (1 = inside the arm's window).
    idx: D x T resampled rows. Returns D x K differences (arm - control) of daily Sharpe and of 21-day-chunk Sortino,
    both computed on the valid resampled rows in resampled order."""
    D, T = idx.shape; K = A.shape[1]
    dS = np.empty((D, K)); dO = np.empty((D, K))
    for d in prange(D):
        for k in range(K):
            n = 0; sa = 0.0; sa2 = 0.0; sb = 0.0; sb2 = 0.0
            ca = 1.0; cb = 1.0; c = 0; nm = 0; ma_ = 0.0; mb_ = 0.0; da = 0.0; db = 0.0
            for t in range(T):
                j = idx[d, t]
                if V[j, k]:
                    a = A[j, k]; b = B[j, k]; n += 1
                    sa += a; sa2 += a * a; sb += b; sb2 += b * b
                    ca *= 1.0 + a; cb *= 1.0 + b; c += 1
                    if c == 21:
                        xa = ca - 1.0; xb = cb - 1.0; nm += 1; ma_ += xa; mb_ += xb
                        if xa < 0:
                            da += xa * xa
                        if xb < 0:
                            db += xb * xb
                        ca = 1.0; cb = 1.0; c = 0
            if n < 60 or nm < 6:
                dS[d, k] = np.nan; dO[d, k] = np.nan; continue
            ma = sa / n; mb = sb / n
            va = (sa2 - n * ma * ma) / (n - 1); vb = (sb2 - n * mb * mb) / (n - 1)
            dS[d, k] = (ma / np.sqrt(va) - mb / np.sqrt(vb)) * np.sqrt(252.0)
            dO[d, k] = ((ma_ / nm) / np.sqrt(da / nm) - (mb_ / nm) / np.sqrt(db / nm)) * np.sqrt(12.0) if da > 0 and db > 0 else np.nan
    return dS, dO


def pvals(draws, obs, fam):
    """One-sided, centred, studentised by each arm's bootstrap SE (D7). Returns se, raw p per arm, single-step
    max-T adjusted p for the arms in `fam`, and the family's 90% critical value."""
    se = np.nanstd(draws, 0, ddof=1); t = obs / se; Z = (draws - obs) / se
    raw = np.array([np.nanmean(Z[:, k] >= t[k]) for k in range(len(obs))])
    mx = np.nanmax(np.where(np.isnan(Z[:, fam]), -9.0, Z[:, fam]), 1)
    adj = {k: float((mx >= t[k]).mean()) for k in fam}
    return se, raw, adj, float(np.percentile(mx, 90))
