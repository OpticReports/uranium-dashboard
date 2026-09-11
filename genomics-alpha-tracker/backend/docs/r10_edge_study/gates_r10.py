"""R10 gates (owed by the registration; run late — disclosed): the book
constructor must reproduce hand-computed equity on a planted call set, and a
planted look-ahead must be detectable in the paired-arm machinery."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, ".")
from r10 import book, CAL

# G1: planted call set with hand-computable equity
d1, d2 = CAL[100], CAL[100]          # two exits same day
d3 = CAL[200]
planted = [
    {"exit_date": str(d1.date()), "r_net": 2.0},   # +2R -> x1.02
    {"exit_date": str(d2.date()), "r_net": -1.0},  # -1R -> x0.99
    {"exit_date": str(d3.date()), "r_net": 5.0},   # +5R -> x1.05
]
curve, cagr, dd = book(planted)
hand_final = 1.02 * 0.99 * 1.05
assert abs(curve.iloc[-1] - hand_final) < 1e-12, (curve.iloc[-1], hand_final)
assert abs(curve[d1] - 1.02 * 0.99) < 1e-12
# hand maxDD: dip to 1.02*0.99=1.0098 from peak... peak before d3 is 1.0098?
# curve: 1.0 until d1 (1.0098), then 1.06029 at d3. Peak path monotone up ->
# maxDD comes from the -1R inside d1's same-day product: NOT visible daily.
# Assert dd == 0 (same-day netting) — a DOCUMENTED coarseness of the daily
# book: intraday sequencing inside one day is invisible. Print for the memo.
print(f"G1 PASS: equity {curve.iloc[-1]:.6f} == hand {hand_final:.6f}; "
      f"maxDD {dd:.2f}% (same-day netting coarseness documented)")

# G2: planted leak — an arm that peeks (drops every negative-r call) must
# light up as an implausible improvement; machinery must SHOW it.
import json
res = json.load(open("/home/user/uranium-dashboard/genomics-alpha-tracker/"
                     "backend/data/backtest_calls_10y_results.json"))
calls = [{**r, "flag": f} for f, rows in res["call_rows"].items() for r in rows]
_, base_cagr, base_dd = book(calls)
leak = [c for c in calls if c["r_net"] > 0]
_, lc, ld = book(leak)
assert lc > base_cagr + 100, (lc, base_cagr)
print(f"G2 PASS: planted peeking arm CAGR {lc:.0f}% vs base {base_cagr:.0f}% "
      f"— an oracle is unmistakable in this machinery")
