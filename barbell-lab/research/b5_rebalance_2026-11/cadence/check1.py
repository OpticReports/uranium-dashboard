"""Counter-agent #1 independent re-derivation of the B.5 v1.0 cadence study.
Own loader, own KMLM correction, own splice, own date masks, plain per-day loop
simulator (engine.py semantics, with a next-close fill option), cross-checked
against the repo's engine.simulate itself (imported read-only)."""
import json, sys, os
from pathlib import Path
import numpy as np, pandas as pd

D = Path(sys.argv[1]); DL = D / "dl"
REPO = "/home/user/uranium-dashboard/barbell-lab"
W = {"AVUV": .25, "AVDV": .19, "PHYS": .18, "KMLM": .14, "AVEM": .10, "QUAL": .09, "TAIL": .05}
COST = {"AVUV": 5, "AVDV": 10, "PHYS": 8, "KMLM": 10, "AVEM": 8, "QUAL": 3, "TAIL": 12}
PROXY = {"AVUV": ("DFSVX", "2019-10-01"), "AVDV": ("DISVX", "2019-10-01"), "KMLM": ("ASFYX", "2020-12-02"),
         "AVEM": ("DFEMX", "2019-10-01"), "PHYS": ("GLD", "2010-03-01")}
out = {}


def raw(t):
    j = json.load(open(DL / f"{t}.json"))["chart"]["result"][0]
    d = pd.to_datetime(j["timestamp"], unit="s").tz_localize("UTC").tz_convert("America/New_York").date
    df = pd.DataFrame({"adj": j["indicators"]["adjclose"][0]["adjclose"],
                       "close": j["indicators"]["quote"][0]["close"]}, index=pd.DatetimeIndex(d))
    df = df[df.index <= "2026-11-13"].dropna()
    return df, j.get("events", {})


def series(t):
    df, ev = raw(t)
    s = df["adj"].copy()
    if t == "KMLM":
        ex = pd.Timestamp("2022-12-28")
        divs = {pd.Timestamp(pd.to_datetime(int(k), unit="s").date()): v["amount"] for k, v in ev["dividends"].items()}
        assert abs(divs[ex] - 2.481) < 1e-9
        i = df.index.get_loc(ex); pc = df["close"].iloc[i - 1]
        # Yahoo factor check: adj/close jump at ex == 1/(1 - vendor/prev)
        r = df["adj"] / df["close"]; obs = r.iloc[i] / r.iloc[i - 1]
        out["kmlm_yahoo_factor_obs"] = float(obs); out["kmlm_yahoo_factor_expected"] = float(1 / (1 - 2.481 / pc))
        s.iloc[:i] *= (1 - 4.0377 / pc) / (1 - 2.481 / pc)
        out["kmlm_scale"] = float((1 - 4.0377 / pc) / (1 - 2.481 / pc)); out["kmlm_prev_close"] = float(pc)
        out["kmlm_exday_total_ret_corrected"] = float(s.iloc[i] / s.iloc[i - 1] - 1)
        out["kmlm_exday_price_ret"] = float(df["close"].iloc[i] / pc - 1)
    return s


def splice(t):
    s = series(t)
    if t not in PROXY: return s
    p, sd = PROXY[t]; eff = max(pd.Timestamp(sd), s.index[0])
    pr = series(p).pct_change()
    live = s[s.index >= eff]
    pre_dates = pr.index[pr.index < eff]
    # level(d) for d < eff: level(eff) / prod_{u in (d, eff]} (1+r_proxy(u))
    rr = pr.loc[pre_dates[0]:eff].iloc[1:]  # returns on dates after first pre-date through eff
    assert rr.index[-1] == eff
    g = (1 + rr)[::-1].cumprod()[::-1]  # product from u..eff
    # g indexed by d_1..eff; level at d_{k} uses product over d_{k+1}..eff = g at d_{k+1}
    levels = pd.Series(live.iloc[0] / g.values, index=pre_dates[:len(g)])
    return pd.concat([levels, live]).sort_index()


def masks(idx):
    nxt = list(idx[1:]) + [None]
    me = np.array([n is None or n.month != d.month for d, n in zip(idx, nxt)])
    qe = np.array([n is None or (n.month - 1) // 3 != (d.month - 1) // 3 or n.year != d.year for d, n in zip(idx, nxt)])
    # last trading day of the Mon-Fri week: next trading day is in a later ISO week
    wk = np.array([n is None or (n - pd.Timedelta(days=n.weekday())) != (d - pd.Timedelta(days=d.weekday())) for d, n in zip(idx, nxt)])
    return dict(daily=np.ones(len(idx), bool), weekly=wk, monthly=me, quarterly=qe)


def sim(R, w, c, check, band=.2, mode="threshold", nextday=True, cal_m=12):
    h = w * (1 - c); V = [1.0]; pend = False; n = 0; mcount = 0; dates = []; me = check
    for t in range(R.shape[0]):
        h = h * (1 + R[t])
        if pend:
            Wt = h.sum(); fee = (np.abs(w * Wt - h) * c).sum(); h = w * (Wt - fee); n += 1; pend = False; dates.append(t)
        if check[t]:
            Wt = h.sum(); trig = False
            if mode == "threshold": trig = (np.abs(h / Wt / w - 1) > band).any()
            elif mode == "calendar":
                mcount += 1; trig = mcount >= cal_m
                if trig: mcount = 0
            if trig:
                if nextday: pend = True
                else:
                    fee = (np.abs(w * Wt - h) * c).sum(); h = w * (Wt - fee); n += 1; dates.append(t)
        V.append(h.sum())
    return np.array(V), n, dates


def stats(V, idx0, n):
    yrs = (len(V) - 1) / 252
    v = pd.Series(V)
    return dict(cagr=round((V[-1] ** (1 / yrs) - 1) * 100, 3), maxdd=round(float((v / v.cummax() - 1).min()) * 100, 2), n_reb=n)


def window(tick, proxy):
    P = pd.DataFrame({t: (splice(t) if proxy else series(t)) for t in tick}).dropna()
    return P


res = {}
spy = series("SPY").index
for lab, tick, proxy in [("A", list(W), False), ("B", list(W), True), ("C", [t for t in W if t != "TAIL"], True)]:
    P = window(tick, proxy); R = P.pct_change().iloc[1:]; idx = R.index
    w = np.array([W[t] for t in tick]); w = w / w.sum(); c = np.array([COST[t] for t in tick]) * 1e-4
    m = masks(idx)
    miss = [str(d.date()) for d in spy[(spy >= P.index[0]) & (spy <= P.index[-1])] if d not in P.index]
    row = dict(start=str(P.index[0].date()), end=str(idx[-1].date()), n=len(idx), missing_vs_SPY=miss[:10], n_missing=len(miss))
    for nm, ck in [("daily", "daily"), ("weekly", "weekly"), ("monthly", "monthly"), ("quarterly", "quarterly")]:
        V, n, dd = sim(R.values, w, c, m[ck]); row[nm] = stats(V, idx, n)
        if nm in ("daily", "monthly"): row[nm]["dates"] = [str(idx[i].date()) for i in dd]
    V, n, dd = sim(R.values, w, c, m["monthly"], mode="calendar"); row["annual_cal"] = stats(V, idx, n); row["annual_cal"]["dates"] = [str(idx[i].date()) for i in dd]
    V, n, _ = sim(R.values, w, c, np.zeros(len(idx), bool)); row["buyhold"] = stats(V, idx, n)
    V, n, _ = sim(R.values, w, c, m["monthly"], nextday=False); row["monthly_sameclose"] = stats(V, idx, n)
    V, n, _ = sim(R.values, w, 0 * c, m["daily"]); row["daily_zero_cost"] = stats(V, idx, n)
    # repo engine, same-close, threshold + calendar
    try:
        os.environ["BARBELL_ROOT"] = REPO; sys.path.insert(0, REPO + "/src")
        from barbell.backtest import engine
        for mode in ("threshold", "calendar", "none"):
            sr = engine.simulate(R, dict(zip(tick, w)), mode=mode)
            v = (1 + sr.returns).cumprod().values
            row[f"engine_{mode}"] = stats(np.r_[1.0, v], idx, sr.n_rebalances)
    except Exception as e:
        row["engine_err"] = repr(e)
    res[lab] = row
    print(lab, {k: v for k, v in row.items() if k not in ("missing_vs_SPY",)} if False else "")
    for k, v in row.items():
        if isinstance(v, dict): print("  ", k, {a: b for a, b in v.items() if a != "dates"})
        else: print("  ", k, v)
    if lab == "A":
        RA, idxA, wA, cA, mA = R.values, idx, w, c, m
    if lab in ("A", "B"):
        print("   monthly dates", row["monthly"]["dates"]); print("   daily dates", row["daily"]["dates"])

# spot-check holiday mechanics in A
mw = masks(idxA)
for d in ["2021-04-01", "2021-04-02", "2022-04-14", "2023-04-06", "2024-03-28", "2024-12-31", "2025-07-03", "2026-04-02", "2026-04-03"]:
    d = pd.Timestamp(d)
    if d in idxA: i = idxA.get_loc(d); print("  ", d.date(), d.day_name(), "weekly", mw["weekly"][i], "me", mw["monthly"][i], "qe", mw["quarterly"][i])
    else: print("  ", d.date(), "not a trading day in data")
print({k: v for k, v in out.items()})

# independent bootstrap of daily-minus-monthly in A (monthly iid blocks, 300 paths)
rng = np.random.default_rng(123)
per = idxA.to_period("M"); blocks = [np.where(per == p)[0] for p in per.unique()]
diffs, bh = [], []
for p in range(300):
    rows = []; ends = []
    while len(rows) < len(idxA):
        b = blocks[rng.integers(len(blocks))]; rows.extend(b); ends.append(len(rows) - 1)
    rows = np.array(rows[:len(idxA)]); Rb = RA[rows]
    me = np.zeros(len(rows), bool); me[[e for e in ends if e < len(rows)]] = True
    vd = sim(Rb, wA, cA, np.ones(len(rows), bool))[0][-1]; vm = sim(Rb, wA, cA, me)[0][-1]; vb = sim(Rb, wA, cA, np.zeros(len(rows), bool))[0][-1]
    y = len(rows) / 252
    diffs.append((vd ** (1 / y) - vm ** (1 / y)) * 1e4); bh.append((vb ** (1 / y) - vm ** (1 / y)) * 1e4)
print("boot A daily-monthly bps mean %.1f CI [%.0f, %.0f]" % (np.mean(diffs), *np.percentile(diffs, [2.5, 97.5])))
print("boot A buyhold-monthly bps mean %.1f CI [%.0f, %.0f]" % (np.mean(bh), *np.percentile(bh, [2.5, 97.5])))
json.dump(dict(res=res, out=out), open(D / "check1_results.json", "w"), indent=1, default=str)
