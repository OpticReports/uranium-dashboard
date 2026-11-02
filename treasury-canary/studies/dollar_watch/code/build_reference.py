"""Build the frozen historical reference for the Dollar watch tab.

    python3 -I studies/dollar_watch/code/build_reference.py studies/dollar_watch/data \
        backend/app/sources/dollar_reference.json

Every historical number the tab displays comes from here, recomputed from the
committed, reviewed study data (studies/dollar_watch/data, fetched 2026-11-02)
with ONE window convention: an event at month m is "followed" by a crisis onset
if an onset falls in (m, m+H] — strictly after m — and the base rate is the
share of all eligible months with an onset in (m, m+H]. (Finder A's band test
counted the excursion's own start month; under the strict convention its
12-month count is 8 of 17, not 9 of 17 — reviewer 1, S-minor.)
Static tables (lead/lag, end-of-scramble sequence, counter-examples) are copied
from the reviewed notes with their source and corrections.
Stdlib only; deterministic (sorted keys, no clock): same inputs -> same bytes.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import sys

FROZEN_ON = "2026-11-02"
DATA, OUT = sys.argv[1], sys.argv[2]
FRED = os.path.join(DATA, "fred")
INPUTS = ["dollar_monthly.csv", "dxy_daily.csv", "crises.csv", "crises_metrics.csv", "band_excursions.csv",
          "gold_daily.csv", "gold_monthly.csv", "spx_daily.csv", "chain_2022.csv", "johnson_quarterly.csv",
          "scoping_dollar_monthly.csv"] + [os.path.join("fred", f) for f in sorted(os.listdir(FRED))]


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def fnum(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def r(x, k=2):
    return None if x is None else round(x, k)


def fred_daily(sid: str) -> dict:
    out = {}
    for row in csv.DictReader(open(os.path.join(FRED, sid + ".csv"))):
        v = fnum(row[sid])
        if v is not None:
            out[row["observation_date"]] = v
    return out


def fred_monthly(sid: str) -> dict:
    return {k[:7]: v for k, v in fred_daily(sid).items()}


# ----------------------------------------------------------------- monthly DXY (ICE, finder A)
mon = [row for row in csv.DictReader(open(os.path.join(DATA, "dollar_monthly.csv")))
       if row["dxy_close"] and row["month"] <= "2026-10"]          # 2026-11 is a one-day partial month
MONTHS = [row["month"] for row in mon]
CLOSE = [float(row["dxy_close"]) for row in mon]
AVG = [float(row["dxy_avg"]) for row in mon]
IDX = {m: i for i, m in enumerate(MONTHS)}
LAST = len(MONTHS) - 1

# ----------------------------------------------------------------- crisis lists
crises = [row for row in csv.DictReader(open(os.path.join(DATA, "crises.csv"))) if row["is_crisis"] == "1"]
LISTS = {
    "A25": {"label": "finder A: 25 global / regional financial crises 1973-2026 (broad; hand-dated with sources)",
            "onsets": [{"month": c["start"], "name": c["name"]} for c in crises]},
    "C16": {"label": "finder C: 16 multi-country dollar-stress onsets 1974-2023 ('L-broad')",
            "onsets": [{"month": m, "name": n} for m, n in [
                ("1974-06", "Herstatt / Franklin National"), ("1982-08", "Mexico / LatAm debt"), ("1987-10", "Black Monday"),
                ("1992-09", "ERM"), ("1994-12", "Tequila"), ("1997-07", "Asia"), ("1998-08", "Russia / LTCM"),
                ("2001-02", "Turkey / Argentina"), ("2008-09", "Lehman"), ("2010-05", "Greece / euro"), ("2013-05", "taper tantrum"),
                ("2015-08", "China devaluation / commodities"), ("2018-08", "Turkey / Argentina"), ("2020-03", "COVID"),
                ("2022-09", "UK LDI / EM FX at the dollar peak"), ("2023-03", "SVB / Credit Suisse")]]},
    "N5": {"label": "the five dollar-funding squeezes proper (1982, 1998, 2008, 2020, 2022) - reported, never inferred on",
           "onsets": [{"month": m, "name": n} for m, n in [("1982-08", "LatAm debt"), ("1998-08", "Russia / LTCM"),
                                                          ("2008-09", "Lehman"), ("2020-03", "COVID"), ("2022-09", "UK LDI / EM FX")]]},
}
ONSET_IDX = {k: sorted(IDX[o["month"]] for o in v["onsets"] if o["month"] in IDX) for k, v in LISTS.items()}


def followed(i: int, h: int, key: str) -> bool:
    return any(i < o <= i + h for o in ONSET_IDX[key])


def base(h: int, key: str) -> dict:
    elig = range(0, LAST - h + 1)
    k = sum(1 for i in elig if followed(i, h, key))
    return {"months": len(elig), "hits": k, "rate": r(k / len(elig), 3)}


# ----------------------------------------------------------------- band 85-105 (17 merged excursions, finder A)
exc = [row for row in csv.DictReader(open(os.path.join(DATA, "band_excursions.csv"))) if row["band"] == "85-105 merged(gap<=3)"]
excursions = [{"side": e["side"], "start": e["start"], "end": e["end"], "months": int(e["months"]),
               "extreme": fnum(e["extreme"]), "extreme_month": e["extreme_month"],
               "began_inside_crisis_A25": e["already_in_crisis_at_start"] == "yes"} for e in exc]
band_by_list = {}
for key in LISTS:
    row = {"n_excursions": len(excursions)}
    for h in (12, 24):
        hits = sum(1 for e in excursions if e["start"] in IDX and followed(IDX[e["start"]], h, key))
        row[f"hits_{h}m"] = hits
        row[f"rate_{h}m"] = r(hits / len(excursions), 3)
        row[f"base_{h}m"] = base(h, key)["rate"]
    band_by_list[key] = row

# ----------------------------------------------------------------- momentum: 12m change of the monthly-average DXY > +10%
mom = {MONTHS[i]: AVG[i] / AVG[i - 12] - 1 for i in range(12, len(MONTHS))}
sig = [m for m, v in mom.items() if v > 0.10]
episodes, prev = [], None
for m in sig:
    if prev is None or IDX[m] - IDX[prev] > 12:
        episodes.append(m)
    prev = m
mom_by_list = {}
for key in LISTS:
    elig_sig = [m for m in sig if IDX[m] <= LAST - 12]
    hits = sum(1 for m in elig_sig if followed(IDX[m], 12, key))
    ep_elig = [m for m in episodes if IDX[m] <= LAST - 12]
    ep_hits = sum(1 for m in ep_elig if followed(IDX[m], 12, key))
    mom_by_list[key] = {"signal_months": len(elig_sig), "signal_months_followed_12m": hits, "rate_months": r(hits / len(elig_sig), 3),
                        "episodes": len(ep_elig), "episodes_followed_12m": ep_hits, "base_12m": base(12, key)["rate"]}

# ----------------------------------------------------------------- dollar-yield quadrant into each onset (3m window, finder C convention)
gs10 = fred_monthly("GS10")


def quad_of(m: str):
    i = IDX.get(m)
    if i is None or i < 3 or m not in gs10 or MONTHS[i - 3] not in gs10:
        return None
    dd = AVG[i] / AVG[i - 3] - 1
    dy = gs10[m] - gs10[MONTHS[i - 3]]
    return {"month": m, "dxy_3m_pct": r(100 * dd, 1), "y10_3m_pp": r(dy, 2),
            "quadrant": ("usd_up" if dd > 0 else "usd_down") + "_" + ("yld_up" if dy > 0 else "yld_down")}


quadrant = {}
_allq = [q for q in (quad_of(m) for m in MONTHS) if q]
_bc = {}
for q in _allq:
    _bc[q["quadrant"]] = _bc.get(q["quadrant"], 0) + 1
quadrant_base = {"months": len(_allq), "first": _allq[0]["month"], "last": _allq[-1]["month"], "counts": _bc,
                 "shares": {k: r(v / len(_allq), 3) for k, v in sorted(_bc.items())},
                 "basis": "every month 1971-2026 classified the same way: the unconditional share to compare the onset counts against"}
for key in ("C16", "A25"):
    rows_ = [q for q in (quad_of(o["month"]) for o in LISTS[key]["onsets"]) if q]
    counts = {}
    for q in rows_:
        counts[q["quadrant"]] = counts.get(q["quadrant"], 0) + 1
    quadrant[key] = {"counts": counts, "n": len(rows_), "onsets": rows_}

# ----------------------------------------------------------------- crisis metrics: dollar at peak stress, gold over the episode
cm = [row for row in csv.DictReader(open(os.path.join(DATA, "crises_metrics.csv"))) if row["is_crisis"] == "1"]
fell = [{"id": c["id"], "name": c["name"], "start": c["start"], "peak_stress": c["peak_stress"],
         "dxy_eve_to_peak_stress_pct": fnum(c["dxy_chg_eve_to_peak_stress_pct"])}
        for c in cm if (fnum(c["dxy_chg_eve_to_peak_stress_pct"]) or 0) < 0]
gold_end = [c for c in cm if fnum(c["gold_eve_to_end_pct"]) is not None]
gold_higher = [{"id": c["id"], "name": c["name"], "pct": fnum(c["gold_eve_to_end_pct"])} for c in gold_end if fnum(c["gold_eve_to_end_pct"]) > 0]


def daily(path, col="close"):
    out = {}
    for row in csv.DictReader(open(path)):
        v = fnum(row.get(col))
        if v is not None:
            out[row["date"]] = v
    return out


gold_c, gold_h, gold_l = (daily(os.path.join(DATA, "gold_daily.csv"), c) for c in ("close", "high", "low"))


def drawdown(series_hi, series_lo, lo, hi):
    """max peak-to-subsequent-trough inside [lo, hi] using highs for peaks and lows for troughs."""
    ds = sorted(d for d in series_hi if lo <= d <= hi)
    best, pk, pkd, out = 0.0, -1e9, None, None
    for d in ds:
        if series_hi[d] > pk:
            pk, pkd = series_hi[d], d
        lw = series_lo.get(d)
        if lw is not None and 1 - lw / pk > best:
            best, out = 1 - lw / pk, (pkd, d)
    return r(-100 * best, 1), out


gold_dd = []
for name, lo, hi in (("GFC 2008", "2008-03-01", "2008-11-30"), ("COVID 2020", "2020-03-01", "2020-03-31"), ("2022", "2022-03-01", "2022-10-31")):
    intra, d_i = drawdown(gold_h, gold_l, lo, hi)
    close, d_c = drawdown(gold_c, gold_c, lo, hi)
    gold_dd.append({"episode": name, "intraday_pct": intra, "close_pct": close, "peak": d_i[0], "trough": d_i[1]})
gm = {row["month"]: fnum(row["gold_best"]) for row in csv.DictReader(open(os.path.join(DATA, "gold_monthly.csv")))}
gold_dd.append({"episode": "dotcom 1999-2001", "monthly_avg_pct": r(100 * (gm["2001-04"] / gm["1999-10"] - 1), 1),
                "peak": "1999-10", "trough": "2001-04"})

# ----------------------------------------------------------------- the frozen deceleration ('dollar-scramble peak') rule
B_ = fred_daily("DTWEXBGS")
Y_ = fred_daily("DGS10")
V_ = fred_daily("VIXCLS")
RULE = {"index": "Fed broad dollar DTWEXBGS, daily, on days with DTWEXBGS, DGS10 and VIXCLS all published (the frozen code/decel_realtime.py index)",
        "roc_days": 20, "window_days": 60, "min_max_roc": 0.04, "decel_ratio": 0.5, "near_high": 0.97,
        "yield_lookback_days": 20, "cooling_days": 120, "rearm_multiple": 1.5, "first_eval_index": 80}


def scramble_firings(dates, B, Y, rearm=True, p=RULE):
    n = len(B)
    roc = [None] * n
    for k in range(p["roc_days"], n):
        roc[k] = B[k] / B[k - p["roc_days"]] - 1
    fires, last, last_mx = [], -10 ** 9, 0.0
    for k in range(p["first_eval_index"], n):
        w = [(roc[j], j) for j in range(k - p["window_days"], k + 1) if roc[j] is not None]
        mx = max(v for v, _ in w)
        kmx = min(j for v, j in w if v == mx)
        if (mx >= p["min_max_roc"] and roc[k] <= p["decel_ratio"] * mx
                and B[k] >= p["near_high"] * max(B[k - p["window_days"]:k + 1])
                and Y[k] < Y[max(0, kmx - p["yield_lookback_days"])]
                and (k - last > p["cooling_days"] or (rearm and mx >= p["rearm_multiple"] * last_mx))):
            fires.append({"date": dates[k], "k": k, "roc20_max_pct": r(100 * mx, 1), "roc20_max_date": dates[kmx],
                          "roc20_now_pct": r(100 * roc[k], 1), "dollar": r(B[k], 2)})
            last, last_mx = k, mx
    return fires


RDATES = sorted(d for d in B_ if d in Y_ and d in V_)     # identical to decel_realtime.py: days with B, VIX and the 10y
RB = [B_[d] for d in RDATES]
RY = [Y_[d] for d in RDATES]
spx = daily(os.path.join(DATA, "spx_daily.csv"))
SPX_D = sorted(spx)
baa10y = fred_daily("BAA10Y")
EMFX_IDS = ["DEXBZUS", "DEXMXUS", "DEXSFUS", "DEXINUS", "DEXKOUS", "DEXTHUS", "DEXCHUS", "DEXMAUS"]
EMFX = {s: fred_daily(s) for s in EMFX_IDS}


def asof(series: dict, d: str, keys=None):
    keys = keys or sorted(series)
    lo, hi = 0, len(keys) - 1
    if not keys or keys[0] > d:
        return None
    while lo < hi:                      # last key <= d
        mid = (lo + hi + 1) // 2
        if keys[mid] <= d:
            lo = mid
        else:
            hi = mid - 1
    return series[keys[lo]]


EMFX_KEYS = {s: sorted(v) for s, v in EMFX.items()}


def emfx(d: str):
    """equal-weight basket of 8 EM currencies per USD, log-average; up = EM currencies weaker. None if any leg missing."""
    vals = [asof(EMFX[s], d, EMFX_KEYS[s]) for s in EMFX_IDS]
    if any(v is None for v in vals):
        return None
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


def add_months(d: str, k: int) -> str:
    y, m = int(d[:4]), int(d[5:7]) + k
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}{d[7:]}"


BAA_K, SPX_K, VIX_K, B_K = sorted(baa10y), SPX_D, sorted(V_), sorted(B_)


def outcomes(d: str) -> dict:
    """what EM FX, spreads and the S&P did over the following 3 / 6 / 12 calendar months (as-of closes)."""
    o = {}
    s0, e0, b0, d0 = asof(spx, d, SPX_K), emfx(d), asof(baa10y, d, BAA_K), asof(B_, d, B_K)
    for k in (3, 6, 12):
        dk = add_months(d, k)
        if dk > FROZEN_ON:
            o[f"{k}m"] = None
            continue
        s1, e1, b1, d1 = asof(spx, dk, SPX_K), emfx(dk), asof(baa10y, dk, BAA_K), asof(B_, dk, B_K)
        o[f"{k}m"] = {"spx_pct": r(100 * (s1 / s0 - 1), 1) if s0 and s1 else None,
                      "emfx_pct": r(100 * (e1 / e0 - 1), 1) if e0 and e1 else None,
                      "baa10y_pp": r(b1 - b0, 2) if b0 is not None and b1 is not None else None,
                      "broad_dollar_pct": r(100 * (d1 / d0 - 1), 1) if d0 and d1 else None}
    return o


def firing_record(f: dict) -> dict:
    k = f["k"]
    seg = RB[k:min(len(RB), k + 250)]
    pk = k + seg.index(max(seg))
    i0 = SPX_D.index(max(x for x in SPX_D if x <= f["date"]))
    fut = [(spx[x], x) for x in SPX_D[i0:i0 + 251]]
    lowv, lowd = min(fut)
    vix0 = asof(V_, f["date"], VIX_K)
    d60 = RDATES[min(len(RDATES) - 1, k + 60)]
    vix60 = asof(V_, d60, VIX_K)
    return {**{x: f[x] for x in ("date", "roc20_max_pct", "roc20_max_date", "roc20_now_pct", "dollar")},
            "dollar_further_rise_pct": r(100 * (RB[pk] / RB[k] - 1), 1), "dollar_peak_date": RDATES[pk],
            "spx_to_next_low_pct": r(100 * (lowv / spx[SPX_D[i0]] - 1), 1), "spx_low_date": lowd,
            "vix_change_60d": r(vix60 - vix0, 1) if vix0 is not None and vix60 is not None else None,
            "outcomes": outcomes(f["date"])}


rearm = [firing_record(f) for f in scramble_firings(RDATES, RB, RY, True) if f["date"] <= FROZEN_ON]
unpatched = [f["date"] for f in scramble_firings(RDATES, RB, RY, False)]
CLASS = {"2008-09-22": "first wave of a two-wave scramble", "2008-11-06": "re-arm firing (added after the 2008-09-22 miss); dollar scramble peaking, equity low still four months away",
         "2010-06-03": "euro-crisis mini-episode, resolved within weeks", "2011-11-01": "euro-crisis mini-episode",
         "2012-06-07": "euro-crisis mini-episode, resolved within weeks", "2020-04-09": "clean: the scramble had peaked",
         "2022-07-28": "first wave of a policy grind (not a funding scramble)"}
for f in rearm:
    f["reading"] = CLASS.get(f["date"], "unclassified")

# V-spike timing (daily): when the 20-day climb, the VIX and the dollar peaked
vspike = []
for name, lo, hi in (("GFC 2008-09", "2008-06-01", "2009-06-30"), ("COVID 2020", "2020-01-15", "2020-06-30")):
    ks = [i for i, d in enumerate(RDATES) if lo <= d <= hi]
    pk = max(ks, key=lambda i: RB[i])
    rk = max((i for i in ks if i <= pk and i >= 20), key=lambda i: RB[i] / RB[i - 20])
    vd = [d for d in V_ if lo <= d <= hi]
    vpk = max(vd, key=lambda d: V_[d])
    vspike.append({"episode": name, "climb_peak": RDATES[rk], "climb_peak_pct": r(100 * (RB[rk] / RB[rk - 20] - 1), 1),
                   "vix_peak": vpk, "dollar_peak": RDATES[pk], "dollar_further_rise_after_climb_peak_pct": r(100 * (RB[pk] / RB[rk] - 1), 1),
                   "index_days_climb_to_dollar_peak": pk - rk,
                   "basis": "20-index-day change of the broad dollar on the rule's own index (days with DTWEXBGS, DGS10 and VIXCLS)",
                   **({"note": "on the full H.10 calendar the 2008 climb peak is 2008-10-24 (+12.3%, dollar +4.1% further)"} if name.startswith("GFC") else {})})

# monthly analogue on 1973-2005 (data the daily parameters never saw) — recomputed from the scoping panel
sm = list(csv.DictReader(open(os.path.join(DATA, "scoping_dollar_monthly.csv"))))
mD = [float(x["dxy_spliced"]) for x in sm]
mY = [float(x["gs10"]) for x in sm]
mP = [float(x["spx_shiller"]) for x in sm]
mM = [x["month"] for x in sm]
roc3 = [None] * len(mD)
for k in range(3, len(mD)):
    roc3[k] = mD[k] / mD[k - 3] - 1
mfires, last = [], -99
for k in range(15, len(mD) - 12):
    w = [(roc3[j], j) for j in range(k - 12, k + 1)]
    mx = max(v for v, _ in w)
    kmx = min(j for v, j in w if v == mx)
    if mx >= 0.06 and roc3[k] <= 0.5 * mx and mD[k] >= 0.97 * max(mD[k - 12:k + 1]) and mY[k] < mY[max(0, kmx - 3)] and k - last >= 12:
        last = k
        win = list(range(max(0, k - 3), min(len(mD), k + 13)))
        pk = max(win, key=lambda j: mD[j])
        mfires.append({"month": mM[k], "peak_within_3m": abs(pk - k) <= 3 and mD[pk] >= max(mD[k - 3:k + 13]) * 0.999,
                       "spx_12m_up": mP[k + 12] > mP[k]})
pre = [f for f in mfires if f["month"] < "2006-01"]
base_k = [k for k in range(15, len(mD) - 12) if mM[k] < "2006-01"]
monthly_null = {"window": "1973-2005 (monthly; unseen by the daily parameter choices)", "firings": len(pre),
                "dollar_peak_within_3m": sum(f["peak_within_3m"] for f in pre),
                "base_dollar_peak_within_3m": r(sum(1 for k in base_k if abs(max(range(max(0, k - 3), min(len(mD), k + 13)), key=lambda j: mD[j]) - k) <= 3) / len(base_k), 2),
                "spx_up_12m": sum(f["spx_12m_up"] for f in pre), "base_spx_up_12m": r(sum(1 for k in base_k if mP[k + 12] > mP[k]) / len(base_k), 2),
                "months": [f["month"] for f in pre]}

# ----------------------------------------------------------------- momentum ledger (reconstructed, in-sample)
spx_m = {}
for d in SPX_D:
    spx_m.setdefault(d[:7], []).append(spx[d])
spx_m = {k: sum(v) / len(v) for k, v in spx_m.items()}
baa_m = fred_monthly("BAA")
mom_ledger = []
for m in episodes:
    i = IDX[m]
    row = {"month": m, "dxy_12m_pct": r(100 * mom[m], 1), "dxy": r(AVG[i], 1), "outcomes": {}}
    for k in (3, 6, 12):
        if i + k > LAST:
            row["outcomes"][f"{k}m"] = None
            continue
        mk = MONTHS[i + k]
        e0, e1 = emfx(m + "-28"), emfx(mk + "-28")
        row["outcomes"][f"{k}m"] = {
            "spx_pct": r(100 * (spx_m[mk] / spx_m[m] - 1), 1) if m in spx_m and mk in spx_m else None,
            "emfx_pct": r(100 * (e1 / e0 - 1), 1) if e0 and e1 else None,
            "baa_minus_10y_pp": r((baa_m[mk] - gs10[mk]) - (baa_m[m] - gs10[m]), 2) if all(x in baa_m and x in gs10 for x in (m, mk)) else None,
            "dxy_pct": r(100 * (AVG[i + k] / AVG[i] - 1), 1)}
    mom_ledger.append(row)

# ----------------------------------------------------------------- re-dollarisation (BIS USD credit outside the US vs the dollar; finder B)
jq = [row for row in csv.DictReader(open(os.path.join(DATA, "johnson_quarterly.csv")))
      if all(fnum(row[c]) is not None for c in ("g_credit", "g_usd", "g_credit_yoy", "g_usd_yoy"))]


def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


gc = [fnum(x["g_credit"]) for x in jq]
gu = [fnum(x["g_usd"]) for x in jq]
gcy = [fnum(x["g_credit_yoy"]) for x in jq]
guy = [fnum(x["g_usd_yoy"]) for x in jq]
down = [fnum(x["g_credit_yoy"]) for x in jq if fnum(x["g_usd_yoy"]) < 0]
up = [fnum(x["g_credit_yoy"]) for x in jq if fnum(x["g_usd_yoy"]) > 0]
redollar = {"quarters": len(jq), "first": jq[0][""][:7], "last": jq[-1][""][:7],
            "corr_yoy_contemporaneous": r(corr(gcy, guy), 2), "corr_yoy_dollar_leads_1q": r(corr(gcy[1:], guy[:-1]), 2),
            "corr_qoq_contemporaneous": r(corr(gc, gu), 2), "corr_qoq_dollar_leads_1q": r(corr(gc[1:], gu[:-1]), 2),
            "corr_caveat": "yoy changes overlap by three quarters, so the yoy correlations rest on roughly a quarter of the nominal sample; "
                           "the non-overlapping qoq correlations are weaker (about -0.3)",
            "credit_growth_yoy_when_dollar_down_pct": r(sum(down) / len(down), 1), "n_down": len(down),
            "credit_growth_yoy_when_dollar_up_pct": r(sum(up) / len(up), 1), "n_up": len(up),
            "basis": "log growth (100 x log-difference); BIS GLI Q.USD.3P.N.A.I.B.USD vs the Fed broad dollar, quarter-end; descriptive, not causal"}

# ----------------------------------------------------------------- dated facts computed from the daily files
dxy_d = daily(os.path.join(DATA, "dxy_daily.csv"))


def pct(series, a, b):
    va, vb = asof(series, a), asof(series, b)
    return r(100 * (vb / va - 1), 1)


apr25 = {"dxy_2025_04_02_to_04_21_pct": pct(dxy_d, "2025-04-02", "2025-04-21"),
         "y10_2025_04_04_to_04_11_pp": r(asof(Y_, "2025-04-11") - asof(Y_, "2025-04-04"), 2)}
chain = {row["date"]: row for row in csv.DictReader(open(os.path.join(DATA, "chain_2022.csv")))}

ref = {
    "_about": "Frozen historical reference for the Dollar watch tab (GET /dollar-watch). Recomputed from the reviewed study data by "
              "studies/dollar_watch/code/build_reference.py; every number is in-sample history, descriptive, with its N and base rate.",
    "frozen_on": FROZEN_ON,
    "provenance": {"study": "studies/dollar-watch.md", "builder": "studies/dollar_watch/code/build_reference.py",
                   "reviews": "studies/dollar_watch/verdicts (numbers; logic and design)",
                   "inputs_sha256": {p: sha(os.path.join(DATA, p)) for p in INPUTS}},
    "window_convention": "an event at month m is followed by an onset if one falls in (m, m+H]; base rate = share of eligible months 1971-01..2026-10 minus H with an onset in (m, m+H]",
    "dxy_monthly": {"basis": "ICE DXY, month-end close and monthly average of daily closes (Yahoo DX-Y.NYB daily, finder A; identical to a fresh pull)",
                    "months": MONTHS, "close": [r(x, 2) for x in CLOSE], "avg": [r(x, 2) for x in AVG]},
    "crisis_lists": LISTS,
    "band": {"lo": 85, "hi": 105, "label": "Johnson's ad hoc 85-105 band (as relayed in the Oct-2026 talk); no edge over the base rate on three crisis lists",
             "excursions": excursions, "by_list": band_by_list,
             "basis": "month-end closes outside 85-105, runs separated by <= 3 in-band months merged (finder A); 17 excursions"},
    "momentum": {"definition": "12-month change of the monthly-average DXY above +10%", "episodes": episodes, "by_list": mom_by_list,
                 "caveat": "in-sample on data the study had already examined; list-dependent; clusters, not independent draws; NOT validated"},
    "quadrant": {"definition": "sign of the 3-month change of the monthly-average DXY and of the 10-year yield (GS10) into the onset month (finder C)",
                 "by_list": quadrant, "base_all_months": quadrant_base},
    "dollar_fell_at_peak_stress": {"n_crises": len(cm), "fell": len(fell), "crises": fell,
                                   "basis": "month-end close, eve of the crisis to its peak-stress month, finder A's 25-crisis list"},
    "gold": {"drawdowns": gold_dd, "ended_higher": len(gold_higher), "n_with_end": len(gold_end),
             "ended_higher_gt_1pct": sum(1 for g in gold_higher if g["pct"] > 1), "ended_higher_list": gold_higher,
             "basis": "COMEX GC=F daily (2000+), World Bank monthly before; 'ended higher' = gold above its eve level at the episode's end "
                      "(monthly averages, finder A's 25-crisis list, col gold_eve_to_end_pct). Corrects the memo's '10 of 25', which "
                      "listed ten examples and missed dotcom (+13.6%), China property (+7.3%) and two flat cases (+0.9%, +0.2%). "
                      "Drawdown windows end with the episode (2022: Mar-Oct, C22 ends 2022-10)."},
    "scramble_rule": {"params": RULE, "variant_live": "re-arm (fires again inside the cooling window on a 1.5x bigger scramble; added after the 2008-09-22 miss)",
                      "firings": rearm, "firings_unpatched": unpatched, "vspike_timing": vspike, "monthly_null": monthly_null,
                      "basis": "outcomes on the rule's own index: dollar_further_rise_pct = broad dollar's max over the next 250 index days vs the firing day; "
                               "spx_to_next_low_pct = S&P 500 from the firing close to its lowest close in the next 250 trading days; "
                               "3/6/12-month outcomes as-of calendar offsets"},
    "momentum_ledger": mom_ledger,
    "momentum_ledger_basis": "one row per momentum episode (first signal month after 12 quiet months); S&P and DXY as monthly averages, "
                             "EM FX basket as-of the 28th, BAA minus GS10 monthly; reconstructed in-sample, not a forecast record",
    "redollarisation": redollar,
    "events": {"swap_lines": [
        {"date": "2007-12-12", "text": "first swap lines (ECB, SNB) with the term auction facility", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20071212a.htm"},
        {"date": "2008-09-18", "text": "swap lines expanded by $180bn", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20080918a.htm"},
        {"date": "2008-10-13", "text": "BoE / ECB / SNB lines made unlimited", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20081013a.htm"},
        {"date": "2008-10-29", "text": "lines for Brazil, Mexico, Korea, Singapore", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20081029b.htm"},
        {"date": "2010-05-09", "text": "lines re-established (euro crisis)", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20100509a.htm"},
        {"date": "2011-11-30", "text": "coordinated 50bp cut in the swap-line rate", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20111130a.htm"},
        {"date": "2013-10-31", "text": "lines made standing", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20131031a.htm"},
        {"date": "2020-03-15", "text": "coordinated repricing, 84-day operations", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20200315c.htm"},
        {"date": "2020-03-19", "text": "nine temporary lines", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20200319b.htm"},
        {"date": "2020-03-20", "text": "daily 7-day operations", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20200320a.htm"},
        {"date": "2020-03-31", "text": "FIMA repo facility", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20200331a.htm"},
        {"date": "2023-03-19", "text": "daily operations (SVB / Credit Suisse)", "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20230319a.htm"}],
        "treasury_2025": {"text": "April 2025 tariff shock: a US-originated shock in which the dollar FELL while Treasury yields rose (the safe-haven pattern inverted)",
                          **apr25, "source": "studies/dollar_watch/data/dxy_daily.csv; FRED DGS10"},
        "chain_2022": {"freeze": "2022-02-28", "first_hike": "2022-03-16",
                       "dxy_6m_after_freeze_pct": fnum(chain["2022-08-28"]["pct_from_freeze_2022-02-28"]) if "2022-08-28" in chain else None,
                       "text": "the reserve freeze and the first Fed hike are 16 days apart; Evergrande's default (2021-12-09) predates the freeze; "
                               "the DXY fell 10% in Oct-Dec 2022 with sanctions intact; Fed swap lines peaked at $11bn - the data cannot separate the freeze from the hiking cycle"}},
    "funding_leadlag": {
        "basis": "date of each series' stress extreme minus the broad dollar's peak, trading days (finder B notes §2, verified by reviewer 1); "
                 "these series lead the DOLLAR, they are coincident with crisis onset, and were silent in the EM growth scares",
        "dollar_peaks": {"2008": "2009-03-03", "2015-16": "2016-01-20", "2018": "2018-11-27", "2020": "2020-03-23", "2022": "2022-09-26"},
        "rows": [
            {"series": "financial CP - 3m bill", "2008": "alarm 2007-06; peak -139d", "2015-16": "-40d", "2018": "-238d", "2020": "+2d",
             "2022": "alarm 2022-03-04; peak -87d on a one-day print (-206d without it)"},
            {"series": "OFR FSI funding", "2008": "alarm 2007-08-09 (BNP week); -144d", "2015-16": "+22d", "2018": "-236d", "2020": "+7d", "2022": "alarm 2022-03-04; -87d"},
            {"series": "NFCI risk", "2008": "alarm 2007-07-13", "2015-16": "-", "2018": "-", "2020": "-24d", "2022": "alarm 2022-02-25"},
            {"series": "gold trough", "2008": "-111d", "2015-16": "-34d", "2018": "-103d", "2020": "-4d", "2022": "0d"},
            {"series": "EMB / EEM trough", "2008": "-126d / -103d", "2015-16": "0d", "2018": "0d / -29d", "2020": "-5d / 0d", "2022": "+24d / +28d"},
            {"series": "Fed swap-line usage", "2008": "-76d (peak $583bn)", "2015-16": "spikes", "2018": "year-end", "2020": "+65d ($449bn)", "2022": "+30d ($11bn)"},
            {"series": "EM FX basket weakest", "2008": "-1d", "2015-16": "0d", "2018": "-83d", "2020": "+32d", "2022": "+28d"}]},
    "end_of_scramble": {
        "basis": "finder B notes §3; the sequence dates the end of the dollar SCRAMBLE, not of the crisis",
        "order": ["policy announcement", "funding spread halves (4 days in 2008, 7 weeks in 2020)", "gold bottoms", "EMB / EEM bottom",
                  "the broad dollar peaks", "EM FX and official custody recover last"],
        "case_2008": "by mid-November 2008 the funding spread had halved (17-Oct), gold had bottomed (12-Nov) and the re-armed rule had fired (6-Nov); "
                     "the S&P 500 low came on 9-Mar-2009, four months and 25% lower"},
    "counter_examples": [
        {"when": "1985-87", "text": "the DXY fell about 40% from its Feb-1985 peak (164.72) with no crisis for 32 months"},
        {"when": "Oct 1987", "text": "the crash came with the dollar FALLING (Louvre dispute)"},
        {"when": "1995", "text": "the peso crisis peaked with the DXY at a then-record low (80.05)"},
        {"when": "Aug-Oct 1998", "text": "LTCM's acute phase saw the DXY fall 8.9% on the yen-carry unwind"},
        {"when": "Mar 2008", "text": "the DXY hit its all-time low (70.70) on the Bear Stearns weekend, seven months into the subprime crisis; it rose only after Lehman"},
        {"when": "2011", "text": "the euro-crisis peak came with the DXY at the bottom of the band"},
        {"when": "2023-25", "text": "SVB (2023), the yen-carry unwind (Aug-2024) and the tariff shock (Apr-2025) all saw the dollar fall"}],
    "honesty": [
        "Every historical number here is in-sample: the study examined all of 1971-2026 before the panel was built.",
        "Crises cluster: 25 crises (A25), 16 onsets (C16), 5 dollar-funding squeezes (N5); counts are of months or episodes, not independent draws.",
        "Reverse causality: the dollar rises because forced deleveraging buys dollars, so 'dollar up then crisis' and 'crisis then dollar up' look alike.",
        "The deceleration rule's parameters were chosen on 2008, 2020 and 2022; its record on unseen 1973-2005 monthly data shows no edge.",
        "The dollar-scramble markers (funding easing, gold's trough, the dollar's peak) date the end of the scramble, not the end of a crisis.",
        "Johnson's claims are as relayed in the user's transcript; the Oct-2026 talk itself was not located."],
}
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
with open(OUT, "w") as f:
    json.dump(ref, f, indent=1, sort_keys=True)
    f.write("\n")
print("wrote", OUT, os.path.getsize(OUT), "bytes")
print("band by list", json.dumps(band_by_list))
print("momentum by list", json.dumps(mom_by_list))
print("quadrant C16", quadrant["C16"]["counts"], "A25", quadrant["A25"]["counts"], "base", quadrant_base["shares"], quadrant_base["months"])
print("fell", len(fell), [x["id"] for x in fell], "| gold ended higher", len(gold_higher), "of", len(gold_end))
print("gold dd", gold_dd)
print("firings (re-arm)", [(x["date"], x["dollar_further_rise_pct"], x["spx_to_next_low_pct"], x["vix_change_60d"]) for x in rearm])
print("firings unpatched", unpatched)
print("vspike", vspike)
print("monthly null", {k: v for k, v in monthly_null.items() if k != "months"})
print("redollar", redollar)
print("apr25", apr25, "| 2022 chain 6m", ref["events"]["chain_2022"]["dxy_6m_after_freeze_pct"])
