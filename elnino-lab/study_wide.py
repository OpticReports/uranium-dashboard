"""Wide sweep: the uncrowded Pink Sheet universe through the same event-study
machinery. Ag/soft items: excess vs Agriculture index. Metals: excess vs Base
Metals index (silver vs gold). Plus an EP-subset pass (1972/1982/1997 + 2023)
for the Ecuador/Peru-mechanism commodities, since 2026 is an EP event."""
import json
import numpy as np
import pandas as pd

DATA = "data"
SEASON_CENTER = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
                 "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}
STRONG = ["1957-04", "1965-06", "1972-06", "1982-05", "1991-06", "1997-05",
          "2009-07", "2014-10", "2023-06"]
EP = ["1972-06", "1982-05", "1997-05", "2023-06"]      # eastern-Pacific flavor

px = pd.read_excel(f"{DATA}/pinksheet.xlsx", sheet_name="Monthly Prices", header=4)
px = px.rename(columns={"Unnamed: 0": "ym"}).iloc[1:]
px = px[px.ym.astype(str).str.match(r"\d{4}M\d{2}")]
px["date"] = pd.to_datetime(px.ym.str.replace("M", "-", regex=False) + "-01")
px = px.set_index("date")

raw = pd.read_excel(f"{DATA}/pinksheet.xlsx", sheet_name="Monthly Indices", header=None)

def index_series(label):
    """Positional lookup: labels live on different header rows (5-8)."""
    for i in range(10):
        for j, v in enumerate(raw.iloc[i]):
            if label in str(v):
                dat = raw[raw[0].astype(str).str.match(r"\d{4}M\d{2}")]
                s = pd.to_numeric(dat[j], errors="coerce")
                s.index = pd.to_datetime(
                    dat[0].str.replace("M", "-", regex=False) + "-01")
                return s
    raise KeyError(label)

ag = index_series("Agriculture")
base = index_series("Base Metals")
gold = pd.to_numeric(px["Gold"], errors="coerce")

# (display name, column, benchmark)
UNIVERSE = [
    ("Banana (US)", "Banana, US", ag), ("Banana (EU)", "Banana, Europe", ag),
    ("Shrimp (Mexican)", "Shrimps, Mexican", ag), ("Orange", "Orange", ag),
    ("Tea Mombasa", "Tea, Mombasa", ag), ("Tea Colombo", "Tea, Colombo", ag),
    ("Tea Kolkata", "Tea, Kolkata", ag),
    ("Coconut oil", "Coconut oil", ag), ("Palm kernel oil", "Palm kernel oil", ag),
    ("Rubber RSS3", "Rubber, RSS3", ag), ("Cotton", "Cotton, A Index", ag),
    ("Logs Malaysian", "Logs, Malaysian", ag), ("Plywood", "Plywood", ag),
    ("Urea", "Urea ", ag), ("DAP", "DAP", ag), ("Phosphate rock", "Phosphate rock", ag),
    ("Rice Viet 5%", "Rice, Viet Namese 5%", ag),
    ("Zinc", "Zinc", base), ("Tin", "Tin", base), ("Nickel", "Nickel", base),
    ("Lead", "Lead", base), ("Aluminum", "Aluminum", base),
    ("Silver (vs gold)", "Silver", gold),
]
HOR = [3, 6, 9, 12]

def path(s, bench, onset):
    onset = pd.Timestamp(onset + "-01")
    if onset not in s.index:
        return None
    b, ab = s.get(onset), bench.get(onset)
    if pd.isna(b) or pd.isna(ab):
        return None
    out = {}
    for h in HOR:
        d = onset + pd.DateOffset(months=h)
        v, av = s.get(d), bench.get(d)
        out[h] = (round(100 * float(np.log(v / b) - np.log(av / ab)), 1)
                  if not (v is None or av is None or pd.isna(v) or pd.isna(av)) else None)
    return out

def agg_table(events):
    rows = {}
    for name, col, bench in UNIVERSE:
        if col not in px.columns:
            continue
        s = pd.to_numeric(px[col], errors="coerce")
        per = {ev: p for ev in events if (p := path(s, bench, ev))}
        agg = {}
        for h in HOR:
            vals = [p[h] for p in per.values() if p.get(h) is not None]
            if len(vals) >= max(3, int(0.5 * len(events))):
                agg[h] = {"n": len(vals),
                          "median": round(float(np.median(vals)), 1),
                          "pos": sum(1 for v in vals if v > 0)}
        rows[name] = {"per_event": per, "agg": agg}
    return rows

full = agg_table(STRONG)
ep = agg_table(EP)

def show(rows, title):
    print(f"\n== {title} (excess vs sector benchmark, % log return)")
    print(f"{'commodity':18} {'+3m':>13} {'+6m':>13} {'+9m':>13} {'+12m':>13}")
    for name, r in rows.items():
        cells = []
        for h in HOR:
            a = r["agg"].get(h)
            cells.append(f"{a['median']:+.1f} ({a['pos']}/{a['n']})" if a else "-")
        print(f"{name:18} {cells[0]:>13} {cells[1]:>13} {cells[2]:>13} {cells[3]:>13}")

show(full, "ALL 9 strong events")
show(ep, "EP-flavor subset (1972/1982/1997/2023) - n=4, DESCRIPTIVE ONLY")
json.dump({"full": {k: v["agg"] for k, v in full.items()},
           "ep": {k: v["agg"] for k, v in ep.items()},
           "per_event_full": {k: v["per_event"] for k, v in full.items()}},
          open("wide_study.json", "w"), indent=1, default=str)
