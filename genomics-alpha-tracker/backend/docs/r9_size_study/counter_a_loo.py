"""Counter-agent audit A: the 3-name problem.
Leave-one-out decomposition of F2 (sig_run B1 IC interaction) and F3 (flags
small-bucket R gaps). Independent reimplementation — does not import stage1."""
import json
import numpy as np
import pandas as pd

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad/r9"
BACKEND = "/home/user/uranium-dashboard/genomics-alpha-tracker/backend"
panel = pd.read_csv(f"{SC}/panel.csv", parse_dates=["date"])
panel["sig_run"] = -panel["c_run"]

def b1(g):
    z = g["z1_mktcap"]
    return pd.Series(np.where(z < 1e9, "S", np.where(z < 10e9, "M", "L")),
                     index=g.index).where(z.notna())

def diff_series(sig, fwd, min_n=5, excl_L=None, excl_S=None):
    """Per-day within-bucket Spearman ICs; returns DataFrame S,L on qualifying
    days. excl_L/excl_S drop a symbol from that bucket BEFORE the min_n test
    (the honest LOO: the day must still qualify without the name)."""
    out = {}
    for d, g in panel.groupby("date"):
        b = b1(g)
        ics = {}
        for lab, excl in (("S", excl_S), ("L", excl_L)):
            v = g[(b == lab) & (g.symbol != excl)][[sig, fwd]].dropna()
            if len(v) >= min_n and v[sig].nunique() > 1:
                ics[lab] = v[sig].rank().corr(v[fwd].rank())
        if "S" in ics and "L" in ics:
            out[d] = (ics["S"], ics["L"])
    return pd.DataFrame(out, index=["S", "L"]).T

for fwd in ("fwd63", "fwd21"):
    df = diff_series("sig_run", fwd)
    print(f"\n===== sig_run {fwd} B1: qualifying-day census =====")
    print(f"days={len(df)}, IC_S={df['S'].mean():+.4f}, IC_L={df['L'].mean():+.4f}, "
          f"diff={(df['S']-df['L']).mean():+.4f}")
    yr = df.index.year
    tab = pd.DataFrame({"days": df.groupby(yr).size(),
                        "IC_S": df["S"].groupby(yr).mean().round(3),
                        "IC_L": df["L"].groupby(yr).mean().round(3),
                        "diff": (df["S"]-df["L"]).groupby(yr).mean().round(3)})
    print(tab.to_string())

    # who is in the L bucket on qualifying days, with valid sig+fwd?
    qd = set(df.index)
    memb = {}
    prof_frac = {}
    for d, g in panel.groupby("date"):
        if d not in qd:
            continue
        b = b1(g)
        v = g[b == "L"][["symbol", "sig_run", fwd]].dropna()
        for s in v.symbol:
            memb[s] = memb.get(s, 0) + 1
        for _, r in v.iterrows():
            prof_frac.setdefault(r.symbol, []).append(r.sig_run == 0)
    print("L-bucket membership on qualifying days (days, %days penalty=0):")
    for s, n in sorted(memb.items(), key=lambda x: -x[1]):
        print(f"  {s:5s} {n:4d}  {np.mean(prof_frac[s]):.0%} profitable(sig=0)")

    print(f"leave-one-out on L bucket ({fwd}):")
    for s in sorted(memb, key=lambda x: -memb[x]):
        d2 = diff_series("sig_run", fwd, excl_L=s)
        if len(d2) < 50:
            print(f"  -{s:5s}: only {len(d2)} qualifying days remain")
            continue
        print(f"  -{s:5s}: days={len(d2):4d}  IC_L={d2['L'].mean():+.4f}  "
              f"diff={(d2['S']-d2['L']).mean():+.4f}")

    # and the S side of the diff
    smemb = {}
    for d, g in panel.groupby("date"):
        if d not in qd:
            continue
        b = b1(g)
        v = g[b == "S"][["symbol", "sig_run", fwd]].dropna()
        for s in v.symbol:
            smemb[s] = smemb.get(s, 0) + 1
    top_s = sorted(smemb, key=lambda x: -smemb[x])[:8]
    print(f"leave-one-out on S bucket (top-8 by presence, {fwd}):")
    for s in top_s:
        d2 = diff_series("sig_run", fwd, excl_S=s)
        print(f"  -{s:5s}: days={len(d2):4d}  IC_S={d2['S'].mean():+.4f}  "
              f"diff={(d2['S']-d2['L']).mean():+.4f}")

# ===== F3 flags: leave-one-symbol-out =====
print("\n===== flags framing: symbol concentration + leave-one-symbol-out =====")
cr = json.load(open(f"{BACKEND}/data/backtest_calls_10y_results.json"))["call_rows"]
sizes = panel.set_index(["date", "symbol"])["z1_mktcap"]
frows = []
for flag, rows_ in cr.items():
    for r in rows_:
        z = sizes.get((pd.Timestamp(r["fire_date"]), r.get("symbol")), np.nan)
        if not np.isnan(z) and r.get("r_net") is not None:
            frows.append({"flag": flag, "symbol": r["symbol"],
                          "bucket": "S" if z < 1e9 else ("M" if z < 10e9 else "L"),
                          "r": r["r_net"]})
fdf = pd.DataFrame(frows)
for flag in ("binary_event_within_n_days", "quiet_before_catalyst",
             "pullback_into_catalyst"):
    g = fdf[fdf.flag == flag]
    gs, gl = g[g.bucket == "S"], g[g.bucket == "L"]
    print(f"\n{flag}: gap {gs.r.mean()-gl.r.mean():+.2f}R "
          f"(nS={len(gs)} across {gs.symbol.nunique()} symbols, "
          f"nL={len(gl)} across {gl.symbol.nunique()} symbols)")
    print("  S fires by symbol:", gs.groupby("symbol")["r"]
          .agg(["count", "mean"]).round(2).to_dict("index"))
    print("  leave-one-S-symbol-out gap:")
    for s in sorted(gs.symbol.unique()):
        g2 = gs[gs.symbol != s]
        print(f"    -{s:5s}: nS={len(g2):3d}  meanS={g2.r.mean():+.2f}  "
              f"gap={g2.r.mean()-gl.r.mean():+.2f}R")
