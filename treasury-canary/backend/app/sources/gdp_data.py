"""Keyless inputs for the GDP tab (studies/gdp-watch.md).

- OECD Quarterly National Accounts, real GDP growth, seasonally adjusted (dataflow
  OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_OECD): GY = % on the same quarter a year earlier, G1 = % on
  the previous quarter.
- IMF World Economic Outlook, DataMapper API v1: LP (population, millions, with projections), NGDPD (GDP, USD bn:
  world shares), NGDP_RPCH (real GDP growth, %, with projections).

Every download rides fred_csv.download_cached, so the repo's degradation contract holds: a failed fetch serves the
last cached copy marked "stale". With nothing cached, the snapshot frozen with the study
(sources/gdp_snapshot.json.gz) fills that input, marked "snapshot", so the tab always renders.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import os

from . import fred_csv

logger = logging.getLogger(__name__)

COUNTRIES = ["USA", "CHN", "DEU", "JPN", "GBR", "IND", "FRA", "ITA", "CAN", "BRA", "ESP", "KOR", "AUS", "MEX", "TUR",
             "IDN", "NLD", "SAU", "CHE", "POL"]
AGGREGATES = ["G20", "OECD"]
OECD_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_OECD,/"
            "Q.Y.{codes}.S1..B1GQ......{t}.?startPeriod=1990-Q1")
OECD_HEADERS = {"Accept": "application/vnd.sdmx.data+csv; charset=utf-8"}
IMF_URL = "https://www.imf.org/external/datamapper/api/v1/{ind}"
SNAPSHOT = os.path.join(os.path.dirname(__file__), "gdp_snapshot.json.gz")
TTL_OECD, TTL_IMF = 12 * 3600, 24 * 3600


def parse_oecd(body: bytes, keep: list[str]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for r in csv.DictReader(io.StringIO(body.decode("utf-8-sig"))):
        v, c, t = r.get("OBS_VALUE"), r.get("REF_AREA"), r.get("TIME_PERIOD") or ""
        if c in keep and v not in ("", None) and len(t) == 7 and t[4:6] == "-Q":
            try:
                out.setdefault(c, {})[t] = round(float(v), 4)
            except ValueError:
                continue
    return {k: dict(sorted(v.items())) for k, v in out.items()}


def parse_imf(body: bytes, ind: str, keep: list[str]) -> dict[str, dict[str, float]]:
    vals = (json.loads(body.decode("utf-8")).get("values") or {}).get(ind) or {}
    out = {}
    for k in keep:
        row = {str(y): float(v) for y, v in (vals.get(k) or {}).items() if isinstance(v, (int, float))}
        if row:
            out[k] = dict(sorted(row.items()))
    return out


def _ok_oecd(b: bytes) -> bool:
    """an SDMX-CSV body (DATAFLOW... or STRUCTURE... header), never an HTML error page."""
    return b.lstrip(b"\xef\xbb\xbf")[:3] in (b"DAT", b"STR") and b"OBS_VALUE" in b[:2000]


def _ok_imf(b: bytes) -> bool:
    try:
        return isinstance(json.loads(b.decode("utf-8")).get("values"), dict)
    except Exception:  # noqa: BLE001
        return False


def load_snapshot() -> dict:
    try:
        with gzip.open(SNAPSHOT, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("GDP snapshot unreadable: %s", exc)
        return {}


def fetch_all() -> dict:
    """{yoy, qoq, pop, ngdpd, weo_growth} plus a status and source per input."""
    snap = load_snapshot()
    codes = "+".join(COUNTRIES + AGGREGATES)
    out: dict = {"status": {}, "src": {}, "snapshot_as_of": snap.get("as_of")}
    for key, t in (("yoy", "GY"), ("qoq", "G1")):
        u = OECD_URL.format(codes=codes, t=t)
        body, st = fred_csv.download_cached(f"gdp_oecd_{t}.csv", u, TTL_OECD, headers=OECD_HEADERS, validate=_ok_oecd)
        data = parse_oecd(body, COUNTRIES + AGGREGATES) if body else {}
        if not data:
            data, st = snap.get(key) or {}, ("snapshot" if snap.get(key) else "error")
        out[key], out["status"][key], out["src"][key] = data, st, u
    for key, ind, keep in (("pop", "LP", COUNTRIES), ("ngdpd", "NGDPD", COUNTRIES + ["WEOWORLD"]),
                           ("weo_growth", "NGDP_RPCH", COUNTRIES + ["WEOWORLD", "G20"])):
        u = IMF_URL.format(ind=ind)
        body, st = fred_csv.download_cached(f"gdp_imf_{ind}.json", u, TTL_IMF, validate=_ok_imf)
        data = {}
        if body:
            try:
                data = parse_imf(body, ind, keep)
            except Exception as exc:  # noqa: BLE001
                logger.warning("IMF %s unparseable: %s", ind, exc)
        if not data:
            data, st = snap.get(key) or {}, ("snapshot" if snap.get(key) else "error")
        out[key], out["status"][key], out["src"][key] = data, st, u
    return out
