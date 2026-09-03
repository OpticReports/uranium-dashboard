"""R9 Stage 1 — size-conditional signal efficacy (registered d3339bb).
Interaction stat: per-day within-bucket Spearman IC, small minus large,
paired-day series; circular block bootstrap (21d blocks, 4000 draws, seed
20260827); Westfall-Young max-T across the full 36-test family. Flags framing:
per-fire R-multiples from the production 10y replay joined to size at fire."""
import json
import numpy as np
import pandas as pd

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad/r9"
BACKEND = "/home/user/uranium-dashboard/genomics-alpha-tracker/backend"
SEED, DRAWS, BLOCK = 20260827, 4000, 21
panel = pd.read_csv(f"{SC}/panel.csv", parse_dates=["date"])
panel["sig_run"] = -panel["c_run"]        # penalty: higher runway risk = worse
COMPONENTS = ["c_cat", "c_rev", "c_pos", "sig_run"]
HORIZONS = ["fwd21", "fwd5", "fwd63"]

def buckets(g, scheme):
    if scheme == "B1":
        z = g["z1_mktcap"]
        return pd.Series(np.where(z < 1e9, "S", np.where(z < 10e9, "M", "L")),
                         index=g.index).where(z.notna())
    if scheme == "B2":
        q = g["z1_mktcap"].rank(pct=True)
        return pd.Series(np.where(q <= 1/3, "S", np.where(q > 2/3, "L", "M")),
                         index=g.index).where(g["z1_mktcap"].notna())
    return pd.Series(np.where(g["z3_commercial"] == 1, "L", "S"), index=g.index)

def daily_diff_series(sig, fwd, scheme, min_n=5):
    out = {}
    for d, g in panel.groupby("date"):
        b = buckets(g, scheme)
        ics = {}
        for lab in ("S", "L"):
            v = g[b == lab][[sig, fwd]].dropna()
            if len(v) >= min_n and v[sig].nunique() > 1:
                ics[lab] = v[sig].rank().corr(v[fwd].rank())
        if "S" in ics and "L" in ics:
            out[d] = (ics["S"], ics["L"])
    return pd.DataFrame(out, index=["S", "L"]).T

def block_boot_means(x, rng):
    n = len(x)
    nb = int(np.ceil(n / BLOCK))
    starts = rng.integers(0, n, size=(DRAWS, nb))
    idx = (starts[:, :, None] + np.arange(BLOCK)[None, None, :]) % n
    return x[idx.reshape(DRAWS, -1)[:, :n]].mean(axis=1)

rng = np.random.default_rng(SEED)
tests, null_mat = [], []
for sig in COMPONENTS:
    for fwd in HORIZONS:
        for scheme in ("B1", "B2", "B3"):
            df = daily_diff_series(sig, fwd, scheme)
            if len(df) < 200:
                tests.append({"sig": sig, "fwd": fwd, "scheme": scheme,
                              "days": len(df), "note": "insufficient"})
                null_mat.append(np.zeros(DRAWS))
                continue
            d = (df["S"] - df["L"]).values
            bm = block_boot_means(d, rng)
            obs = d.mean()
            se = bm.std()
            t = obs / se if se > 0 else 0.0
            p_raw = 2 * min((bm <= 0).mean(), (bm >= 0).mean())
            tests.append({"sig": sig, "fwd": fwd, "scheme": scheme,
                          "days": len(df), "ic_S": round(df['S'].mean(), 4),
                          "ic_L": round(df['L'].mean(), 4),
                          "diff": round(obs, 4), "t": round(t, 2),
                          "p_raw": round(p_raw, 4)})
            null_mat.append((bm - obs) / se if se > 0 else np.zeros(DRAWS))

# Westfall-Young max-T over the family
null_mat = np.abs(np.vstack(null_mat))
maxT = null_mat.max(axis=0)
for row in tests:
    if "t" in row:
        row["p_wy"] = round(float((maxT >= abs(row["t"])).mean()), 4)
res = pd.DataFrame(tests)
res.to_csv(f"{SC}/stage1_results.csv", index=False)
print(res.sort_values("p_wy").to_string(index=False))

# ── flags framing: production 10y call rows joined to size at fire ──
cr = json.load(open(f"{BACKEND}/data/backtest_calls_10y_results.json"))["call_rows"]
sizes = panel.set_index(["date", "symbol"])["z1_mktcap"]
frows = []
for flag, rows_ in cr.items():
    for r in rows_:
        z = sizes.get((pd.Timestamp(r["fire_date"]), r.get("symbol")), np.nan)
        if not np.isnan(z) and r.get("r_net") is not None:
            frows.append({"flag": flag, "symbol": r["symbol"],
                          "month": r["entry_month"],
                          "bucket": "S" if z < 1e9 else ("M" if z < 10e9 else "L"),
                          "r": r["r_net"]})
fdf = pd.DataFrame(frows)
if len(fdf):
    summ = fdf.groupby(["flag", "bucket"])["r"].agg(["mean", "count"]).round(2)
    print("\nflags framing: mean R-multiple by B1 bucket (production grader rows)")
    print(summ.to_string())
    # bootstrap the S-minus-L mean-R gap per flag, clustered by symbol|month
    print("\nS-minus-L mean-R gap (cluster bootstrap by symbol|month):")
    for flag, g in fdf.groupby("flag"):
        gs, gl = g[g.bucket == "S"], g[g.bucket == "L"]
        if len(gs) < 15 or len(gl) < 15:
            print(f"  {flag}: skipped (nS={len(gs)}, nL={len(gl)})")
            continue
        g2 = g[g.bucket.isin(["S", "L"])].copy()
        g2["cl"] = g2.symbol + "|" + g2.month
        cls = g2["cl"].unique()
        obs = gs.r.mean() - gl.r.mean()
        agg = g2.groupby("cl").apply(
            lambda x: pd.Series({"sS": x[x.bucket == "S"].r.sum(),
                                 "nS": (x.bucket == "S").sum(),
                                 "sL": x[x.bucket == "L"].r.sum(),
                                 "nL": (x.bucket == "L").sum()}),
            include_groups=False)
        A = agg.values
        picks = rng.integers(0, len(A), size=(2000, len(A)))
        T = A[picks].sum(axis=1)          # (2000, 4)
        with np.errstate(invalid="ignore", divide="ignore"):
            bs = T[:, 0] / T[:, 1] - T[:, 2] / T[:, 3]
        bs = bs[np.isfinite(bs)]
        p = 2 * min((bs <= 0).mean(), (bs >= 0).mean())
        print(f"  {flag}: gap {obs:+.2f}R (nS={len(gs)}, nL={len(gl)}), p={p:.3f}")
fdf.to_csv(f"{SC}/stage1_flags.csv", index=False)
