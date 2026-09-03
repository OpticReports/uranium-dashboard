"""R9 Stage 2 — 112-arm size-conditional weight replay (registered d3339bb).

Baseline deviation (stated): live weights are equal over FOUR signals incl.
hype_divergence, which has no historical record; the replayable baseline is
equal over the three replayable signals (1/3 each) + runway 0.10, size-blind.
Portfolio: month-end composite -> top tercile, entered at NEXT day's close,
held one month, equal weight, XBI-excess. Paired inference vs baseline with
monthly block bootstrap; Westfall-Young max-T over the 111 non-baseline arms.
"""
import itertools
import json
import numpy as np
import pandas as pd

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad/r9"
BACKEND = "/home/user/uranium-dashboard/genomics-alpha-tracker/backend"
SEED, DRAWS = 20260827, 2000
rng = np.random.default_rng(SEED)

panel = pd.read_csv(f"{SC}/panel.csv", parse_dates=["date"])
bars = json.load(open(f"{BACKEND}/data/backtest_bars.json"))
px = pd.DataFrame({s: pd.DataFrame(b).assign(date=lambda d: pd.to_datetime(d["date"]))
                   .set_index("date")["adj_close"] for s, b in bars.items()}).sort_index()
ret = px.pct_change(fill_method=None)
xret = ret["XBI"]

# per-day cross-sectional 0-100 z-scaling of components (live convention)
def z100(g):
    out = {}
    for c in ("c_cat", "c_rev", "c_pos"):
        v = g[c]
        m, sd = v.mean(), v.std()
        out[c] = 50.0 + 15.0 * (v - m) / sd if sd and sd > 0 else pd.Series(50.0, index=v.index).where(v.notna())
    return pd.DataFrame(out)

Z = panel.groupby("date", group_keys=False).apply(z100, include_groups=False)
panel = pd.concat([panel, Z.add_suffix("_z")], axis=1)

TILTS = {
    "eq":   {"c_cat": 1/3, "c_rev": 1/3, "c_pos": 1/3},
    "cat40": {"c_cat": .40, "c_rev": .30, "c_pos": .30},
    "rev40": {"c_cat": .30, "c_rev": .40, "c_pos": .30},
    "pos40": {"c_cat": .30, "c_rev": .30, "c_pos": .40},
    "cat55": {"c_cat": .55, "c_rev": .225, "c_pos": .225},
    "rev55": {"c_cat": .225, "c_rev": .55, "c_pos": .225},
}
RUN_W = 0.10

def bucket_col(df, scheme):
    z = df["z1_mktcap"]
    if scheme == "B1":
        return np.where(z < 1e9, "S", np.where(z < 10e9, "M", "L"))
    if scheme == "B2":
        q = df.groupby("date")["z1_mktcap"].rank(pct=True)
        return np.where(q <= 1/3, "S", np.where(q > 2/3, "L", "M"))
    return np.where(df["z3_commercial"] == 1, "L", "S")

for sch in ("B1", "B2", "B3"):
    panel[f"bk_{sch}"] = bucket_col(panel, sch)

def composite(df, wmap_by_bucket, scheme):
    w = df[f"bk_{scheme}"].map(wmap_by_bucket)
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    for c in ("c_cat", "c_rev", "c_pos"):
        wi = w.map(lambda x, c=c: x[c])
        v = df[f"{c}_z"]
        ok = v.notna()
        num[ok] += (wi * v)[ok]
        den[ok] += wi[ok]
    comp = num / den.replace(0, np.nan)
    pen = df["c_run"].fillna(0.0)
    return comp - RUN_W * pen             # runway enters negatively (live law)

# month-end signal dates -> next-day entry, hold through next month-end
dates = sorted(panel.date.unique())
dser = pd.Series(dates)
month_ends = dser.groupby(dser.dt.to_period("M")).max().tolist()

def run_arm(wmap, scheme):
    p = panel.copy()
    p["comp"] = composite(p, wmap, scheme)
    daily = []
    for i, me in enumerate(month_ends[:-1]):
        g = p[p.date == me].dropna(subset=["comp"])
        if len(g) < 9:
            continue
        top = g[g["comp"] >= g["comp"].quantile(2/3)]["symbol"].tolist()
        nxt = month_ends[i + 1]
        w_ = ret.loc[(ret.index > me) & (ret.index <= nxt), top]
        port = w_.mean(axis=1, skipna=True).shift(-0)      # equal weight
        # entry at NEXT day's close: drop the first day after the signal
        port = port.iloc[1:]
        ex = port - xret.reindex(port.index)
        daily.append(ex)
    r = pd.concat(daily).dropna()
    return r

ARMS = {"baseline": (dict.fromkeys(("S", "M", "L"), TILTS["eq"]), "B1")}
for sch in ("B1", "B2", "B3"):
    for tS, tL in itertools.product(TILTS, TILTS):
        ARMS[f"{sch}:{tS}|{tL}"] = (
            {"S": TILTS[tS], "M": TILTS["eq"], "L": TILTS[tL]}, sch)
print(len(ARMS), "arms (incl. baseline; monotone arms folded into grid: "
      "cat55|rev55 IS the monotone extreme per scheme)")

rets = {}
for name, (wmap, sch) in ARMS.items():
    rets[name] = run_arm(wmap, sch)
base = rets["baseline"]

def ir(r):
    return float(r.mean() / r.std() * np.sqrt(252)) if len(r) and r.std() > 0 else np.nan

rows, nulls = [], []
months_idx = base.index.to_period("M")
for name, r in rets.items():
    a = pd.DataFrame({"arm": r, "base": base}).dropna()
    d = (a["arm"] - a["base"])
    row = {"arm": name, "days": len(a), "IR": round(ir(r), 3),
           "IR_base": round(ir(base), 3),
           "ann_excess_vs_base": round(d.mean() * 252 * 100, 2)}
    if name != "baseline" and len(a) > 200:
        dm = d.groupby(d.index.to_period("M")).sum()   # monthly cluster sums
        M = dm.values
        picks = rng.integers(0, len(M), size=(DRAWS, len(M)))
        bs = M[picks].mean(axis=1) * 12
        obs = M.mean() * 12
        se = bs.std()
        row["t"] = round(obs / se, 2) if se > 0 else 0.0
        row["p_raw"] = round(float(2 * min((bs <= 0).mean(), (bs >= 0).mean())), 4)
        nulls.append((bs - obs) / se if se > 0 else np.zeros(DRAWS))
        # split-half sign
        half = dm.index[len(dm) // 2]
        row["h1"] = round(dm[dm.index < half].mean() * 12 * 100, 2)
        row["h2"] = round(dm[dm.index >= half].mean() * 12 * 100, 2)
    rows.append(row)

null_mat = np.abs(np.vstack(nulls))
maxT = null_mat.max(axis=0)
j = 0
for row in rows:
    if "t" in row:
        row["p_wy"] = round(float((maxT >= abs(row["t"])).mean()), 4)
res = pd.DataFrame(rows)
res.to_csv(f"{SC}/stage2_results.csv", index=False)
print("baseline IR:", res[res.arm == "baseline"]["IR"].iloc[0])
top = res[res.arm != "baseline"].sort_values("p_wy").head(15)
print(top.to_string(index=False))
surv = res[(res.get("p_wy", 1) < 0.05) & (res.h1 * res.h2 > 0)] if "p_wy" in res else res.iloc[0:0]
print(f"\nSURVIVORS (WY p<0.05 AND same-sign halves): {len(surv)}")
if len(surv):
    print(surv.to_string(index=False))
