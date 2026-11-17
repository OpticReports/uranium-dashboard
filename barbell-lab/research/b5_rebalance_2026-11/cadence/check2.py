"""Counter-agent #2 independent re-derivation of the B.5 cadence study.
Own parser, own total-return build (raw close + dividends, KMLM dividend corrected),
own splice, own loop simulator, own bootstrap. Usage: python check2.py <studydir>
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

D = Path(sys.argv[1]); DL = D / "dl"; DL2 = D / "dl2"
TGT = {"AVUV": .25, "AVDV": .19, "PHYS": .18, "KMLM": .14, "AVEM": .10, "QUAL": .09, "TAIL": .05}
CB = {"AVUV": 5, "AVDV": 10, "PHYS": 8, "KMLM": 10, "AVEM": 8, "QUAL": 3, "TAIL": 12}
PROXY = {"AVUV": ("DFSVX", "2019-10-01"), "AVDV": ("DISVX", "2019-10-01"), "KMLM": ("ASFYX", "2020-12-02"),
         "AVEM": ("DFEMX", "2019-10-01")}
END = pd.Timestamp("2026-11-14")


def raw(t, d=DL):
    j = json.load(open(d / f"{t}.json"))["chart"]["result"][0]
    ix = pd.to_datetime(j["timestamp"], unit="s").tz_localize("UTC").tz_convert("America/New_York").normalize().tz_localize(None)
    df = pd.DataFrame({"c": j["indicators"]["quote"][0]["close"], "a": j["indicators"]["adjclose"][0]["adjclose"]}, index=ix)
    df = df[~df.index.duplicated(keep="last")].dropna()
    df = df[df.index < END]
    dv = pd.Series({pd.Timestamp(v["date"], unit="s").tz_localize("UTC").tz_convert("America/New_York").normalize().tz_localize(None): v["amount"]
                    for v in j.get("events", {}).get("dividends", {}).values()}, dtype=float)
    pass  # Yahoo close + dividends are split-adjusted; checked vs adjclose below
    return df, dv


def tr_index(t, d=DL, fix=True):
    """Own total-return series from raw close + cash dividends (reinvested at ex-date close)."""
    df, dv = raw(t, d)
    if t == "KMLM" and fix:
        k = pd.Timestamp("2022-12-28")
        assert abs(dv[k] - 2.481) < 1e-6
        dv[k] = 4.0377
    div = dv.reindex(df.index).fillna(0.0)
    r = (df.c + div) / df.c.shift(1) - 1
    return r.iloc[1:], df


def splice(t):
    r, df = tr_index(t)
    if t not in PROXY:
        return r, pd.Series(False, index=r.index)
    p, sd = PROXY[t]
    rp, _ = tr_index(p)
    eff = max(pd.Timestamp(sd), df.index.min())
    live = r[r.index > eff] if df.index.min() >= eff else r[r.index >= eff]
    pre = rp[rp.index <= eff] if df.index.min() >= eff else rp[rp.index < eff]
    s = pd.concat([pre, live]).sort_index()
    return s, pd.Series(s.index < eff, index=s.index)


def sim(R, w, c, check, band=.2, fill_lag=1, calendar=False):
    """R: (T,N) daily returns. check: bool (T,). Check after close t, trade at close t+fill_lag."""
    T, N = R.shape
    H = w * (1 - c); V = np.empty(T); pend = -1; n = 0; dates = []; fees = 0.0
    for t in range(T):
        H = H * (1 + R[t])
        if pend == t:
            W = H.sum(); tr = w * W - H; fee = (np.abs(tr) * c).sum(); fees += fee / W
            H = w * (W - fee); n += 1; dates.append(t); pend = -1
        if check[t] and pend < 0:
            W = H.sum()
            if calendar or (np.abs(H / W / w - 1) > band).any():
                if fill_lag == 0:
                    tr = w * W - H; fee = (np.abs(tr) * c).sum(); fees += fee / W
                    H = w * (W - fee); n += 1; dates.append(t)
                else:
                    pend = t + fill_lag
        V[t] = H.sum()
    return V, n, dates, fees


def stats(V, idx):
    v = pd.Series(np.r_[1.0, V]); yrs = len(V) / 252
    r = v.pct_change().dropna()
    return dict(cagr=v.iloc[-1] ** (1 / yrs) - 1, vol=r.std() * 252 ** .5, mdd=(v / v.cummax() - 1).min(),
                w12=(v / v.shift(252) - 1).min())


def masks(idx):
    s = pd.Series(np.arange(len(idx)), index=idx)
    me = (s.groupby(idx.to_period("M")).transform("max") == s).values
    ann = np.zeros(len(idx), bool); ann[np.where(me)[0][11::12]] = True
    return dict(daily=np.ones(len(idx), bool), monthly=me, annual=ann, none=np.zeros(len(idx), bool))


def window(proxy, tick, w):
    cols = {t: (splice(t)[0] if proxy else tr_index(t)[0]) for t in tick}
    R = pd.DataFrame(cols).dropna()
    return R


out = {}
# --- data cross-check vs fresh fetch (through 2025-11) and vs Yahoo adjclose ---
for t in ["KMLM", "AVUV", "TAIL", "PHYS"]:
    a, _ = tr_index(t, DL); b, _ = tr_index(t, DL2)
    j = a.index.intersection(b.index)
    df, _ = raw(t); ya = df.a.pct_change().dropna()
    jj = a.index.intersection(ya.index)
    out[f"data_{t}"] = dict(max_abs_diff_vs_fresh=float((a[j] - b[j]).abs().max()),
                            n_days_diff_vs_yahooadj_gt1bp=int(((a[jj] - ya[jj]).abs() > 1e-4).sum()),
                            worst_vs_yahooadj=str((a[jj] - ya[jj]).abs().idxmax().date()))
for t in ["QUAL","AVDV","AVEM","ASFYX","DFSVX","DISVX","DFEMX"]:
    a, df = tr_index(t); ya = df.a.pct_change().dropna(); jj = a.index.intersection(ya.index); dd=(a[jj]-ya[jj]).abs()
    out[f"data_{t}"] = dict(n_gt1bp=int((dd>1e-4).sum()), worst=str(dd.idxmax().date()), worst_val=float(dd.max()))
# KMLM ex-date total return check
r, df = tr_index("KMLM"); ru, _ = tr_index("KMLM", fix=False)
out["kmlm_exday"] = dict(corrected=float(r[pd.Timestamp("2022-12-28")]), vendor=float(ru[pd.Timestamp("2022-12-28")]),
                         cum_effect=float((1 + r).prod() / (1 + ru).prod() - 1))
w = np.array(list(TGT.values())); tick = list(TGT); c = np.array([CB[t] for t in tick]) * 1e-4
for lab, prox, tk, ww in [("A", False, tick, w), ("B", True, tick, w),
                          ("C", True, tick[:-1], w[:-1] / w[:-1].sum())]:
    R = window(prox, tk, ww); cc = np.array([CB[t] for t in tk]) * 1e-4
    m = masks(R.index); res = {"start_first_ret": str(R.index[0].date()), "end": str(R.index[-1].date()), "n": len(R)}
    for arm, ck, cal, lag in [("daily", "daily", False, 1), ("monthly", "monthly", False, 1), ("monthly_sameclose", "monthly", False, 0),
                              ("annual", "annual", True, 1), ("bh", "none", False, 1)]:
        V, n, ds, fees = sim(R.values, ww, cc, m[ck], calendar=cal, fill_lag=lag)
        st = stats(V, R.index); st.update(n_reb=n, fee_drag_bps=fees / (len(R) / 252) * 1e4,
                                          first_dates=[str(R.index[i].date()) for i in ds[:6]])
        res[arm] = st
    out[lab] = res
    if lab == "A":
        # independent engine replication: call repo engine.simulate as coded
        sys.path.insert(0, "/home/user/uranium-dashboard/barbell-lab/src")
        try:
            import os; os.chdir("/home/user/uranium-dashboard/barbell-lab")
            from barbell.backtest import engine
            from barbell.backtest.metrics import cagr as ecagr, max_drawdown as emdd
            e = engine.simulate(R, TGT, mode="threshold")
            out["A"]["repo_engine_monthly"] = dict(cagr=float(ecagr(e.returns)), n_reb=e.n_rebalances)
        except Exception as ex:
            out["A"]["repo_engine_monthly"] = repr(ex)
    # own bootstrap: monthly blocks, daily - monthly, bh - monthly, annual - monthly
    if lab in ("A", "B"):
        rng = np.random.default_rng(123); per = R.index.to_period("M")
        blocks = [np.where(per == p)[0] for p in per.unique()]; T = len(R); Rv = R.values
        dd, bh, an = [], [], []
        for _ in range(300):
            rows, me = [], []
            while len(rows) < T:
                b = blocks[rng.integers(len(blocks))]; rows.extend(b); me.append(len(rows) - 1)
            rows = np.array(rows[:T]); Rb = Rv[rows]
            mm = np.zeros(T, bool); mm[[x for x in me if x < T]] = True
            aa = np.zeros(T, bool); aa[np.where(mm)[0][11::12]] = True
            yrs = T / 252; g = lambda V: V[-1] ** (1 / yrs) - 1
            vm = g(sim(Rb, ww, cc, mm)[0]); vd = g(sim(Rb, ww, cc, np.ones(T, bool))[0])
            vb = g(sim(Rb, ww, cc, np.zeros(T, bool))[0]); va = g(sim(Rb, ww, cc, aa, calendar=True)[0])
            dd.append(vd - vm); bh.append(vb - vm); an.append(va - vm)
        q = lambda x: [round(float(np.mean(x)) * 1e4, 1), round(float(np.percentile(x, 2.5)) * 1e4, 1),
                       round(float(np.percentile(x, 97.5)) * 1e4, 1), round(float(np.mean(np.array(x) > 0)), 2)]
        out[lab]["boot300"] = dict(daily_minus_monthly=q(dd), bh_minus_monthly=q(bh), annual_minus_monthly=q(an))
json.dump(out, open(D / "check2_out.json", "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
