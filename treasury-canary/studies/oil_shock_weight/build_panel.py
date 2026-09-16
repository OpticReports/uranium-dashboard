"""Build the shared monthly panel for the oil-shock study (spec v1, 2026-09-15).
Every analysis block reads panel.csv / events.json / tic_oil_exporters.csv, so
all blocks use identical inputs.

Sources (FRED fredgraph.csv, keyless; Yahoo ^GSPC daily 1927+; Dallas Fed IGREA):
  WTISPLC   spot WTI, monthly, 1946+   PRIMARY long oil series (D1/D2/D3)
  WPU0561   PPI crude petroleum, 1947+ (Hamilton's series) — pre-1983 cross-check
  DCOILWTICO daily WTI 1986+ -> monthly mean AND month-end 252-obs point change
             (the deployed channel's exact construction)
  DGS10/DGS3MO daily -> deployed 'curve flat' rule (min over trailing 183 days)
  GS10-TB3MS = spread_gs, the ONE curve basis used for every fit (1953+)
  T10Y3M monthly mean = spread_cmt, live-reading / 1982+ agreement check only
  CPIAUCSL (2025-10 gap log-linearly interpolated, flagged), USREC, FEDFUNDS,
  UNRATE, INDPRO, PAYEMS, WMTSECL1 custody, DTWEXM+DTWEXBGS ratio-spliced at
  2006-01, DNRGRC1M027SBEA/PCE energy share, IGREA (Kilian global activity).
Panel is truncated at the last COMPLETE month of WTISPLC.
"""
import json, datetime as dt
import numpy as np, pandas as pd

import os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def fred(sid):
    s = pd.read_csv(f"{D}/{sid}.csv")
    s.columns = ["date", "v"]
    s["date"] = pd.to_datetime(s["date"])
    s["v"] = pd.to_numeric(s["v"], errors="coerce")
    return s.set_index("date")["v"]


def monthly_mean(s):
    return s.dropna().resample("MS").mean()


wti = fred("WTISPLC")
LAST = wti.dropna().index.max()                       # last complete month
idx = pd.date_range("1946-01-01", LAST, freq="MS")
P = pd.DataFrame(index=idx)
P["wti"] = wti
P["ppi_crude"] = fred("WPU0561")
oil_d = fred("DCOILWTICO").dropna()
P["wti_daily_mean"] = monthly_mean(oil_d)
P["brent_daily_mean"] = monthly_mean(fred("DCOILBRENTEU"))
cpi = fred("CPIAUCSL")
cpi_gap = cpi.reindex(idx)
missing_cpi = [d.strftime("%Y-%m") for d in cpi_gap.index[cpi_gap.isna() & (cpi_gap.index <= cpi.dropna().index.max()) & (cpi_gap.index >= cpi.dropna().index.min())]]
cpi_filled = np.exp(np.log(cpi_gap).interpolate(limit_area="inside"))
P["cpi"] = cpi_filled
P["cpi_interpolated"] = cpi_gap.isna() & cpi_filled.notna()
P["usrec"] = fred("USREC")
P["tb3ms"] = fred("TB3MS")
P["gs10"] = fred("GS10")
P["spread_cmt"] = monthly_mean(fred("T10Y3M"))
P["fedfunds"] = fred("FEDFUNDS")
P["unrate"] = fred("UNRATE")
P["indpro"] = fred("INDPRO")
P["payems"] = fred("PAYEMS")
P["custody_bn"] = monthly_mean(fred("WMTSECL1").replace(0.0, np.nan)) / 1000.0   # FRED prints 0 before 2007-07-04 (not yet reported): NaN, not zero
# broad dollar: DTWEXM (majors, 1973-2019) ratio-spliced onto DTWEXBGS (broad, 2006+)
m_old = monthly_mean(fred("DTWEXM")); m_new = monthly_mean(fred("DTWEXBGS"))
ratio = (m_new.loc["2006-01-01":"2006-12-01"] / m_old.loc["2006-01-01":"2006-12-01"]).mean()
usd = pd.concat([(m_old.loc[:"2005-12-01"] * ratio), m_new.loc["2006-01-01":]])
P["usd_broad"] = usd
P["usd_broad_note"] = "DTWEXM*%.4f before 2006-01, DTWEXBGS after (ratio-splice on 2006 overlap)" % ratio
# energy share of consumption (nominal PCE energy goods & services / PCE), %
P["energy_share_pct"] = fred("DNRGRC1M027SBEA") / fred("PCE") * 100.0
# Kilian global real economic activity index (Dallas Fed), monthly
try:
    x = pd.read_excel(f"{D}/igrea.xlsx", header=None)
    # find the first row whose first cell parses as a date
    rows = []
    for _, r in x.iterrows():
        try:
            d = pd.to_datetime(r.iloc[0])
            v = float(r.iloc[1])
        except Exception:
            continue
        if pd.notna(d) and pd.notna(v):
            rows.append((pd.Timestamp(d.year, d.month, 1), v))
    ig = pd.Series(dict(rows)).sort_index()
    P["igrea"] = ig
except Exception as e:  # noqa: BLE001
    print("IGREA not loaded:", e)

# --- deployed-instrument daily reconstructions (1986+/1982+), evaluated at month-end
oil_vals = oil_d.values; oil_dates = oil_d.index
pt = {}
for i in range(252, len(oil_vals)):
    m = pd.Timestamp(oil_dates[i].year, oil_dates[i].month, 1)
    pt[m] = (oil_vals[i] - oil_vals[i - 252]) / oil_vals[i - 252] * 100.0   # last print of month wins
P["wti_daily_252_pct"] = pd.Series(pt)
d10, d3 = fred("DGS10"), fred("DGS3MO")
sp = (d10 - d3).dropna()
cf = {}
for m in idx[idx >= "1982-01-01"]:
    eom = (m + pd.offsets.MonthEnd(0))
    w = sp.loc[eom - pd.Timedelta(days=183):eom]
    if len(w):
        cf[m] = float(w.min() < 0.25)
        pt_ = None
P["curve_flat_daily183"] = pd.Series(cf)

# --- SPX monthly close/low from daily bars 1927+ (UTC-labeled)
r = json.load(open(f"{D}/gspc_daily_1927.json"))["chart"]["result"][0]
assert r["meta"]["dataGranularity"] == "1d"
q = r["indicators"]["quote"][0]
rows = []
for ts, c, l in zip(r["timestamp"], q["close"], q["low"]):
    if c is None:
        continue
    d = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date()
    rows.append((pd.Timestamp(d.year, d.month, 1), c, l if l is not None else c))
spx = pd.DataFrame(rows, columns=["m", "close", "low"]).groupby("m").agg(spx_close=("close", "last"), spx_low=("low", "min"))
P = P.join(spx)

# --- derived oil measures (WTISPLC primary; PPI companions)
P["real_oil"] = P["wti"] / P["cpi"] * 100.0
P["oil_12m_pct"] = P["wti"].pct_change(12) * 100.0
P["oil_12m_pct_w"] = P["oil_12m_pct"].clip(-100, 100)          # winsorised regressor (deployed cap)
P["real_oil_12m_pct"] = P["real_oil"].pct_change(12) * 100.0
P["ppi_crude_12m_pct"] = P["ppi_crude"].pct_change(12) * 100.0
P["brent_12m_pct"] = P["brent_daily_mean"].pct_change(12) * 100.0
for src, col in (("wti", "nopi36_monthly"), ("ppi_crude", "ppi_nopi36_monthly")):
    lp = np.log(P[src])
    prior_max = lp.shift(1).rolling(36, min_periods=36).max()
    P[col] = np.maximum(lp - prior_max, 0.0) * 100.0            # Hamilton monthly net increase, log-pct
    P[col.replace("_monthly", "_sum12")] = P[col].rolling(12, min_periods=12).sum()   # D2 regressor / state
P["spread_gs"] = P["gs10"] - P["tb3ms"]                          # THE fit series, 1953-04+
P["curve_flat_gs6m"] = (P["spread_gs"].rolling(6, min_periods=6).min() < 0.25).where(P["spread_gs"].rolling(6, min_periods=6).min().notna())
P["spread_spliced_do_not_fit"] = P["spread_cmt"].where(P["spread_cmt"].notna(), P["spread_gs"])
P["indpro_12m_pct"] = P["indpro"].pct_change(12) * 100.0
P["ff_12m_chg_bps"] = P["fedfunds"].diff(12) * 100.0
P["usd_12m_pct"] = P["usd_broad"].pct_change(12) * 100.0
P["custody_12m_pct"] = (P["custody_bn"].pct_change(12) * 100.0).replace([np.inf, -np.inf], np.nan)
if "igrea" in P:
    P["igrea_12m_chg"] = P["igrea"].diff(12)

# --- events
u = P["usrec"]
onsets = [d.strftime("%Y-%m") for d in u.index[(u == 1) & (u.shift(1) == 0)]]
ends = [d.strftime("%Y-%m") for d in u.index[(u == 0) & (u.shift(1) == 1)]]


def drawdown_starts_running(df, threshold=15.0):
    """B1: from a RUNNING all-time peak (pin_history._drawdown_spans construction)."""
    spans, peak, peak_m, active, depth_max = [], None, None, None, 0.0
    for m, row in df.dropna(subset=["spx_close"]).iterrows():
        c, low = row["spx_close"], row["spx_low"]
        if peak is not None and peak > 0:
            depth = (peak - low) / peak * 100.0
            if depth >= threshold:
                if active is None:
                    active = [peak_m, depth]; depth_max = depth
                elif depth > depth_max:
                    active[1] = depth; depth_max = depth
        if peak is None or c >= peak:
            if active is not None:
                spans.append(tuple(active)); active = None; depth_max = 0.0
            peak, peak_m = c, m
    if active is not None:
        spans.append(tuple(active))
    return [(m.strftime("%Y-%m"), round(d, 1)) for m, d in spans]


def drawdown_starts_local(df, threshold=15.0):
    """B2: from any LOCAL peak. A span opens when the monthly LOW is >= threshold
    below the running local peak; its trough updates on new lows; the span CLOSES
    once the close has rallied >= threshold above the running trough low (or
    regains the peak) AND has retraced at least half of the decline, after which
    the local peak restarts from the highest close since closure. This lets 1976-09 and 2011-04 register (a running-all-time-peak
    rule absorbs them into the 1972 and 2007 spans)."""
    d = df.dropna(subset=["spx_close"])
    spans = []
    peak = peak_m = None
    active = None; trough = None
    for m, row in d.iterrows():
        c, low = row["spx_close"], row["spx_low"]
        if active is not None:
            if low < trough:
                trough = low
                active[1] = (peak - trough) / peak * 100.0
            # close: regain the peak, OR retrace >= 50% of the decline while
            # sitting >= threshold above the trough (bear-market rallies of
            # 35-49% retracement in 2001-02 and 2008 do NOT close a span;
            # the 77% retracements of 1976 and 2011 do)
            if c >= peak or (c >= trough * (1 + threshold / 100.0)
                             and c >= trough + 0.5 * (peak - trough)):
                spans.append((active[0], active[1])); active = None
                peak, peak_m = c, m
                continue
            continue
        if peak is None or c >= peak:
            peak, peak_m = c, m
        depth = (peak - low) / peak * 100.0 if peak else 0.0
        if depth >= threshold:
            active = [peak_m, depth]; trough = low
    if active is not None:
        spans.append((active[0], active[1]))
    return [(m.strftime("%Y-%m"), round(dd, 1)) for m, dd in spans]


dd_b1 = drawdown_starts_running(P.loc["1950-01-01":])
dd_b2 = drawdown_starts_local(P.loc["1950-01-01":])
P.index.name = "date"
P.round(4).to_csv(f"{D}/panel.csv")
json.dump({"recession_onsets": onsets, "recession_ends": ends,
           "drawdown_starts_B1_running_peak": dd_b1,
           "drawdown_starts_B2_local_peak": dd_b2,
           "last_complete_month": LAST.strftime("%Y-%m"),
           "last_resolved_month_h12": (LAST - pd.DateOffset(months=12)).strftime("%Y-%m"),
           "cpi_interpolated_months": missing_cpi,
           "note": ("onsets = first USREC=1 month after a 0; B1 = pin_history running-peak "
                    "construction from 1950; B2 = local-peak construction (reported second)")},
          open(f"{D}/events.json", "w"), indent=1)
print(P.shape)
print("onsets:", onsets)
print("B1:", dd_b1)
print("B2:", dd_b2)
print("cpi interpolated:", missing_cpi, "| last complete:", LAST.date())
print("coverage:", {c: (P[c].first_valid_index().strftime("%Y-%m"), P[c].last_valid_index().strftime("%Y-%m")) for c in P.columns if P[c].notna().any() and P[c].dtype != object})
print(P[["wti", "oil_12m_pct", "nopi36_monthly", "nopi36_sum12", "spread_gs", "curve_flat_gs6m", "curve_flat_daily183", "wti_daily_252_pct", "energy_share_pct", "igrea"]].tail(4).round(2).to_string())
