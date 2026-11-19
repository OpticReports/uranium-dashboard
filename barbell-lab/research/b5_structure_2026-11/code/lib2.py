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


# ---------- risk balance
def erc(cov, budget=None):
    n = len(cov); b = np.full(n, 1.0 / n) if budget is None else np.asarray(budget, float)
    def f(w):
        rc = w * (cov @ w); rc = rc / rc.sum(); return ((rc - b) ** 2).sum() * 1e4
    res = minimize(f, np.full(n, 1.0 / n), bounds=[(1e-6, 1)] * n, constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}], method="SLSQP",
                   options={"ftol": 1e-14, "maxiter": 500})
    w = res.x / res.x.sum(); rc = w * (cov @ w); rc /= rc.sum()
    if np.abs(rc - b).max() > 1e-3:
        raise RuntimeError(f"ERC did not converge: {rc}")
    return w


def semicov(X):
    D = np.minimum(X, 0.0); return D.T @ D / len(D)


def cap25(w, to=EQ, cap=0.25):
    """Any position above the cap is cut to it; the excess goes to the `to` legs in live equity proportions."""
    w = w.copy()
    for _ in range(10):
        over = np.where(w[:-1] > cap + 1e-12)[0]
        if not len(over):
            break
        ex = (w[over] - cap).sum(); w[over] = cap
        for l, pr in zip(to, EQP):
            w[IX[l]] += ex * pr
    return w


# ---------- statistics
def sortino(ex):
    ex = np.asarray(ex, float); return float(ex.mean() * 252 / (np.sqrt((np.minimum(ex, 0) ** 2).mean()) * np.sqrt(252)))


@njit(parallel=True, cache=True)
def boot2(A, B, V, idx):
    """A: T x K arm excess returns, B: T x K control excess returns, V: T x K validity (1 = inside the arm's window).
    idx: D x T resampled rows. Returns D x K differences (arm - control) of Sharpe and of Sortino on the valid rows."""
    D, T = idx.shape; K = A.shape[1]
    dS = np.empty((D, K)); dO = np.empty((D, K))
    for d in prange(D):
        for k in range(K):
            n = 0; sa = 0.0; sa2 = 0.0; sb = 0.0; sb2 = 0.0; da = 0.0; db = 0.0
            for t in range(T):
                j = idx[d, t]
                if V[j, k]:
                    a = A[j, k]; b = B[j, k]; n += 1
                    sa += a; sa2 += a * a; sb += b; sb2 += b * b
                    if a < 0:
                        da += a * a
                    if b < 0:
                        db += b * b
            if n < 30:
                dS[d, k] = np.nan; dO[d, k] = np.nan; continue
            ma = sa / n; mb = sb / n
            va = (sa2 - n * ma * ma) / (n - 1); vb = (sb2 - n * mb * mb) / (n - 1)
            dS[d, k] = (ma / np.sqrt(va) - mb / np.sqrt(vb)) * np.sqrt(252.0)
            dO[d, k] = (ma / np.sqrt(da / n) - mb / np.sqrt(db / n)) * np.sqrt(252.0) if da > 0 and db > 0 else np.nan
    return dS, dO


def pvals(draws, obs, fam):
    """One-sided, centred, studentised. Returns se, raw p per arm, single-step max-T adjusted p for arms in `fam`, crit."""
    se = np.nanstd(draws, 0, ddof=1); t = obs / se; Z = (draws - obs) / se
    raw = np.array([np.nanmean(Z[:, k] >= t[k]) for k in range(len(obs))])
    mx = np.nanmax(np.where(np.isnan(Z[:, fam]), -9, Z[:, fam]), 1)
    adj = {k: float((mx >= t[k]).mean()) for k in fam}
    return se, raw, adj, float(np.percentile(mx, 90))
