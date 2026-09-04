"""COUNTER-AGENT audit A/B — independent reproduction of the R10 book,
A1 removal accounting, LOSO, calendar audit, bootstrap replication.
Loads raw JSON directly; does NOT import r10.py (independence)."""
import json
import math

import numpy as np
import pandas as pd

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad/r10"
BACKEND = "/home/user/uranium-dashboard/genomics-alpha-tracker/backend"
CATALYST_FLAGS = {"quiet_before_catalyst", "pullback_into_catalyst",
                  "binary_event_within_n_days"}

raw = json.load(open(f"{BACKEND}/data/backtest_bars.json"))
res = json.load(open(f"{BACKEND}/data/backtest_calls_10y_results.json"))
panel = pd.read_csv(f"{SC}/../r9/panel.csv", parse_dates=["date"])

calls = []
for flag, rows_ in res["call_rows"].items():
    for r in rows_:
        calls.append({**r, "flag": flag})
print(f"[A0] calls loaded: {len(calls)}  (expected 7393)")
print(f"[A0] flags: {sorted(set(c['flag'] for c in calls))}")
print(f"[A0] results period: {res['period']}")

xbi = pd.DataFrame(raw["XBI"]).assign(date=lambda d: pd.to_datetime(d["date"])) \
    .set_index("date")["adj_close"]
CAL = xbi.index
print(f"[A1] CAL span: {CAL[0].date()} -> {CAL[-1].date()}  n={len(CAL)}")
yrs = (CAL[-1] - CAL[0]).days / 365.25
print(f"[A1] yrs used as CAGR denominator: {yrs:.3f}")
first_entry = min(c["entry_date"] for c in calls)
first_exit = min(c["exit_date"] for c in calls)
print(f"[A1] first entry {first_entry}, first exit {first_exit} "
      f"-> dead time before first exit inflates denominator if CAL starts earlier")

# exits landing off the XBI calendar (silently dropped by reindex in r10.book)
cal_set = set(CAL)
off = [c for c in calls if pd.Timestamp(c["exit_date"]) not in cal_set]
print(f"[A2] exits NOT on XBI calendar (dropped by reindex): {len(off)}")
if off:
    print("     sum r_net of dropped:", sum(c["r_net"] for c in off))

# ---- independent book: explicit event ledger, no reindex tricks ------------
def book_indep(callset):
    ledger = {}
    for c in callset:
        d = pd.Timestamp(c["exit_date"])
        ledger.setdefault(d, []).append(c["r_net"])
    eq, path = 1.0, []
    for d in sorted(ledger):
        for r in ledger[d]:
            eq *= (1.0 + 0.01 * r)
        path.append((d, eq))
    peak, mdd = -np.inf, 0.0
    for _, e in path:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1)
    cagr = eq ** (1 / yrs) - 1
    return eq, cagr * 100, mdd * 100, path

base_eq, base_cagr, base_dd, base_path = book_indep(calls)
print(f"[A3] INDEP baseline: CAGR {base_cagr:.2f}%  maxDD {base_dd:.2f}%  "
      f"(r10 reported 96.42 / -99.63)")

# ---- A1a reproduction from scratch -----------------------------------------
mcap = panel.set_index(["date", "symbol"])["z1_mktcap"].sort_index()

def pit_mcap(sym, d):
    try:
        s = mcap.loc[(slice(None), sym)]
        s = s[s.index <= d]
        return float(s.iloc[-1]) if len(s) and not np.isnan(s.iloc[-1]) else np.nan
    except KeyError:
        return np.nan

removed, kept, nan_cat = [], [], 0
border = []
for c in calls:
    if c["flag"] in CATALYST_FLAGS:
        z = pit_mcap(c["symbol"], pd.Timestamp(c["fire_date"]))
        if np.isnan(z):
            nan_cat += 1
            kept.append(c)
            continue
        if 0.8e9 <= z <= 1.25e9:
            border.append((c["symbol"], c["fire_date"], z, c["r_net"]))
        if z < 1e9:
            removed.append(c)
            continue
    kept.append(c)
print(f"[B1] A1a removes {len(removed)} calls (r10 log implies 152); "
      f"catalyst-flag calls with NaN mcap: {nan_cat} "
      f"(A1b==A1a iff 0)")
sr = sum(c["r_net"] for c in removed)
lg = sum(math.log1p(0.01 * c["r_net"]) for c in removed)
print(f"[B2] removed set: sum r_net {sr:+.1f}R, hit rate "
      f"{np.mean([c['r_net'] > 0 for c in removed]):.1%}, "
      f"log-equity impact {lg:+.4f} (multiplier {math.exp(lg):.4f})")
a1_eq, a1_cagr, a1_dd, _ = book_indep(kept)
print(f"[B3] INDEP A1a: CAGR {a1_cagr:.2f}%  dCAGR {a1_cagr - base_cagr:+.2f}pp "
      f"(r10 reported +7.23)  maxDD {a1_dd:.2f}%")
# closed form: removing calls divides final equity by prod(1+.01r) exactly
pred = (base_eq / math.exp(lg)) ** (1 / yrs) - 1
print(f"[B4] closed-form check: predicted A1a CAGR {pred*100:.2f}% "
      f"(multipliers commute -> dCAGR is 100% the removed calls' product; "
      f"no path dependence in final equity)")

# per-symbol structure of the removed set + LOSO
bysym = {}
for c in removed:
    bysym.setdefault(c["symbol"], []).append(c)
tab = sorted(((s, len(v), sum(c["r_net"] for c in v),
               sum(math.log1p(0.01 * c["r_net"]) for c in v))
              for s, v in bysym.items()), key=lambda r: r[3])
print("[B5] removed set by symbol (n, sum r_net, log-impact):")
for s, n, r, l in tab:
    print(f"     {s:6s} n={n:3d}  sumR={r:+7.1f}  logimp={l:+.4f}")
print("[B6] LOSO: dCAGR if that symbol's removed calls are ADDED BACK:")
for s, n, r, l in tab:
    dc = ((base_eq / math.exp(lg - l)) ** (1 / yrs) - 1) * 100 - base_cagr
    print(f"     w/o {s:6s}: dCAGR {dc:+.2f}pp")
print(f"[B7] borderline 0.8-1.25B catalyst fires: {len(border)} "
      f"(gate flips possible under mcap noise/lag)")
bb = [b for b in border if b[2] < 1e9]
print(f"     of which below 1B (removed): {len(bb)}, sum r_net {sum(b[3] for b in bb):+.1f}")

# staleness probe: recompute mcap with NO 45d lag from the r9 ev files
import os
from datetime import date, timedelta
flips = 0
checked = 0
cat_fires = [c for c in calls if c["flag"] in CATALYST_FLAGS]
evc = {}
for c in cat_fires:
    sym = c["symbol"]
    if sym not in evc:
        f = f"{SC}/../r9/ev/{sym}.json"
        evc[sym] = sorted(({"date": date.fromisoformat(r["date"][:10]),
                            "mc": r.get("marketCapitalization"),
                            "px": r.get("stockPrice")}
                           for r in (json.load(open(f)) if os.path.exists(f) else [])
                           if r.get("date")), key=lambda r: r["date"])
    px = pd.DataFrame(raw[sym]).assign(date=lambda d: pd.to_datetime(d["date"])) \
        .set_index("date")["adj_close"] if sym not in evc or True else None
for sym in {c["symbol"] for c in cat_fires}:
    pass
pxc = {}
for c in cat_fires:
    sym = c["symbol"]
    dd = date.fromisoformat(c["fire_date"])
    if sym not in pxc:
        pxc[sym] = pd.DataFrame(raw[sym]).assign(
            date=lambda d: pd.to_datetime(d["date"])).set_index("date")["adj_close"]
    px = pxc[sym]
    z_lag = pit_mcap(sym, pd.Timestamp(c["fire_date"]))
    eq0 = [r for r in evc[sym] if r["date"] + timedelta(days=45) <= dd
           and r.get("mc") and r.get("px")]
    eqf = [r for r in evc[sym] if r["date"] <= dd and r.get("mc") and r.get("px")]
    if not eqf or np.isnan(z_lag):
        continue
    q = eqf[-1]
    anchor = px[px.index.date <= q["date"]]
    if not len(anchor):
        continue
    z_fresh = q["mc"] * (float(px[px.index <= pd.Timestamp(dd)].iloc[-1]) / anchor.iloc[-1])
    checked += 1
    if (z_lag < 1e9) != (z_fresh < 1e9):
        flips += 1
print(f"[B8] lag-sensitivity: of {checked} catalyst fires, gate decision flips "
      f"under no-lag mcap for {flips}")

# ---- bootstrap / halves replication ----------------------------------------
def curve_series(callset):
    mult = {}
    for c in callset:
        d = pd.Timestamp(c["exit_date"])
        mult[d] = mult.get(d, 1.0) * (1.0 + 0.01 * c["r_net"])
    return pd.Series(mult).reindex(CAL).fillna(1.0).cumprod()

bcur, acur = curve_series(calls), curve_series(kept)
dr = acur.pct_change().fillna(0.0) - bcur.pct_change().fillna(0.0)
dm = dr.groupby(dr.index.to_period("M")).sum()
M = dm.values
rng = np.random.default_rng(777)  # DIFFERENT seed on purpose: seed-robustness
picks = rng.integers(0, len(M), size=(8000, len(M)))
bs = M[picks].mean(axis=1) * 12
obs, se = M.mean() * 12, bs.std()
print(f"[C1] A1a monthly-diff bootstrap (indep seed): obs {obs*100:+.2f}pp/yr, "
      f"t={obs/se:.2f}, p_raw={2*min((bs<=0).mean(),(bs>=0).mean()):.4f} "
      f"(r10: t=1.60, p=0.0965)")
# registered halves = 2016-2021 / 2022-2026 (code used index midpoint)
h1r = dm[dm.index < pd.Period("2022-01")].mean() * 12 * 100
h2r = dm[dm.index >= pd.Period("2022-01")].mean() * 12 * 100
mid = dm.index[len(dm) // 2]
print(f"[C2] halves: REGISTERED 2022 boundary h1={h1r:+.2f} h2={h2r:+.2f}; "
      f"code midpoint boundary {mid} h1={dm[dm.index < mid].mean()*12*100:+.2f} "
      f"h2={dm[dm.index >= mid].mean()*12*100:+.2f}")

# ---- ship-filter DD sign audit (analytic) -----------------------------------
print("[D1] ship filter requires dDD<=0 with DD stored NEGATIVE: an arm with a "
      "SHALLOWER (better) drawdown has dDD>0 and is REJECTED; a deeper (worse) "
      "one passes the DD leg. The registered intent (maxDD_arm no worse) is "
      "inverted. A1a dDD=+0.06 would have failed the DD leg even at p<0.05.")

# ---- A2v quick reproduction -------------------------------------------------
pit = json.load(open(f"{BACKEND}/data/pit_catalysts.json"))["symbols"]
DOWN = {"SUSPENDED", "TERMINATED", "WITHDRAWN"}
events = []
for sym, trials in pit.items():
    for t in trials:
        tl = t.get("timeline", [])
        for a, b in zip(tl, tl[1:]):
            d = pd.Timestamp(b["from"])
            pa, pb = a.get("pcd"), b.get("pcd")
            if pa and pb and len(pa) >= 7 and len(pb) >= 7:
                mo = (int(pb[:4]) - int(pa[:4])) * 12 + int(pb[5:7]) - int(pa[5:7])
                if mo >= 2:
                    events.append({"symbol": sym, "date": d, "type": "slip"})
                elif mo <= -2:
                    events.append({"symbol": sym, "date": d, "type": "pullin"})
            if b.get("status") in DOWN and a.get("status") not in DOWN:
                events.append({"symbol": sym, "date": d, "type": "downgrade"})
ev = pd.DataFrame(events)
print(f"[E1] raw event census: {ev.groupby('type').size().to_dict()} "
      f"(registration: 409 slips / 113 pullins / 34 downgrades)")
sw = {}
for _, r in ev[ev.type == "slip"].sort_values("date").iterrows():
    sw.setdefault(r.symbol, []).append(r.date)
a2v = [c for c in calls
       if not any(0 <= (pd.Timestamp(c["fire_date"]) - w).days <= 60
                  for w in sw.get(c["symbol"], []))]
_, a2c, a2d, _ = book_indep(a2v)
print(f"[E2] INDEP A2v: n={len(a2v)} CAGR {a2c:.2f}% dCAGR {a2c-base_cagr:+.2f}pp "
      f"(r10: 6023 calls, -14.11pp) [note: r10 de-clusters slips first; "
      f"veto windows barely differ]")
rm2 = [c for c in calls if c not in a2v]
print(f"[E3] A2v removed {len(rm2)} calls, sum r_net {sum(c['r_net'] for c in rm2):+.1f}R, "
      f"mean {np.mean([c['r_net'] for c in rm2]):+.3f}")
