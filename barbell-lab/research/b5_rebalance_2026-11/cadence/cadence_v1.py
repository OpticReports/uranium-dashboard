"""B.5 Enhanced v1.0 — rebalance-check cadence study (read-only research, scratch only).

Portfolio v1.0: AVUV .25 AVDV .19 PHYS .18 KMLM .14 AVEM .10 QUAL .09 TAIL .05
Bands: +/-20% relative; any holding out -> trade. Every trade executes at the
NEXT trading day's close after the triggering check (no look-ahead).
Costs: barbell-lab/config/backtest.yaml costs_bps (one-way, documented there as
half-spread + fee), applied to every trade incl. initial buy. Stress: 2x.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

D = Path(sys.argv[1])
DL = D / "dl"
TODAY = pd.Timestamp("2026-11-16")
TARGETS = {"AVUV": .25, "AVDV": .19, "PHYS": .18, "KMLM": .14, "AVEM": .10, "QUAL": .09, "TAIL": .05}
COST_BPS = {"AVUV": 5, "AVDV": 10, "PHYS": 8, "KMLM": 10, "AVEM": 8, "QUAL": 3, "TAIL": 12}  # backtest.yaml
PROXY = {"AVUV": ("DFSVX", "2019-10-01"), "AVDV": ("DISVX", "2019-10-01"), "PHYS": ("GLD", "2010-03-01"),
         "KMLM": ("ASFYX", "2020-12-02"), "AVEM": ("DFEMX", "2019-10-01")}  # data.yaml
KMLM_CORR = dict(ex="2022-12-28", vendor=2.481, true=4.0377)  # data.yaml distribution_corrections
log = []


def load(t):
    j = json.load(open(DL / f"{t}.json"))["chart"]["result"][0]
    idx = pd.to_datetime(j["timestamp"], unit="s", utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
    df = pd.DataFrame({"adj": j["indicators"]["adjclose"][0]["adjclose"], "raw": j["indicators"]["quote"][0]["close"]}, index=idx)
    df = df[~df.index.duplicated(keep="last")].dropna()
    df = df[df.index < TODAY]  # today's bar is intraday
    if t == "KMLM":
        divs = {pd.to_datetime(int(k), unit="s", utc=True).tz_convert("America/New_York").strftime("%Y-%m-%d"): v["amount"]
                for k, v in j["events"]["dividends"].items()}
        got = divs.get(KMLM_CORR["ex"])
        assert got is not None and abs(got - KMLM_CORR["vendor"]) < 1e-6, f"Yahoo KMLM div now {got}; correction would be wrong"
        ex = pd.Timestamp(KMLM_CORR["ex"]); before = df.index < ex
        prev = float(df.loc[before, "raw"].iloc[-1])
        f = (1 - KMLM_CORR["true"] / prev) / (1 - KMLM_CORR["vendor"] / prev)
        df.loc[before, "adj"] *= f
        if not any(x.startswith("KMLM correction") for x in log): log.append(f"KMLM correction applied: vendor {got} -> true {KMLM_CORR['true']}, pre-ex adj x{f:.5f} (prev raw close {prev:.2f})")
    return df["adj"]


def spliced(t, lag_bug=False):
    live = load(t)
    if t not in PROXY:
        return live, pd.Series("live", index=live.index)
    p, sd = PROXY[t]
    eff = max(pd.Timestamp(sd), live.index.min())
    px = load(p)
    live_part = live[live.index >= eff]
    pr = px.pct_change()
    if lag_bug:  # barbell-lab series.py as coded (see report): proxy returns land one day late
        pre = px[px.index < eff]; pre_ret = pre.pct_change().dropna()
        back = live_part.iloc[0] / np.cumprod(1 + pre_ret.values[::-1])
        ext = pd.Series(back[::-1], index=pre_ret.index)
    else:  # returns-only chaining with each proxy return on its own date; splice-day return = proxy's
        pre_idx = px.index[px.index < eff]
        r_chain = pr.reindex(pre_idx[1:].append(pd.DatetimeIndex([eff]))).values  # r on dates d1..eff
        # level(d_k) = level(d_{k+1}) / (1 + r(d_{k+1}))
        lv = live_part.iloc[0] / np.cumprod((1 + r_chain)[::-1])
        ext = pd.Series(lv[::-1], index=pre_idx)
    s = pd.concat([ext, live_part]).sort_index()
    prov = pd.Series("live", index=s.index); prov[s.index < eff] = f"proxy:{p}"
    return s, prov


def build(tickers, use_proxy, lag_bug=False):
    lv, pv = {}, {}
    for t in tickers:
        s, p = spliced(t, lag_bug) if use_proxy else (load(t), None)
        lv[t] = s; pv[t] = p
    P = pd.DataFrame(lv).dropna()
    R = P.pct_change().iloc[1:]
    prov = {t: (pv[t].reindex(R.index) != "live").sum() if pv[t] is not None else 0 for t in tickers}
    first_live = {t: str(pv[t][pv[t] == "live"].index.min().date()) for t in tickers if pv[t] is not None}
    return P.index[0], R, prov, first_live


# ---------------- vectorized simulator: R (P,T,N), check masks (P,T) ----------------
def simulate(R, w, c, check, band, partial=False, calendar=False, same_day=False):
    Pn, T, N = R.shape
    H = np.tile(w * (1 - c), (Pn, 1))
    V = np.empty((Pn, T)); pend = np.zeros(Pn, bool); pset = np.zeros((Pn, N), bool)
    fees = np.zeros(Pn); turn = np.zeros(Pn); nreb = np.zeros(Pn, int)
    reb_days = [[] for _ in range(Pn)] if Pn == 1 else None

    def trade(idx, Hs, S):
        W = Hs.sum(1, keepdims=True)
        if partial:
            Sd = S.copy()
            tgt_val = (w * W * Sd).sum(1, keepdims=True)
            rest = np.where(Sd, 0, Hs).sum(1, keepdims=True)
            scale = np.where(rest > 0, (W - tgt_val) / np.where(rest > 0, rest, 1), 0)
            Hn = np.where(Sd, w * W, Hs * scale)
            allS = Sd.all(1)
            Hn[allS] = (w * W)[allS]
        else:
            Hn = w * W
        tr = np.abs(Hn - Hs)
        fee = (tr * c).sum(1)
        Hn = Hn * ((W[:, 0] - fee) / W[:, 0])[:, None]
        return Hn, fee / W[:, 0], tr.sum(1) / 2 / W[:, 0]

    for t in range(T):
        H = H * (1 + R[:, t])
        if pend.any():
            i = np.where(pend)[0]
            Hn, f, tv = trade(i, H[i], pset[i])
            H[i] = Hn; fees[i] += f; turn[i] += tv; nreb[i] += 1
            if reb_days is not None: reb_days[0].append(t)
            pend[:] = False
        m = check[:, t]
        if m.any():
            W = H.sum(1, keepdims=True); rel = np.abs(H / W / w - 1)
            out = rel > band if band is not None else np.ones_like(rel, bool)
            trig = m & out.any(1)
            if same_day and trig.any():
                i = np.where(trig)[0]
                Hn, f, tv = trade(i, H[i], out[i]); H[i] = Hn; fees[i] += f; turn[i] += tv; nreb[i] += 1
                if reb_days is not None: reb_days[0].append(t)
            else:
                pend = trig; pset = out
        V[:, t] = H.sum(1)
    return V, fees, turn, nreb, reb_days


def masks_from_dates(idx):
    s = pd.Series(np.arange(len(idx)), index=idx)
    per = lambda f: s.groupby(f).transform("max").values == s.values
    me = per(idx.to_period("M")); qe = per(idx.to_period("Q"))
    wk = per(idx.to_period("W-FRI"))  # last trading day of each Fri-ending week (Friday or holiday-shifted)
    me_i = np.where(me)[0]; ann = np.zeros(len(idx), bool); ann[me_i[11::12]] = True  # every 12th month-end from start
    return dict(daily=np.ones(len(idx), bool), weekly=wk, monthly=me, quarterly=qe, annual=ann, none=np.zeros(len(idx), bool))


ARMS = [  # name, cadence, band, partial, calendar
    ("1 daily", "daily", .20, False), ("2 weekly(Fri)", "weekly", .20, False), ("3 month-end", "monthly", .20, False),
    ("4 quarter-end", "quarterly", .20, False), ("5 annual calendar", "annual", None, False), ("6 buy&hold", "none", .20, False),
    ("7 daily band10 (expl)", "daily", .10, False), ("8 daily band30 (expl)", "daily", .30, False),
    ("9 daily partial", "daily", .20, True)]


def run_all(R, masks, w, c, same_day_ref=True):
    out = {}
    for name, cad, band, part in ARMS:
        out[name] = simulate(R, w, c, np.broadcast_to(masks[cad], R.shape[:2]), band, partial=part)
    if same_day_ref:
        out["3s month-end same-close (engine)"] = simulate(R, w, c, np.broadcast_to(masks["monthly"], R.shape[:2]), .20, same_day=True)
    return out


def cagr(v, start=1.0, n=None):
    n = n or v.shape[-1]
    return (v[..., -1] / start) ** (252 / n) - 1


def metrics(V, dates, rf, fees, turn, nreb, reb_days):
    v = pd.Series(np.r_[1.0, V[0]], index=dates)
    r = v.pct_change().dropna(); yrs = len(r) / 252
    ex = r - rf.reindex(r.index).fillna(0)
    dd = v / v.cummax() - 1
    rd = [str(dates[1:][i].date()) for i in reb_days[0]] if reb_days else []
    gaps = np.diff([dates[0]] + [pd.Timestamp(x) for x in rd] + [dates[-1]])
    return dict(cagr=float(v.iloc[-1] ** (1 / yrs) - 1), vol=float(r.std() * np.sqrt(252)),
                sharpe=float(ex.mean() / ex.std() * np.sqrt(252)), maxdd=float(dd.min()),
                worst12m=float((v / v.shift(252) - 1).min()), n_reb=int(nreb[0]), reb_per_yr=float(nreb[0] / yrs),
                turnover_oneway_ann=float(turn[0] / yrs), fees_total_pct=float(fees[0]), fee_drag_bps_yr=float(fees[0] / yrs * 1e4),
                longest_gap_days=int(max(gaps).days), rebalance_dates=rd)


def bootstrap(R, w, c, idx, n_paths=1000, seed=7):
    rng = np.random.default_rng(seed)
    per = idx.to_period("M"); blocks = [np.where(per == p)[0] for p in per.unique()]
    wd = idx.day_of_week.values; T = len(idx); N = R.shape[1]
    Rb = np.empty((n_paths, T, N)); M = {k: np.zeros((n_paths, T), bool) for k in ["daily", "weekly", "monthly", "quarterly", "annual", "none"]}
    for p in range(n_paths):
        rows, mends = [], []
        while len(rows) < T:
            b = blocks[rng.integers(len(blocks))]; rows.extend(b); mends.append(len(rows) - 1)
        rows = np.array(rows[:T]); Rb[p] = R[rows]
        me = np.array([m for m in mends if m < T]); M["monthly"][p, me] = True
        M["quarterly"][p, me[2::3]] = True; M["annual"][p, me[11::12]] = True; M["daily"][p] = True
        d = wd[rows]; nxt = np.r_[d[1:], 0]  # last trading day of a week: next day's weekday <= today's (or block break)
        M["weekly"][p] = (nxt <= d) | np.isin(np.arange(T), me)
    res = {}
    for name, cad, band, part in ARMS:
        V = simulate(Rb, w, c, M[cad], band, partial=part)[0]
        res[name] = cagr(V)
    base = res["3 month-end"]
    return {k: dict(mean_diff_bps=float(np.mean(v - base) * 1e4), ci95_bps=[float(np.percentile(v - base, 2.5) * 1e4), float(np.percentile(v - base, 97.5) * 1e4)],
                    p_gt0=float(np.mean(v - base > 0))) for k, v in res.items() if k != "3 month-end"}


def study(label, tickers, w, use_proxy, rf, n_boot=1000, offsets=21, lag_bug=False):
    start, Rdf, prov, first_live = build(tickers, use_proxy, lag_bug)
    c = np.array([COST_BPS[t] * 1e-4 for t in tickers])
    idx = Rdf.index; R = Rdf.values
    dates = idx.insert(0, start)
    masks = masks_from_dates(idx)
    runs = run_all(R[None], masks, w, c)
    tab = {k: metrics(v[0], dates, rf, *v[1:]) for k, v in runs.items()}
    runs0 = run_all(R[None], masks, w, np.zeros_like(c), same_day_ref=False)
    runs2 = run_all(R[None], masks, w, 2 * c, same_day_ref=False)
    for k in runs0:
        tab[k]["cagr_zero_cost"] = float(cagr(runs0[k][0])[0]); tab[k]["cagr_2x_cost"] = float(cagr(runs2[k][0])[0])
        tab[k]["cost_drag_bps_yr"] = (tab[k]["cagr_zero_cost"] - tab[k]["cagr"]) * 1e4
    # start-date sensitivity
    sd = {k: [] for k, *_ in ARMS}
    for o in range(offsets):
        Ro = R[o:]; io = idx[o:]; mo = masks_from_dates(io)
        rr = run_all(Ro[None], mo, w, c, same_day_ref=False)
        for k in sd: sd[k].append(float(cagr(rr[k][0])[0]))
    sdiff = {k: np.array(v) - np.array(sd["3 month-end"]) for k, v in sd.items()}
    startsens = {k: dict(min=min(v), max=max(v), spread_bps=(max(v) - min(v)) * 1e4,
                         diff_vs_monthly_bps_min=float(sdiff[k].min() * 1e4), diff_vs_monthly_bps_max=float(sdiff[k].max() * 1e4))
                 for k, v in sd.items()}
    boot = bootstrap(R, w, c, idx, n_paths=n_boot) if n_boot else None
    return dict(label=label, start=str(start.date()), end=str(idx[-1].date()), n_days=len(idx), years=len(idx) / 252,
                proxy_rows=prov, first_live=first_live, table=tab, start_sensitivity=startsens, bootstrap=boot,
                _curves={k: np.r_[1.0, v[0][0]] for k, v in runs.items()}, _dates=dates)


if __name__ == "__main__":
    rf_raw = pd.read_csv(DL / "DTB3.csv", index_col=0, parse_dates=True).iloc[:, 0]
    rf = (pd.to_numeric(rf_raw, errors="coerce").ffill() / 100 / 252)
    tick = list(TARGETS); w = np.array([TARGETS[t] for t in tick])
    # data sanity: >15% one-day moves
    for t in tick + [p for p, _ in PROXY.values()]:
        r = load(t).pct_change().dropna(); big = r[r.abs() > .15]
        if len(big): log.append(f"GAP>15% {t}: " + ", ".join(f"{d.date()} {v:+.1%}" for d, v in big.items()))
    A = study("A live ETFs only (all 7 real)", tick, w, False, rf)
    B = study("B proxy-extended 7-sleeve (TAIL live)", tick, w, True, rf)
    t6 = [t for t in tick if t != "TAIL"]; w6 = np.array([TARGETS[t] for t in t6]); w6 = w6 / w6.sum()
    C = study("C proxy-extended 6-sleeve, TAIL weight pro-rata (no-tail counterfactual)", t6, w6, True, rf, n_boot=500)
    # repo splice lag check on B, monthly arm only
    for t in ["AVUV", "KMLM"]:
        p_, sd_ = PROXY[t]; raw = load(p_).pct_change(); rep = spliced(t, True)[0].pct_change()
        df_ = pd.DataFrame({"raw": raw, "rep": rep}).dropna(); df_ = df_[df_.index < pd.Timestamp(sd_)]
        log.append(f"repo series.py splice check {t}: corr(repo, proxy same day)={df_.rep.corr(df_.raw):.3f}, corr(repo, proxy prior day)={df_.rep.corr(raw.shift(1).reindex(df_.index)):.3f}")
    BL = study("B-lagbug", tick, w, True, rf, n_boot=0, offsets=1, lag_bug=True)
    log.append("B monthly arm CAGR with repo splice as coded: %.4f vs same-day splice %.4f" % (BL["table"]["3 month-end"]["cagr"], B["table"]["3 month-end"]["cagr"]))
    res = dict(meta=dict(portfolio=TARGETS, cost_bps_oneway=COST_BPS, cost_note="backtest.yaml costs_bps (documented as half-spread+fee); 2x stress reported; IBKR fixed per-order minimums not modeled",
                         execution="check after close on day t; trade at close t+1; arm 3s = engine-as-coded same-close", rf="FRED DTB3 discount yield /252, ffilled",
                         log=log), studies={})
    for S in (A, B, C):
        res["studies"][S["label"]] = {k: v for k, v in S.items() if not k.startswith("_")}
    json.dump(res, open(D / "results.json", "w"), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else int(o))
    pd.to_pickle({S["label"]: (S["_curves"], S["_dates"], S["table"]) for S in (A, B, C)}, D / "curves.pkl")
    print("\n".join(log))
