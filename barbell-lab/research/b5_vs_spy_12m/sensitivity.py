"""Robustness numbers added after the counter-agent review (MINOR-1/3/4/5).

  * start-date shift: buy close moved +-2 weeks, mark fixed at 2026-10-09;
  * end-date shift: trailing-12m excess for each of the last 28 sessions;
  * spliced history: the older thesis-page weights until v1.0's adoption
    (register: v1.0 LIVE, adopted 2026-07-17), then v1.0 — switch trades
    only the difference, at platform costs;
  * each drawdown measured over the other series' drawdown window;
  * beta at daily / weekly / monthly frequency.
usage: python -I sensitivity.py   (reads prices.parquet next to this file)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from barbell.backtest.engine import resolve_targets, simulate
from barbell.config import load

HERE = Path(__file__).resolve().parent
px = pd.read_parquet(HERE / "prices.parquet")["yahoo"]
R = px.pct_change()
V10 = resolve_targets("TAIL")
OLD = {"AVUV": .23, "PHYS": .18, "AVDV": .16, "KMLM": .14, "AVEM": .13, "MTUM": .08, "QUAL": .05, "BIL": .03}
BAND = float(load("backtest")["rebalance"]["band_relative"])
COSTS = load("backtest")["costs_bps"]


def excess(t0, t1, targets=V10):
    r = R.loc[t0:t1].iloc[1:]
    b = (1 + simulate(r, targets, mode="threshold").returns).prod()
    s = (1 + simulate(r, {"SPY": 1.0}, mode="none").returns).prod()
    return float(b - 1), float(s - 1), float(b - s)


def spliced(t0, switch, t1, a, b):
    """Daily path under weights `a` until the `switch` close, then `b`.
    Same rules as engine.simulate (entry cost on 100%, +-band checked at the
    calendar month-ends of the full window); the switch pays cost only on
    the traded difference."""
    r = R.loc[t0:t1].iloc[1:]
    tk = sorted(set(a) | set(b))
    c = np.array([float(COSTS.get(t, COSTS["default"])) * 1e-4 for t in tk])
    vec = lambda tg: np.array([tg.get(t, 0.0) for t in tk])
    wt = vec(a)
    h = wt * (1 - c)
    month_ends = set(r.groupby(r.index.to_period("M")).apply(lambda g: g.index.max()))
    for dt, row in zip(r.index, r[tk].values):
        h = h * (1 + row)
        W = h.sum()
        live = wt > 0
        if dt in month_ends and (np.abs((h / W)[live] / wt[live] - 1) > BAND).any():
            W -= float(np.abs(wt * W - h) @ c)
            h = wt * W
        if dt == pd.Timestamp(switch):
            wt = vec(b)
            W -= float(np.abs(wt * W - h) @ c)
            h = wt * W
    return float(h.sum() - 1)


out = {}
# validate the splice engine against simulate() on an unspliced path
for tg in (V10, OLD):
    ref = excess("2025-10-09", "2026-10-09", tg)[0]
    mine = spliced("2025-10-09", "1900-01-01", "2026-10-09", tg, tg)
    assert abs(ref - mine) < 1e-6, (ref, mine)

days = R.loc["2025-09-25":"2025-10-23"].index
out["start_shift"] = {str(d.date()): round(excess(d, "2026-10-09")[2] * 100, 2) for d in days}
ends = R.loc[:"2026-10-09"].index[-28:]
es = {}
for e in ends:
    s0 = R.loc[:e - pd.DateOffset(years=1)].index[-1]
    es[str(e.date())] = round(excess(s0, e)[2] * 100, 2)
out["end_shift_last28"] = es
spy = excess("2025-10-09", "2026-10-09")[1]
sp = spliced("2025-10-09", "2026-07-17", "2026-10-09", OLD, V10)
out["spliced_old_until_2026-07-17_then_v1.0"] = {"b5": round(sp * 100, 2), "spy": round(spy * 100, 2),
                                                  "excess_pp": round((sp - spy) * 100, 2)}
res = json.load(open(HERE / "results.json"))["primary"]
b = pd.Series(res["B5_v1.0_TAIL_bands"]["daily_returns"]); s = pd.Series(res["SPY"]["daily_returns"])
b.index = s.index = pd.to_datetime(b.index)
wb, ws = (1 + b).cumprod(), (1 + s).cumprod()
wb0 = pd.concat([pd.Series([1.0], [pd.Timestamp("2025-10-09")]), wb])
ws0 = pd.concat([pd.Series([1.0], [pd.Timestamp("2025-10-09")]), ws])
win = lambda w, a, z: round((w[z] / w[a] - 1) * 100, 2)
out["b5_over_spy_dd_window_0127_0330"] = win(wb0, "2026-01-27", "2026-03-30")
out["spy_over_b5_dd_window_0302_0320"] = win(ws0, "2026-03-02", "2026-03-20")
beta = {}
for name, rule in (("daily", None), ("weekly_fri", "W-FRI"), ("monthly", "ME")):
    if rule:
        x, y = wb0.resample(rule).last().pct_change().dropna(), ws0.resample(rule).last().pct_change().dropna()
    else:
        x, y = b, s
    cv = np.cov(x, y, ddof=1)
    beta[name] = {"beta": round(cv[0, 1] / cv[1, 1], 3), "n": len(x)}
out["beta_by_frequency"] = beta
(HERE / "sensitivity.json").write_text(json.dumps(out, indent=1))
ss, ee = list(out["start_shift"].values()), list(es.values())
print("start-shift excess pp: min", min(ss), "max", max(ss), "| 10-09:", out["start_shift"]["2025-10-09"], "10-10:", out["start_shift"]["2025-10-10"])
print(" ", out["start_shift"])
print("end-shift (last 28) pp: min", min(ee), "max", max(ee), "median", float(np.median(ee)))
print("spliced:", out["spliced_old_until_2026-07-17_then_v1.0"])
print("B5 over SPY DD window:", out["b5_over_spy_dd_window_0127_0330"], "| SPY over B5 DD window:", out["spy_over_b5_dd_window_0302_0320"])
print("beta:", beta)
