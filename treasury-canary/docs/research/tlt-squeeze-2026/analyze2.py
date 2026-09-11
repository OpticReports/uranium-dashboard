import os
import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "data")
tlt = pd.read_csv(f"{DATA}/TLT.csv", parse_dates=["date"]).set_index("date")["close"]
dgs30 = pd.read_csv(f"{DATA}/DGS30.csv", parse_dates=["date"]).set_index("date")["DGS30"].dropna()
tp = pd.read_csv(f"{DATA}/THREEFYTP10.csv", parse_dates=["date"]).set_index("date")["THREEFYTP10"].dropna()
move = pd.read_csv(f"{DATA}/MOVE.csv", parse_dates=["date"]).set_index("date")["close"].dropna()

leg = pd.read_csv(f"{DATA}/legacy_cot.csv")
leg["date"] = pd.to_datetime(leg["report_date_as_yyyy_mm_dd"])
for c in ("noncomm_positions_long_all","noncomm_positions_short_all","open_interest_all"):
    leg[c] = pd.to_numeric(leg[c], errors="coerce")
tff = pd.read_csv(f"{DATA}/tff.csv")
tff["date"] = pd.to_datetime(tff["report_date_as_yyyy_mm_dd"])
for c in ("lev_money_positions_long","lev_money_positions_short","open_interest_all"):
    tff[c] = pd.to_numeric(tff[c], errors="coerce")

def agg(df, mkts, lc, sc):
    d = df[df["contract_market_name"].isin(mkts)]
    g = d.groupby("date").agg(long=(lc,"sum"), short=(sc,"sum"), oi=("open_interest_all","sum"))
    g["net_pct_oi"] = 100.0*(g["long"]-g["short"])/g["oi"]
    return g.sort_index()

ALL_UST = ["UST BOND","ULTRA UST BOND","UST 10Y NOTE","ULTRA UST 10Y"]
LONG_END = ["UST BOND","ULTRA UST BOND"]
nc = agg(leg, LONG_END, "noncomm_positions_long_all","noncomm_positions_short_all")
lev = agg(tff, ALL_UST, "lev_money_positions_long","lev_money_positions_short")

def fwd_min_yield_chg(d, days):
    y0s = dgs30[dgs30.index >= d]
    if not len(y0s): return np.nan
    y0 = y0s.iloc[0]
    w = dgs30[(dgs30.index > d) & (dgs30.index <= d + pd.Timedelta(days=days))]
    return 100.0*(w.min() - y0) if len(w) else np.nan

# conditional vs unconditional: P(30y falls >=50/100bp at its 6m best) 
s = nc["net_pct_oi"].dropna()
dec_mask = pd.Series(False, index=s.index)
for i in range(156, len(s)):
    dec_mask.iloc[i] = s.iloc[i] < s.iloc[:i].quantile(0.10)
cond_dates = s.index[dec_mask]
all_dates = s.index[156:]
for label, dates in (("bottom-decile short weeks", cond_dates), ("ALL weeks", all_dates)):
    r = pd.Series([fwd_min_yield_chg(d, 182) for d in dates]).dropna()
    print(f"{label} (n={len(r)}): P(best 6m 30y drop >=50bp) {(r<=-50).mean():.1%}  "
          f">=100bp {(r<=-100).mean():.1%}  median best drop {r.median():+.0f}bp")

# what did the SIGNED 6m outcome look like — shorts right vs squeezed
def fwd_yield_chg(d, days):
    y0s = dgs30[dgs30.index >= d]; 
    if not len(y0s): return np.nan
    w = dgs30[dgs30.index >= d + pd.Timedelta(days=days)]
    return 100.0*(w.iloc[0]-y0s.iloc[0]) if len(w) else np.nan
r_c = pd.Series([fwd_yield_chg(d,182) for d in cond_dates]).dropna()
r_a = pd.Series([fwd_yield_chg(d,182) for d in all_dates]).dropna()
print(f"\nsigned 6m 30y change | bottom-decile: mean {r_c.mean():+.0f}bp, P(down) {(r_c<0).mean():.0%}, n={len(r_c)}")
print(f"signed 6m 30y change | all weeks:     mean {r_a.mean():+.0f}bp, P(down) {(r_a<0).mean():.0%}, n={len(r_a)}")

# ── 2023 anatomy: does COT lead or lag the rally? ───────────────────────────
print("\n=== Oct-Dec 2023 anatomy ===")
ep = lev.loc["2023-06-01":"2024-04-01", "net_pct_oi"]
t = tlt.loc["2023-08-01":"2024-02-01"]
print("TLT trough:", t.idxmin().date(), f"{t.min():.2f}")
print("TLT +10% from trough reached:", t[t.index > t.idxmin()][t[t.index > t.idxmin()] >= t.min()*1.10].index[0].date())
print("lev-fund net%OI, weekly, Sep'23-Feb'24:")
print(ep.loc["2023-09-01":"2024-02-15"].round(1).to_string())

# ── same anatomy for the CURRENT episode: 2026 YTD ──────────────────────────
print("\n=== 2026 YTD state ===")
t26 = tlt.loc["2025-12-31":]
print(f"TLT 2026: start {t26.iloc[0]:.2f} now {t26.iloc[-1]:.2f} ({100*(t26.iloc[-1]/t26.iloc[0]-1):+.1f}%)  "
      f"low {t26.min():.2f} ({t26.idxmin().date()})  high {t26.max():.2f} ({t26.idxmax().date()})")
y26 = dgs30.loc["2025-12-31":]
print(f"30y 2026: start {y26.iloc[0]:.2f} now {y26.iloc[-1]:.2f}  range {y26.min():.2f}-{y26.max():.2f}")
print(f"10y term premium: now {tp.iloc[-1]:+.2f} ({tp.index[-1].date()}), "
      f"percentile since 1990 {100*(tp < tp.iloc[-1]).mean():.0f}%, since 2015 "
      f"{100*(tp.loc['2015-01-01':] < tp.iloc[-1]).mean():.0f}%")
print(f"MOVE: now {move.iloc[-1]:.0f} ({move.index[-1].date()}), percentile since 2003 "
      f"{100*(move < move.iloc[-1]).mean():.0f}%")
print(f"lev net%OI trend 2026: {lev.loc['2026-01-01':, 'net_pct_oi'].iloc[::4].round(1).to_string()}")

# TLT dollar-volume for days-to-cover context
v = pd.read_csv(f"{DATA}/TLT.csv", parse_dates=["date"]).set_index("date")
adv = v["volume"].tail(63).mean()
print(f"\nTLT 3m ADV: {adv/1e6:.1f}M shares/day")
