"""Counter-agent audit C: Stage-1 inference mechanics.
(1) min_n=7 variant; (2) monthly/quarterly (non-overlapping) sampling;
(3) block-size sensitivity (21 vs 63 vs 126) — fwd63 daily ICs overlap 63
    bars, a 21d block bootstrap can understate SE;
(4) runway construction spot checks vs raw statements;
(5) quality-confound: is IC_L just long-profitable/short-burner among 5 megacaps?
"""
import json
import numpy as np
import pandas as pd

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad/r9"
panel = pd.read_csv(f"{SC}/panel.csv", parse_dates=["date"])
panel["sig_run"] = -panel["c_run"]
SEED, DRAWS = 20260827, 4000

def b1(g):
    z = g["z1_mktcap"]
    return pd.Series(np.where(z < 1e9, "S", np.where(z < 10e9, "M", "L")),
                     index=g.index).where(z.notna())

def diff_series(sig, fwd, min_n=5):
    out = {}
    for d, g in panel.groupby("date"):
        b = b1(g)
        ics = {}
        for lab in ("S", "L"):
            v = g[b == lab][[sig, fwd]].dropna()
            if len(v) >= min_n and v[sig].nunique() > 1:
                ics[lab] = v[sig].rank().corr(v[fwd].rank())
        if "S" in ics and "L" in ics:
            out[d] = (ics["S"], ics["L"])
    return pd.DataFrame(out, index=["S", "L"]).T

def block_boot(x, block, draws=DRAWS, seed=SEED):
    rng = np.random.default_rng(seed)
    n = len(x)
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(draws, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    bm = x[idx.reshape(draws, -1)[:, :n]].mean(axis=1)
    obs = x.mean()
    se = bm.std()
    p = 2 * min((bm <= 0).mean(), (bm >= 0).mean())
    return obs, obs / se if se > 0 else 0.0, p

for fwd in ("fwd63", "fwd21"):
    print(f"\n===== sig_run {fwd} B1 robustness =====")
    for mn in (5, 7):
        df = diff_series("sig_run", fwd, min_n=mn)
        if len(df) < 30:
            print(f" min_n={mn}: only {len(df)} days")
            continue
        d = (df["S"] - df["L"]).values
        for blk in (21, 63, 126):
            obs, t, p = block_boot(d, blk)
            print(f" min_n={mn} block={blk:3d}: days={len(d)} "
                  f"diff={obs:+.4f} t={t:+.2f} p_raw={p:.4f}")
    # non-overlapping sampling: last qualifying day per month (fwd21)
    # / per quarter (fwd63) -> plain iid bootstrap
    df = diff_series("sig_run", fwd)
    per = df.index.to_period("M" if fwd == "fwd21" else "Q")
    sub = df.groupby(per).tail(1)
    d = (sub["S"] - sub["L"]).values
    rng = np.random.default_rng(SEED)
    bm = d[rng.integers(0, len(d), size=(DRAWS, len(d)))].mean(axis=1)
    p = 2 * min((bm <= 0).mean(), (bm >= 0).mean())
    print(f" non-overlap ({'monthly' if fwd=='fwd21' else 'quarterly'} last day): "
          f"n={len(d)} diff={d.mean():+.4f} t={d.mean()/bm.std():+.2f} p={p:.4f}")

# ---- (4) runway spot checks ----
print("\n===== runway construction spot checks =====")
for sym in ("ILMN", "MRNA", "CERS", "LLY"):
    g = panel[panel.symbol == sym].set_index("date")
    for dt in ("2024-06-03", "2025-06-02"):
        if pd.Timestamp(dt) in g.index:
            r = g.loc[dt]
            print(f" {sym} {dt}: c_run={r.c_run:.1f} z1={r.z1_mktcap/1e9:.1f}B")
# recompute MRNA runway by hand from raw statements at 2025-06-02
inc = json.load(open(f"{SC}/inc/MRNA.json"))
bs = json.load(open(f"{SC}/bs/MRNA.json"))
dd = pd.Timestamp("2025-06-02").date()
import datetime as _dt
def latest(rows, f):
    rs = [r for r in rows if _dt.date.fromisoformat(
        (r.get("acceptedDate") or r.get("filingDate") or r["date"])[:10]) <= dd]
    rs.sort(key=lambda r: (r.get("acceptedDate") or r.get("filingDate") or r["date"]))
    return rs[-1] if rs else None
li, lb = latest(inc, None), latest(bs, None)
oi = li["operatingIncome"]; cash = lb["cashAndShortTermInvestments"]
burn = max(-oi, 0.0)
pen = 0.0 if burn <= 0 else 100.0 * (1.0 - min(cash / burn / 8.0, 1.0))
print(f" MRNA hand-check 2025-06-02: OI={oi/1e6:.0f}M cash={cash/1e9:.2f}B "
      f"runway_q={cash/burn if burn else float('inf'):.1f} -> penalty {pen:.1f} "
      f"(panel says {panel[(panel.symbol=='MRNA')&(panel.date=='2025-06-02')].c_run.iloc[0]:.1f})")

# ---- (5) quality confound: L-bucket IC as long-profitable vs short-burner ----
print("\n===== quality-confound decomposition (fwd63, qualifying days) =====")
df = diff_series("sig_run", "fwd63")
qd = set(df.index)
rows = []
for d, g in panel.groupby("date"):
    if d not in qd:
        continue
    b = b1(g)
    v = g[b == "L"][["symbol", "sig_run", "fwd63"]].dropna()
    prof = v[v.sig_run == 0]["fwd63"]
    burn = v[v.sig_run < 0]["fwd63"]
    if len(prof) and len(burn):
        rows.append({"date": d, "spread": prof.mean() - burn.mean(),
                     "n_prof": len(prof), "n_burn": len(burn)})
q = pd.DataFrame(rows).set_index("date")
print(f" days with both groups: {len(q)}; mean profitable-minus-burner fwd63 "
      f"spread {q.spread.mean()*100:+.2f}% ; median n_burn={q.n_burn.median():.0f}")
print(q.groupby(q.index.year)[["spread", "n_burn"]].mean().round(4).to_string())
# within-burner-only IC: does sig_run rank-order among the penalized names?
rows = []
for d, g in panel.groupby("date"):
    if d not in qd:
        continue
    b = b1(g)
    v = g[(b == "L") & (g.sig_run < 0)][["sig_run", "fwd63"]].dropna()
    if len(v) >= 3 and v.sig_run.nunique() > 1:
        rows.append(v["sig_run"].rank().corr(v["fwd63"].rank()))
print(f" IC among PENALIZED large names only (n>=3 days: {len(rows)}): "
      f"{np.mean(rows) if rows else float('nan'):+.4f}")
