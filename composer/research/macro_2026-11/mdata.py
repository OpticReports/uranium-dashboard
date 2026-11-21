"""Macro states and engine paths for the macro regime study (PREREG.md). Every state is 0/1 per NYSE
session and uses only data dated before that session, less the publication lag in the table. Raw series
are the files the scouting pass saved (session scratchpad macro_scout/raw) plus two frozen repo copies."""
import bisect
import csv
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for p in ("windows_2026-11", "sleeve_weight_2026-11"):
    sys.path.insert(0, os.path.join(HERE, "..", p))
import wsim as w  # noqa: E402

SCR = w.kdata.SCRATCH
RAW = SCR + "/macro_scout/raw"
REPO = os.path.join(HERE, "..", "..", "..", "treasury-canary", "studies")
END = "2026-11-19"
_c = {}


def fred(sid):
    out = {}
    for row in csv.reader(open(f"{RAW}/fred/{sid}.csv")):
        if len(row) == 2 and re.match(r"\d{4}-\d{2}-\d{2}", row[0]):
            try:
                out[row[0]] = float(row[1])
            except ValueError:
                pass
    return out


def yahoo(sym, field="close"):
    import datetime as dt
    r = json.load(open(f"{RAW}/yahoo/{sym.replace('^', '_').replace('=', '_')}.json"))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    vals = r["indicators"]["adjclose"][0]["adjclose"] if field == "adjclose" else q[field]
    out = {}
    for t, v, c in zip(r["timestamp"], vals, q["close"]):
        if v is not None and c is not None:
            out[dt.datetime.fromtimestamp(t, tz=dt.timezone.utc).date().isoformat()] = float(v)
    return {d: v for d, v in out.items() if d <= END}


def sessions():
    if "days" not in _c:
        _c["days"] = sorted(d for d in yahoo("^GSPC") if d >= "1970-01-02")
    return _c["days"]


def asof(series, lag):
    """array over sessions: the last observation dated on or before the session `lag` sessions earlier"""
    days = sessions()
    ks, out, j, last = sorted(series), np.full(len(days), np.nan), 0, np.nan
    for i in range(len(days)):
        if i >= lag:
            cut = days[i - lag]
            while j < len(ks) and ks[j] <= cut:
                last = series[ks[j]]
                j += 1
            out[i] = last
    return out


def chg(x, n):
    out = np.full(len(x), np.nan)
    out[n:] = x[n:] - x[:-n]
    return out


def roc(x, n):
    out = np.full(len(x), np.nan)
    out[n:] = x[n:] / x[:-n] - 1
    return out


def sma(x, n):
    out = np.full(len(x), np.nan)
    c = np.cumsum(np.where(np.isnan(x), 0.0, x))
    k = np.cumsum(~np.isnan(x))
    out[n - 1:] = (c[n - 1:] - np.concatenate([[0.0], c[:-n]])) / n
    bad = np.full(len(x), True)
    bad[n - 1:] = (k[n - 1:] - np.concatenate([[0], k[:-n]])) < n
    out[bad] = np.nan
    return out


def pct_to_date(x):
    """share of earlier-or-equal values (among all non-missing values to date) that are below the current one"""
    out, seen = np.full(len(x), np.nan), []
    for i, v in enumerate(x):
        if not np.isnan(v):
            if len(seen) >= 252:
                out[i] = bisect.bisect_left(seen, v) / len(seen)
            bisect.insort(seen, v)
    return out


def flag(cond, valid):
    return np.where(valid, cond.astype(float), np.nan)


def month_add(m, k):
    y, mo = int(m[:4]), int(m[5:7]) + k
    y, mo = y + (mo - 1) // 12, (mo - 1) % 12 + 1
    return f"{y:04d}-{mo:02d}"


def monthly():
    """monthly series keyed 'YYYY-MM': CPI, M2, CAPE, gold (average), S&P 500 (average close)"""
    if "m" in _c:
        return _c["m"]
    cpi = {d[:7]: v for d, v in fred("CPIAUCSL").items()}
    m2 = {d[:7]: v for d, v in fred("M2SL").items()}
    cape = {}
    for r in csv.DictReader(open(os.path.join(REPO, "yield_dynamics", "data", "valuation_monthly.csv"))):
        if r["cape"]:
            cape[r["Date"]] = float(r["cape"])
    mon = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
    html = open(f"{RAW}/cape/multpl_cape.html").read()
    for mm, dd, yy, v in re.findall(r"<td>(\w{3}) (\d+), (\d{4})</td>\s*<td>\s*(?:&#x2002;|<[^>]+>|\s)*([\d.]+)", html):
        k = f"{yy}-{mon[mm]:02d}"
        if dd == "1" and k not in cape:
            cape[k] = float(v)
    gold = {}
    for r in csv.DictReader(open(os.path.join(REPO, "dollar_watch", "data", "gold_monthly.csv"))):
        if r["gold_best"]:
            gold[r["month"]] = float(r["gold_best"])
    spx, acc = {}, {}
    for d, v in yahoo("^GSPC").items():
        acc.setdefault(d[:7], []).append(v)
    spx = {k: sum(v) / len(v) for k, v in acc.items()}
    _c["m"] = {"cpi": cpi, "m2": m2, "cape": cape, "gold": gold, "spx": spx}
    return _c["m"]


def from_monthly(vals, avail):
    """{availability date: value} for a monthly dict; avail(month) -> ISO date the value is first usable"""
    return {avail(m): v for m, v in vals.items()}


def states():
    """{id: array over sessions()} of 1.0 / 0.0 / nan, and the family map"""
    if "st" in _c:
        return _c["st"]
    days = sessions()
    M = monthly()
    S = {}
    # daily FRED series for session d-1 are published AFTER that close: lag 2 (PREREG "session before, plus extra lag 1"; review A)
    y10, y2, c3m, c2y = asof(fred("DGS10"), 2), asof(fred("DGS2"), 2), asof(fred("T10Y3M"), 2), asof(fred("T10Y2Y"), 2)
    S["R1"] = flag(chg(y10, 63) > 0.50, ~np.isnan(chg(y10, 63)))
    S["R2"] = flag(chg(y2, 63) > 0.50, ~np.isnan(chg(y2, 63)))
    S["R3"] = flag(c3m < 0, ~np.isnan(c3m))
    inv = np.where(np.isnan(c3m), 0.0, (c3m < 0).astype(float))
    was = np.convolve(inv, np.ones(252), mode="full")[:len(inv)] > 0
    S["R4"] = flag(was & (chg(c3m, 63) > 0.50), ~np.isnan(chg(c3m, 63)) & (np.arange(len(days)) >= np.argmax(~np.isnan(c3m)) + 252))
    S["R5"] = flag(c2y < 0, ~np.isnan(c2y))
    ry = asof(fred("DFII10"), 2)
    S["R6"] = flag(chg(ry, 63) > 0.40, ~np.isnan(chg(ry, 63)))
    ff = asof(fred("DFF"), 2)
    S["R7"] = flag(chg(ff, 126) > 0.25, ~np.isnan(chg(ff, 126)))
    be = asof(fred("T10YIE"), 2)
    S["I1"] = flag(chg(be, 63) > 0.25, ~np.isnan(chg(be, 63)))
    cpi = M["cpi"]
    yoy = {m: cpi[m] / cpi[month_add(m, -12)] - 1 for m in cpi if month_add(m, -12) in cpi}
    acc = {m: yoy[m] - yoy[month_add(m, -6)] for m in yoy if month_add(m, -6) in yoy}
    cpi_av = lambda m: month_add(m, 1) + "-22"   # the 15th was before the release in most months (review A)                               # noqa: E731
    yoy_s, acc_s = asof(from_monthly(yoy, cpi_av), 1), asof(from_monthly(acc, cpi_av), 1)
    S["I2"] = flag(acc_s >= 0.010, ~np.isnan(acc_s))
    S["I3"] = flag(yoy_s > 0.04, ~np.isnan(yoy_s))
    cape = M["cape"]
    ms = sorted(cape)
    cp = {}
    seen = []
    for m in ms:
        if len(seen) >= 120:
            cp[m] = bisect.bisect_left(seen, cape[m]) / len(seen)
        bisect.insort(seen, cape[m])
    cape_av = lambda m: month_add(m, 2) + "-01"                              # noqa: E731
    cp_s = asof(from_monthly(cp, cape_av), 0)
    S["V1"] = flag(cp_s > 0.90, ~np.isnan(cp_s))
    c12 = {m: cape[m] / cape[month_add(m, -12)] - 1 for m in cape if month_add(m, -12) in cape}
    c12_s = asof(from_monthly(c12, cape_av), 0)
    S["V2"] = flag(c12_s < -0.10, ~np.isnan(c12_s))
    cape_s = asof(from_monthly(cape, cape_av), 0)
    erp = 100.0 / cape_s - (y10 - 100 * yoy_s)
    ep = pct_to_date(erp)
    S["V3"] = flag(ep < 0.25, ~np.isnan(ep))
    # gold: daily from GC=F once 200 sessions exist, monthly averages before
    gd = asof(yahoo("GC=F"), 1)
    px = asof(yahoo("^GSPC"), 1)
    first = int(np.argmax(~np.isnan(sma(gd, 200))))
    gm, sm = M["gold"], M["spx"]
    m_av = lambda m: month_add(m, 1) + "-01"                                 # noqa: E731

    def m10(v):
        ks = sorted(v)
        return {k: v[k] > sum(v[x] for x in ks[i - 9:i + 1]) / 10 for i, k in enumerate(ks) if i >= 9}
    g1m = asof({k: float(x) for k, x in from_monthly(m10(gm), m_av).items()}, 0)
    ratio_m = {k: gm[k] / sm[k] for k in gm if k in sm}
    g2m = asof({k: float(x) for k, x in from_monthly(m10(ratio_m), m_av).items()}, 0)
    g5m = asof(from_monthly({m: gm[m] / gm[month_add(m, -3)] - 1 for m in gm if month_add(m, -3) in gm}, m_av), 0)
    idx = np.arange(len(days))
    daily = idx >= first
    S["G1"] = np.where(daily, flag(gd > sma(gd, 200), ~np.isnan(sma(gd, 200))), g1m)
    rd = gd / px
    S["G2"] = np.where(daily, flag(rd > sma(rd, 200), ~np.isnan(sma(rd, 200))), g2m)
    rg = {m: gm[m] / cpi[m] for m in gm if m in cpi}
    rg12 = {m: rg[m] / rg[month_add(m, -12)] - 1 for m in rg if month_add(m, -12) in rg}
    rg_s = asof(from_monthly(rg12, cpi_av), 1)
    S["G3"] = flag(rg_s > 0.10, ~np.isnan(rg_s))
    cg = asof(yahoo("HG=F"), 1) / gd
    S["G4"] = flag(cg < sma(cg, 200), ~np.isnan(sma(cg, 200)))
    S["G5"] = np.where(daily, flag(roc(gd, 63) > 0.10, ~np.isnan(roc(gd, 63))), flag(g5m > 0.10, ~np.isnan(g5m)))
    baa = asof(fred("BAA10Y"), 2)
    S["C1"] = flag(chg(baa, 63) > 0.30, ~np.isnan(chg(baa, 63)))
    bp = pct_to_date(baa)
    S["C2"] = flag(bp > 0.80, ~np.isnan(bp))
    nf = asof(fred("NFCI"), 4)
    S["C3"] = flag(nf > 0, ~np.isnan(nf))
    S["C4"] = flag(chg(nf, 65) > 0.15, ~np.isnan(chg(nf, 65)))
    dx = asof(yahoo("DX-Y.NYB"), 1)
    S["D1"] = flag(dx > sma(dx, 200), ~np.isnan(sma(dx, 200)))
    S["D2"] = flag(roc(dx, 63) > 0.05, ~np.isnan(roc(dx, 63)))
    vol = asof(yahoo("^GSPC", "volume"), 1)
    vol = np.where(vol > 0, vol, np.nan)
    for i in range(1, len(vol)):                                             # a zero print (2023-05-24) must not blank a year of averages
        if np.isnan(vol[i]) and not np.isnan(vol[i - 1]) and i > int(np.argmax(~np.isnan(vol))):
            vol[i] = vol[i - 1]
    vr = sma(vol, 21) / sma(vol, 252)
    S["M1"] = flag(vr > 1.25, ~np.isnan(vr))
    S["M2"] = flag(vr < 0.85, ~np.isnan(vr))
    down = np.concatenate([[np.nan], (px[1:] < px[:-1]).astype(float)])
    dv = sma(np.where(np.isnan(vol) | np.isnan(down), np.nan, vol * down), 21) / sma(vol, 21)
    S["M3"] = flag(dv > 0.60, ~np.isnan(dv))
    m2 = M["m2"]
    m2y = {m: m2[m] / m2[month_add(m, -12)] - 1 for m in m2 if month_add(m, -12) in m2}
    l1 = {m: float(m2y[m] < 0.05 and m2y[m] < m2y[month_add(m, -6)]) for m in m2y if month_add(m, -6) in m2y}
    S["L1"] = asof(from_monthly(l1, cape_av), 1)
    wa = asof(fred("WALCL"), 3)                        # H.4.1 comes out Thursday after the close
    S["L2"] = flag(chg(wa, 130) < 0, ~np.isnan(chg(wa, 130)))
    oil = asof(fred("DCOILWTICO"), 4)
    oil = np.where(oil > 5, oil, np.nan)
    S["O1"] = flag(roc(oil, 252) > 0.50, ~np.isnan(roc(oil, 252)))
    S["T1"] = flag(px < sma(px, 200), ~np.isnan(sma(px, 200)))
    fam = {"RATES": ["R1", "R2", "R3", "R4", "R5", "R6", "R7"], "INFLATION": ["I1", "I2", "I3"], "VALUATION": ["V1", "V2", "V3"], "GOLD": ["G1", "G2", "G3", "G4", "G5"],
           "CREDIT": ["C1", "C2", "C3", "C4"], "DOLLAR": ["D1", "D2"], "VOLUME": ["M1", "M2", "M3"], "LIQUIDITY": ["L1", "L2"], "OIL": ["O1"]}
    for f, ids in fam.items():
        X = np.array([S[i] for i in ids])
        n = (~np.isnan(X)).sum(0)
        on = np.nansum(X, 0)
        S["F_" + f] = np.where(n > 0, (on * 2 >= np.maximum(n, 1)).astype(float), np.nan)
    F = np.array([S["F_" + f] for f in fam])
    nf_, on_ = (~np.isnan(F)).sum(0), np.nansum(F, 0)
    for k in (2, 3):
        S[f"GC{k}"] = np.where(nf_ >= 5, (on_ >= k).astype(float), np.nan)
    _c["st"] = (S, fam)
    return _c["st"]


PRIMARY = ["F_RATES", "F_INFLATION", "F_VALUATION", "F_GOLD", "F_CREDIT", "F_DOLLAR", "F_VOLUME", "F_LIQUIDITY", "F_OIL", "GC2", "GC3"]


def engines():
    """{HG, KMLM, SLEEVE, BOOK, TBILL: {day: return}} from the caches of addenda 58-59"""
    if "eng" in _c:
        return _c["eng"]
    hg = json.load(open(w.CACHE + "/cells_HG.json"))
    sl = json.load(open(w.CACHE + "/cells_SLEEVE.json"))
    ks_ = SCR + "/kmlm_synth"
    kl, kr = json.load(open(ks_ + "/cells_long.json")), json.load(open(ks_ + "/cells_real_tr.json"))
    cat = lambda o: {**dict(zip(o["long_days"], o["cells"]["base"]["long"]["ret"])), **dict(zip(o["real_days"], o["cells"]["base"]["real"]["ret"]))}   # noqa: E731
    E = {"HG": cat(hg), "SLEEVE": cat(sl), "KMLM": {**dict(zip(kl["days"], kl["cells"]["base"]["ret"])), **dict(zip(kr["days"], kr["cells"]["base"]["ret"]))}}
    PL = w.long_panel()
    b = PL["BIL"]
    bd = sorted(b)
    tb = {d1: b[d1] / b[d0] - 1 for d0, d1 in zip(bd, bd[1:]) if d1 <= "2023-01-31"}
    b = w.kdata.series("BIL", END)
    bd = sorted(b)
    tb.update({d1: b[d1] / b[d0] - 1 for d0, d1 in zip(bd, bd[1:]) if d1 > "2023-01-31"})
    E["TBILL"] = tb
    common = sorted(set(E["HG"]) & set(E["KMLM"]) & set(E["SLEEVE"]) & set(tb))
    E["BOOK"] = {d: 0.341 * E["HG"][d] + 0.341 * E["KMLM"][d] + 0.318 * E["SLEEVE"][d] for d in common}
    _c["eng"] = E
    return E


STRETCH = {"HG": ("1991-04-01", "2006-07-18", "2015-09-01"), "KMLM": ("1991-04-01", "2021-06-01", "2021-06-01"), "SLEEVE": ("1994-06-01", "2015-06-01", "2020-12-02"),
           "BOOK": ("1994-06-01", "2015-06-01", "2021-06-01")}          # start of: shape, mostly real, real


if __name__ == "__main__":
    S, fam = states()
    days = sessions()
    i0 = days.index("1994-06-02")
    print(f"{'id':12s} first      on-share(1994+) episodes(1994+) on-share(2015-06+) episodes(2015-06+) now")
    i1 = days.index("2015-06-01")
    for k, x in S.items():
        ok = ~np.isnan(x)
        f = days[int(np.argmax(ok))]
        ep = lambda a: int(((a[1:] == 1) & (a[:-1] == 0)).sum())            # noqa: E731
        a, b = x[i0:], x[i1:]
        print(f"{k:12s} {f} {np.nanmean(a):6.2f} {ep(a):5d} {np.nanmean(b):12.2f} {ep(b):8d} {x[-1]:8.0f}")
    E = engines()
    print({k: (min(v), max(v), len(v)) for k, v in E.items()})
