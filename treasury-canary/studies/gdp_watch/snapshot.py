"""Freeze the GDP study's inputs into one compact, dated snapshot (studies/gdp_watch/data/snapshot_<date>.json.gz).

Sources (all keyless):
- OECD Quarterly National Accounts, real GDP growth, seasonally adjusted
  (dataflow OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_OECD): GY = change on the same quarter a year
  earlier, G1 = change on the previous quarter, both in %.
- IMF World Economic Outlook via the DataMapper API: LP (population, millions, with projections),
  NGDPD (GDP, current USD bn: shares of world GDP), NGDP_RPCH (real GDP growth, %, with projections).

    python3 -I snapshot.py <download dir> <out.json.gz> <as_of YYYY-MM-DD>
"""
from __future__ import annotations

import csv
import gzip
import json
import sys

COUNTRIES = ["USA", "CHN", "DEU", "JPN", "GBR", "IND", "FRA", "ITA", "CAN", "BRA", "ESP", "KOR", "AUS", "MEX", "TUR",
             "IDN", "NLD", "SAU", "CHE", "POL"]
AGGREGATES = ["G20", "OECD"]


def oecd(path: str) -> dict:
    out: dict = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        v = r.get("OBS_VALUE")
        if r["REF_AREA"] in COUNTRIES + AGGREGATES and v not in ("", None):
            out.setdefault(r["REF_AREA"], {})[r["TIME_PERIOD"]] = round(float(v), 4)
    return {k: dict(sorted(v.items())) for k, v in out.items()}


def imf(path: str, ind: str, keep: list[str]) -> dict:
    vals = json.load(open(path, encoding="utf-8"))["values"][ind]
    return {k: {y: v for y, v in sorted(vals[k].items())} for k in keep if k in vals}


if __name__ == "__main__":
    d, out, as_of = sys.argv[1], sys.argv[2], sys.argv[3]
    snap = {"as_of": as_of, "countries": COUNTRIES, "aggregates": AGGREGATES,
            "sources": {"oecd": "OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_OECD (Q, seasonally adjusted, B1GQ)",
                        "imf": "IMF WEO DataMapper API v1: LP, NGDPD, NGDP_RPCH"},
            "yoy": oecd(f"{d}/oecd_GY.csv"), "qoq": oecd(f"{d}/oecd_G1.csv"),
            "pop": imf(f"{d}/imf_LP.json", "LP", COUNTRIES),
            "ngdpd": imf(f"{d}/imf_NGDPD.json", "NGDPD", COUNTRIES + ["WEOWORLD"]),
            "weo_growth": imf(f"{d}/imf_NGDP_RPCH.json", "NGDP_RPCH", COUNTRIES + ["WEOWORLD", "G20"])}
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(snap, fh, separators=(",", ":"), sort_keys=True)
    print(out, {k: len(v) for k, v in snap["yoy"].items()})
