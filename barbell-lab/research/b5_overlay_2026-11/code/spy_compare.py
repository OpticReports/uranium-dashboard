"""B.5 live book vs SPY (total return) on the study's windows. Writes ../spy_compare.json and ../charts/13_vs_spy.png."""
import json, os, pickle
import numpy as np, pandas as pd
import common as C, engine as E

p = C.load_panel(); S = pickle.load(open(os.path.join(C.CACHE, "series.pkl"), "rb"))["T1"]
cal = S["cal"]; live = pd.Series(S["live"], index=cal); cash = pd.Series(S["cash"], index=cal)
spy = p["ret"]["SPY"].reindex(cal); sptr = p["ret"]["^SP500TR"].reindex(cal)
assert spy.loc["2007-06-01":].notna().all()
WIN = {"2007-06..2026-11": "2007-06-01", "2010-01..2026-11": "2010-01-01", "2017-04..2026-11": "2017-04-07"}

def stats(r, c):
    m = E.metrics(r.values, c.values)
    nav = (1 + r).cumprod(); yr = (1 + r).groupby(r.index.year).prod() - 1
    dd = nav / nav.cummax() - 1; trough = dd.idxmin(); peak = nav.loc[:trough].idxmax()
    rec = nav.loc[trough:][nav.loc[trough:] >= nav.loc[peak]]
    return dict(cagr=m["cagr"], vol=m["vol"], sharpe=m["sharpe"], sortino=m["sortino"], maxdd=m["maxdd"], calmar=m["calmar"],
                ulcer=m["ulcer"], worst252=m["worst252"], worst_year=float(yr.min()), worst_year_when=int(yr.idxmin()),
                dd_peak=str(peak.date()), dd_trough=str(trough.date()), dd_recovered=str(rec.index[0].date()) if len(rec) else "not yet",
                total=m["total"])

out = {}
for name, a in WIN.items():
    i = cal >= pd.Timestamp(a)
    out[name] = dict(b5=stats(live[i], cash[i]), spy=stats(spy[i], cash[i]), spx_tr_check=stats(sptr[i], cash[i]),
                     corr_daily=float(np.corrcoef(live[i], spy[i])[0, 1]),
                     corr_monthly=float(((1 + live[i]).resample("ME").prod() - 1).corr((1 + spy[i]).resample("ME").prod() - 1)),
                     beta=float(np.cov(live[i], spy[i])[0, 1] / spy[i].var()))
yrs = list(range(2008, 2027))
out["calendar_years"] = {y: dict(b5=float((1 + live.loc[str(y)]).prod() - 1), spy=float((1 + spy.loc[str(y)]).prod() - 1)) for y in yrs}
ep = [("2008 crisis", "2007-10-09", "2009-03-09"), ("2018 Q4", "2018-09-20", "2018-12-24"), ("2020 fall", "2020-02-19", "2020-03-23"),
      ("2020 rebound", "2020-03-24", "2020-12-31"), ("2022", "2022-01-03", "2022-10-12"), ("2025 tariff drop", "2025-02-19", "2025-04-08")]
out["episodes"] = {n: dict(b5=float((1 + live.loc[a:b]).prod() - 1), spy=float((1 + spy.loc[a:b]).prod() - 1)) for n, a, b in ep}
json.dump(out, open(os.path.join(C.STUDY, "spy_compare.json"), "w"), indent=1)

for n, w in out.items():
    if n in ("calendar_years", "episodes"): continue
    print(n, f"corr d {w['corr_daily']:.2f} m {w['corr_monthly']:.2f} beta {w['beta']:.2f}")
    for k in ("b5", "spy", "spx_tr_check"):
        s = w[k]; print(f"  {k:13s} CAGR {s['cagr']*100:5.2f} vol {s['vol']*100:5.1f} Sh {s['sharpe']:.2f} Sort {s['sortino']:.2f} DD {s['maxdd']*100:6.1f} Calmar {s['calmar']:.2f} ulcer {s['ulcer']*100:4.1f} worst252 {s['worst252']*100:6.1f} worstY {s['worst_year']*100:6.1f} ({s['worst_year_when']}) dd {s['dd_peak']}->{s['dd_trough']} rec {s['dd_recovered']} total {s['total']*100:.0f}%")
print({y: (round(v['b5']*100,1), round(v['spy']*100,1)) for y, v in out["calendar_years"].items()})
print({k: (round(v['b5']*100,1), round(v['spy']*100,1)) for k, v in out["episodes"].items()})
print('B5 beats SPY in', sum(v['b5'] > v['spy'] for v in out['calendar_years'].values()), 'of', len(yrs), 'calendar years')

# ---- risk-matched SPY: SPY + T-bills mixed monthly-rebalanced to B.5's own volatility per window
def mix(w, idx):
    W = np.array([[w, 1 - w]]); R = np.column_stack([spy[idx].values, cash[idx].values]); me = np.zeros(idx.sum(), bool)
    ym = cal[idx].year * 12 + cal[idx].month; me[:-1] = ym[1:] != ym[:-1]
    return pd.Series(E.simulate(np.ascontiguousarray(R), np.repeat(W, idx.sum(), 0), np.array([1e-4, 1e-4]), me, 0.0, 10 ** 9, 1e-9, False,
                                np.zeros(2, bool), 0.0, 0, idx.sum())[0], index=cal[idx])
for name, a in WIN.items():
    i = cal >= pd.Timestamp(a); target = live[i].std(); lo, hi = 0.0, 1.0
    for _ in range(40):
        w = (lo + hi) / 2; (lo, hi) = (w, hi) if mix(w, i).std() < target else (lo, w)
    out[name]["spy_risk_matched"] = dict(stats(mix(w, i), cash[i]), spy_weight=w)
    s = out[name]["spy_risk_matched"]
    print(name, f"SPY {w*100:.0f}% / bills {100-w*100:.0f}%: CAGR {s['cagr']*100:.2f} vol {s['vol']*100:.1f} Sh {s['sharpe']:.2f} DD {s['maxdd']*100:.1f} ulcer {s['ulcer']*100:.1f} worst252 {s['worst252']*100:.1f}")
json.dump(out, open(os.path.join(C.STUDY, "spy_compare.json"), "w"), indent=1)
