"""Data for the synthetic KMLM build (PREREG.md). Everything is cached OUTSIDE the repo ($KSYNTH_CACHE,
default the session scratchpad); only hashes and first/last dates are committed (out/data_manifest.json).

futures()     22 markets' back-adjusted and held-contract prices from the pysystemtrade project's public data
              files (github.com/robcarver17/pysystemtrade, data/futures/{adjusted_prices_csv,multiple_prices_csv}).
              NOT redistributed here: the project's code is GPL-3 and the data files' own terms are unverified.
              Daily percentage return of the held position = change in the back-adjusted price / the held
              contract's price the day before (a back-adjusted LEVEL can be near zero or negative far back, so
              its own ratio is never used). xr_index() chains those returns into an excess-return index.
fund_tr()     the real fund's total return from RAW closes and the distributions on the fund's own page: Yahoo's
              adjusted close uses $2.481 for the 2022-12-28 distribution; the fund paid $4.037692 (its 2022 NAV
              return of +30.52% in the prospectus is matched only with the latter).
index_monthly()  the KFA MLM Index's published monthly returns, 1988-01..2025-03 (KraneShares investor deck p15),
              a splice: MLM Index to 2004-12, MLM Index EV 2005-01..2020-11, KFA MLM Index after.
tbill()       daily T-bill return from the 13-week yield (^IRX / 100 / 252).
"""
import csv
import math
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "kmlm_2026-11"))
import data as kdata  # noqa: E402

CACHE = os.environ.get("KSYNTH_CACHE", kdata.SCRATCH + "/kmlm_synth")
RAW = "https://raw.githubusercontent.com/robcarver17/pysystemtrade/master/data/futures"
BASKETS = {
    "commodities": "CORN CRUDE_W COPPER GOLD HEATOIL LIVECOW GAS_US SOYBEAN SUGAR11 WHEAT GASOILINE".split(),
    "currencies": "GBP CAD AUD EUR JPY CHF".split(),
    "bonds": "CAD10 BUND JGB GILT US10".split(),
}
MARKETS = [m for b in BASKETS.values() for m in b]
DISTRIBUTIONS = {"2021-12-29": 1.838123, "2022-12-28": 4.037692, "2024-12-17": 0.230111, "2025-12-22": 1.303457}
INDEX_FILE = kdata.SCRATCH + "/kmlm_synth_scout/hold/kfa_mlm_index_monthly.json"     # parsed from the deck by the scout


def _get(kind, m):
    os.makedirs(f"{CACHE}/psy", exist_ok=True)
    path = f"{CACHE}/psy/{kind}_{m}.csv"
    if not os.path.exists(path):
        folder = "adjusted_prices_csv" if kind == "adj" else "multiple_prices_csv"
        r = subprocess.run(["curl", "-sSL", "--retry", "2", "--max-time", "120", "-o", path, f"{RAW}/{folder}/{m}.csv"],
                           capture_output=True, text=True)
        if r.returncode != 0 or os.path.getsize(path) < 1000:
            raise RuntimeError(f"fetch failed for {kind} {m}: {r.stderr[:200]}")
    return path


REF = {"CORN": "ZC=F", "CRUDE_W": "CL=F", "COPPER": "HG=F", "GOLD": "GC=F", "HEATOIL": "HO=F", "LIVECOW": "LE=F", "GAS_US": "NG=F",
       "SOYBEAN": "ZS=F", "SUGAR11": "SB=F", "WHEAT": "ZW=F", "GASOILINE": "RB=F", "GBP": "6B=F", "CAD": "6C=F", "AUD": "6A=F",
       "EUR": "6E=F", "JPY": "6J=F", "CHF": "6S=F", "US10": "ZN=F"}
BOND_REF = {"CAD10": 0, "BUND": 0, "GILT": 0, "JGB": 1}          # reference = the US 10y, this many sessions earlier
READINGS = ("mark", "intraday", "per_day")
_fut = {}


def _rows(m):
    """[(stamp, adjusted)] and [(stamp, held contract's price)] as filed"""
    adj, px = [], []
    with open(_get("adj", m)) as f:
        rd = csv.reader(f)
        next(rd)
        for r in rd:
            if len(r) > 1 and r[1] != "":
                try:
                    adj.append((r[0], float(r[1])))
                except ValueError:
                    pass
    with open(_get("mp", m)) as f:
        for r in csv.DictReader(f):
            if r["PRICE"] != "":
                try:
                    px.append((r["DATETIME"], float(r["PRICE"])))
                except ValueError:
                    pass
    return adj, px


def _readings(rows):
    """{reading: {day: value}} (DEVIATIONS.md 13)"""
    mark, intra = {}, {}
    for stamp, v in rows:
        (mark if stamp[11:] == "23:00:00" else intra)[stamp[:10]] = v
    return {"mark": mark, "intraday": intra}


def _per_day(mark, intra):
    """{day: 'mark' | 'intraday'}: the filed close is kept unless it sits nearer the day before's value than
    the day's own last print (then it is yesterday's close and the last print is used)"""
    out, prev = {}, None
    for d in sorted(set(mark) | set(intra)):
        if d in mark and d in intra and prev is not None and abs(mark[d] - intra[d]) > abs(mark[d] - prev):
            out[d] = "intraday"
        else:
            out[d] = "mark" if d in mark else "intraday"
        prev = (mark if out[d] == "mark" else intra)[d]
    return out


def _rets(x):
    ds = sorted(x)
    return {b: x[b] / x[a] - 1 for a, b in zip(ds, ds[1:]) if x[a] > 0}


def _xr(adj, px):
    """{day: excess return} of one reading: change in the back-adjusted price over the held contract's price"""
    ds = sorted(set(adj) & set(px))
    return {b: (adj[b] - adj[a]) / px[a] for a, b in zip(ds, ds[1:]) if px[a] > 0}


def _corr(a, b):
    n = len(a)
    if n < 60:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb) if va > 0 and vb > 0 else None


def _reference(m):
    if m in REF:
        r = _rets(kdata.series(REF[m], field="close"))
        return {d: v for d, v in r.items() if abs(v) < 0.15}
    us = _xr(*futures("US10"))
    ds = sorted(us)
    k = BOND_REF[m]
    return {ds[i]: us[ds[i - k]] for i in range(k, len(ds))}


def futures(m):
    """({day: back-adjusted price}, {day: held contract's price}), each year read the way whose excess
    returns match an independent daily close best (DEVIATIONS.md 13, 13b, 13c). Choices: choices(m)."""
    if m in _fut:
        return _fut[m][0], _fut[m][1]
    adj_rows, px_rows = _rows(m)
    A, P = _readings(adj_rows), _readings(px_rows)
    which = _per_day(A["mark"], A["intraday"])
    for X in (A, P):
        X["per_day"] = {d: X[k][d] for d, k in which.items() if d in X[k]}
    ref = _reference(m)
    years = sorted({d[:4] for d in A["mark"]} | {d[:4] for d in A["intraday"]})
    R = {k: _xr(A[k], P[k]) for k in READINGS}
    pick = {}
    for y in years:
        cs = {}
        for k in READINGS:
            ds = [d for d in R[k] if d[:4] == y and d in ref]
            cs[k] = _corr([R[k][d] for d in ds], [ref[d] for d in ds])
        ok = {k: v for k, v in cs.items() if v is not None}
        best = max(ok, key=ok.get) if ok else "mark"
        pick[y] = {"reading": best, "corr": {k: (None if v is None else round(v, 3)) for k, v in cs.items()}}
    adj, px = {}, {}
    for src, out in ((A, adj), (P, px)):
        for y in years:
            k = pick[y]["reading"]
            for d, v in src[k].items():
                if d[:4] == y:
                    out[d] = v
            for other in ("mark", "intraday"):            # no session with a print is dropped (DEVIATIONS.md 13c)
                for d, v in src[other].items():
                    if d[:4] == y and d not in out:
                        out[d] = v
    _fut[m] = (adj, px, pick)
    return adj, px


def choices(m):
    futures(m)
    return _fut[m][2]


def xr_index(m):
    """{day: excess-return index} of holding the market's futures, starting at 1.0"""
    adj, px = futures(m)
    ds = sorted(set(adj) & set(px))
    out, lvl = {ds[0]: 1.0}, 1.0
    for a, b in zip(ds, ds[1:]):
        if px[a] > 0:
            lvl *= 1 + (adj[b] - adj[a]) / px[a]
        out[b] = lvl
    return out


def fund_tr(end=None):
    """{day: total-return level of the KMLM fund} from raw closes and the fund page's distributions"""
    o = kdata.fetch("KMLM")
    ds = [d for d in o["dates"] if end is None or d <= end]
    c = dict(zip(o["dates"], o["close"]))
    out, lvl = {ds[0]: 1.0}, 1.0
    for a, b in zip(ds, ds[1:]):
        lvl *= (c[b] + DISTRIBUTIONS.get(b, 0.0)) / c[a]
        out[b] = lvl
    return out


def index_monthly():
    return {k: float(v) for k, v in json.load(open(INDEX_FILE)).items()}


def tbill():
    irx = kdata.series("^IRX", field="close")
    ds = sorted(irx)
    return {b: irx[a] / 100.0 / 252.0 for a, b in zip(ds, ds[1:])}


def manifest():
    out = {}
    for m in MARKETS:
        adj, px = futures(m)
        ds = sorted(set(adj) & set(px))
        ch = choices(m)
        out[m] = {"first": ds[0], "last": ds[-1], "days": len(ds),
                  "reading_by_year": {y: v["reading"] for y, v in ch.items()},
                  "corr_with_reference_by_year": {y: v["corr"][v["reading"]] for y, v in ch.items() if v["corr"][v["reading"]] is not None},
                  "unresolved_years": [y for y, v in ch.items() if v["corr"][v["reading"]] is not None and v["corr"][v["reading"]] < 0.5],
                  "sha256_adj": hashlib.sha256(open(_get("adj", m), "rb").read()).hexdigest()[:16],
                  "sha256_mp": hashlib.sha256(open(_get("mp", m), "rb").read()).hexdigest()[:16]}
    return out


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    man = manifest()
    json.dump(man, open(os.path.join(HERE, "out", "data_manifest.json"), "w"), indent=1)
    for m, v in man.items():
        print(f"{m:10s} {v['first']} .. {v['last']}  {v['days']:6d}")
    o = kdata.fetch("KMLM")
    c = dict(zip(o["dates"], o["close"]))
    ds = o["dates"]
    for d, amt in DISTRIBUTIONS.items():
        i = ds.index(d)
        print(f"distribution {d}: ${amt:.4f}; raw close {c[ds[i - 1]]:.2f} -> {c[d]:.2f} (change {c[d] - c[ds[i - 1]]:+.2f})")
    ix = index_monthly()
    print("index months", min(ix), "..", max(ix), len(ix), "| sample", {k: ix[k] for k in sorted(ix)[-2:]})
