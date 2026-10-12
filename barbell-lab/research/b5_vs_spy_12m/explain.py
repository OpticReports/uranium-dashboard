import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
import numpy as np, pandas as pd
px = pd.read_parquet(HERE / "prices.parquet")["yahoo"].loc["2025-10-09":"2026-10-09"]
r = px.pct_change().iloc[1:]
m = ((1 + r).groupby(r.index.to_period("M")).prod() - 1) * 100
print(m[["AVUV","AVDV","PHYS","KMLM","AVEM","QUAL","TAIL","SPY"]].round(1).to_string())
res = json.load(open(HERE / "results.json"))["primary"]
b = pd.Series(res["B5_v1.0_TAIL_bands"]["daily_returns"]); s = pd.Series(res["SPY"]["daily_returns"])
d = b - s
te = d.std(ddof=1) * np.sqrt(252)
print(f"\ntracking error (ann, daily) {te:.2%}; excess {res['B5_v1.0_TAIL_bands']['excess_vs_spy']:+.2%}; IR ~ {res['B5_v1.0_TAIL_bands']['excess_vs_spy']/te:.2f}")
# sub-period: start -> lead peak, lead peak -> end
wb = (1 + b).cumprod(); ws = (1 + s).cumprod()
wb.index = ws.index = pd.to_datetime(wb.index)
pk = pd.Timestamp("2026-03-02")
print(f"to {pk.date()}: B5 {wb[pk]-1:+.2%} SPY {ws[pk]-1:+.2%}")
print(f"{pk.date()} -> end: B5 {wb.iloc[-1]/wb[pk]-1:+.2%} SPY {ws.iloc[-1]/ws[pk]-1:+.2%}")
# PHYS path
ph = px["PHYS"] / px["PHYS"].iloc[0] - 1
print(f"PHYS peak {ph.max():+.1%} on {ph.idxmax().date()}, end {ph.iloc[-1]:+.1%}; trough after peak {ph.loc[ph.idxmax():].min():+.1%} on {ph.loc[ph.idxmax():].idxmin().date()}")
print("month-end weights at rebalance:", res["B5_v1.0_TAIL_bands"]["month_end_weights"]["2026-05-29"])
