"""Counter-agent audit D: flags multiplicity + clustering + join.
- Recompute S-minus-L gaps with (a) symbol|month clusters (as run),
  (b) SYMBOL-level clusters (character-of-the-name dependence), for all 6 flags.
- Holm correction across the 6-test family (they sat outside the WY family —
  registration deviation).
- Join spot-check: size used = z1 at fire_date (PIT), r_net = net grading."""
import json
import numpy as np
import pandas as pd

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad/r9"
BACKEND = "/home/user/uranium-dashboard/genomics-alpha-tracker/backend"
rng = np.random.default_rng(20260827)

panel = pd.read_csv(f"{SC}/panel.csv", parse_dates=["date"])
sizes = panel.set_index(["date", "symbol"])["z1_mktcap"]
cr = json.load(open(f"{BACKEND}/data/backtest_calls_10y_results.json"))["call_rows"]
frows = []
for flag, rows_ in cr.items():
    for r in rows_:
        z = sizes.get((pd.Timestamp(r["fire_date"]), r.get("symbol")), np.nan)
        if not np.isnan(z) and r.get("r_net") is not None:
            frows.append({"flag": flag, "symbol": r["symbol"],
                          "month": r["entry_month"], "fire_date": r["fire_date"],
                          "bucket": "S" if z < 1e9 else ("M" if z < 10e9 else "L"),
                          "r": r["r_net"], "z": z})
fdf = pd.DataFrame(frows)

def gap_p(g, clcol, draws=4000):
    gs, gl = g[g.bucket == "S"], g[g.bucket == "L"]
    g2 = g[g.bucket.isin(["S", "L"])].copy()
    obs = gs.r.mean() - gl.r.mean()
    agg = g2.groupby(clcol).apply(
        lambda x: pd.Series({"sS": x[x.bucket == "S"].r.sum(),
                             "nS": float((x.bucket == "S").sum()),
                             "sL": x[x.bucket == "L"].r.sum(),
                             "nL": float((x.bucket == "L").sum())}),
        include_groups=False)
    A = agg.values
    picks = rng.integers(0, len(A), size=(draws, len(A)))
    T = A[picks].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        bs = T[:, 0] / T[:, 1] - T[:, 2] / T[:, 3]
    bs = bs[np.isfinite(bs)]
    p = 2 * min((bs <= 0).mean(), (bs >= 0).mean())
    return obs, max(p, 1.0 / draws), len(A)

fdf["sm"] = fdf.symbol + "|" + fdf.month
res = []
for flag, g in fdf.groupby("flag"):
    ns, nl = (g.bucket == "S").sum(), (g.bucket == "L").sum()
    if ns < 15 or nl < 15:
        continue
    o1, p1, k1 = gap_p(g, "sm")
    o2, p2, k2 = gap_p(g, "symbol")
    res.append({"flag": flag, "gap": round(o1, 3), "nS": ns, "nL": nl,
                "S_syms": g[g.bucket == "S"].symbol.nunique(),
                "L_syms": g[g.bucket == "L"].symbol.nunique(),
                "p_symmonth": p1, "p_symbol": p2})
res = pd.DataFrame(res).sort_values("p_symmonth")
# Holm across the 6-test family, on each clustering
for col in ("p_symmonth", "p_symbol"):
    r = res.sort_values(col).reset_index(drop=True)
    m = len(r)
    adj, run = [], 0.0
    for i, p in enumerate(r[col]):
        run = max(run, min(1.0, (m - i) * p))
        adj.append(run)
    res.loc[r["flag"].map(lambda f: res.index[res.flag == f][0]).values,
            f"holm_{col[2:]}"] = adj
print(res.to_string(index=False))

# join spot-check: 3 rows by hand
print("\njoin spot-check (fire_date size is PIT z1 that day):")
for _, r in fdf[fdf.flag == "binary_event_within_n_days"].head(3).iterrows():
    z = sizes.get((pd.Timestamp(r.fire_date), r.symbol))
    print(f"  {r.symbol} fired {r.fire_date}: z1={z/1e9:.2f}B bucket={r.bucket} "
          f"r_net={r.r:+.2f}")
