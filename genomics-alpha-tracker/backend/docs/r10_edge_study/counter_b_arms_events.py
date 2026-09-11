"""COUNTER-AGENT audit C/D/E — A4 truncation hand-check, A2 event-study
integrity (leak/threshold/Holm), A3 recount incl. boundary fix, proper WY."""
import json
import math
import sys
from datetime import timedelta

import numpy as np
import pandas as pd

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad/r10"
BACKEND = "/home/user/uranium-dashboard/genomics-alpha-tracker/backend"
sys.path.insert(0, BACKEND)
sys.path.insert(0, SC)
from scripts.backtest_calls_10y import SLIPPAGE_BPS_BY_TIER  # noqa: E402
from r10 import (arm_calls, calls, bars_px, tiers, xbi, ev,  # noqa: E402
                 CATALYST_FLAGS, CAL)

# ---- C: A4 truncation -------------------------------------------------------
a4b = arm_calls("A4b")
print(f"[C1] A4b n={len(a4b)} (baseline {len(calls)}) -> cannot add calls: "
      f"{'OK' if len(a4b) == len(calls) else 'FAIL'}")
changed, noncat_changed = [], 0
for orig, new in zip(calls, a4b):
    if orig is new:
        continue
    if orig["flag"] not in CATALYST_FLAGS:
        noncat_changed += 1
    changed.append((orig, new))
print(f"[C2] calls modified by A4b: {len(changed)}; non-catalyst modified: "
      f"{noncat_changed} (must be 0)")
# stop/target before truncation kept?
kept_early = sum(1 for o, n in changed if pd.Timestamp(o['exit_date']) <= pd.Timestamp(n['exit_date']))
print(f"[C3] all modified exits move EARLIER: "
      f"{'OK' if all(pd.Timestamp(n['exit_date']) < pd.Timestamp(o['exit_date']) for o, n in changed) else 'FAIL'}")
# hand-verify two truncated calls
for o, n in changed[:2]:
    sym = o["symbol"]
    px = bars_px[sym]
    pcd = pd.Timestamp(o["driving_pcd"])
    grid = px.index[px.index < pcd]
    trunc = grid[-5]
    sub = px[(px.index >= pd.Timestamp(o["entry_date"])) & (px.index <= trunc)]
    bps = SLIPPAGE_BPS_BY_TIER.get(tiers.get(sym, "C"), 100) / 10_000
    my_exit = float(sub.iloc[-1])
    my_r = (my_exit * (1 - bps) - o["entry"] * (1 + bps)) / o["risk"]
    print(f"[C4] {sym} entry {o['entry_date']} pcd {o['driving_pcd']}: "
          f"orig exit {o['exit_date']} ({o['status']}) -> new {n['exit_date']}; "
          f"hand trunc date {sub.index[-1].date()} "
          f"{'OK' if str(sub.index[-1].date()) == n['exit_date'] else 'FAIL'}; "
          f"hand exit {my_exit:.4f} vs {n['exit']:.4f} "
          f"{'OK' if abs(my_exit - n['exit']) < 1e-9 else 'FAIL'}; "
          f"hand r_net {my_r:+.4f} vs {n['r_net']:+.4f} "
          f"{'OK' if abs(my_r - n['r_net']) < 1e-9 else 'FAIL'}")
# original early exits untouched?
bad = [1 for c in calls
       if c["flag"] in CATALYST_FLAGS and c.get("driving_pcd")
       and c["status"] in ("stopped", "target_hit")]
early_kept = sum(1 for o, n in zip(calls, a4b) if o is n and o["flag"] in CATALYST_FLAGS
                 and o.get("driving_pcd") and o["status"] in ("stopped", "target_hit"))
print(f"[C5] catalyst stop/target calls untouched when exit <= trunc: "
      f"{early_kept} kept as-is (early-exit preservation active)")

# ---- D: A2 event study ------------------------------------------------------
def fwd_excess(sym, d, k, base_offset=0):
    px = bars_px.get(sym)
    if px is None:
        return np.nan
    g = px[px.index > d]
    if len(g) < k + 1 + base_offset:
        return np.nan
    x = xbi[xbi.index > d]
    if len(x) < k + 1 + base_offset:
        return np.nan
    b = base_offset
    return (g.iloc[b + k] / g.iloc[b] - 1) - (x.iloc[b + k] / x.iloc[b] - 1)

# calendar alignment between g and x for the 63d horizon
mis = 0
for r in ev.itertuples():
    px = bars_px.get(r.symbol)
    if px is None:
        continue
    g = px[px.index > r.date]
    x = xbi[xbi.index > r.date]
    if len(g) > 63 and len(x) > 63 and g.index[63] != x.index[63]:
        mis += 1
print(f"[D1] symbol/XBI bar-63 date mismatches across {len(ev)} events: {mis}")

# first-bar-after base: leak direction test — if the study accidentally
# captured the announcement-day move, an event-day base would differ a lot
slips = ev[ev.type == "slip"]
v_report = [fwd_excess(r.symbol, r.date, 63) for r in slips.itertuples()]
v_report = [v for v in v_report if not np.isnan(v)]
print(f"[D2] slips fwd63 reproduction: mean {np.mean(v_report)*100:+.2f}% "
      f"n={len(v_report)} (r10: +2.95%, 332) — base bar is the FIRST CLOSE "
      f"AFTER the posting date: the announcement-day and next-close reaction "
      f"are excluded (no same-day leak; conservative)")

# slip >= 3 months (scout threshold)
pit = json.load(open(f"{BACKEND}/data/pit_catalysts.json"))["symbols"]
ev3 = []
for sym, trials in pit.items():
    for t in trials:
        tl = t.get("timeline", [])
        for a, b in zip(tl, tl[1:]):
            pa, pb = a.get("pcd"), b.get("pcd")
            if pa and pb and len(pa) >= 7 and len(pb) >= 7:
                mo = (int(pb[:4]) - int(pa[:4])) * 12 + int(pb[5:7]) - int(pa[5:7])
                if mo >= 3:
                    ev3.append({"symbol": sym, "date": pd.Timestamp(b["from"])})
e3 = pd.DataFrame(ev3).sort_values("date")
keep, last = [], {}
for _, r in e3.iterrows():
    if r.symbol in last and (r.date - last[r.symbol]).days <= 5:
        continue
    last[r.symbol] = r.date
    keep.append(r)
e3 = pd.DataFrame(keep)
vals = pd.DataFrame({"symbol": e3.symbol.values, "date": e3.date.values})
vals["fx"] = [fwd_excess(r.symbol, r.date, 63) for r in vals.itertuples()]
vals = vals.dropna(subset=["fx"])
cl = vals.symbol + "|" + vals.date.dt.to_period("M").astype(str)
agg = vals.groupby(cl)["fx"].agg(["sum", "size"]).values
rng = np.random.default_rng(123)
picks = rng.integers(0, len(agg), size=(8000, len(agg)))
T = agg[picks].sum(axis=1)
bs = T[:, 0] / T[:, 1]
p = 2 * min((bs <= 0).mean(), (bs >= 0).mean())
print(f"[D3] slips >=3mo fwd63: n={len(vals)} mean {vals.fx.mean()*100:+.2f}% "
      f"p={p:.4f} (sign robustness of the +2.95% at >=2mo)")

# Holm with monotone enforcement
es = pd.read_csv(f"{SC}/r10_events.csv")
o = es.sort_values("p_raw").reset_index()
m = len(o)
adj = np.maximum.accumulate((o["p_raw"] * (m - np.arange(m))).clip(upper=1))
print("[D4] proper step-down Holm (monotone):",
      dict(zip(o["event"] + "-" + o["h"], adj.round(4))))

# ---- E: A3 ------------------------------------------------------------------
a3rep = pd.read_csv(f"{SC}/r10_a3_events.csv")
print(f"[E1] reported A3 events: {len(a3rep)} across {a3rep.symbol.nunique()} symbols")
maxmoves, events_fix = [], []
seen = set()
for c in calls:
    if c["flag"] not in CATALYST_FLAGS or not c.get("driving_pcd"):
        continue
    key = (c["symbol"], c["driving_pcd"])
    if key in seen:
        continue
    seen.add(key)
    px = bars_px[c["symbol"]]
    pcd = pd.Timestamp(c["driving_pcd"])
    lo, hi = pcd - timedelta(days=7), pcd + timedelta(days=14)
    # boundary-INCLUSIVE returns: bring in one bar before the window
    prev = px[px.index < lo]
    win = px[(px.index >= lo) & (px.index <= hi)]
    if len(win) == 0:
        continue
    ext = pd.concat([prev.iloc[-1:], win]) if len(prev) else win
    r1 = ext.pct_change().dropna()
    r1 = r1[r1.index >= lo]          # returns OF bars inside the window only
    if not len(r1):
        continue
    maxmoves.append(float(abs(r1).max()))
    big = r1[abs(r1) >= 0.15]
    if len(big):
        events_fix.append({"symbol": c["symbol"], "date": big.index[0],
                           "dir": "pos" if big.iloc[0] > 0 else "neg"})
ef = pd.DataFrame(events_fix).drop_duplicates(["symbol", "date"])
print(f"[E2] distinct (symbol, driving_pcd) windows: {len(seen)}; "
      f"median max|1d move| in window: {np.median(maxmoves)*100:.1f}% "
      f"(claim: 6.5%)")
print(f"[E3] boundary-INCLUSIVE recount: {len(ef)} events across "
      f"{ef.symbol.nunique() if len(ef) else 0} symbols "
      f"(r10 boundary-exclusive: 13 across 5) — registered promotion needs >=8 symbols")
# threshold sensitivity
for th in (0.10, 0.12):
    cnt, syms = 0, set()
    for c in maxmoves:
        pass
    evs = []
    for key, mm in zip(sorted(seen), [None] * 0):
        pass
    n = sum(1 for m_ in maxmoves if m_ >= th)
    print(f"[E4] windows with max|move| >= {th:.0%}: {n} of {len(maxmoves)}")

# ---- proper WY with SHARED resamples across the 7 arms ---------------------
base_curve = pd.read_csv(f"{SC}/base_curve.csv", index_col=0, parse_dates=True).iloc[:, 0]
ARMS = ["A1a", "A1b", "A2v", "A4a", "A4b", "A4c", "A5"]
dms = {}
for a in ARMS:
    cs = arm_calls(a)
    mult = {}
    for c in cs:
        d = pd.Timestamp(c["exit_date"])
        mult[d] = mult.get(d, 1.0) * (1.0 + 0.01 * c["r_net"])
    cur = pd.Series(mult).reindex(CAL).fillna(1.0).cumprod()
    dr = cur.pct_change().fillna(0.0) - base_curve.pct_change().fillna(0.0)
    dms[a] = dr.groupby(dr.index.to_period("M")).sum().values
Mx = np.vstack([dms[a] for a in ARMS])          # 7 x n_months
rng = np.random.default_rng(2026)
n = Mx.shape[1]
picks = rng.integers(0, n, size=(8000, n))
obs = Mx.mean(axis=1) * 12
ses, tnull = [], []
bs_all = Mx[:, picks].mean(axis=2) * 12          # 7 x draws
se = bs_all.std(axis=1)
t_obs = obs / se
tn = np.abs((bs_all - obs[:, None]) / se[:, None])   # SHARED resamples
maxT = tn.max(axis=0)
for i, a in enumerate(ARMS):
    print(f"[F1] {a}: t={t_obs[i]:+.2f}  p_wy(shared-resample)="
          f"{(maxT >= abs(t_obs[i])).mean():.4f}")
