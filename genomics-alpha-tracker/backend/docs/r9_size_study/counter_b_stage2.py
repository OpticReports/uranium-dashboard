"""Counter-agent audit B: Stage-2 implementation.
(i) groupby-apply/concat index-alignment proof; (ii) hand-computed composite;
(iii) same-day-leak check on the portfolio loop; (iv) skipped months census;
(v) arm family + split-half definition; (vi) independent baseline IR."""
import itertools
import json
import numpy as np
import pandas as pd

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad/r9"
BACKEND = "/home/user/uranium-dashboard/genomics-alpha-tracker/backend"

panel = pd.read_csv(f"{SC}/panel.csv", parse_dates=["date"])

# ---- (i) alignment proof ----
def z100(g):
    out = {}
    for c in ("c_cat", "c_rev", "c_pos"):
        v = g[c]
        m, sd = v.mean(), v.std()
        out[c] = 50.0 + 15.0 * (v - m) / sd if sd and sd > 0 else \
            pd.Series(50.0, index=v.index).where(v.notna())
    return pd.DataFrame(out)

Z = panel.groupby("date", group_keys=False).apply(z100, include_groups=False)
print("(i) index alignment:")
print("  panel.index unique:", panel.index.is_unique,
      " Z.index unique:", Z.index.is_unique)
print("  set-equal:", set(Z.index) == set(panel.index),
      " order-equal:", bool((Z.index == panel.index).all())
      if len(Z) == len(panel) else False)
merged = pd.concat([panel, Z.add_suffix("_z")], axis=1)
# brute-force check on 5 random dates: recompute z from scratch row-by-row
rng = np.random.default_rng(7)
dates_ck = rng.choice(panel.date.unique(), 5, replace=False)
bad = 0
for d in dates_ck:
    g = merged[merged.date == d]
    for c in ("c_cat", "c_rev", "c_pos"):
        v = g[c]
        m, sd = v.mean(), v.std()
        if sd and sd > 0:
            exp = 50 + 15 * (v - m) / sd
            if not np.allclose(exp.dropna(), g[f"{c}_z"].dropna(), atol=1e-10):
                bad += 1
print(f"  brute-force recheck on 5 dates x 3 cols: {bad} mismatches")

# ---- (ii) hand-computed composite for one (date,symbol) ----
TILTS = {"eq": {"c_cat": 1/3, "c_rev": 1/3, "c_pos": 1/3},
         "cat40": {"c_cat": .40, "c_rev": .30, "c_pos": .30}}
d0 = pd.Timestamp("2024-06-28")
g = merged[merged.date == d0]
r = g[g.symbol == "CRSP"].iloc[0]
w = TILTS["cat40"]  # CRSP mid bucket in a B1 arm gets "eq"; test S-tilt map anyway
num = den = 0.0
for c in ("c_cat", "c_rev", "c_pos"):
    v = r[f"{c}_z"]
    if not np.isnan(v):
        num += w[c] * v
        den += w[c]
hand = num / den - 0.10 * (0.0 if np.isnan(r["c_run"]) else r["c_run"])
print(f"(ii) hand composite CRSP {d0.date()} cat40: {hand:.4f} "
      f"(z's: {[round(r[f'{c}_z'],2) if not np.isnan(r[f'{c}_z']) else None for c in ('c_cat','c_rev','c_pos')]}, c_run={r['c_run']})")

# replicate stage2's composite() for the same row
def bucket_col(df, scheme):
    z = df["z1_mktcap"]
    return np.where(z < 1e9, "S", np.where(z < 10e9, "M", "L"))
merged["bk_B1"] = bucket_col(merged, "B1")
wmap = {"S": TILTS["cat40"], "M": TILTS["cat40"], "L": TILTS["cat40"]}
df = merged[merged.date == d0].copy()
wcol = df["bk_B1"].map(wmap)
num = pd.Series(0.0, index=df.index); den = pd.Series(0.0, index=df.index)
for c in ("c_cat", "c_rev", "c_pos"):
    wi = wcol.map(lambda x, c=c: x[c]); v = df[f"{c}_z"]; ok = v.notna()
    num[ok] += (wi * v)[ok]; den[ok] += wi[ok]
comp = (num / den.replace(0, np.nan)) - 0.10 * df["c_run"].fillna(0.0)
got = comp[df.symbol == "CRSP"].iloc[0]
print(f"     stage2-style composite: {got:.4f}  match={abs(got-hand)<1e-10}")

# ---- (iii) leak check + (iv) skipped months ----
bars = json.load(open(f"{BACKEND}/data/backtest_bars.json"))
px = pd.DataFrame({s: pd.DataFrame(b).assign(date=lambda d: pd.to_datetime(d["date"]))
                   .set_index("date")["adj_close"] for s, b in bars.items()}).sort_index()
ret = px.pct_change(fill_method=None)
dser = pd.Series(sorted(panel.date.unique()))
month_ends = dser.groupby(dser.dt.to_period("M")).max().tolist()
me = month_ends[100]; nxt = month_ends[101]
w_ = ret.loc[(ret.index > me) & (ret.index <= nxt), ["CRSP", "ILMN"]]
first_used = w_.index[1]  # after .iloc[1:]
print(f"(iii) signal {me.date()}: first return day USED {first_used.date()} = "
      f"close({w_.index[0].date()})->close({first_used.date()}); "
      f"entry at next-day close, no same-day leak: {w_.index[0] > me}")

# skipped months (<9 names with composite) under baseline weights
wmap_eq = dict.fromkeys(("S", "M", "L"), TILTS["eq"])
skipped = []
for i, m in enumerate(month_ends[:-1]):
    df = merged[merged.date == m].copy()
    wcol = df["bk_B1"].map(wmap_eq)
    num = pd.Series(0.0, index=df.index); den = pd.Series(0.0, index=df.index)
    for c in ("c_cat", "c_rev", "c_pos"):
        wi = wcol.map(lambda x, c=c: x[c]); v = df[f"{c}_z"]; ok = v.notna()
        num[ok] += (wi * v)[ok]; den[ok] += wi[ok]
    comp = (num / den.replace(0, np.nan)) - 0.10 * df["c_run"].fillna(0.0)
    if comp.notna().sum() < 9:
        skipped.append(m)
print(f"(iv) months skipped (<9 composite names): {len(skipped)} of "
      f"{len(month_ends)-1}; skipped range: "
      f"{skipped[0].date() if skipped else '-'} -> {skipped[-1].date() if skipped else '-'}")

# ---- (v) family + split-half month ----
r2 = pd.read_csv(f"{SC}/stage2_results.csv")
print(f"(v) arms in results: {len(r2)} (registered 112; grid 108 + baseline = 109; "
      f"3 monotone-interpolation arms NOT run)")
base = r2[r2.arm == "baseline"]
d = r2[r2.arm != "baseline"]
print(f"    arms with t (in WY family): {d['t'].notna().sum()}")
print(f"    best raw p: {d.p_raw.min():.4f} ({d.loc[d.p_raw.idxmin(),'arm']}), "
      f"its p_wy={d.loc[d.p_raw.idxmin(),'p_wy']:.4f}")
# what calendar month is the code's split-half boundary?
n_months = len(pd.period_range(dser.min(), dser.max(), freq='M'))
# approximate: the diff series months = baseline months; recompute directly
print(f"    registered split: 2021-07-01; code splits at median month of the "
      f"paired series (panel spans {dser.min().date()} -> {dser.max().date()}, "
      f"median month ≈ {pd.period_range(dser.min(), dser.max(), freq='M')[n_months//2]})")

# ---- (vi) independent baseline IR ----
def run_arm(wmap):
    daily = []
    for i, m in enumerate(month_ends[:-1]):
        df = merged[merged.date == m].copy()
        wcol = df["bk_B1"].map(wmap)
        num = pd.Series(0.0, index=df.index); den = pd.Series(0.0, index=df.index)
        for c in ("c_cat", "c_rev", "c_pos"):
            wi = wcol.map(lambda x, c=c: x[c]); v = df[f"{c}_z"]; ok = v.notna()
            num[ok] += (wi * v)[ok]; den[ok] += wi[ok]
        df["comp"] = (num / den.replace(0, np.nan)) - 0.10 * df["c_run"].fillna(0.0)
        g = df.dropna(subset=["comp"])
        if len(g) < 9:
            continue
        top = g[g["comp"] >= g["comp"].quantile(2/3)]["symbol"].tolist()
        w_ = ret.loc[(ret.index > m) & (ret.index <= month_ends[i+1]), top]
        port = w_.mean(axis=1, skipna=True).iloc[1:]
        daily.append(port - ret["XBI"].reindex(port.index))
    r = pd.concat(daily).dropna()
    return float(r.mean() / r.std() * np.sqrt(252)), len(r)
ir_b, nd = run_arm(wmap_eq)
print(f"(vi) independent baseline IR: {ir_b:.3f} over {nd} days "
      f"(stage2 reported {base.IR.iloc[0]})")
