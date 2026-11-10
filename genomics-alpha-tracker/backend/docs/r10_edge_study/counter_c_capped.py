"""COUNTER-AGENT audit A(capped) — reproduce the max_open=10 diagnostic and
decompose the A1a delta into (gated calls dropped) vs (slot reshuffle:
crowd-out and replacement admissions). Independent: no r10 import.

RESULT (as run 2026-09-04):
[G1'] base 7.44%/-57.69% taken 1143 | A1a 9.69%/-56.46% taken 1125
      dCAGR +2.25pp dDD +1.23pp            <- reproduces diag_capped.py
[G2'] only-in-base 101 (gated 23, crowd-out 78); replacements 83
[G3'] log-equity: -gated +0.0000  -crowdout -0.0631  +replacements +0.2886
[G5'] sum r_net: gated dropped +0.1R, crowd-out +7.1R, replacements +29.6R
=> the ENTIRE capped dCAGR is slot reshuffle; the gate's own trades in the
   capped base book were 23 calls summing +0.1R (nil)."""
import json
import math
import sys

import numpy as np
import pandas as pd

BACKEND = "/home/user/uranium-dashboard/genomics-alpha-tracker/backend"
sys.path.insert(0, BACKEND)
from scripts.backtest_calls_10y import equity_curve  # noqa: E402

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad/r10"
raw = json.load(open(f"{BACKEND}/data/backtest_bars.json"))
res = json.load(open(f"{BACKEND}/data/backtest_calls_10y_results.json"))
panel = pd.read_csv(f"{SC}/../r9/panel.csv", parse_dates=["date"])
mcap = panel.set_index(["date", "symbol"])["z1_mktcap"].sort_index()
CAT = {"quiet_before_catalyst", "pullback_into_catalyst",
       "binary_event_within_n_days"}
calls = [{**r, "flag": f} for f, rows in res["call_rows"].items() for r in rows]
xbi = pd.DataFrame(raw["XBI"]).assign(date=lambda d: pd.to_datetime(d["date"])) \
    .set_index("date")["adj_close"]
CAL = xbi.index
yrs = (CAL[-1] - CAL[0]).days / 365.25

cache = {}
def pm(sym, d):
    k = (sym, d)
    if k in cache:
        return cache[k]
    try:
        s = mcap.loc[(slice(None), sym)]
        s = s[s.index <= d]
        v = float(s.iloc[-1]) if len(s) and not np.isnan(s.iloc[-1]) else np.nan
    except KeyError:
        v = np.nan
    cache[k] = v
    return v

kept = [c for c in calls
        if not (c["flag"] in CAT
                and (lambda z: not np.isnan(z) and z < 1e9)(
                    pm(c["symbol"], pd.Timestamp(c["fire_date"]))))]

def capped(cs):
    _, taken = equity_curve(cs, max_open=10)
    mult = {}
    for c in taken:
        d = pd.Timestamp(c["exit_date"])
        mult[d] = mult.get(d, 1.0) * (1 + 0.01 * c["r_net"])
    m = pd.Series(mult).reindex(CAL).fillna(1.0).cumprod()
    return m.iloc[-1] ** (1 / yrs) - 1, (m / m.cummax() - 1).min(), taken

bc, bd, bt = capped(calls)
ac, ad, at = capped(kept)
print(f"[G1'] base {bc*100:.2f}%/{bd*100:.2f}% taken {len(bt)} | "
      f"A1a {ac*100:.2f}%/{ad*100:.2f}% taken {len(at)} "
      f"dCAGR {(ac-bc)*100:+.2f}pp dDD {(ad-bd)*100:+.2f}pp")
key = lambda c: (c["symbol"], c["entry_date"], c["flag"], c["exit_date"])
bs = {key(c): c for c in bt}
as_ = {key(c): c for c in at}
gated = {key(c) for c in calls} - {key(c) for c in kept}
only_b = [c for k, c in bs.items() if k not in as_]
only_a = [c for k, c in as_.items() if k not in bs]
gb = [c for c in only_b if key(c) in gated]
cb = [c for c in only_b if key(c) not in gated]
lg = sum(math.log1p(0.01 * c["r_net"]) for c in gb)
lc = sum(math.log1p(0.01 * c["r_net"]) for c in cb)
la = sum(math.log1p(0.01 * c["r_net"]) for c in only_a)
print(f"[G2'] only-in-base {len(only_b)} (gated {len(gb)}, crowd-out {len(cb)}); "
      f"replacements only-in-arm {len(only_a)}")
print(f"[G3'] log-equity: -gated {-lg:+.4f}  -crowdout {-lc:+.4f}  "
      f"+replacements {la:+.4f}  total {la-lg-lc:+.4f}")
print(f"[G5'] sum r_net: gated dropped {sum(c['r_net'] for c in gb):+.1f}R, "
      f"crowd-out {sum(c['r_net'] for c in cb):+.1f}R, "
      f"replacements {sum(c['r_net'] for c in only_a):+.1f}R")
