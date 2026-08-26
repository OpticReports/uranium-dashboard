"""COUNTER-AGENT Attack A: prove run()/perf() alignment by construction on a
hand-computable synthetic panel. Independent of replicate.py internals: we
re-express the pipeline formulas verbatim and check each output cell against
loop-computed ground truth."""
import numpy as np
import pandas as pd

dates = pd.bdate_range("2020-01-01", periods=10)
# 3 stocks, deterministic prices (hand-checkable)
P = pd.DataFrame({
    "X": [100, 101, 103, 102, 105, 104, 108, 107, 110, 111],
    "Y": [50, 49, 50, 52, 51, 53, 52, 54, 55, 53],
    "Z": [200, 202, 199, 203, 205, 204, 208, 210, 207, 212],
}, index=dates, dtype=float)
R = P.pct_change(fill_method=None)

# arbitrary weights, set to distinct recognizable values per day
rng = np.random.default_rng(7)
w = pd.DataFrame(rng.normal(size=P.shape), index=dates, columns=P.columns)

# --- replicate.py run() gross, verbatim formula ---
def run_gross(w, R, lag):
    wl = w.shift(lag)
    return (wl * R.shift(-1)).sum(axis=1).shift(1)

# ground truth by explicit loop: candidate conventions
def truth(w, R, k):
    """series where value at date t equals sum_i w[t-k, i] * R[t, i]
       i.e. weights formed k days before the return day earn that day."""
    out = pd.Series(np.nan, index=dates)
    for ti in range(len(dates)):
        if ti - k < 0:
            continue
        out.iloc[ti] = np.nansum(w.iloc[ti - k].values * R.iloc[ti].values)
    return out

g0 = run_gross(w, R, 0)
g1 = run_gross(w, R, 1)
t1 = truth(w, R, 1)   # w_{t-1} earns R_t  == w_t earns R_{t+1}   (same-close fill)
t2 = truth(w, R, 2)   # w_{t-2} earns R_t  == w_t earns R_{t+2}   (t+1-close fill)
t0 = truth(w, R, 0)   # w_t earns R_t      (the look-ahead bug)

def close(a, b):
    m = a.notna() & b.notna()
    return m.sum(), bool(np.allclose(a[m], b[m]))

print("run(lag=0) == [w_t earns R_{t+1}] :", close(g0, t1))
print("run(lag=0) == [w_t earns R_t]     :", close(g0, t0))
print("run(lag=0) == [w_t earns R_{t+2}] :", close(g0, t2))
print("run(lag=1) == [w_t earns R_{t+2}] :", close(g1, t2))
print("run(lag=1) == [w_t earns R_{t+1}] :", close(g1, t1))

# --- diagnose.py perf() formulas, verbatim ---
same_day = (w * R).sum(axis=1)
honest = (w * R.shift(-1)).sum(axis=1).shift(1)
print("perf same_day == [w_t earns R_t]     :", close(same_day, t0))
print("perf honest   == [w_t earns R_{t+1}] :", close(honest, t1))

# --- cost alignment in run(): cost at t matches the trade INTO the weights
# earning gross at t? gross at t (lag=0) = w_{t-1}*R_t; trade into w_{t-1}
# happened at close t-1 with turnover |w_{t-1}-w_{t-2}|.
wl = w.shift(0)
to = (wl - wl.shift(1)).abs().sum(axis=1)
cost_at_t = to.shift(1)
manual = (w.shift(1) - w.shift(2)).abs().sum(axis=1)
m = cost_at_t.notna() & manual.notna()
print("cost booked at t == |w_{t-1}-w_{t-2}| :", bool(np.allclose(cost_at_t[m], manual[m])))

# --- NaN semantics: does .sum(axis=1) over all-NaN row create phantom 0?
Rn = R.copy(); Rn.iloc[4] = np.nan
g = (w * Rn.shift(-1)).sum(axis=1)
print("all-NaN return row sums to (pandas .sum skipna default):", g.iloc[3])
