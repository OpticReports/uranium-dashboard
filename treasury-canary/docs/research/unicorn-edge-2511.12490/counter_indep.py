"""COUNTER-AGENT independent re-implementation. Written from the pre-registered
spec, NOT from replicate.py: weights built row-by-row in numpy, portfolio
returns computed by explicit array index arithmetic (port[t] = w[t-1-lag].R[t]),
so any pandas shift-semantics bug in the study code would show up as a
disagreement here."""
import glob, os
import numpy as np
import pandas as pd

SC = os.path.dirname(os.path.abspath(__file__))

def load(sub, col):
    frames = {}
    for f in sorted(glob.glob(f"{SC}/{sub}/*.csv")):
        df = pd.read_csv(f, parse_dates=["date"]).set_index("date")
        if col in df.columns:
            frames[os.path.basename(f)[:-4]] = df[col]
    p = pd.DataFrame(frames).sort_index()
    return p.loc["2004-01-01":"2024-12-31"]

P_div = load("prices_div", "adjClose")
P_raw = load("prices_raw", "adjClose")
dates = P_div.index
R = P_div.pct_change(fill_method=None)
nguard = int((R.abs() >= 1.0).sum().sum())
R = R.where(R.abs() < 1.0)
Rv = R.values
print(f"panel {P_div.shape}, returns nulled by |R|>=1 guard: {nguard}")

# ---------- micro-test of my own upfrac convention (Eq.2 excludes day t) ----
s = pd.Series([1, -1, 1, 1, -1, 1, 1, 1], dtype=float)
pos = (s > 0).astype(float)
uf3 = pos.shift(1).rolling(3, min_periods=3).mean()
# at index 4 this must average signs of r_1..r_3 = (-1,1,1) -> 2/3
assert abs(uf3.iloc[4] - 2/3) < 1e-12, "my upfrac convention is wrong"

# ---------- signal builders (from the written spec) --------------------------
def upfrac_matrix(include_t: bool):
    pos = (R > 0).astype(float).where(R.notna())
    base = pos if include_t else pos.shift(1)
    return base.rolling(63, min_periods=63).mean()

def edge_matrix(P_sig, sign: int, regime_mask):
    """sign=-1 reversal (spec), +1 momentum (bug). Row ops all cross-sectional."""
    inv = 1.0 / P_sig
    vrank = inv.rank(axis=1, pct=True)
    mom = P_sig / P_sig.shift(10) - 1.0
    revc = sign * mom
    z = revc.sub(revc.mean(axis=1), axis=0).div(revc.std(axis=1), axis=0)
    base = 0.7 * vrank + 0.3 * z
    return base.where(regime_mask)

def weights_rowwise(edge):
    """independent numpy row loop; |z|-proportional, 0.5/side."""
    E = edge.values
    W = np.zeros_like(E)
    stats = {"empty": 0, "one_qual": 0, "days": 0}
    for i in range(E.shape[0]):
        row = E[i]
        m = np.isfinite(row)
        n = int(m.sum())
        stats["days"] += 1
        if n == 0:
            stats["empty"] += 1
            continue
        if n == 1:
            stats["one_qual"] += 1
            continue
        x = row[m]
        sd = x.std(ddof=1)
        if sd == 0 or not np.isfinite(sd):
            stats["empty"] += 1
            continue
        z = (x - x.mean()) / sd
        lng = np.where(z > 0, z, 0.0)
        sht = np.where(z < 0, -z, 0.0)
        w = np.zeros(n)
        if lng.sum() > 0:
            w += 0.5 * lng / lng.sum()
        if sht.sum() > 0:
            w -= 0.5 * sht / sht.sum()
        W[i, m] = w
    return W, stats

def portfolio(W, Rv, k, cost):
    """port[t] = sum_i W[t-k,i]*R[t,i] - cost*sum|W[t-k]-W[t-k-1]|.
    k=1: same-close fill (w_t earns R_{t+1}); k=2: t+1-close fill; k=0: bug."""
    T = len(dates)
    port = np.full(T, np.nan)
    grossexp = np.full(T, np.nan)
    for t in range(T):
        if t - k < 0:
            continue
        wrow = W[t - k]
        r = Rv[t]
        valid = np.isfinite(r)
        g = float(np.sum(wrow[valid] * r[valid]))
        c = 0.0
        if t - k - 1 >= 0:
            c = cost * float(np.abs(wrow - W[t - k - 1]).sum())
        port[t] = g - c
        grossexp[t] = float(np.abs(wrow).sum())
    s = pd.Series(port, index=dates).dropna()
    ge = pd.Series(grossexp, index=dates)
    return s[s.index >= "2006-01-03"], ge[ge.index >= "2006-01-03"]

def met(r, years=None):
    if years is not None:
        r = r[r.index.year.isin(years)]
    mu, sd = r.mean(), r.std()
    curve = (1 + r).cumprod()
    dd = (curve / curve.cummax() - 1).min()
    return dict(sharpe=round(mu / sd * np.sqrt(252), 2),
                ann=round(mu * 252 * 100, 1), vol=round(sd * np.sqrt(252) * 100, 1),
                mdd=round(dd * 100, 1), med=round(float(np.median(r)) * 100, 3),
                n=len(r))

# ---------- census (Attack: claim 3) ----------------------------------------
uf_ex = upfrac_matrix(include_t=False)
uf_in = upfrac_matrix(include_t=True)
for name, uf, th in [("excl-t >0.60", uf_ex, 0.60), ("incl-t >0.60", uf_in, 0.60),
                     ("excl-t >0.55", uf_ex, 0.55), ("incl-t >0.55", uf_in, 0.55)]:
    q = (uf > th)
    frac = (q.sum(axis=1) / uf.notna().sum(axis=1).replace(0, np.nan))
    frac = frac[frac.index >= "2006-01-03"]
    print(f"census {name}: mean {frac.mean():.1%}  max {frac.max():.1%}  min {frac.min():.1%}")

# empirical up-day prob and binomial expectation
pos = (R > 0).astype(float).where(R.notna())
p_up = float(np.nanmean(pos.values))
from math import comb
def binom_tail(n, p, kmin):
    return sum(comb(n, k) * p**k * (1-p)**(n-k) for k in range(kmin, n+1))
print(f"empirical P(up day) = {p_up:.4f}")
print(f"binomial P(>=38/63 | p) [>0.60 strict] = {binom_tail(63, p_up, 38):.1%}")
print(f"binomial P(>=35/63 | p) [>0.55 strict] = {binom_tail(63, p_up, 35):.1%}")
# threshold needed for ~35% qualify:
for kmin in (34, 35, 36, 37):
    print(f"  P(>= {kmin}/63) = {binom_tail(63, p_up, kmin):.1%}  (threshold {kmin/63:.3f})")

# ---------- ladder rungs, independent ---------------------------------------
reg60_ex = uf_ex > 0.60
E_L0 = edge_matrix(P_div, -1, reg60_ex)
W_L0, st_L0 = weights_rowwise(E_L0)
E_raw = edge_matrix(P_raw, -1, reg60_ex)
W_raw, st_raw = weights_rowwise(E_raw)

L0, ge0 = portfolio(W_L0, Rv, 1, 0.00006)       # same-close fill
L1b, _ = portfolio(W_raw, Rv, 2, 0.00006)       # t+1-close fill
L2, ge2 = portfolio(W_raw, Rv, 2, 0.00035)      # honest + 3.5bp
print("\nqualifier-day stats (adj signal, 0.60 excl-t):", st_L0)
print("L0  full:", met(L0), " 2010/15/20:", met(L0, [2010, 2015, 2020]))
print("L1b full:", met(L1b))
print("L2  full:", met(L2), " 2010/15/20:", met(L2, [2010, 2015, 2020]))

flat = (ge2 < 1e-9)
print(f"L2 flat-book days: {int(flat.sum())} of {len(ge2)}")
L2x = L2[~flat.reindex(L2.index).fillna(False)]
print("L2 excluding flat days:", met(L2x))

# turnover, my measure (one-sided = sum|dW|/2)
dW = np.abs(np.diff(W_raw, axis=0)).sum(axis=1)
print(f"avg daily sum|dW| (two-sided) = {dW[520:].mean():.2f}, one-sided = {dW[520:].mean()/2:.2f}")

# ---------- fingerprint D4 + neighbours (Attack D) ---------------------------
reg55_in = uf_in > 0.55
reg60_in = uf_in > 0.60
variants = [
    ("D4  momentum sign, SAME-DAY, 0.55 incl-t", P_div, +1, reg55_in, 0),
    ("V1  reversal (spec sign), SAME-DAY, 0.55 incl-t", P_div, -1, reg55_in, 0),
    ("V2  reversal, SAME-DAY, 0.60 incl-t", P_div, -1, reg60_in, 0),
    ("V3  momentum, SAME-DAY, 0.60 incl-t", P_div, +1, reg60_in, 0),
    ("V4  momentum, SAME-DAY, 0.55 excl-t regime", P_div, +1, uf_ex > 0.55, 0),
    ("V5  momentum, honest same-close (R_{t+1}), 0.55", P_div, +1, reg55_in, 1),
    ("V6  momentum, t+1 fill (R_{t+2}), 0.55", P_div, +1, reg55_in, 2),
]
print("\n--- fingerprint family (cost 0.6bp) ---")
for name, Psig, sign, mask, k in variants:
    E = edge_matrix(Psig, sign, mask)
    W, _ = weights_rowwise(E)
    r, _ = portfolio(W, Rv, k, 0.00006)
    print(f"{name}: {met(r)}")
