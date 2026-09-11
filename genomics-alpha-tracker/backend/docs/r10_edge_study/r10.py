"""R10 harness — registered 2c9ee6b. Book arms + event studies.
Reuses the production replay's own slippage/tier machinery; nothing regraded
by hand. Frozen: 1R risk unit = 1% of equity, P&L compounded at exit; seed
20260904; monthly-cluster paired bootstrap, 4000 draws; WY across 7 arms."""
import json
import math
import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

SC = os.path.dirname(os.path.abspath(__file__))
BACKEND = "/home/user/uranium-dashboard/genomics-alpha-tracker/backend"
sys.path.insert(0, BACKEND)
from scripts.backtest_calls_10y import (  # noqa: E402
    SLIPPAGE_BPS_BY_TIER, median_addv, tier_of, to_adjusted_barlikes)

SEED, DRAWS = 20260904, 4000
rng = np.random.default_rng(SEED)
CATALYST_FLAGS = {"quiet_before_catalyst", "pullback_into_catalyst",
                  "binary_event_within_n_days"}

raw = json.load(open(f"{BACKEND}/data/backtest_bars.json"))
res = json.load(open(f"{BACKEND}/data/backtest_calls_10y_results.json"))
pit = json.load(open(f"{BACKEND}/data/pit_catalysts.json"))["symbols"]
panel = pd.read_csv(f"{SC}/../r9/panel.csv", parse_dates=["date"])
mcap = panel.set_index(["date", "symbol"])["z1_mktcap"]
crun = panel.set_index(["date", "symbol"])["c_run"]

bars_px = {s: pd.DataFrame(b).assign(date=lambda d: pd.to_datetime(d["date"]))
           .set_index("date")["adj_close"] for s, b in raw.items()}
xbi = bars_px["XBI"]

tiers = {}
for sym in raw:
    if len(raw[sym]) >= 120:
        b, v = to_adjusted_barlikes(raw[sym])
        tiers[sym] = tier_of(median_addv(b, v))

calls = []
for flag, rows_ in res["call_rows"].items():
    for r in rows_:
        calls.append({**r, "flag": flag})
print(f"{len(calls)} baseline calls")

# ── slip events (A2 census + A2v veto windows) ──────────────────────────────
DOWN = {"SUSPENDED", "TERMINATED", "WITHDRAWN"}
events = []
for sym, trials in pit.items():
    for t in trials:
        tl = t.get("timeline", [])
        for a, b in zip(tl, tl[1:]):
            d = pd.Timestamp(b["from"])
            pa, pb = a.get("pcd"), b.get("pcd")
            if pa and pb and len(pa) >= 7 and len(pb) >= 7:
                months = (int(pb[:4]) - int(pa[:4])) * 12 + int(pb[5:7]) - int(pa[5:7])
                if months >= 2:
                    events.append({"symbol": sym, "date": d, "type": "slip"})
                elif months <= -2:
                    events.append({"symbol": sym, "date": d, "type": "pullin"})
            if b.get("status") in DOWN and a.get("status") not in DOWN:
                events.append({"symbol": sym, "date": d, "type": "downgrade"})
ev = pd.DataFrame(events).sort_values("date")
# de-cluster: drop events within 5d of a prior same-symbol same-type event
keep = []
last = {}
for _, r in ev.iterrows():
    k = (r.symbol, r.type)
    if k in last and (r.date - last[k]).days <= 5:
        continue
    last[k] = r.date
    keep.append(r)
ev = pd.DataFrame(keep)
print("events after de-cluster:", ev.groupby("type").size().to_dict())

slip_windows = {}
for _, r in ev[ev.type == "slip"].iterrows():
    slip_windows.setdefault(r.symbol, []).append(r.date)

# ── arm call-set transforms ─────────────────────────────────────────────────
def pit_mcap(sym, d):
    try:
        s = mcap.loc[(slice(None), sym)]
        s = s[s.index <= d]
        return float(s.iloc[-1]) if len(s) and not np.isnan(s.iloc[-1]) else np.nan
    except KeyError:
        return np.nan

def pit_run(sym, d):
    try:
        s = crun.loc[(slice(None), sym)]
        s = s[s.index <= d]
        return float(s.iloc[-1]) if len(s) else np.nan
    except KeyError:
        return np.nan

def truncate_call(c, n_days):
    """Tighten a catalyst call's expiry to PCD - n trading days."""
    if c["flag"] not in CATALYST_FLAGS or not c.get("driving_pcd"):
        return c
    px = bars_px[c["symbol"]]
    pcd = pd.Timestamp(c["driving_pcd"])
    grid = px.index[px.index < pcd]
    if len(grid) < n_days:
        return c
    trunc = grid[-n_days]
    if pd.Timestamp(c["exit_date"]) <= trunc:
        return c
    sub = px[(px.index >= pd.Timestamp(c["entry_date"])) & (px.index <= trunc)]
    if not len(sub):
        return c
    bps = SLIPPAGE_BPS_BY_TIER.get(tiers.get(c["symbol"], "C"), 100) / 10_000
    new_exit = float(sub.iloc[-1])
    r_net = (new_exit * (1 - bps) - c["entry"] * (1 + bps)) / c["risk"]
    return {**c, "exit": new_exit, "exit_date": str(sub.index[-1].date()),
            "r_net": r_net, "status": "runup_exit"}

def arm_calls(name):
    out = []
    for c in calls:
        ed = pd.Timestamp(c["fire_date"])
        if name in ("A1a", "A1b") and c["flag"] in CATALYST_FLAGS:
            z = pit_mcap(c["symbol"], ed)
            if (not np.isnan(z) and z < 1e9) or (name == "A1b" and np.isnan(z)):
                continue
        if name == "A2v":
            ws = slip_windows.get(c["symbol"], [])
            if any(0 <= (ed - w).days <= 60 for w in ws):
                continue
        if name == "A5":
            if pit_run(c["symbol"], ed) > 75.0:      # runway < 2 quarters
                continue
        if name.startswith("A4") and c["flag"] in CATALYST_FLAGS:
            c = truncate_call(c, {"A4a": 3, "A4b": 5, "A4c": 10}[name])
        out.append(c)
    return out

# ── the book (frozen metric) ────────────────────────────────────────────────
CAL = xbi.index

def book(callset):
    eq = pd.Series(1.0, index=CAL)
    mult = {}
    for c in callset:
        xd = pd.Timestamp(c["exit_date"])
        mult[xd] = mult.get(xd, 1.0) * (1.0 + 0.01 * c["r_net"])
    m = pd.Series(mult).reindex(CAL).fillna(1.0).cumprod()
    curve = m
    dd = (curve / curve.cummax() - 1).min()
    yrs = (CAL[-1] - CAL[0]).days / 365.25
    cagr = curve.iloc[-1] ** (1 / yrs) - 1
    return curve, cagr * 100, dd * 100

base_curve, base_cagr, base_dd = book(calls)
print(f"BASELINE: CAGR {base_cagr:.2f}%  maxDD {base_dd:.2f}%  ({len(calls)} calls)")

rows, nulls = [], []
ARMS = ["A1a", "A1b", "A2v", "A4a", "A4b", "A4c", "A5"]
for a in ARMS:
    cs = arm_calls(a)
    curve, cagr, dd = book(cs)
    dr = curve.pct_change().fillna(0.0) - base_curve.pct_change().fillna(0.0)
    dm = dr.groupby(dr.index.to_period("M")).sum()
    M = dm.values
    picks = rng.integers(0, len(M), size=(DRAWS, len(M)))
    bs = M[picks].mean(axis=1) * 12
    obs, se = M.mean() * 12, bs.std()
    t = obs / se if se > 0 else 0.0
    half = dm.index[len(dm) // 2]
    h1 = dm[dm.index < half].mean() * 12 * 100
    h2 = dm[dm.index >= half].mean() * 12 * 100
    # late-half CAGR comparison for the tainted arms (A1/A4)
    late = curve[curve.index >= "2022-01-01"]
    lbase = base_curve[base_curve.index >= "2022-01-01"]
    lc = (late.iloc[-1] / late.iloc[0]) ** (365.25 / (late.index[-1] - late.index[0]).days) - 1
    lb = (lbase.iloc[-1] / lbase.iloc[0]) ** (365.25 / (lbase.index[-1] - lbase.index[0]).days) - 1
    rows.append({"arm": a, "n_calls": len(cs), "CAGR": round(cagr, 2),
                 "maxDD": round(dd, 2), "dCAGR": round(cagr - base_cagr, 2),
                 "dDD": round(dd - base_dd, 2),
                 "lateCAGR": round(lc * 100, 2), "lateBase": round(lb * 100, 2),
                 "t": round(t, 2),
                 "p_raw": round(float(2 * min((bs <= 0).mean(), (bs >= 0).mean())), 4),
                 "h1": round(h1, 2), "h2": round(h2, 2)})
    nulls.append((bs - obs) / se if se > 0 else np.zeros(DRAWS))

maxT = np.abs(np.vstack(nulls)).max(axis=0)
for row in rows:
    row["p_wy"] = round(float((maxT >= abs(row["t"])).mean()), 4)
r10 = pd.DataFrame(rows)
r10.to_csv(f"{SC}/r10_book_arms.csv", index=False)
print(r10.to_string(index=False))
# CF-1a fix: DD is stored NEGATIVE, so "maxDD no worse" is dDD >= 0
ship = r10[(r10.dCAGR > 0) & (r10.dDD >= 0) & (r10.p_wy < 0.05)
           & (r10.h1 * r10.h2 > 0)]
print(f"\nSHIP-QUALIFIED ARMS: {len(ship)}")
if len(ship):
    print(ship.to_string(index=False))
base_curve.to_csv(f"{SC}/base_curve.csv")

# ── event studies ───────────────────────────────────────────────────────────
def fwd_excess(sym, d, k):
    px = bars_px.get(sym)
    if px is None:
        return np.nan
    g = px[px.index > d]
    if len(g) < k + 1:
        return np.nan
    x = xbi[xbi.index > d]
    return (g.iloc[k] / g.iloc[0] - 1) - (x.iloc[k] / x.iloc[0] - 1)

print("\n=== A2 registry-revision event study (XBI-excess, first bar after) ===")
es_rows = []
for typ in ("slip", "pullin", "downgrade"):
    sub = ev[ev.type == typ]
    for k, lab in ((5, "5d"), (21, "21d"), (63, "63d")):
        vals = sub.assign(fx=[fwd_excess(r.symbol, r.date, k)
                              for r in sub.itertuples()]).dropna(subset=["fx"])
        if len(vals) < 10:
            continue
        cl = vals.symbol + "|" + vals.date.dt.to_period("M").astype(str)
        agg = vals.groupby(cl)["fx"].agg(["sum", "size"]).values
        picks = rng.integers(0, len(agg), size=(DRAWS, len(agg)))
        T = agg[picks].sum(axis=1)
        bs = T[:, 0] / T[:, 1]
        p = 2 * min((bs <= 0).mean(), (bs >= 0).mean())
        es_rows.append({"event": typ, "h": lab, "n": len(vals),
                        "syms": vals.symbol.nunique(),
                        "mean_fx%": round(vals.fx.mean() * 100, 2),
                        "p_raw": round(float(p), 4),
                        "se": bs.std()})
es = pd.DataFrame(es_rows)
# WY across the event family
# Holm across the event family (WY-across-events registered but substituted;
# disclosed in the verdict ledger CF-4)
es["p_holm"] = (es["p_raw"] * (len(es) - es["p_raw"].rank() + 1)).clip(upper=1).round(4)
print(es.drop(columns=["se"]).to_string(index=False))
es.to_csv(f"{SC}/r10_events.csv", index=False)

print("\n=== A3 post-readout drift ===")
a3 = []
for c in calls:
    if c["flag"] not in CATALYST_FLAGS or not c.get("driving_pcd"):
        continue
    sym = c["symbol"]
    px = bars_px[sym]
    pcd = pd.Timestamp(c["driving_pcd"])
    win = px[(px.index >= pcd - timedelta(days=7)) & (px.index <= pcd + timedelta(days=14))]
    r1 = win.pct_change().dropna()
    big = r1[abs(r1) >= 0.15]
    if not len(big):
        continue
    d0 = big.index[0]
    a3.append({"symbol": sym, "date": d0, "dir": "pos" if big.iloc[0] > 0 else "neg"})
a3 = pd.DataFrame(a3).drop_duplicates(["symbol", "date"])
for direc in ("pos", "neg"):
    sub = a3[a3.dir == direc]
    for k in (21, 63):
        vals = [fwd_excess(r.symbol, r.date, k) for r in sub.itertuples()]
        vals = [v for v in vals if not np.isnan(v)]
        if len(vals) >= 8:
            print(f"  {direc} resolution, fwd{k}: mean {np.mean(vals)*100:+.2f}% "
                  f"(n={len(vals)}, syms={sub.symbol.nunique()})")
a3.to_csv(f"{SC}/r10_a3_events.csv", index=False)
