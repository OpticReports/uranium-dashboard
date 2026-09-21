#!/usr/bin/env python3
"""Can the 16 scoreable blowoff peaks behind the corroboration study be
re-derived from what this repo actually ships — and does the fed_tightened
SERIES CHOICE change how they score?

MARGIN_DEBT.md ("Blowoff-peak study", "What separates real blowoffs from false
positives") scores 16 peaks — bears 1955/1967/1972/1980/1998/2000/2007/2021,
fizzles 1963/1976/1978/1983/1986/1992/2004/2010 — from "all local peaks of the
long margin-YoY series >=35% (deduped to 18 episodes, 1949-2026)". The analysis
script "lived in the working session" (MARGIN_DEBT.md, Data note) and was never
committed. This rebuilds the episode list from the SHIPPED pipeline and prints
the diff, so the gap is a measured fact rather than an assertion.

Part 2 re-scores every reconstructed peak with all six late-cycle flags, twice:
once with fed_tightened reading the 3-month bill (as shipped) and once reading
the fed funds rate. If the bear/fizzle split is identical under both, the
series choice is immaterial to the SCORING, not just to the crossing dates.

It reuses the deployed splice and YoY code (app.api.routes_margin), with the
data legs pulled keylessly:
  - Z.1 households security credit (HNOSCIQ027S), quarterly, via FRED's CSV
    endpoint, because fetch_series() needs an API key the study environment
    may not have;
  - FINRA margin statistics (1997+) via the app's own keyless fetcher.

Re-run:  python3 studies/corroboration_episode_reconstruction.py
Writes nothing. Findings recorded in MARGIN_DEBT.md, "Flag definition audit".
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from app.api.routes_margin import _yoy_by_date  # noqa: E402
from app.sources.finra_margin import fetch_margin_stats  # noqa: E402

PUBLISHED = {
    1955: "bear", 1963: "fizzle", 1967: "bear", 1972: "bear", 1976: "fizzle",
    1978: "fizzle", 1980: "bear", 1983: "fizzle", 1986: "fizzle",
    1992: "fizzle", 1998: "bear", 2000: "bear", 2004: "fizzle",
    2007: "bear", 2010: "fizzle", 2021: "bear",
}
BAR = 35.0          # the study's blowoff threshold, margin YoY %
Z1 = "HNOSCIQ027S"


def z1_quarterly(datadir: str):
    path = os.path.join(datadir, f"{Z1}.csv")
    if not os.path.exists(path):
        os.makedirs(datadir, exist_ok=True)
        subprocess.run(["curl", "-sS", "-m", "90", "-o", path,
                        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={Z1}"],
                       check=True)
    out = []
    for r in csv.reader(open(path)):
        if r[0][:1].isdigit() and r[1] not in (".", ""):
            out.append((dt.date.fromisoformat(r[0]), float(r[1])))
    return out


def peaks(dates, yoy, bar: float = BAR, window: int = 12):
    """Local maxima of the YoY series above `bar`, deduped to the highest
    reading inside +/- `window` months (the study's 'deduped to episodes')."""
    pts = [(d, v) for d, v in zip(dates, yoy) if v is not None and v >= bar]
    out = []
    for d, v in pts:
        near = [(d2, v2) for d2, v2 in pts
                if abs((d2.year - d.year) * 12 + d2.month - d.month) <= window]
        if v == max(v2 for _, v2 in near) and (not out or
                                               (d.year - out[-1][0].year) * 12
                                               + d.month - out[-1][0].month > window):
            out.append((d, v))
    return out


def main() -> None:
    datadir = os.path.join(HERE, "data_fedflag")
    z = z1_quarterly(datadir)
    finra = fetch_margin_stats()
    fd, fv = finra["margin_debit"]
    first_finra = next((d for d, v in zip(fd, fv) if v is not None), None)
    print(f"Z.1 {Z1}: {len(z)} quarters "
          f"{z[0][0] if z else '—'}..{z[-1][0] if z else '—'}")
    print(f"FINRA margin_debit: {sum(1 for v in fv if v is not None)} months "
          f"{first_finra}..{fd[-1] if fd else '—'}")
    if not z or not first_finra:
        print("\nLEG MISSING -> the long series cannot be rebuilt here at all.")
        return

    dates = [d for d, v in z if d < first_finra] + [d for d, v in zip(fd, fv) if v is not None]
    vals = [v for d, v in z if d < first_finra] + [v for v in fv if v is not None]
    yd, yv = _yoy_by_date(dates, vals, tol_days=20)
    cutoff = first_finra + dt.timedelta(days=360)
    yv = [None if (v is not None and first_finra <= d < cutoff) else v
          for d, v in zip(yd, yv)]

    yoy_by_month = {f"{d.year:04d}-{d.month:02d}": v for d, v in zip(yd, yv)}
    for window in (6, 12, 18, 24):
        ep = peaks(yd, yv, window=window)
        years = sorted({d.year for d, _ in ep})
        matched = [y for y in PUBLISHED if any(abs(y - e) <= 1 for e in years)]
        print(f"\ndedup window {window:>2}mo -> {len(ep)} episodes "
              f"({min(years)}-{max(years)})")
        print("   " + ", ".join(f"{d:%Y-%m} {v:.0f}%" for d, v in ep))
        print(f"   published peaks matched (+/-1y): {len(matched)}/16 "
              f"{sorted(matched)}")
        print(f"   published peaks NOT reconstructed: "
              f"{sorted(set(PUBLISHED) - set(matched))}")
        print(f"   reconstructed years with no published peak: "
              f"{[y for y in years if not any(abs(y - p) <= 1 for p in PUBLISHED)]}")
        if window == 18:          # the window that reproduces "18 episodes"
            rescore(ep, yoy_by_month, datadir)


# ---------------------------------------------------------------------------
# Part 2: re-score the reconstructed peaks under both policy-rate series.

FRED_MONTHLY = ("GS10", "TB3MS", "FEDFUNDS", "UNRATE", "USREC")


def fred_monthly(series_id: str, datadir: str) -> dict:
    path = os.path.join(datadir, f"{series_id}.csv")
    if not os.path.exists(path):
        os.makedirs(datadir, exist_ok=True)
        subprocess.run(["curl", "-sS", "-m", "90", "-o", path,
                        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"],
                       check=True)
    out = {}
    for r in csv.reader(open(path)):
        if r[0][:1].isdigit() and r[1] not in (".", ""):
            d = dt.date.fromisoformat(r[0])
            out[(d.year, d.month)] = float(r[1])
    return out


def months_since_recession(usrec: dict, key) -> int | None:
    ends = [k for k in sorted(usrec) if usrec[k] == 1.0 and k <= key]
    if not ends:
        return None
    last = ends[-1]
    return (key[0] - last[0]) * 12 + key[1] - last[1]


def score(peak, m: dict, spx_me: dict, yoy_by_month: dict, rate: dict):
    """The six flags as routes_margin.late_cycle_flags computes them, at a
    historical month. `rate` is the policy-rate series under test."""
    y, mo = peak.year, peak.month
    k, k12, k36 = (y, mo), (y - 1, mo), (y - 3, mo)
    ym, ym12, ym36 = f"{y:04d}-{mo:02d}", f"{y - 1:04d}-{mo:02d}", f"{y - 3:04d}-{mo:02d}"
    bill = m["TB3MS"].get(k)
    curve = (m["GS10"][k] - bill) if (k in m["GS10"] and bill is not None) else None
    d_rate = (rate[k] - rate[k12]) if (k in rate and k12 in rate) else None
    un = m["UNRATE"].get(k)
    mo_since = months_since_recession(m["USREC"], k)
    s_now, s_36 = spx_me.get(ym), spx_me.get(ym36)
    spx3y = (s_now / s_36 - 1) * 100 if (s_now and s_36) else None
    s_12 = spx_me.get(ym12)
    spx_yoy = (s_now / s_12 - 1) * 100 if (s_now and s_12) else None
    myoy = yoy_by_month.get(ym)
    excess = (myoy - spx_yoy) if (myoy is not None and spx_yoy is not None) else None
    flags = {
        "flat_curve": (curve < 1.0) if curve is not None else None,
        "fed_tightened": (d_rate > 0.5) if d_rate is not None else None,
        "late_expansion": (mo_since >= 48) if mo_since is not None else None,
        "low_unemployment": (un < 5.0) if un is not None else None,
        "extended_market": (spx3y > 50) if spx3y is not None else None,
        "high_excess": (excess >= 25) if excess is not None else None,
    }
    return flags, {"curve": curve, "d_rate": d_rate, "unrate": un,
                   "mo_since": mo_since, "spx3y": spx3y, "excess": excess}


def rescore(episodes, yoy_by_month, datadir: str) -> None:
    sys.path.insert(0, os.path.join(HERE, "..", "backend"))
    from app.api.routes_margin import fetch_spx_long, _month_end_closes

    m = {s: fred_monthly(s, datadir) for s in FRED_MONTHLY}
    spx = fetch_spx_long()
    if not spx[0]:
        print("\nS&P leg unavailable -> cannot re-score."); return
    spx_me = _month_end_closes(spx)

    scored = [(d, v) for d, v in episodes if d.year in PUBLISHED]
    print(f"\n=== Re-scoring {len(scored)} published peaks under both series ===")
    print(f"{'peak':>9} {'outcome':>7} | {'bill':>16} | {'fed funds':>10}")
    out = {"TB3MS": [], "FEDFUNDS": []}
    for d, _ in scored:
        line = f"{d:%Y-%m}  {PUBLISHED[d.year]:>7} |"
        for sid in ("TB3MS", "FEDFUNDS"):
            flags, vals = score(d, m, spx_me, yoy_by_month, m[sid])
            known = {k: v for k, v in flags.items() if v is not None}
            n = sum(1 for v in known.values() if v)
            out[sid].append((d, PUBLISHED[d.year], n, len(known), flags["fed_tightened"]))
            line += (f" {n}/{len(known)} flags, tightening="
                     f"{str(flags['fed_tightened']):>5} |")
        print(line)

    for sid in ("TB3MS", "FEDFUNDS"):
        hi = [r for r in out[sid] if r[2] >= 4]
        lo = [r for r in out[sid] if r[2] <= 2]
        print(f"\n{sid}: >=4 flags -> {sum(1 for r in hi if r[1] == 'bear')}/{len(hi)} bears"
              f"  |  <=2 flags -> {sum(1 for r in lo if r[1] == 'bear')}/{len(lo)} bears"
              f"  |  base {sum(1 for r in out[sid] if r[1] == 'bear')}/{len(out[sid])}")
    diff = [(a[0], a[2], b[2]) for a, b in zip(out["TB3MS"], out["FEDFUNDS"])
            if a[2] != b[2] or a[4] != b[4]]
    print("\npeaks where the series choice changes the flag or the count: "
          + (", ".join(f"{d:%Y-%m} {x}->{y}" for d, x, y in diff) if diff else "NONE"))


if __name__ == "__main__":
    main()
