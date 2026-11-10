"""R9 panel builder — PIT component scores + sizes + forward excess returns.

Conventions (frozen in the registration d3339bb + amendment):
- signals at close t use only data available <= t (financials by acceptedDate,
  SI by settlement+10 business days, grades/catalysts by their own dates);
- forward returns SKIP A DAY: close(t+1) -> close(t+1+k), XBI-excess
  (the Unicorn lesson: nothing earns the print inside its own signal);
- C_rev / C_pos are labeled PROXIES; C_pos exists 2018+ only.
"""
import csv
import io
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
from scripts.backtest_calls_10y import (  # noqa: E402  (reuse, never rewrite)
    parse_trial_timeline, pit_calendar_by_bar)

bars_all = json.load(open(f"{BACKEND}/data/backtest_bars.json"))
pit = json.load(open(f"{BACKEND}/data/pit_catalysts.json"))["symbols"]
import yaml  # noqa: E402
scfg = yaml.safe_load(open(f"{BACKEND}/config/scoring.yaml"))
IMPACTS = scfg["components"]["catalyst_score"]["impact_weights"]
LAM_CAT = math.log(2) / scfg["components"]["catalyst_score"]["half_life_days"]
HORIZON = scfg["components"]["catalyst_score"]["horizon_days"]
LAM_REV = math.log(2) / 30.0
REV_WIN = 90

class Bar:
    __slots__ = ("date",)
    def __init__(self, d):
        self.date = d

def biz_add(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d

xbi = pd.DataFrame(bars_all["XBI"]).assign(
    date=lambda d: pd.to_datetime(d["date"])).set_index("date")["adj_close"]

rows = []
for sym in sorted(k for k in bars_all if k != "XBI"):
    df = pd.DataFrame(bars_all[sym]).assign(
        date=lambda d: pd.to_datetime(d["date"])).set_index("date")
    px = df["adj_close"]
    dates = px.index

    # C_cat: as-known catalyst score per bar (reused PIT machinery)
    trials = pit.get(sym, [])
    cal = pit_calendar_by_bar(trials, [Bar(d.date()) for d in dates], IMPACTS)
    c_cat, n_active = [], []
    for d, cats in zip(dates, cal):
        s = 0.0
        for c in cats:
            du = (c["pcd"] - d.date()).days
            if 0 <= du <= HORIZON:
                s += c["impact"] * math.exp(-LAM_CAT * du)
        c_cat.append(s)
        n_active.append(len(cats))          # active trials w/ live future PCD
    c_cat = pd.Series(c_cat, index=dates)
    n_active = pd.Series(n_active, index=dates)

    # Z2 full: count of non-terminated trials as-known (active per store)
    parsed = [parse_trial_timeline(t, IMPACTS) for t in trials]
    z2 = []
    for d in dates:
        dd = d.date()
        cnt = 0
        for ivs in parsed:
            for iv in ivs:
                if iv["from"] <= dd and (iv["to"] is None or dd < iv["to"]):
                    cnt += iv["active"]
                    break
        z2.append(cnt)
    z2 = pd.Series(z2, index=dates)

    # C_rev proxy: net rating-action direction, 90d window, 30d half-life
    try:
        g = json.load(open(f"{SC}/grades/{sym}.json"))
    except Exception:
        g = []
    acts = sorted(((date.fromisoformat(r["date"][:10]),
                    1 if r.get("action") == "upgrade" else
                    -1 if r.get("action") == "downgrade" else 0)
                   for r in g if r.get("date")), key=lambda x: x[0])
    c_rev = []
    for d in dates:
        dd, s, any_ = d.date(), 0.0, False
        for ad, dirn in acts:
            age = (dd - ad).days
            if 0 <= age <= REV_WIN and dirn != 0:
                s += dirn * math.exp(-LAM_REV * age)
                any_ = True
        c_rev.append(s if any_ else np.nan)
    c_rev = pd.Series(c_rev, index=dates)

    # C_pos proxy: -delta(SI/ADV) over trailing 3 settlements, +10 biz days lag
    c_pos = pd.Series(np.nan, index=dates)
    try:
        si = list(csv.DictReader(io.StringIO(open(f"{SC}/si/{sym}.csv").read())))
        si = sorted(({"d": date.fromisoformat(r["settlementDate"]),
                      "x": float(r["currentShortPositionQuantity"]) /
                           max(float(r["averageDailyVolumeQuantity"] or 0), 1.0)}
                     for r in si if r.get("settlementDate")), key=lambda r: r["d"])
        avail = [(biz_add(r["d"], 10), i) for i, r in enumerate(si)]
        ai = 0
        latest = None
        for d in dates:
            dd = d.date()
            while ai < len(avail) and avail[ai][0] <= dd:
                latest = avail[ai][1]
                ai += 1
            if latest is not None and latest >= 3:
                c_pos[d] = -(si[latest]["x"] - si[latest - 3]["x"])
    except Exception:
        pass

    # C_run + Z1 + Z3 from quarterly statements (acceptedDate = availability)
    def qload(sub, fields):
        try:
            rs = json.load(open(f"{SC}/{sub}/{sym}.json"))
        except Exception:
            return []
        out = []
        for r in rs:
            try:
                out.append({"avail": date.fromisoformat(
                    (r.get("acceptedDate") or r.get("filingDate")
                     or r["date"])[:10]),
                    "date": date.fromisoformat(r["date"][:10]),
                    **{f: r.get(f) for f in fields}})
            except Exception:
                continue
        return sorted(out, key=lambda r: r["avail"])

    bs = qload("bs", ["cashAndShortTermInvestments"])
    inc = qload("inc", ["revenue", "operatingIncome"])
    ev = json.load(open(f"{SC}/ev/{sym}.json")) if \
        os.path.exists(f"{SC}/ev/{sym}.json") else []
    ev = sorted(({"date": date.fromisoformat(r["date"][:10]),
                  "mc": r.get("marketCapitalization"),
                  "px": r.get("stockPrice")} for r in ev if r.get("date")),
                key=lambda r: r["date"])

    c_run, z1, z3 = [], [], []
    for d in dates:
        dd = d.date()
        b = [r for r in bs if r["avail"] <= dd]
        i_ = [r for r in inc if r["avail"] <= dd]
        cash = b[-1]["cashAndShortTermInvestments"] if b else None
        burn = None
        if i_:
            oi = i_[-1].get("operatingIncome")
            burn = max(-(oi or 0.0), 0.0)
        if cash is None or burn is None:
            c_run.append(np.nan)
        elif burn <= 0:
            c_run.append(0.0)               # profitable: no runway penalty
        else:
            rq = cash / burn
            c_run.append(100.0 * (1.0 - min(rq / 8.0, 1.0)))
        ltm = sum(r.get("revenue") or 0.0 for r in i_[-4:]) if len(i_) >= 4 else None
        z3.append(1 if (ltm is not None and ltm >= 250e6) else 0)
        # Z1: quarter mktcap scaled by adjusted-price ratio (split-safe),
        # 45d lag on the quarter record
        eq = [r for r in ev if r["date"] + timedelta(days=45) <= dd
              and r.get("mc") and r.get("px")]
        if eq:
            q = eq[-1]
            anchor = px[px.index.date <= q["date"]]
            z1.append(q["mc"] * (px[d] / anchor.iloc[-1]) if len(anchor) else np.nan)
        else:
            z1.append(np.nan)

    fwd = {}
    for k in (5, 21, 63):
        f_sym = px.shift(-(1 + k)) / px.shift(-1) - 1.0
        f_x = xbi.reindex(dates).shift(-(1 + k)) / xbi.reindex(dates).shift(-1) - 1.0
        fwd[k] = f_sym - f_x

    rows.append(pd.DataFrame({
        "symbol": sym, "c_cat": c_cat, "c_rev": c_rev, "c_pos": c_pos,
        "c_run": c_run, "z1_mktcap": z1, "z2_trials": z2.astype(float),
        "z3_commercial": z3, "n_active_cat": n_active,
        "fwd5": fwd[5], "fwd21": fwd[21], "fwd63": fwd[63]}))

panel = pd.concat(rows).reset_index().rename(columns={"index": "date"})
panel.to_csv(f"{SC}/panel.csv", index=False)
print(f"panel: {len(panel)} rows, {panel['symbol'].nunique()} symbols, "
      f"{panel['date'].min().date()} -> {panel['date'].max().date()}")
for c in ("c_cat", "c_rev", "c_pos", "c_run", "z1_mktcap"):
    print(c, "coverage:", f"{panel[c].notna().mean():.0%}")
