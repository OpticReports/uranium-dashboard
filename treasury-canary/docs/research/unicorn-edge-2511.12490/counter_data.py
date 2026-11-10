"""COUNTER-AGENT: sensitivity probes + raw data integrity checks."""
import numpy as np
import pandas as pd
from counter_indep import (P_div, P_raw, R, Rv, dates, upfrac_matrix,
                           edge_matrix, weights_rowwise, portfolio, met)

uf_in = upfrac_matrix(include_t=True)

# --- paper Table 6 probe: does the bug survive threshold 0.42 / no gate? ---
for th in (0.42, None):
    mask = (uf_in > th) if th is not None else P_div.notna()
    E = edge_matrix(P_div, +1, mask)
    W, _ = weights_rowwise(E)
    r, _ = portfolio(W, Rv, 0, 0.00006)
    print(f"momentum+same-day, gate {th}: {met(r)}")

# --- per-year spot recompute (independent code) vs per_year_sharpe.csv ------
reg60_ex = upfrac_matrix(include_t=False) > 0.60
E_L0 = edge_matrix(P_div, -1, reg60_ex)
W_L0, _ = weights_rowwise(E_L0)
L0, _ = portfolio(W_L0, Rv, 1, 0.00006)
E_raw = edge_matrix(P_raw, -1, reg60_ex)
W_raw, _ = weights_rowwise(E_raw)
L2, _ = portfolio(W_raw, Rv, 2, 0.00035)
for yr in (2008, 2015, 2021, 2023):
    a = L0[L0.index.year == yr]; b = L2[L2.index.year == yr]
    print(f"{yr}: my L0 {a.mean()/a.std()*np.sqrt(252):.1f}  my L2 {b.mean()/b.std()*np.sqrt(252):.1f}")

# committed ret_L0 vs my independent series, elementwise
com = pd.read_csv("ret_L0.csv", parse_dates=["date"], index_col="date").iloc[:, 0]
al = pd.concat([com, L0], axis=1, join="inner")
print("ret_L0.csv vs mine: n_overlap", len(al), "max|diff|", float((al.iloc[:,0]-al.iloc[:,1]).abs().max()))

# --- |R|>=1 guard census ----------------------------------------------------
Rug = P_div.pct_change(fill_method=None)
hits = Rug.abs() >= 1.0
for c in hits.columns[hits.any()]:
    for d in Rug.index[hits[c]]:
        print("guard-hit:", c, d.date(), round(float(Rug.loc[d, c]), 3))

# --- split / dividend verification -----------------------------------------
def around(panel, sym, date, n=2):
    s = panel[sym].dropna()
    i = s.index.get_indexer([pd.Timestamp(date)], method="nearest")[0]
    return s.iloc[max(0, i - n):i + n + 1]

import glob, os
P_fullc = {}
for sym in ("AAPL", "NVDA", "TSLA"):
    P_fullc[sym] = pd.read_csv(f"prices_full/{sym}.csv", parse_dates=["date"]).set_index("date")

print("\nAAPL 7:1 split 2014-06-09  raw:", around(P_raw, "AAPL", "2014-06-09").round(2).to_dict())
print("AAPL div-adj same dates:", around(P_div, "AAPL", "2014-06-09").round(3).to_dict())
print("NVDA 10:1 split 2024-06-10 raw:", around(P_raw, "NVDA", "2024-06-10").round(2).to_dict())
print("NVDA div-adj:", around(P_div, "NVDA", "2024-06-10").round(3).to_dict())
print("TSLA 5:1 split 2020-08-31  raw:", around(P_raw, "TSLA", "2020-08-31").round(2).to_dict())

# raw/div ratio stability for AAPL: big jumps only at split or dividend dates
ratio = (P_raw["AAPL"] / P_div["AAPL"]).dropna()
jumps = ratio.pct_change().abs()
print("\nAAPL raw/div ratio jump days >2%:", [(d.date(), round(float(ratio.pct_change().loc[d]), 3)) for d in jumps.index[jumps > 0.02]])
# dividend visibility: ex-div dates should move ratio by ~div yield (<2%)
small = jumps[(jumps > 0.001) & (jumps < 0.02)]
print("AAPL 0.1-2% ratio steps (ex-div dates), count:", len(small), "first few:",
      [(d.date(), round(float(small.loc[d]), 4)) for d in small.index[:4]])

# prices_full close vs div-adj close on last day (should match ex-dividends)
a = P_fullc["AAPL"]["close"]
print("\nAAPL prices_full close 2024-12-30:", float(a.loc["2024-12-30"]),
      " div-adj:", float(P_div["AAPL"].loc["2024-12-30"]),
      " raw:", float(P_raw["AAPL"].loc["2024-12-30"]))
