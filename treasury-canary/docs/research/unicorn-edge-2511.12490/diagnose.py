"""POST-HOC DIAGNOSTICS (labeled as such; not the registered ladder):
which implementation bug manufactures the paper's 13-Sharpe? Each candidate
is a plausible one-line coding error in a naive pandas backtest."""
import os
import numpy as np
import pandas as pd
from replicate import load_panel, build_weights, metrics

SC = os.path.dirname(os.path.abspath(__file__))
P = load_panel("prices_div", "adjClose")
R = P.pct_change(fill_method=None)
R = R.where(R.abs() < 1.0)

def signals(thresh=0.60, include_t=False, zero_pos=False):
    value_rank = (1.0 / P).rank(axis=1, pct=True)
    rev = -(P / P.shift(10) - 1.0)
    rev_z = rev.sub(rev.mean(axis=1), axis=0).div(rev.std(axis=1), axis=0)
    base = 0.7 * value_rank + 0.3 * rev_z
    pos = (R >= 0) if zero_pos else (R > 0)
    pos = pos.astype(float).where(R.notna())
    up = pos.rolling(63, min_periods=63).mean() if include_t else \
         pos.shift(1).rolling(63, min_periods=63).mean()
    return base.where(up > thresh), (up > thresh)

def perf(w, align, cost=0.00006):
    if align == "same_day":            # w_t earns R_t — the look-ahead bug
        gross = (w * R).sum(axis=1)
    elif align == "honest":            # w_t earns R_{t+1}
        gross = (w * R.shift(-1)).sum(axis=1).shift(1)
    to = (w - w.shift(1)).abs().sum(axis=1)
    net = (gross - to.shift(1).fillna(0.0) * cost).dropna()
    return net[net.index >= "2006-01-03"]

rows = []
for name, thresh, inc_t, zpos, align in [
    ("D0 control: honest align, >0.60",          0.60, False, False, "honest"),
    ("D1 regime includes day t, honest align",   0.60, True,  False, "honest"),
    ("D2 SAME-DAY RETURN (w_t x R_t), >0.60",    0.60, True,  False, "same_day"),
    ("D2b same-day, thresh>0.55 (census~theirs)", 0.55, True,  False, "same_day"),
    ("D2c same-day, r>=0 counts positive",       0.60, True,  True,  "same_day"),
    ("D3 honest align, thresh>0.55",             0.55, False, False, "honest"),
]:
    edge, reg = signals(thresh, inc_t, zpos)
    w = build_weights(edge)
    net = perf(w, align)
    m = metrics(net, "2006-2024")
    census = (reg.sum(axis=1) / reg.notna().sum(axis=1).replace(0, np.nan)).mean()
    m.update({"diag": name, "census": f"{census:.0%}"})
    rows.append(m)
    m3 = metrics(net, "2010/15/20", years=[2010, 2015, 2020])
    rows.append({**m3, "diag": "   ... windows 2010/2015/2020", "census": ""})
print(pd.DataFrame(rows)[["diag", "census", "window", "sharpe", "ann_ret_arith",
                          "vol", "maxDD", "median_daily"]].to_string(index=False))

print("\n=== positive-sign look-ahead candidates ===")
rows2 = []
value_rank = (1.0 / P).rank(axis=1, pct=True)
pos = (R > 0).astype(float).where(R.notna())
up_inc = pos.rolling(63, min_periods=63).mean()

def build_and_run(rev_component, regime_mask, align, name, cost=0.00006):
    rev_z = rev_component.sub(rev_component.mean(axis=1), axis=0) \
                         .div(rev_component.std(axis=1), axis=0)
    base = 0.7 * value_rank + 0.3 * rev_z
    w = build_weights(base.where(regime_mask))
    net = perf(w, align, cost)
    m = metrics(net, "2006-2024")
    m["diag"] = name
    rows2.append(m)

# sign bug: momentum instead of reversal (forgot the minus), same-day earn
build_and_run(+(P / P.shift(10) - 1.0), up_inc > 0.55, "same_day",
              "D4 sign bug (+10d ret), same-day, >0.55")
# forward window: reversal of the NEXT 10 days (shift direction bug), honest
build_and_run(-(P.shift(-10) / P - 1.0), up_inc > 0.55, "honest",
              "D5 forward-window reversal, honest align, >0.55")
# one-day future leak in reversal window only
build_and_run(-(P.shift(-1) / P.shift(9) - 1.0), up_inc > 0.55, "honest",
              "D6 one-day future leak in reversal, >0.55")
print(pd.DataFrame(rows2)[["diag", "sharpe", "ann_ret_arith", "vol",
                           "maxDD", "median_daily"]].to_string(index=False))
