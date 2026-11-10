"""Counter-agent audit E2: rerun the full Stage-1 WY family with 63-day blocks
(fwd63 ICs overlap 63 bars; the as-run 21d block is anti-conservative)."""
import numpy as np
import pandas as pd

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad/r9"
SEED, DRAWS, BLOCK = 20260827, 4000, 63
panel = pd.read_csv(f"{SC}/panel.csv", parse_dates=["date"])
panel["sig_run"] = -panel["c_run"]

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
for sig in ("c_cat", "c_rev", "c_pos", "sig_run"):
    for fwd in ("fwd21", "fwd5", "fwd63"):
        for scheme in ("B1", "B2", "B3"):
            df = daily_diff_series(sig, fwd, scheme)
            if len(df) < 200:
                null_mat.append(np.zeros(DRAWS))
                continue
            d = (df["S"] - df["L"]).values
            bm = block_boot_means(d, rng)
            obs, se = d.mean(), bm.std()
            t = obs / se if se > 0 else 0.0
            tests.append({"sig": sig, "fwd": fwd, "scheme": scheme,
                          "days": len(df), "diff": round(obs, 4),
                          "t": round(t, 2)})
            null_mat.append((bm - obs) / se if se > 0 else np.zeros(DRAWS))

maxT = np.abs(np.vstack(null_mat)).max(axis=0)
for row in tests:
    row["p_wy63"] = round(float((maxT >= abs(row["t"])).mean()), 4)
res = pd.DataFrame(tests).sort_values("p_wy63")
print(res.head(8).to_string(index=False))
