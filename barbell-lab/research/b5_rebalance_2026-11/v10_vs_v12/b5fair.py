"""B.5 v1.0 vs v1.2 fair comparison (matched windows + bracketing CAOS stand-ins).

Read-only. Data: Yahoo v8 chart adjclose (split+div adjusted), KMLM 2022-12-28
distribution correction per barbell-lab/config/data.yaml, FRED DTB3 for rf.
Rebalance: month-end check, full rebalance to target if any |w/target-1|>0.20,
12-month calendar fallback; one-way costs from config/backtest.yaml, initial buy charged.
"""
import json, os, sys, time, io
import numpy as np, pandas as pd, httpx, yaml

OUT = os.path.dirname(os.path.abspath(__file__))
REPO = "/home/user/uranium-dashboard/barbell-lab"
DATA = yaml.safe_load(open(f"{REPO}/config/data.yaml"))
BT = yaml.safe_load(open(f"{REPO}/config/backtest.yaml"))
COSTS = BT["costs_bps"]
BAND = float(BT["rebalance"]["band_relative"]); CAL_M = int(os.environ.get("B5_CAL_M", BT["rebalance"]["calendar_months"]))

V10 = dict(AVUV=.25, AVDV=.19, PHYS=.18, KMLM=.14, AVEM=.10, QUAL=.09, TAIL=.05)
V12 = dict(AVUV=.20, AVDV=.10, PHYS=.20, KMLM=.12, AVEM=.05, QUAL=.13, TAIL=.05, CAOS=.15)
assert abs(sum(V10.values()) - 1) < 1e-9 and abs(sum(V12.values()) - 1) < 1e-9
REAL = ["AVUV", "AVDV", "PHYS", "KMLM", "AVEM", "QUAL", "TAIL"]
PROXIES = {t: (c["proxy"], pd.Timestamp(str(c["splice_date"]))) for t, c in DATA["tickers"].items()
           if t in REAL and c.get("proxy")}

H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-script"}


def yahoo(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    p = {"period1": int(pd.Timestamp("1995-01-01", tz="UTC").timestamp()),
         "period2": int(time.time()) + 86400, "interval": "1d", "events": "div,split"}
    for a in range(4):
        try:
            r = httpx.get(url, params=p, headers=H, timeout=30); r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
            df = pd.DataFrame({"adj": res["indicators"]["adjclose"][0]["adjclose"],
                               "raw": res["indicators"]["quote"][0]["close"]}, index=idx)
            df = df[~df.index.duplicated(keep="last")].dropna()
            return df
        except Exception as e:  # noqa
            err = e; time.sleep(2 ** a)
    raise RuntimeError(f"yahoo {sym} failed: {err}")


def kmlm_fix(df):
    for c in DATA["distribution_corrections"]:
        if c["ticker"] != "KMLM": continue
        ex = pd.Timestamp(str(c["ex_date"])); before = df.index < ex
        prev = float(df.loc[before, "raw"].iloc[-1])
        f = (1 - c["true_amount"] / prev) / (1 - c["vendor_amount"] / prev)
        df = df.copy(); df.loc[before, "adj"] *= f
        return df, f
    raise RuntimeError("no KMLM correction found")


syms = REAL + ["CAOS", "BIL"] + [p for p, _ in PROXIES.values()]
px = {s: yahoo(s) for s in syms}
px["KMLM"], kmlm_factor = kmlm_fix(px["KMLM"])
first_px = {s: str(px[s].index.min().date()) for s in syms}
rets = pd.DataFrame({s: px[s]["adj"].pct_change() for s in syms})
cal = px["AVUV"].index.union(px["QUAL"].index)
rets = rets.reindex(rets.index.intersection(cal))

# END CAP (counter-agent 2 defect 1): use only COMPLETED closes. If run on a weekday
# before 16:30 ET, today's Yahoo bar is a live intraday price -> drop it.
_now_et = pd.Timestamp.now(tz="America/New_York")
_today = _now_et.tz_localize(None).normalize()
END = pd.Timestamp(os.environ["B5_END"]) if os.environ.get("B5_END") else (
    _today - pd.Timedelta(days=1) if (_now_et.hour * 60 + _now_et.minute) < 16 * 60 + 30 else _today)
rets = rets.loc[rets.index <= END]

# sanity: largest abs daily moves per holding (data check)
big = {s: [(str(d.date()), round(float(v), 4)) for d, v in rets[s].dropna().abs().nlargest(3).items()]
       for s in REAL + ["CAOS", "BIL"]}

# proxy-extended columns (repo-declared proxies, returns chained, never levels)
rets_px = rets.copy(); SPLICE_ACTUAL = {}
for t, (p, sd) in PROXIES.items():
    use = (rets.index < sd) | rets[t].isna()   # proxy until splice date, or until the live ETF's first return if later
    rets_px.loc[use, t] = rets.loc[use, p]
    SPLICE_ACTUAL[t] = str(rets.index[~use & rets[t].notna()].min().date())

CAOS_D0 = px["CAOS"].index.min()          # first CAOS price (close of conversion day)
CAOS_R0 = rets["CAOS"].dropna().index.min()  # first CAOS daily return

# --- rf ---
rf_src = "FRED DTB3"
try:
    r = httpx.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3", headers=H, timeout=30); r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text)); d.columns = ["date", "v"]
    d["v"] = pd.to_numeric(d["v"], errors="coerce")
    rf_annual = d.set_index(pd.to_datetime(d["date"]))["v"].ffill() / 100
except Exception as e:
    rf_annual = None; rf_src = f"UNAVAILABLE ({type(e).__name__}) -> rf=0"


def cost(t):
    return float(COSTS.get(t, COSTS["default"])) * 1e-4


def simulate(R, schedule):
    """schedule: list of (start_date, {ticker: w}) - first entry starts the sim.
    On each later schedule date the book is fully rebalanced to the new targets at
    that day's close (trades charged). Otherwise month-end band + 12m fallback."""
    tick = sorted({t for _, w in schedule for t in w})
    start = schedule[0][0]
    R = R.loc[R.index > start, tick]
    switches = {pd.Timestamp(d): w for d, w in schedule[1:]}
    c = np.array([cost(t) for t in tick])
    w = np.array([schedule[0][1].get(t, 0.0) for t in tick])
    req = [t for t in tick if w[tick.index(t)] > 0]
    wealth = 1.0; hold = w * (1 - c)  # initial buy pays cost
    me = set(R.groupby(R.index.to_period("M")).apply(lambda g: g.index.max()))
    out = []; msr = 0; nreb = 0; reb_dates = []
    for dt, row in zip(R.index, R.fillna(0.0).values):
        live = hold > 0
        if np.isnan(R.loc[dt, [tick[i] for i in np.where(live)[0]]].values).any():
            bad=[tick[i] for i in np.where(live)[0] if np.isnan(R.loc[dt, tick[i]])]; raise RuntimeError(f"missing return {bad} on {dt.date()}")
        hold = hold * (1 + row); nw = hold.sum(); out.append([dt, nw / wealth - 1]); wealth = nw
        force = dt in switches
        if force:
            w = np.array([switches[dt].get(t, 0.0) for t in tick])
        if dt in me or force:
            if dt in me: msr += 1
            wn = hold / wealth
            m = w > 0
            band_hit = bool((np.abs(wn[m] / w[m] - 1) > BAND).any())
            if force or band_hit or msr >= CAL_M:
                tr = w * wealth - hold; fee = float(np.sum(np.abs(tr) * c))
                wealth -= fee; hold = w * wealth; out[-1][1] -= fee / nw
                nreb += 1; msr = 0; reb_dates.append(str(dt.date()))
    s = pd.Series([v for _, v in out], index=pd.DatetimeIndex([d for d, _ in out]))
    return s, nreb, reb_dates


def stats(s):
    n = len(s); wealth = (1 + s).cumprod()
    cagr = wealth.iloc[-1] ** (252 / n) - 1
    vol = s.std(ddof=1) * np.sqrt(252)
    rf = (rf_annual.reindex(s.index, method="ffill").fillna(0) / 252) if rf_annual is not None else 0 * s
    ex = s - rf
    dd = wealth / wealth.cummax() - 1
    roll = np.expm1(np.log1p(s).rolling(252).sum().dropna())
    yrs = (1 + s).groupby(s.index.year).prod() - 1
    first, last = s.index.min(), s.index.max()
    cy = {}
    for y, v in yrs.items():
        lab = str(y)
        if y == first.year and first.month > 1 or (y == first.year and first.day > 7 and first.month == 1): lab += " (partial, from %s)" % first.date()
        if y == last.year and not (last.month == 12 and last.day >= 28): lab += " (YTD to %s)" % last.date()
        cy[lab] = float(v)
    trough = dd.idxmin(); peak = wealth.loc[:trough].idxmax()
    return {"start_first_return": str(first.date()), "end": str(last.date()), "n_days": n,
            "cagr": float(cagr), "vol": float(vol), "sharpe": float(ex.mean() / s.std(ddof=1) * np.sqrt(252)),
            "rf_mean_annual": float(rf.mean() * 252), "max_dd": float(dd.min()),
            "max_dd_peak": str(peak.date()), "max_dd_trough": str(trough.date()),
            "worst_12m": float(roll.min()) if len(roll) else None,
            "worst_12m_end": str(roll.idxmin().date()) if len(roll) else None,
            "calendar_years": cy}


def window_dd(s, a, b):
    """Deepest drawdown (vs all-time running peak) reached inside [a,b], and the window's return."""
    w = (1 + s).cumprod(); dd = w / w.cummax() - 1
    seg = dd.loc[a:b]; ws = w.loc[a:b]; pre = w.loc[:pd.Timestamp(a) - pd.Timedelta(days=1)]
    base = pre.iloc[-1] if len(pre) else 1.0
    return {"min_dd": float(seg.min()), "trough": str(seg.idxmin().date()),
            "window_return": float(ws.iloc[-1] / base - 1)}


res = {"meta": {}, "A_common_window": {}, "B_full_history_real": {}, "B2_proxy_extended": {},
       "C_window_effect": {}, "rebalance_counts": {}}
series = {}

# A) common window: buy at close of CAOS first price day; first return = next day
d0 = CAOS_D0
for name, tg, R in [("v1.0", V10, rets), ("v1.2", V12, rets)]:
    s, n, rd = simulate(R, [(d0, tg)])
    res["A_common_window"][name] = stats(s); res["rebalance_counts"][f"A {name}"] = n
    series[f"A {name}"] = s

# B) full history, real holdings only
real_d0 = max(px[t].index.min() for t in REAL)
v12_ex = {k: v / (1 - V12["CAOS"]) for k, v in V12.items() if k != "CAOS"}
v12_bil = {**{k: v for k, v in V12.items() if k != "CAOS"}, "BIL": V12["CAOS"]}


def full_runs(R, d0, tag):
    out = {}
    runs = {
        "v1.0": [(d0, V10)],
        "v1.2 stand-in (i) CAOS->BIL pre-inception": [(d0, v12_bil), (CAOS_D0, V12)],
        "v1.2 stand-in (ii) CAOS removed pro-rata pre-inception": [(d0, v12_ex), (CAOS_D0, V12)],
        "v1.2 counterfactual: BIL in place of CAOS throughout": [(d0, v12_bil)],
        "v1.2 counterfactual: no CAOS throughout (pro-rata)": [(d0, v12_ex)],
    }
    for k, sch in runs.items():
        s, n, rd = simulate(R, sch)
        st = stats(s)
        st["covid_2020"] = window_dd(s, "2020-02-19", "2020-06-30") if s.index.min() < pd.Timestamp("2020-02-19") else "NOT COMPUTABLE: series starts after 2020-02-19"
        st["dd_2022"] = window_dd(s, "2022-01-03", "2022-12-30")
        st["post_caos_window"] = stats(s.loc[s.index >= CAOS_R0])
        out[k] = st; series[f"{tag} {k}"] = s; res["rebalance_counts"][f"{tag} {k}"] = n
    return out


res["B_full_history_real"] = full_runs(rets, real_d0, "B")
px_d0 = max(max(px[t].index.min() for t in REAL if t not in PROXIES),
            max(px[p].index.min() for p, _ in PROXIES.values()))
res["B2_proxy_extended"] = full_runs(rets_px, px_d0, "B2")

# C) window effect for v1.0: full vs post-CAOS, both bases
res["C_window_effect"] = {
    "v1.0 full (real, from %s)" % real_d0.date(): {k: res["B_full_history_real"]["v1.0"][k] for k in ("cagr", "vol", "sharpe", "max_dd", "worst_12m")},
    "v1.0 full (proxy-extended, from %s)" % px_d0.date(): {k: res["B2_proxy_extended"]["v1.0"][k] for k in ("cagr", "vol", "sharpe", "max_dd", "worst_12m")},
    "v1.0 2023-03+": {k: res["A_common_window"]["v1.0"][k] for k in ("cagr", "vol", "sharpe", "max_dd", "worst_12m")},
    "v1.2 2023-03+": {k: res["A_common_window"]["v1.2"][k] for k in ("cagr", "vol", "sharpe", "max_dd", "worst_12m")},
}

# daily-return correlation and difference significance in the common window
a, b = series["A v1.0"], series["A v1.2"]
diff = b - a
res["A_common_window"]["v1.2_minus_v1.0"] = {
    "ann_mean_return_diff": float(diff.mean() * 252),
    "tracking_error": float(diff.std(ddof=1) * np.sqrt(252)),
    "t_stat_mean_diff": float(diff.mean() / diff.std(ddof=1) * np.sqrt(len(diff))),
    "corr_daily": float(np.corrcoef(a, b)[0, 1])}
# CAOS itself in window
res["A_common_window"]["CAOS_alone"] = stats(rets["CAOS"].loc[rets.index > d0].dropna())
res["A_common_window"]["BIL_alone"] = stats(rets["BIL"].loc[rets.index > d0].dropna())
res["A_common_window"]["v1.2 with BIL instead of CAOS"] = stats(simulate(rets, [(d0, v12_bil)])[0])
# counter-agent 1 defect 1: v1.2 weights with CAOS dropped, 15% spread pro-rata (isolates reweighting vs sleeve)
s_ex = simulate(rets, [(d0, v12_ex)])[0]
res["A_common_window"]["v1.2 without CAOS, pro-rata"] = stats(s_ex); series["A v1.2 no-CAOS pro-rata"] = s_ex
series["A v1.2 BIL instead of CAOS"] = simulate(rets, [(d0, v12_bil)])[0]

# counter-agent 2 gap: test the Sharpe DIFFERENCE, not just the mean-return difference
rfA = rf_annual.reindex(a.index, method="ffill").fillna(0) / 252 if rf_annual is not None else 0 * a
def _sh(x, r): return (x - r).mean() / x.std(ddof=1) * np.sqrt(252)
rng = np.random.default_rng(20261116); L = 21; n = len(a); nb = int(np.ceil(n / L)); A_, B_, F_ = a.values, b.values, rfA.values
bs = []
for _ in range(10000):
    st_ = rng.integers(0, n - L + 1, nb); ix = (st_[:, None] + np.arange(L)).ravel()[:n]
    xa, xb, xf = A_[ix], B_[ix], F_[ix]
    bs.append((xb - xf).mean() / xb.std(ddof=1) * np.sqrt(252) - (xa - xf).mean() / xa.std(ddof=1) * np.sqrt(252))
bs = np.array(bs)
ma, mb = (1 + a).resample("ME").prod() - 1, (1 + b).resample("ME").prod() - 1
md = (mb - ma)
res["A_common_window"]["v1.2_minus_v1.0"].update({
    "sharpe_diff_point": float(_sh(b, rfA) - _sh(a, rfA)),
    "sharpe_diff_block_bootstrap": {"block_days": L, "reps": 10000, "ci90": [float(np.quantile(bs, .05)), float(np.quantile(bs, .95))],
                                    "p_gt_0": float((bs > 0).mean())},
    "t_stat_monthly_diff": float(md.mean() / md.std(ddof=1) * np.sqrt(len(md))), "n_months": int(len(md))})

# counter-agent 1 MINOR: start-date sensitivity of window A
sens = {}
tds = rets.index[rets.index >= d0]
for k in [0, 5, 10, 20, 40, 65]:
    dk = tds[k]
    sa, _, _ = simulate(rets, [(dk, V10)]); sb, _, _ = simulate(rets, [(dk, V12)])
    xa, xb = stats(sa), stats(sb)
    sens[str(dk.date())] = {"v1.0_sharpe": xa["sharpe"], "v1.2_sharpe": xb["sharpe"], "v1.0_cagr": xa["cagr"], "v1.2_cagr": xb["cagr"],
                            "v1.0_max_dd": xa["max_dd"], "v1.2_max_dd": xb["max_dd"]}
res["A_start_date_sensitivity"] = sens

# counter-agent 1 MINOR: calendar-2022 returns labelled by basis
res["calendar_2022_by_basis"] = {tag: {k: v["calendar_years"].get("2022") for k, v in res[sec].items()}
                                 for tag, sec in [("real ETFs (B)", "B_full_history_real"), ("proxy-extended (B2)", "B2_proxy_extended")]}
# second sizeable episode in window A (counter-agent 2 wording note): all drawdowns deeper than -5%
def _episodes(s, thr=-0.05):
    w = (1 + s).cumprod(); dd = w / w.cummax() - 1; out = []; i = 0; v = dd.values; idx = dd.index
    while i < len(v):
        if v[i] < 0:
            j = i
            while j < len(v) and v[j] < 0: j += 1
            seg = dd.iloc[i:j]
            if seg.min() < thr: out.append({"trough": str(seg.idxmin().date()), "depth": float(seg.min()), "recovered": j < len(v)})
            i = j
        else: i += 1
    return out
res["A_drawdown_episodes_gt5pct"] = {k: _episodes(series[f"A {k}"]) for k in ("v1.0", "v1.2")}

res["meta"] = {
    "generated": pd.Timestamp.now().isoformat(), "rf_source": rf_src, "end_cap_last_completed_close": str(END.date()),
    "first_price_dates": first_px, "caos_first_price": str(CAOS_D0.date()), "caos_first_return": str(CAOS_R0.date()),
    "real_holdings_common_start_price": str(real_d0.date()), "proxy_extended_start_price": str(px_d0.date()),
    "kmlm_correction_factor_pre_2022-12-28": kmlm_factor, "proxies_used_B2": {k: [v[0], str(v[1].date())] for k, v in PROXIES.items()}, "first_live_return_after_splice": SPLICE_ACTUAL,
    "band": BAND, "calendar_fallback_months": CAL_M, "costs_bps": {t: COSTS.get(t, COSTS["default"]) for t in sorted(set(V10) | set(V12) | {"BIL"})},
    "largest_abs_daily_moves": big}
json.dump(res, open(f"{OUT}/results.json", "w"), indent=2, default=str)
pd.DataFrame(series).to_csv(f"{OUT}/daily_returns.csv")
print("ok", res["meta"]["rf_source"], res["meta"]["caos_first_price"], res["meta"]["real_holdings_common_start_price"], res["meta"]["proxy_extended_start_price"])
