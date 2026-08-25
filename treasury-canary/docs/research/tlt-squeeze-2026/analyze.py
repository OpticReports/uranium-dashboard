"""TLT squeeze study: positioning extremes -> forward returns, PIT throughout.

Measurement basis: TLT PRICE returns (FMP eod closes are NOT dividend-adjusted;
TLT yields ~3-5%, so 6m total returns run ~1.5-2.5pp above price returns —
stated, not hidden). Pre-2002 windows use the 30y yield change instead.
"""
import os
import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "data")

# ── load ─────────────────────────────────────────────────────────────────────
tlt = pd.read_csv(f"{DATA}/TLT.csv", parse_dates=["date"]).set_index("date")["close"]
dgs30 = pd.read_csv(f"{DATA}/DGS30.csv", parse_dates=["date"]).set_index("date")["DGS30"].dropna()
move = pd.read_csv(f"{DATA}/MOVE.csv", parse_dates=["date"]).set_index("date")["close"]

leg = pd.read_csv(f"{DATA}/legacy_cot.csv")
leg["date"] = pd.to_datetime(leg["report_date_as_yyyy_mm_dd"])
for c in ("noncomm_positions_long_all", "noncomm_positions_short_all", "open_interest_all"):
    leg[c] = pd.to_numeric(leg[c], errors="coerce")

tff = pd.read_csv(f"{DATA}/tff.csv")
tff["date"] = pd.to_datetime(tff["report_date_as_yyyy_mm_dd"])
for c in ("lev_money_positions_long", "lev_money_positions_short",
          "asset_mgr_positions_long", "asset_mgr_positions_short", "open_interest_all"):
    tff[c] = pd.to_numeric(tff[c], errors="coerce")

# ── positioning series ───────────────────────────────────────────────────────
def agg(df, mkts, long_c, short_c, oi_c="open_interest_all"):
    d = df[df["contract_market_name"].isin(mkts)]
    g = d.groupby("date").agg(long=(long_c, "sum"), short=(short_c, "sum"),
                              oi=(oi_c, "sum"))
    g["net"] = g["long"] - g["short"]
    g["net_pct_oi"] = 100.0 * g["net"] / g["oi"]
    return g.sort_index()

LONG_END = ["UST BOND", "ULTRA UST BOND"]
ALL_UST = ["UST BOND", "ULTRA UST BOND", "UST 10Y NOTE", "ULTRA UST 10Y"]

nc_long_end = agg(leg, LONG_END, "noncomm_positions_long_all", "noncomm_positions_short_all")
nc_all = agg(leg, ALL_UST, "noncomm_positions_long_all", "noncomm_positions_short_all")
lev_all = agg(tff, ALL_UST, "lev_money_positions_long", "lev_money_positions_short")
am_all = agg(tff, ALL_UST, "asset_mgr_positions_long", "asset_mgr_positions_short")

print("=== CURRENT STATE (latest report) ===")
for name, g in [("noncomm long-end (bond+ultra) %OI", nc_long_end),
                ("noncomm all-UST %OI", nc_all),
                ("lev funds all-UST %OI", lev_all),
                ("asset mgrs all-UST %OI", am_all)]:
    last = g.iloc[-1]
    hist = g["net_pct_oi"].dropna()
    pct = 100.0 * (hist < last["net_pct_oi"]).mean()
    print(f"{name}: {last['net_pct_oi']:+.1f}%OI on {g.index[-1].date()} "
          f"(all-time percentile {pct:.0f}%, min {hist.min():+.1f} max {hist.max():+.1f})")
    print(f"   net contracts {last['net']:+,.0f}  (long {last['long']:,.0f} / short {last['short']:,.0f})")

# ── forward outcome helpers ──────────────────────────────────────────────────
def fwd_price_ret(series, d, days):
    s = series[series.index >= d]
    if len(s) == 0: return np.nan
    p0 = s.iloc[0]
    s2 = series[series.index >= d + pd.Timedelta(days=days)]
    if len(s2) == 0: return np.nan
    return 100.0 * (s2.iloc[0] / p0 - 1.0)

def fwd_yield_chg(series, d, days):
    s = series[series.index >= d]
    if len(s) == 0: return np.nan
    y0 = s.iloc[0]
    s2 = series[series.index >= d + pd.Timedelta(days=days)]
    if len(s2) == 0: return np.nan
    return 100.0 * (s2.iloc[0] - y0)          # bp

# ── episode detection: PIT record shorts & bottom-decile ────────────────────
def episodes(g, mode="record", q=0.10, min_hist=156, sep_weeks=26):
    """Onset dates where net %OI sets a PIT all-time low ('record') or first
    crosses into the PIT bottom decile ('decile'). Episodes separated by
    sep_weeks with a reset above the threshold in between."""
    s = g["net_pct_oi"].dropna()
    out, last_end, below = [], None, False
    for i in range(min_hist, len(s)):
        hist = s.iloc[:i]
        thr = hist.min() if mode == "record" else hist.quantile(q)
        v = s.iloc[i]
        if v < thr:
            if not below and (last_end is None or
                              (s.index[i] - last_end).days > sep_weeks * 7):
                out.append(s.index[i])
            below = True
            last_end = s.index[i]
        else:
            below = False
    return out

print("\n=== EPISODES: PIT RECORD net-short, long-end noncommercial (1986+) ===")
rec = episodes(nc_long_end, "record")
rows = []
for d in rec:
    row = {"onset": d.date(),
           "net%OI": nc_long_end.loc[d, "net_pct_oi"]}
    for m, days in (("3m", 91), ("6m", 182), ("12m", 365)):
        row[f"TLT_{m}%"] = fwd_price_ret(tlt, d, days) if d >= tlt.index[0] else np.nan
        row[f"y30_{m}bp"] = fwd_yield_chg(dgs30, d, days)
    rows.append(row)
recdf = pd.DataFrame(rows)
print(recdf.to_string(index=False, float_format=lambda x: f"{x:+.1f}"))

print("\n=== EPISODES: PIT bottom-decile onset, long-end noncommercial ===")
dec = episodes(nc_long_end, "decile")
rows = []
for d in dec:
    row = {"onset": d.date(), "net%OI": nc_long_end.loc[d, "net_pct_oi"]}
    for m, days in (("3m", 91), ("6m", 182), ("12m", 365)):
        row[f"TLT_{m}%"] = fwd_price_ret(tlt, d, days) if d >= tlt.index[0] else np.nan
        row[f"y30_{m}bp"] = fwd_yield_chg(dgs30, d, days)
    rows.append(row)
decdf = pd.DataFrame(rows)
print(decdf.to_string(index=False, float_format=lambda x: f"{x:+.1f}"))

print("\n=== SAME, leveraged funds (TFF, 2006+) — the basis-trade-contaminated series ===")
lev_dec = episodes(lev_all, "decile", min_hist=104)
rows = []
for d in lev_dec:
    row = {"onset": d.date(), "net%OI": lev_all.loc[d, "net_pct_oi"]}
    for m, days in (("3m", 91), ("6m", 182), ("12m", 365)):
        row[f"TLT_{m}%"] = fwd_price_ret(tlt, d, days)
        row[f"y30_{m}bp"] = fwd_yield_chg(dgs30, d, days)
    rows.append(row)
print(pd.DataFrame(rows).to_string(index=False, float_format=lambda x: f"{x:+.1f}"))

# ── unconditional base rates ─────────────────────────────────────────────────
print("\n=== UNCONDITIONAL base rates (all weekly dates with data) ===")
base_dates = nc_long_end.index[nc_long_end.index >= tlt.index[0]]
for m, days in (("3m", 91), ("6m", 182), ("12m", 365)):
    r = pd.Series([fwd_price_ret(tlt, d, days) for d in base_dates]).dropna()
    print(f"TLT fwd {m}: mean {r.mean():+.2f}%  median {r.median():+.2f}%  "
          f"P(>+10%) {(r > 10).mean():.1%}  P(>+15%) {(r > 15).mean():.1%}  n={len(r)}")
y_dates = nc_long_end.index
for m, days in (("6m", 182),):
    r = pd.Series([fwd_yield_chg(dgs30, d, days) for d in y_dates]).dropna()
    print(f"30y fwd {m}: mean {r.mean():+.0f}bp  P(<-50bp) {(r < -50).mean():.1%}  "
          f"P(<-100bp) {(r < -100).mean():.1%}  n={len(r)}")

# ── the 100bp+ 3m yield-drop census: what actually causes squezes-sized moves ─
print("\n=== ALL 30y drops >= 80bp in 91 days since 1986 (episode starts) ===")
y = dgs30[dgs30.index >= "1986-01-01"]
drops = []
in_ep = None
for d in y.index:
    fut = y[(y.index > d) & (y.index <= d + pd.Timedelta(days=91))]
    if len(fut) and (fut.min() - y.loc[d]) * 100 <= -80:
        if in_ep is None or (d - in_ep).days > 120:
            drops.append(d)
        in_ep = d
for d in drops:
    fut = y[(y.index > d) & (y.index <= d + pd.Timedelta(days=91))]
    print(f"{d.date()}  30y {y.loc[d]:.2f}% -> min {fut.min():.2f}%  ({(fut.min()-y.loc[d])*100:+.0f}bp)")
