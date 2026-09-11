"""DIAGNOSTIC (labeled; registration defect disclosed): the registered
uncapped book is leverage fiction (100+ concurrent 1R calls). Re-rank the
arms under the production replay's own max_open-capped sequential book
(equity_curve(max_open=10), the replay's published convention) with
compounded 1% risk. Ship decisions remain governed by the registered test."""
import json, sys
import numpy as np
import pandas as pd
sys.path.insert(0, "/home/user/uranium-dashboard/genomics-alpha-tracker/backend")
from scripts.backtest_calls_10y import equity_curve
sys.path.insert(0, ".")
from r10 import arm_calls, calls, CAL          # reuse the harness objects

def capped_book(callset, max_open=10):
    _, taken = equity_curve(callset, max_open=max_open)
    eq = 1.0
    mult = {}
    for c in taken:
        xd = pd.Timestamp(c["exit_date"])
        mult[xd] = mult.get(xd, 1.0) * (1.0 + 0.01 * c["r_net"])
    m = pd.Series(mult).reindex(CAL).fillna(1.0).cumprod()
    dd = (m / m.cummax() - 1).min()
    yrs = (CAL[-1] - CAL[0]).days / 365.25
    return m.iloc[-1] ** (1 / yrs) - 1, dd, len(taken)

bc, bd, bn = capped_book(calls)
print(f"DIAG capped baseline: CAGR {bc*100:.2f}%  maxDD {bd*100:.2f}%  taken {bn}")
for a in ("A1a", "A2v", "A4b", "A5"):
    cs = arm_calls(a)
    c_, d_, n_ = capped_book(cs)
    print(f"DIAG {a}: CAGR {c_*100:+.2f}%  maxDD {d_*100:.2f}%  taken {n_}  "
          f"dCAGR {(c_-bc)*100:+.2f}pp  dDD {(d_-bd)*100:+.2f}pp")
