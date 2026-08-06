"""El Nino event-study engine — Layer 3 (the honest core).

Events from ONI (NOAA): a run of >=5 overlapping seasons with anomaly >=0.5
whose peak reaches >=1.0 (moderate+). Onset = center month of the run's
first season. Strong subset: peak >=1.5.

Per event x commodity: cumulative log return from onset to +3/6/9/12m,
both raw and EXCESS vs the World Bank Agriculture index (controls broad
commodity/dollar/inflation beta). Prices: WB Pink Sheet monthly (1960-).

2026 gauge: realized futures moves since the 2026-05 onset (Yahoo) vs the
historical strong-event path distribution -> crowded/laggard scores.
"""
import json
import ssl
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd

DATA = "/home/user/uranium-dashboard/elnino-lab/data"
OUT = "/home/user/uranium-dashboard/elnino-lab"
ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")

# ---------- ONI -> events ----------
SEASON_CENTER = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
                 "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}
rows = []
for ln in open(f"{DATA}/oni.txt").read().splitlines()[1:]:
    p = ln.split()
    if len(p) == 4 and p[0] in SEASON_CENTER:
        rows.append((int(p[1]), SEASON_CENTER[p[0]], float(p[3])))
oni = pd.DataFrame(rows, columns=["yr", "m", "anom"])
oni["date"] = pd.to_datetime(dict(year=oni.yr, month=oni.m, day=1))
oni = oni.sort_values("date").reset_index(drop=True)

events = []
in_run, start_i = False, None
for i, r in oni.iterrows():
    if r.anom >= 0.5 and not in_run:
        in_run, start_i = True, i
    elif r.anom < 0.5 and in_run:
        run = oni.iloc[start_i:i]
        if len(run) >= 5 and run.anom.max() >= 1.0:
            events.append({"onset": run.iloc[0].date, "peak": float(run.anom.max()),
                           "end": run.iloc[-1].date})
        in_run = False
if in_run:
    run = oni.iloc[start_i:]
    if run.anom.max() >= 1.0:
        events.append({"onset": run.iloc[0].date, "peak": float(run.anom.max()),
                       "end": None, "current": True})
hist = [e for e in events if not e.get("current")]
cur = next((e for e in events if e.get("current")), None)
print("events:", [(e["onset"].strftime("%Y-%m"), e["peak"]) for e in events])

# ---------- Pink Sheet ----------
px = pd.read_excel(f"{DATA}/pinksheet.xlsx", sheet_name="Monthly Prices", header=4)
px = px.rename(columns={"Unnamed: 0": "ym"}).iloc[1:]
px = px[px.ym.astype(str).str.match(r"\d{4}M\d{2}")]
px["date"] = pd.to_datetime(px.ym.str.replace("M", "-", regex=False) + "-01")
px = px.set_index("date")
idx = pd.read_excel(f"{DATA}/pinksheet.xlsx", sheet_name="Monthly Indices", header=None)
# find header row with 'Agriculture'
hdr = None
for i in range(12):
    if idx.iloc[i].astype(str).str.contains("Agriculture").any():
        hdr = i
        break
idx = pd.read_excel(f"{DATA}/pinksheet.xlsx", sheet_name="Monthly Indices", header=hdr)
idx = idx.rename(columns={idx.columns[0]: "ym"})
idx = idx[idx.ym.astype(str).str.match(r"\d{4}M\d{2}")]
idx["date"] = pd.to_datetime(idx.ym.str.replace("M", "-", regex=False) + "-01")
ag_col = next(c for c in idx.columns if "Agriculture" in str(c))
ag = pd.to_numeric(idx.set_index("date")[ag_col], errors="coerce")

COMMODS = {
    "Cocoa": "Cocoa", "Coffee arabica": "Coffee, Arabica",
    "Coffee robusta": "Coffee, Robusta", "Rice (Thai 5%)": "Rice, Thai 5% ",
    "Palm oil": "Palm oil", "Fish meal": "Fish meal",
    "Soybean meal": "Soybean meal", "Soybeans": "Soybeans",
    "Wheat (US HRW)": "Wheat, US HRW", "Maize": "Maize",
    "Sugar": next((c for c in px.columns if "Sugar, world" in str(c)), "Sugar, World"),
    "Natural gas US": "Natural gas, US",
    "Copper": next((c for c in px.columns if "Copper" in str(c)), "Copper"),
}
series = {}
for name, col in COMMODS.items():
    if col in px.columns:
        series[name] = pd.to_numeric(px[col], errors="coerce")
    else:
        print("MISSING column:", name, col)

HORIZONS = [3, 6, 9, 12]
def event_path(s, onset, excess=True):
    out = {}
    base_i = s.index.searchsorted(onset)
    if base_i >= len(s.index):
        return None
    base_d = s.index[base_i]
    b = s.get(base_d)
    ab = ag.get(base_d)
    if pd.isna(b) or b is None:
        return None
    for h in HORIZONS:
        d = base_d + pd.DateOffset(months=h)
        if d not in s.index:
            out[h] = None
            continue
        v, av = s.get(d), ag.get(d)
        if pd.isna(v):
            out[h] = None
            continue
        r = np.log(v / b)
        if excess and not (pd.isna(av) or pd.isna(ab)):
            r -= np.log(av / ab)
        out[h] = round(100 * float(r), 1)
    return out

strong = [e for e in hist if e["peak"] >= 1.5]
results = {}
for name, s in series.items():
    per_event = {}
    for e in strong:
        p = event_path(s, e["onset"])
        if p:
            per_event[e["onset"].strftime("%Y-%m")] = p
    agg = {}
    for h in HORIZONS:
        vals = [p[h] for p in per_event.values() if p.get(h) is not None]
        if len(vals) >= 4:
            agg[h] = {"n": len(vals), "median": round(float(np.median(vals)), 1),
                      "q25": round(float(np.percentile(vals, 25)), 1),
                      "q75": round(float(np.percentile(vals, 75)), 1),
                      "pos": sum(1 for v in vals if v > 0)}
    results[name] = {"events": per_event, "agg": agg}

json.dump({"strong_events": [(e["onset"].strftime("%Y-%m"), e["peak"]) for e in strong],
           "current_onset": cur["onset"].strftime("%Y-%m") if cur else None,
           "results": results},
          open(f"{OUT}/event_study.json", "w"), indent=1)

print(f"\nstrong events (peak>=1.5): {[(e['onset'].strftime('%Y-%m'), e['peak']) for e in strong]}")
print(f"current event onset: {cur['onset'].strftime('%Y-%m') if cur else '?'} peak-so-far {cur['peak'] if cur else '?'}")
print(f"\nEXCESS-vs-Agriculture median path (strong events), % log return:")
print(f"{'commodity':18} {'+3m':>12} {'+6m':>12} {'+9m':>12} {'+12m':>12}")
for name, r in results.items():
    cells = []
    for h in HORIZONS:
        a = r["agg"].get(h)
        cells.append(f"{a['median']:+.1f} ({a['pos']}/{a['n']})" if a else "-")
    print(f"{name:18} {cells[0]:>12} {cells[1]:>12} {cells[2]:>12} {cells[3]:>12}")
