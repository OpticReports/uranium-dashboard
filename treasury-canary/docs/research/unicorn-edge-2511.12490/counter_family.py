"""COUNTER-AGENT: fingerprint-family breadth, randomization tension, position
counts, turnover, and stale-output checks. Uses my independent builders."""
import numpy as np
import pandas as pd
from counter_indep import (P_div, R, Rv, dates, upfrac_matrix, edge_matrix,
                           weights_rowwise, portfolio, met)

uf_in = upfrac_matrix(include_t=True)
reg55 = uf_in > 0.55

def run_edge(E, k, name, cost=0.00006):
    W, _ = weights_rowwise(E)
    r, _ = portfolio(W, Rv, k, cost)
    print(f"{name}: full {met(r)}")
    return W, r

# D4 on the paper's three windows
E_d4 = edge_matrix(P_div, +1, reg55)
W_d4, r_d4 = run_edge(E_d4, 0, "D4 momentum+same-day 0.55")
print("   D4 on 2010/15/20:", met(r_d4, [2010, 2015, 2020]))
print("   D4 mean daily %:", round(r_d4.mean() * 100, 3),
      " winning days:", f"{(r_d4 > 0).mean():.0%}")

# full-base inversion (long/short buckets swapped) + same-day
inv = 1.0 / P_div
vrank = inv.rank(axis=1, pct=True)
mom = P_div / P_div.shift(10) - 1.0
mz = mom.sub(mom.mean(axis=1), axis=0).div(mom.std(axis=1), axis=0)
base_spec = 0.7 * vrank + 0.3 * (-mz)
run_edge((-base_spec).where(reg55), 0, "V7 buckets inverted (-BASE), same-day 0.55")

# component pieces under same-day (context vs paper Table 8)
run_edge(vrank.where(reg55), 0, "V8 value-only, same-day 0.55")
run_edge(mz.where(reg55), 0, "V9 momentum-z only, same-day 0.55")
run_edge((-mz).where(reg55), 0, "V10 reversal-z only, same-day 0.55")

# RANDOM regime (30% of stock-days), momentum sign, same-day — tension with
# the paper's claim that 1000 random regime filters max out at Sharpe 1.89
rng = np.random.default_rng(0)
for trial in range(3):
    mask = pd.DataFrame(rng.random(P_div.shape) < 0.30,
                        index=dates, columns=P_div.columns) & P_div.notna()
    run_edge(edge_matrix(P_div, +1, mask), 0, f"V11.{trial} RANDOM 30% regime, momentum, same-day")
# and the honest-spec signal under same-day with random regime (their D2 analog)
mask = pd.DataFrame(rng.random(P_div.shape) < 0.30,
                    index=dates, columns=P_div.columns) & P_div.notna()
run_edge(edge_matrix(P_div, -1, mask), 0, "V12 RANDOM 30% regime, reversal, same-day")

# position counts + turnover for D4 (paper: 187L/189S, turnover 42%)
nz = (np.abs(W_d4) > 1e-12)
longs = (W_d4 > 1e-12).sum(axis=1)
shorts = (W_d4 < -1e-12).sum(axis=1)
sel = np.array([d >= pd.Timestamp("2006-01-03") for d in dates])
print(f"\nD4 avg positions: long {longs[sel].mean():.0f}, short {shorts[sel].mean():.0f}")
dW = np.abs(np.diff(W_d4, axis=0)).sum(axis=1)
print(f"D4 turnover sum|dW| two-sided {dW[520:].mean():.2f} one-sided {dW[520:].mean()/2:.2f}")
q55 = reg55.sum(axis=1)
q55 = q55[q55.index >= "2006-01-03"]
print(f"qualifiers/day at 0.55: mean {q55.mean():.0f}; at 0.60: ", end="")
q60 = (upfrac_matrix(False) > 0.60).sum(axis=1)
print(f"{q60[q60.index >= '2006-01-03'].mean():.0f}")

# committed ret files vs fresh: are L0/L2 stale too?
for f, lag_cost in [("ret_L0.csv", None), ("ret_L2.csv", None)]:
    ser = pd.read_csv(f, parse_dates=["date"], index_col="date").iloc[:, 0]
    print(f"{f}: n={len(ser)}, committed full Sharpe "
          f"{ser.mean()/ser.std()*np.sqrt(252):.2f}")
