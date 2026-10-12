import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
import numpy as np, pandas as pd
px = pd.read_parquet(HERE / "prices.parquet")
T0, T1 = pd.Timestamp("2025-10-09"), pd.Timestamp("2026-10-09")
ev = json.load(open(HERE / "events.json"))
w = px.loc[T0:T1]
print("rows in window (incl t0):", len(w), "first", w.index[0].date(), "last", w.index[-1].date())
print("NaNs in window:", int(w.isna().sum().sum()))
for t in sorted(set(px.columns.get_level_values(1))):
    ya, fa = w[("yahoo", t)], w[("fmp", t)]
    ry, rf = ya.pct_change().dropna(), fa.pct_change().dropna()
    d = (ry - rf).abs()
    tr_y, tr_f = ya.iloc[-1] / ya.iloc[0] - 1, fa.iloc[-1] / fa.iloc[0] - 1
    big = d[d > 0.005]
    print(f"{t:5s} TR yahoo {tr_y:+.4%}  fmp {tr_f:+.4%}  diff {tr_y-tr_f:+.4%}  max|dret| {d.max()*1e4:6.1f}bp  >50bp days: {[(str(k.date()), round(v*1e4,1)) for k,v in big.items()]}")
print()
for t, e in ev.items():
    inwin = {k: [x for x in v if "2025-10-10" <= x["date"] <= "2026-10-09"] for k, v in e.items()}
    print(t, json.dumps(inwin))
