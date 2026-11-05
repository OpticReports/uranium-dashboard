#!/usr/bin/env python3
"""Futures and VOLUME as overnight signals — study F of the 2026-11-05 batch (add. 54).

Owner, 2026-11-05: "Did you look at volume of futures? Not just price, and look at other signals on
futures." Add. 53 was price-only and used no futures: the fund's own 09:30 open, sector ETF opens,
Asia/DAX cash indices, VIX cash. This study adds
  A. prior-session VOLUME as a conditioner (2015-06..2026-11, daily): ES and NQ futures volume, the
     fund's own volume and SPY's, each as a ratio to its trailing 20-session median, on the mornings
     add. 53 studied (own gap at the open x oversold state), model-free and on the engines' legs;
  B. the OVERNIGHT GLOBEX SESSION itself (2024-06-17..2026-11-05: hourly ES/NQ/ZN/GC/6J bars with
     volume from Yahoo, the only free intraday futures history): overnight return to 09:00 ET,
     overnight volume vs its trailing median, range, position in range, recovery from the low,
     Asia-hours vs Europe-hours split, late (06:00-09:00) volume share, 10-year note / gold / yen
     overnight moves as risk-off confirmation; outcomes = the next regular session open->close of
     SPY, QQQ, SMH and the 3x funds, and the engines' held legs;
  C. the 2026-11-04 -> 11-05 night in that frame, and the ten worst nights;
  D. opening-minutes volume of SOXL/TECL (FMP 1-minute bars, last 30 sessions): illustration only.
Not available free: VIX futures intraday, open interest, ES-SPY basis intraday, order flow.
Basis: raw opens/closes; signals read at 09:00 ET from the hourly bar that ends then (add. 53's
bridge: 09:25 ~ open, sd 0.1%); exits cost 25 bps as add. 53; t with the sample sd; permutation
tests shuffle outcomes within the conditioning sample. Report-only. Writes
composer/results/futures-signals-2026-11-05.json.
"""
import bisect
import datetime as dt
import json
import math
import os
import random
import statistics
import sys
import time
import urllib.request
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import overnight_study as os_  # noqa: E402
from edge_study import wilder_rsi, tstat, mornings_all, FUNDS  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "results", "futures-signals-2026-11-05.json")
FUT = os.path.join(os_.S, "fut")
ET = zoneinfo.ZoneInfo("America/New_York")
START, END = "2015-06-01", "2026-11-05"
HSTART = "2024-06-17"                    # first complete overnight in Yahoo's 730-day hourly history
HOURLY = ["ES=F", "NQ=F", "ZN=F", "GC=F", "6J=F"]
DAILYF = ["ES=F", "NQ=F", "YM=F", "RTY=F", "ZN=F", "ZB=F", "GC=F", "CL=F", "6J=F"]
OUTCOMES = ["SPY", "QQQ", "SMH", "SOXL", "TECL", "TQQQ"]
TECH3 = ["SOXL", "TECL", "TQQQ"]
COST = 0.0025                            # exit at the open + re-entry at the close (15 + 10 bps)
PERM_N, PLACEBO_N = 4000, 2000
HOLD_1105 = {"KMLM": {"SOXL": 0.75, "PULS": 0.25}, "HG": {"BIL": 1.0}}   # what earned on 11-05 (paths end 11-04)
H = {"User-Agent": "Mozilla/5.0"}
random.seed(20261105)


# ------------------------------------------------------------------ data
def yget(u, t=60):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=t))


def daily_futures():
    p = os.path.join(FUT, "daily_fut.json")
    if os.path.exists(p):
        return json.load(open(p))
    os.makedirs(FUT, exist_ok=True)
    out, now = {}, int(time.time())
    for s in DAILYF:
        j = yget(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1=946684800&period2={now}&interval=1d")["chart"]["result"][0]
        q, rows = j["indicators"]["quote"][0], {}
        for i, x in enumerate(j["timestamp"]):
            if q["close"][i] is None:
                continue
            rows[dt.datetime.utcfromtimestamp(x).strftime("%Y-%m-%d")] = {"o": q["open"][i], "h": q["high"][i], "l": q["low"][i], "c": q["close"][i], "v": q["volume"][i]}
        out[s] = rows
        time.sleep(0.5)
    json.dump(out, open(p, "w"))
    return out


def intraday_futures():
    p = os.path.join(FUT, "intraday_fut.json")
    if os.path.exists(p):
        return json.load(open(p))
    os.makedirs(FUT, exist_ok=True)
    out = {}
    for s in HOURLY:
        for iv, rng in (("1h", "730d"), ("5m", "60d")):
            j = yget(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?range={rng}&interval={iv}&includePrePost=true")["chart"]["result"][0]
            q = j["indicators"]["quote"][0]
            out[f"{s}|{iv}"] = {"t": j["timestamp"], "o": q["open"], "h": q["high"], "l": q["low"], "c": q["close"], "v": q["volume"],
                                "gmtoffset": j["meta"].get("gmtoffset"), "tz": j["meta"].get("exchangeTimezoneName")}
            time.sleep(0.5)
    json.dump(out, open(p, "w"))
    return out


def tkeys(rows):
    ks = rows.get("_keys")
    if ks is None:
        ks = rows["_keys"] = sorted(k for k in rows if not k.startswith("_"))
    return ks


def vol_ratio(rows, d, n=20, min_n=10):
    """rows[d]['v'] over the median of the n sessions before d; None if fewer than min_n of them print"""
    ks = tkeys(rows)
    i = bisect.bisect_left(ks, d)
    if i >= len(ks) or ks[i] != d:
        return None
    v = rows[d].get("v")
    prior = [rows[k]["v"] for k in ks[max(0, i - n):i] if rows[k].get("v")]
    if not v or len(prior) < min_n:
        return None
    m = statistics.median(prior)
    return v / m if m else None


# ------------------------------------------------------------------ B: the overnight Globex session
def hourly_index(b):
    """{(date, hour): (o, h, l, c, v)} in ET for one symbol's 1h bars (stub bars off the hour dropped)"""
    idx = {}
    for i, t in enumerate(b["t"]):
        if b["c"][i] is None:
            continue
        e = dt.datetime.fromtimestamp(t, ET)
        if e.minute != 0:
            continue
        idx[(e.strftime("%Y-%m-%d"), e.hour)] = (b["o"][i], b["h"][i], b["l"][i], b["c"][i], b["v"][i] or 0)
    return idx


def overnight(idx, p, d):
    """the Globex session from the cash close of p (the 15:00 bar closes at 16:00 ET) to 09:00 ET on d
    (the 08:00 bar closes at 09:00); None if either anchor is missing"""
    ref = idx.get((p, 15))
    end = idx.get((d, 8))
    if not ref or not end:
        return None
    keys = sorted(k for k in idx if (k[0] == p and k[1] >= 16) or (p < k[0] < d) or (k[0] == d and k[1] <= 8))
    if len(keys) < 6:
        return None
    ref, p09 = ref[3], end[3]
    highs, lows, vols = [idx[k][1] for k in keys], [idx[k][2] for k in keys], [idx[k][4] for k in keys]
    hi, lo, vol = max(highs), min(lows), sum(vols)
    a = idx.get((d, 2))                                     # the 02:00 bar closes at 03:00 ET: Asia done, Europe open
    p03 = a[3] if a else None
    late = sum(idx[k][4] for k in keys if k[0] == d and 6 <= k[1] <= 8)
    lk = keys[lows.index(lo)]
    low_t = dt.datetime.strptime(f"{lk[0]} {lk[1]:02d}", "%Y-%m-%d %H").replace(tzinfo=ET)
    open_t = dt.datetime.strptime(f"{d} 09", "%Y-%m-%d %H").replace(tzinfo=ET)
    return {"ref": ref, "p09": p09, "ret": p09 / ref - 1, "range": (hi - lo) / ref, "vol": vol, "nbars": len(keys),
            "pos": (p09 - lo) / (hi - lo) if hi > lo else None,
            "recovery": (p09 - lo) / (ref - lo) if ref > lo and p09 >= lo else None,
            "asia": p03 / ref - 1 if p03 else None, "eu": p09 / p03 - 1 if p03 else None,
            "late_share": late / vol if vol else None, "low_h": (open_t - low_t).total_seconds() / 3600 - 1}


def with_ratios(sess, key, n=20, min_n=10):
    """adds key+'_ratio': the value over the median of the previous n sessions"""
    hist = []
    for d in sorted(sess):
        s = sess[d]
        v = s.get(key)
        s[key + "_ratio"] = (v / statistics.median(hist[-n:]) if v is not None and len(hist) >= min_n and statistics.median(hist[-n:]) else None)
        if v is not None:
            hist.append(v)


def leg_on(paths, eng, d):
    """(weighted leveraged-long legs earning on d, total weight) from the engine path, or the 11-05 override"""
    if d == "2026-11-05":
        h = HOLD_1105.get(eng, {})
    else:
        P = paths[eng]
        i = bisect.bisect_left(P["days"], d)
        if i >= len(P["days"]) or P["days"][i] != d:
            return {}, 0.0
        h = P["hold"][i]
    legs = {t: w for t, w in h.items() if t in os_.LONG3 and w > 0}
    return legs, sum(legs.values())


def leg_stats(D, legs, d):
    """weighted gap / open->close of the leg(s) on d"""
    g = o = w = 0.0
    for t, x in legs.items():
        gi = os_.gap_intraday(D, t, d)
        if gi is None:
            continue
        g += x * gi["gap"]
        o += x * gi["intra"]
        w += x
    return (g / w, o / w, w) if w else (None, None, 0.0)


def build_nights(D, paths, I, tdays):
    idx = {s: hourly_index(I[f"{s}|1h"]) for s in HOURLY}
    sess = {s: {} for s in HOURLY}
    for i in range(1, len(tdays)):
        p, d = tdays[i - 1], tdays[i]
        if d < HSTART or d > END:
            continue
        for s in HOURLY:
            o = overnight(idx[s], p, d)
            if o:
                sess[s][d] = o
    for s in ("ES=F", "NQ=F"):
        with_ratios(sess[s], "vol")
        with_ratios(sess[s], "range")
    rows = []
    for i in range(1, len(tdays)):
        p, d = tdays[i - 1], tdays[i]
        es = sess["ES=F"].get(d)
        if not es:
            continue
        r = {"date": d, "prev": p, "es": es["ret"], "es_vol": es["vol"], "es_volr": es.get("vol_ratio"), "es_ranger": es.get("range_ratio"),
             "es_range": es["range"], "es_pos": es["pos"], "es_rec": es["recovery"], "es_asia": es["asia"], "es_eu": es["eu"],
             "es_late": es["late_share"], "es_lowh": es["low_h"]}
        for s, k in (("NQ=F", "nq"), ("ZN=F", "zn"), ("GC=F", "gc"), ("6J=F", "jpy")):
            o = sess[s].get(d)
            r[k] = o["ret"] if o else None
            if s == "NQ=F":
                r["nq_volr"] = o.get("vol_ratio") if o else None
        r["nq_minus_es"] = (r["nq"] - r["es"]) if r["nq"] is not None else None
        for t in OUTCOMES:
            gi = os_.gap_intraday(D, t, d)
            r[f"{t}_gap"], r[f"{t}_oc"], r[f"{t}_cc"] = (gi["gap"], gi["intra"], gi["day"]) if gi else (None, None, None)
        t3 = [r[f"{t}_oc"] for t in TECH3 if r[f"{t}_oc"] is not None]
        r["tech3_oc"] = statistics.mean(t3) if len(t3) == 3 else None
        for eng in ("KMLM", "HG"):
            legs, w = leg_on(paths, eng, d)
            g, o, w2 = leg_stats(D, legs, d) if w >= os_.MIN_W else (None, None, 0.0)
            r[f"{eng.lower()}_leg"] = "+".join(sorted(legs)) if w >= os_.MIN_W else None
            r[f"{eng.lower()}_w"], r[f"{eng.lower()}_gap"], r[f"{eng.lower()}_oc"] = (round(w2, 4) if w2 else None), g, o
        rows.append(r)
    # the regular-session hourly path on 11-05 (and 11-04), for the case exhibit
    paths_rth = {}
    for d in ("2026-11-04", "2026-11-05"):
        p = tdays[tdays.index(d) - 1]
        ref = idx["ES=F"].get((p, 15))
        pts = [(f"{h:02d}:00", idx["ES=F"][(d, h - 1)][3] / ref[3] - 1) for h in range(1, 17) if (d, h - 1) in idx["ES=F"]] if ref else []
        vols = [(f"{h:02d}:00", idx["ES=F"][(d, h)][4]) for h in range(0, 17) if (d, h) in idx["ES=F"]]
        paths_rth[d] = {"ref_close_prev": ref[3] if ref else None, "cum_ret_by_hour_end": pts, "vol_by_hour_start": vols}
    return rows, paths_rth


def stats(x):
    x = [v for v in x if v is not None]
    if not x:
        return {"n": 0}
    return {"n": len(x), "mean": statistics.mean(x), "median": statistics.median(x), "t": tstat(x) if len(x) >= 3 else None,
            "win": sum(1 for v in x if v > 0) / len(x)}


def split_table(rows, outcome, splits, perm_n=PERM_N):
    """two-way splits of one outcome over one conditioning sample, each with the difference of means, a
    per-split permutation p, and the family-wise p of the largest |difference| across all splits"""
    base = [r for r in rows if r.get(outcome) is not None]
    out, diffs = {}, {}
    for name, side in splits.items():
        a = [r[outcome] for r in base if side(r) is True]
        b = [r[outcome] for r in base if side(r) is False]
        sa, sb = stats(a), stats(b)
        out[name] = {"yes": sa, "no": sb, "diff": (sa["mean"] - sb["mean"]) if sa["n"] and sb["n"] else None}
        if sa["n"] >= 3 and sb["n"] >= 3:
            diffs[name] = (len(a), out[name]["diff"])
    if not diffs:
        return {"base": stats([r[outcome] for r in base]), "splits": out, "p_family": None}
    vals = [r[outcome] for r in base]
    # per-split and family-wise permutation (shuffle outcomes across the sample, keep the split masks)
    masks = {name: [side(r) for r in base] for name in diffs for side in [splits[name]]}
    hits = {name: 0 for name in diffs}
    fam = 0
    obs_max = max(abs(v[1]) for v in diffs.values())
    for _ in range(perm_n):
        random.shuffle(vals)
        mx = 0.0
        for name in diffs:
            m = masks[name]
            a = [v for v, k in zip(vals, m) if k is True]
            b = [v for v, k in zip(vals, m) if k is False]
            dd = abs(statistics.mean(a) - statistics.mean(b))
            if dd >= abs(diffs[name][1]):
                hits[name] += 1
            mx = max(mx, dd)
        if mx >= obs_max:
            fam += 1
    for name in diffs:
        out[name]["p_perm"] = hits[name] / perm_n
    return {"base": stats([r[outcome] for r in base]), "splits": out, "p_family": fam / perm_n,
            "family_best": max(diffs, key=lambda k: abs(diffs[k][1]))}


def ols(xs, ys):
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pts)
    if n < 10:
        return {"n": n}
    mx, my = statistics.mean(p[0] for p in pts), statistics.mean(p[1] for p in pts)
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    sxy = sum((x - mx) * (y - my) for x, y in pts)
    b = sxy / sxx if sxx else 0.0
    a = my - b * mx
    res = [y - a - b * x for x, y in pts]
    s2 = sum(e * e for e in res) / (n - 2)
    se = math.sqrt(s2 / sxx) if sxx else None
    r = sxy / math.sqrt(sxx * sum((y - my) ** 2 for _, y in pts)) if sxx else None
    return {"n": n, "slope": b, "t": b / se if se else None, "r": r}


def analyse_nights(rows):
    med = lambda k, rs: statistics.median([r[k] for r in rs if r.get(k) is not None])
    R = [r for r in rows if r.get("SPY_oc") is not None]
    out = {"n_nights": len(R), "first": R[0]["date"], "last": R[-1]["date"]}
    # 1. does the overnight move carry into the session? all nights, and by overnight volume
    out["carry_all"] = {o: ols([r["es"] for r in R], [r[o] for r in R]) for o in ("SPY_oc", "tech3_oc", "SPY_cc")}
    vm = med("es_volr", R)
    out["carry_by_volume"] = {"es_volr_median": vm,
                              "high": {o: ols([r["es"] for r in R if (r["es_volr"] or 0) >= vm], [r[o] for r in R if (r["es_volr"] or 0) >= vm]) for o in ("SPY_oc", "tech3_oc")},
                              "low": {o: ols([r["es"] for r in R if r["es_volr"] is not None and r["es_volr"] < vm], [r[o] for r in R if r["es_volr"] is not None and r["es_volr"] < vm]) for o in ("SPY_oc", "tech3_oc")}}
    # 2. does overnight volume / range predict the SIZE of the session move (either way)?
    out["size_by_volume"] = {}
    for k in ("es_volr", "es_ranger"):
        q = [r[k] for r in R if r.get(k) is not None]
        q.sort()
        t1, t2 = q[len(q) // 3], q[2 * len(q) // 3]
        out["size_by_volume"][k] = {"terciles": [t1, t2],
                                    "abs_SPY_oc": [stats([abs(r["SPY_oc"]) for r in R if r.get(k) is not None and c(r[k])]) for c in (lambda v: v < t1, lambda v: t1 <= v < t2, lambda v: v >= t2)],
                                    "abs_SPY_cc": [stats([abs(r["SPY_cc"]) for r in R if r.get(k) is not None and c(r[k])]) for c in (lambda v: v < t1, lambda v: t1 <= v < t2, lambda v: v >= t2)],
                                    "corr_abs_SPY_oc": ols([r[k] for r in R], [abs(r["SPY_oc"]) for r in R])}
    # 3. down nights: continuation vs reversal, and what confirms
    out["down"] = {}
    for thr in (-0.005, -0.01):
        S = [r for r in R if r["es"] <= thr]
        vmed = med("es_volr", S) if S else None
        rmed = med("es_ranger", S) if S else None
        lmed = med("es_late", S) if S else None
        splits = {
            "ES volume >= 1.5x median": lambda r: (r["es_volr"] >= 1.5) if r.get("es_volr") is not None else None,
            "ES volume >= sample median": lambda r, v=vmed: (r["es_volr"] >= v) if r.get("es_volr") is not None else None,
            "ES range >= sample median": lambda r, v=rmed: (r["es_ranger"] >= v) if r.get("es_ranger") is not None else None,
            "recovered >= half of the drop by 09:00": lambda r: (r["es_rec"] >= 0.5) if r.get("es_rec") is not None else None,
            "09:00 in the top half of the night's range": lambda r: (r["es_pos"] >= 0.5) if r.get("es_pos") is not None else None,
            "low set in the last 3 hours": lambda r: (r["es_lowh"] <= 3) if r.get("es_lowh") is not None else None,
            "late (06-09) volume share >= median": lambda r, v=lmed: (r["es_late"] >= v) if r.get("es_late") is not None else None,
            "10y note up overnight (flight to quality)": lambda r: (r["zn"] > 0) if r.get("zn") is not None else None,
            "yen up overnight": lambda r: (r["jpy"] > 0) if r.get("jpy") is not None else None,
            "gold up overnight": lambda r: (r["gc"] > 0) if r.get("gc") is not None else None,
            "tech-led (NQ - ES <= -0.3%)": lambda r: (r["nq_minus_es"] <= -0.003) if r.get("nq_minus_es") is not None else None,
            "Asia hours did most of it (asia <= eu)": lambda r: (r["es_asia"] <= r["es_eu"]) if r.get("es_asia") is not None and r.get("es_eu") is not None else None,
        }
        blk = {"n": len(S), "continuation_rate": {o: (sum(1 for r in S if r[o] is not None and r[o] < 0) / max(1, sum(1 for r in S if r[o] is not None))) for o in ("SPY_oc", "tech3_oc")}}
        for o in ("SPY_oc", "tech3_oc"):
            blk[o] = split_table(S, o, splits) if len(S) >= 8 else {"base": stats([r[o] for r in S])}
        legs = [r for r in S if r.get("kmlm_oc") is not None]
        blk["kmlm_leg"] = {"n": len(legs), "oc": stats([r["kmlm_oc"] for r in legs]),
                           "by_volume_high": stats([r["kmlm_oc"] for r in legs if (r["es_volr"] or 0) >= 1.5]),
                           "by_volume_low": stats([r["kmlm_oc"] for r in legs if r["es_volr"] is not None and r["es_volr"] < 1.5])}
        out["down"][f"{thr:+.1%}"] = blk
    # 4. mirror: up nights
    U = [r for r in R if r["es"] >= 0.005]
    out["up_mirror"] = {"n": len(U), "SPY_oc": stats([r["SPY_oc"] for r in U]), "tech3_oc": stats([r["tech3_oc"] for r in U]),
                        "continuation_rate_SPY": sum(1 for r in U if r["SPY_oc"] > 0) / max(1, len(U))}
    # 5. the worst ten nights and this week
    cols = ["date", "es", "es_volr", "es_ranger", "es_rec", "es_pos", "es_late", "es_lowh", "nq", "zn", "gc", "jpy", "SPY_gap", "SPY_oc", "SPY_cc", "tech3_oc", "kmlm_leg", "kmlm_w", "kmlm_gap", "kmlm_oc"]
    worst = sorted(R, key=lambda r: r["es"])[:10]
    out["worst_nights"] = [{k: r.get(k) for k in cols} for r in worst]
    out["this_week"] = [{k: r.get(k) for k in cols} for r in R if r["date"] >= "2026-11-02"]
    # 6. where 11-05 sits
    r5 = next((r for r in R if r["date"] == "2026-11-05"), None)
    if r5:
        rank = lambda k, v: sum(1 for r in R if r.get(k) is not None and r[k] <= v) / max(1, sum(1 for r in R if r.get(k) is not None))
        out["case_1105"] = {k: {"value": r5.get(k), "pct_rank": rank(k, r5[k]) if r5.get(k) is not None else None} for k in ("es", "es_volr", "es_ranger", "nq", "zn", "gc", "jpy", "SPY_gap", "SPY_oc", "SPY_cc")}
    return out


# ------------------------------------------------------------------ A: prior-session volume, 2015-2026
def analyse_history(D, F, paths):
    rows = [r for r in mornings_all(D, FUNDS) if START <= r["date"] <= END]
    for r in rows:
        pd = os_.prev_day(D[r["fund"]], r["date"])
        r["prev"] = pd
        r["fund_volr"] = vol_ratio(D[r["fund"]], pd) if pd else None
        r["spy_volr"] = vol_ratio(D["SPY"], pd) if pd else None
        r["es_volr"] = vol_ratio(F["ES=F"], pd) if pd and pd in F["ES=F"] else None
        r["nq_volr"] = vol_ratio(F["NQ=F"], pd) if pd and pd in F["NQ=F"] else None
    # one trade per day: pool the qualifying funds
    def pooled(cond):
        by = {}
        for r in rows:
            if cond(r):
                by.setdefault(r["date"], []).append(r)
        out = []
        for d, rs in sorted(by.items()):
            m = lambda k: (statistics.mean([x[k] for x in rs if x[k] is not None]) if any(x[k] is not None for x in rs) else None)
            out.append({"date": d, "n_funds": len(rs), "oc": statistics.mean(x["intra"] for x in rs), "gap": statistics.mean(x["gap"] for x in rs),
                        "fund_volr": m("fund_volr"), "spy_volr": m("spy_volr"), "es_volr": m("es_volr"), "nq_volr": m("nq_volr")})
        return out
    conds = {
        "oversold AND own gap <= -5% (the E1 sample)": lambda r: r["oversold"] and r["gap"] <= -0.05,
        "oversold AND own gap <= -3%": lambda r: r["oversold"] and r["gap"] <= -0.03,
        "any state AND own gap <= -5%": lambda r: r["gap"] <= -0.05,
        "any state AND own gap <= -3%": lambda r: r["gap"] <= -0.03,
        "NOT oversold AND own gap <= -5%": lambda r: (not r["oversold"]) and r["gap"] <= -0.05,
        "oversold, any gap": lambda r: r["oversold"],
        "MIRROR: any state AND own gap >= +3%": lambda r: r["gap"] >= 0.03,
    }
    out = {}
    for name, cond in conds.items():
        T = pooled(cond)
        splits = {}
        for k, lab in (("fund_volr", "fund volume"), ("es_volr", "ES volume"), ("nq_volr", "NQ volume"), ("spy_volr", "SPY volume")):
            vals = [t[k] for t in T if t[k] is not None]
            if len(vals) < 6:
                continue
            md = statistics.median(vals)
            splits[f"{lab} >= 2x (climax)"] = (lambda t, k=k: (t[k] >= 2.0) if t[k] is not None else None)
            splits[f"{lab} >= sample median ({md:.2f}x)"] = (lambda t, k=k, md=md: (t[k] >= md) if t[k] is not None else None)
            splits[f"{lab} < 1x (quiet)"] = (lambda t, k=k: (t[k] < 1.0) if t[k] is not None else None)
        out[name] = split_table(T, "oc", splits) if len(T) >= 8 and splits else {"base": stats([t["oc"] for t in T])}
        out[name]["days"] = len(T)
        out[name]["volume_on_those_days"] = {k: stats([t[k] for t in T]) for k in ("fund_volr", "es_volr", "spy_volr")}
    # the engines' own legs: exit at the open when the gap AND a volume condition hold
    eng = {}
    rsi = {}
    for f in FUNDS:
        ks = [k for k in tkeys(D[f])]
        rr = wilder_rsi([D[f][d]["a"] for d in ks], 10)
        rsi[f] = {d: v for d, v in zip(ks, rr) if v is not None}
    for e in ("KMLM", "HG"):
        P = paths[e]
        M = []
        days = [d for d in P["days"] if START <= d <= "2026-11-04"] + ["2026-11-05"]
        for d in days:
            legs, w = leg_on(paths, e, d)
            if w < os_.MIN_W:
                continue
            g, o, w2 = leg_stats(D, legs, d)
            if g is None:
                continue
            pd = os_.prev_day(D["SPY"], d)
            fv = [vol_ratio(D[t], pd) for t in legs if t in D]
            fv = [v for v in fv if v is not None]
            M.append({"date": d, "legs": "+".join(sorted(legs)), "w": w2, "gap": g, "oc": o,
                      "oversold": any(rsi.get(t, {}).get(pd, 100) < 30 for t in legs),
                      "fund_volr": statistics.mean(fv) if fv else None, "es_volr": vol_ratio(F["ES=F"], pd) if pd in F["ES=F"] else None})
        rules = {}
        vconds = {"no volume condition": lambda m: True,
                  "fund volume >= 2x (climax)": lambda m: m["fund_volr"] is not None and m["fund_volr"] >= 2.0,
                  "fund volume < 1x (quiet)": lambda m: m["fund_volr"] is not None and m["fund_volr"] < 1.0,
                  "ES volume >= 1.5x": lambda m: m["es_volr"] is not None and m["es_volr"] >= 1.5,
                  "ES volume < 1x": lambda m: m["es_volr"] is not None and m["es_volr"] < 1.0}
        sconds = {"any state": lambda m: True, "leg oversold": lambda m: m["oversold"], "leg NOT oversold": lambda m: not m["oversold"]}
        allv = [m["w"] * (-m["oc"] - COST) for m in M]
        for gthr in (-0.03, -0.05):
            for vn, vc in vconds.items():
                for sn, sc in sconds.items():
                    fired = [m for m in M if m["gap"] <= gthr and vc(m) and sc(m)]
                    if not fired:
                        continue
                    val = sum(m["w"] * (-m["oc"] - COST) for m in fired)
                    k = len(fired)
                    draws = sorted(sum(random.sample(allv, k)) for _ in range(PLACEBO_N)) if k <= len(allv) else []
                    pct = (bisect.bisect_left(draws, val) / PLACEBO_N) if draws else None
                    rules[f"gap <= {gthr:.0%} AND {vn} AND {sn}"] = {
                        "n": k, "leg_oc": stats([m["oc"] for m in fired]), "exit_value_pp": val * 100, "placebo_pct": pct,
                        "dates": [m["date"] for m in fired] if k <= 12 else None}
        eng[e] = {"mornings": len(M), "window": [days[0], days[-1]], "base_exit_value_pp_all_mornings": sum(allv) * 100, "rules": rules}
    return {"mornings": len(rows), "conditions": out, "engines": eng}


# ------------------------------------------------------------------ D: opening-minutes volume (illustration)
def opening_volume(D, tdays, funds=("SOXL", "TECL"), n_days=30):
    key = os.environ.get("FMP_API_KEY")
    if not key:
        return {"note": "FMP_API_KEY not set; skipped"}
    days = [d for d in tdays if d <= END][-n_days:]
    out = {}
    for f in funds:
        rows = []
        for d in days:
            u = f"https://financialmodelingprep.com/stable/historical-chart/1min?symbol={f}&from={d}&to={d}&apikey={key}"
            try:
                j = yget(u, 30)
            except Exception as e:  # noqa: BLE001
                rows.append({"date": d, "error": str(e).replace(key, "***")[:80]})
                continue
            if not isinstance(j, list) or not j:
                rows.append({"date": d, "error": "no bars"})
                continue
            v5 = sum(r.get("volume") or 0 for r in j if r["date"][11:16] in ("09:30", "09:31", "09:32", "09:33", "09:34"))
            gi = os_.gap_intraday(D, f, d)
            rows.append({"date": d, "open5_vol": v5, "day_vol": D[f].get(d, {}).get("v"), "gap": gi["gap"] if gi else None, "oc": gi["intra"] if gi else None})
            time.sleep(0.15)
        ok = [r for r in rows if r.get("open5_vol")]
        if ok:
            med = statistics.median(r["open5_vol"] for r in ok)
            for r in ok:
                r["open5_ratio"] = r["open5_vol"] / med if med else None
            x = [(r["open5_ratio"], r["oc"]) for r in ok if r.get("oc") is not None and r.get("open5_ratio") is not None]
            out[f] = {"rows": rows, "median_open5_vol": med, "corr_ratio_vs_oc": ols([a for a, _ in x], [b for _, b in x]),
                      "corr_ratio_vs_abs_oc": ols([a for a, _ in x], [abs(b) for _, b in x])}
        else:
            out[f] = {"rows": rows}
    return out


# ------------------------------------------------------------------ main
def pct(v, d=2):
    return "n/a" if v is None else f"{v:+.{d}%}"


def main():
    D = os_.load_daily()
    F = daily_futures()
    I = intraday_futures()
    paths = os_.load_paths()
    tdays = [k for k in tkeys(D["SPY"]) if k <= END]
    nights, rth = build_nights(D, paths, I, tdays)
    B = analyse_nights(nights)
    A = analyse_history(D, F, paths)
    Dv = opening_volume(D, tdays)
    res = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "basis": __doc__,
           "coverage": {"hourly": {s: {"first": min(k for k in I[f"{s}|1h"]["t"]), "n_bars": len(I[f"{s}|1h"]["t"])} for s in HOURLY},
                        "daily_futures": {s: [min(F[s]), max(F[s]), len(F[s])] for s in F},
                        "nights": B["n_nights"], "history_window": [START, END]},
           "B_overnight_session": B, "A_prior_session_volume": A, "D_opening_volume": Dv,
           "C_rth_paths": rth, "nights": nights}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1, default=float)
    # console
    print(f"B. overnight sessions {B['first']}..{B['last']}: {B['n_nights']} nights")
    c = B["carry_all"]
    print(f"   carry (slope of session o->c on overnight ES): SPY {c['SPY_oc'].get('slope', 0):+.2f} (t {c['SPY_oc'].get('t', 0):+.1f}); tech3x {c['tech3_oc'].get('slope', 0):+.2f} (t {c['tech3_oc'].get('t', 0):+.1f})")
    cv = B["carry_by_volume"]
    print(f"   by overnight volume: high-volume nights SPY slope {cv['high']['SPY_oc'].get('slope', 0):+.2f} (t {cv['high']['SPY_oc'].get('t', 0):+.1f}, n {cv['high']['SPY_oc'].get('n')}); low {cv['low']['SPY_oc'].get('slope', 0):+.2f} (t {cv['low']['SPY_oc'].get('t', 0):+.1f}, n {cv['low']['SPY_oc'].get('n')})")
    sv = B["size_by_volume"]["es_volr"]
    print(f"   |SPY o->c| by overnight-volume tercile: {' / '.join(pct(s['mean']) for s in sv['abs_SPY_oc'])} (corr t {sv['corr_abs_SPY_oc'].get('t', 0):+.1f})")
    for thr, blk in B["down"].items():
        print(f"   ES overnight <= {thr}: n {blk['n']}; continuation rate SPY {blk['continuation_rate']['SPY_oc']:.0%}, tech3x {blk['continuation_rate']['tech3_oc']:.0%}; "
              f"SPY o->c {pct(blk['SPY_oc']['base'].get('mean'))} (t {blk['SPY_oc']['base'].get('t') or 0:+.1f}); tech3x {pct(blk['tech3_oc']['base'].get('mean'))} (t {blk['tech3_oc']['base'].get('t') or 0:+.1f})")
        for o in ("SPY_oc", "tech3_oc"):
            st = blk[o]
            if "splits" not in st:
                continue
            print(f"     {o}: family-wise p {st['p_family']:.2f} (best split: {st['family_best']})")
            for name, s in st["splits"].items():
                if s.get("diff") is None:
                    continue
                print(f"       {name:46s} yes n{s['yes']['n']:3d} {pct(s['yes']['mean'])} | no n{s['no']['n']:3d} {pct(s['no']['mean'])} | diff {pct(s['diff'])} p {s.get('p_perm', float('nan')):.2f}")
        kl = blk["kmlm_leg"]
        print(f"     KMLM leg held on {kl['n']} of those nights: leg o->c {pct(kl['oc'].get('mean'))} (t {kl['oc'].get('t') or 0:+.1f}); high-vol {pct(kl['by_volume_high'].get('mean'))} n{kl['by_volume_high'].get('n')} / low-vol {pct(kl['by_volume_low'].get('mean'))} n{kl['by_volume_low'].get('n')}")
    print("   worst nights (ES overnight, vol ratio, recovery, ZN, SPY gap, SPY o->c, tech3x o->c, KMLM leg o->c):")
    for r in B["worst_nights"] + [w for w in B["this_week"] if w["date"] >= "2026-11-04"]:
        print(f"     {r['date']} ES {pct(r['es'])} vol {r['es_volr'] or 0:.1f}x rec {r['es_rec'] if r['es_rec'] is None else round(r['es_rec'], 2)} ZN {pct(r['zn'])} | SPY gap {pct(r['SPY_gap'])} o->c {pct(r['SPY_oc'])} | tech3x {pct(r['tech3_oc'])} | KMLM {r['kmlm_leg']} {pct(r['kmlm_oc'])}")
    if "case_1105" in B:
        bits = []
        for k, v in B["case_1105"].items():
            if v["value"] is None:
                continue
            shown = f"{v['value']:.2f}x" if k in ("es_volr", "es_ranger") else pct(v["value"])
            bits.append(f"{k} {shown} (pct {v['pct_rank']:.0%})")
        print("   11-05 in the 2-year distribution: " + ", ".join(bits))
    print(f"\nA. prior-session volume, {START}..{END}: {A['mornings']} fund-mornings")
    for name, st in A["conditions"].items():
        b = st["base"]
        print(f"   {name}: {st['days']} days, o->c {pct(b.get('mean'))} (t {b.get('t') or 0:+.1f}); volume on those days: fund {A['conditions'][name]['volume_on_those_days']['fund_volr'].get('median', 0):.2f}x, ES {A['conditions'][name]['volume_on_those_days']['es_volr'].get('median', 0):.2f}x" + (f"; family-wise p {st['p_family']:.2f}" if st.get("p_family") is not None else ""))
        for sn, s in st.get("splits", {}).items():
            if s.get("diff") is None:
                continue
            print(f"       {sn:46s} yes n{s['yes']['n']:3d} {pct(s['yes']['mean'])} | no n{s['no']['n']:3d} {pct(s['no']['mean'])} | diff {pct(s['diff'])} p {s.get('p_perm', float('nan')):.2f}")
    for e, blk in A["engines"].items():
        print(f"   {e}: {blk['mornings']} leveraged-long mornings {blk['window'][0]}..{blk['window'][1]}; exiting every morning would be worth {blk['base_exit_value_pp_all_mornings']:+.1f} pp")
        for rn, r in blk["rules"].items():
            print(f"       {rn:70s} n{r['n']:3d} leg o->c {pct(r['leg_oc'].get('mean'))} exit value {r['exit_value_pp']:+.1f} pp placebo pct {r['placebo_pct'] if r['placebo_pct'] is None else round(r['placebo_pct'] * 100)}")
    print("\nD. opening 5-minute volume, last 30 sessions:")
    for f, blk in Dv.items():
        if "rows" not in blk:
            print("   ", f, blk)
            continue
        print(f"   {f}: corr(open-5-min volume ratio, o->c) t {blk['corr_ratio_vs_oc'].get('t', 0):+.1f}; vs |o->c| t {blk['corr_ratio_vs_abs_oc'].get('t', 0):+.1f}")
        for r in blk["rows"][-4:]:
            print(f"     {r['date']} open5 {r.get('open5_ratio', 0) or 0:.1f}x gap {pct(r.get('gap'))} o->c {pct(r.get('oc'))}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
