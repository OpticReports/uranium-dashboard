"""TIC foreign bid by country: Treasuries vs corporate bonds (free, keyless).

Two sources, two bases — the distinction is the whole point of the panel:

1. FRED mirrors of the TIC SLT + Fed staff estimates, monthly 1984-12 ->:
   FORLT{TREAS,CORP}{NET,POS}<TIC code>. LONG-TERM securities only (original
   maturity > 1y): Treasury BILLS are excluded, so Japan's 2026 bill selling
   is invisible here. Codes verified live 2026-10-15 against the finder D
   panel (studies/ai_debt_flows/data/tic_*.csv headers) and the CSLT titles.
2. The TIC CSLT dataset (cslt.zip, ~9 MB -> 122 MB JSON) carries the same
   series PLUS `for_treas_net_<code>`: Treasuries of ALL maturities (bills
   included). bills_inclusive() streams the handful of series it needs out of
   the zip without loading the JSON (a 512 MB instance cannot).

Attribution is by custody country, not beneficial owner (UK, Belgium,
Luxembourg, Cayman, Ireland are custody/fund centres); "Grand Total" includes
international and regional organizations, "All Countries" excludes them.
Units: $ millions at source -> $bn here. Net = foreign net purchases at
market value (+ = foreigners bought).
"""
from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from datetime import date

from . import fred_csv

logger = logging.getLogger(__name__)

CSLT_URL = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/cslt.zip"
_CSLT_TTL = 3 * 24 * 3600   # monthly release (~6-week lag); re-pull every 3 days

# key, display name, TIC country code, custody/fund centre (unattributable)
COUNTRIES: list[tuple[str, str, str, bool]] = [
    ("japan", "Japan", "42609", False),
    ("china", "China", "41408", False),
    ("uk", "United Kingdom", "13005", True),
    ("taiwan", "Taiwan", "46302", False),
    ("korea", "Korea", "43001", False),
    ("cayman", "Cayman Islands", "36137", True),
    ("luxembourg", "Luxembourg", "11703", True),
    ("ireland", "Ireland", "11401", True),
    ("belgium", "Belgium", "10251", True),
    ("switzerland", "Switzerland", "12688", False),
    ("norway", "Norway", "12203", False),
]
AGGREGATES: list[tuple[str, str, str]] = [
    ("grand_total", "Grand Total", "99996"),
    ("official", "Foreign Official", "99990"),
    ("non_official", "Foreign Non-Official", "99991"),
    ("all_countries", "All Countries", "69995"),
]
LABELS = {
    "grand_total": "Grand Total = all countries plus international and regional organizations",
    "all_countries": "All Countries = excludes international and regional organizations",
    "official": "Foreign Official institutions (central banks, sovereign funds, governments)",
    "non_official": "Foreign private holders (Grand Total minus Foreign Official)",
}
_MEASURES = {"treas_net": "FORLTTREASNET", "corp_net": "FORLTCORPNET",
             "treas_pos": "FORLTTREASPOS", "corp_pos": "FORLTCORPPOS"}
BASIS_LT = ("TIC SLT + Fed staff estimates via FRED; long-term securities only (bills "
            "excluded); attributed by custody country, not beneficial owner; $bn; "
            "net = foreign net purchases at market value; corp share of LT = LT corporate "
            "positions / (LT Treasury + LT corporate positions), agencies and equities excluded")


def series_id(measure: str, code: str) -> str:
    return _MEASURES[measure] + code


def _ym(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _bn(v: float | None) -> float | None:
    return None if v is None else round(v / 1000.0, 3)


def _sum_last(vals: list[float | None], n: int) -> float | None:
    """Sum of the last n observations; None if any is missing (never 0 for a gap)."""
    tail = vals[-n:]
    if len(tail) < n or any(v is None for v in tail):
        return None
    return round(sum(tail), 3)


def _last(vals: list[float | None]) -> float | None:
    for v in reversed(vals):
        if v is not None:
            return v
    return None


def _entity(code: str, months: list[str], by_month: dict[str, dict[str, dict[str, float | None]]]
            ) -> dict:
    """Aligned series + headline stats for one TIC code."""
    out: dict = {"code": code}
    for m in _MEASURES:
        out[m] = [by_month[m].get(code, {}).get(ym) for ym in months]
    out["treas_net_12m"] = _sum_last(out["treas_net"], 12)
    out["corp_net_12m"] = _sum_last(out["corp_net"], 12)
    out["treas_pos_latest"] = _last(out["treas_pos"])
    out["corp_pos_latest"] = _last(out["corp_pos"])
    tp, cp = out["treas_pos_latest"], out["corp_pos_latest"]
    out["corp_share_of_lt_pct"] = (round(100.0 * cp / (tp + cp), 1)
                                   if tp is not None and cp is not None and tp + cp else None)
    out["status"] = fred_csv.worst_status(series_id(m, code) for m in _MEASURES)
    return out


def fetch_by_country(start: str = "2015-01-01") -> dict:
    """Monthly LT Treasuries vs corporates, net and positions, by country and
    aggregate. $bn. Any series that fails is None-filled and the block's
    status says so."""
    codes = [c[2] for c in COUNTRIES] + [a[2] for a in AGGREGATES]
    ids = [series_id(m, c) for c in codes for m in _MEASURES]
    raw = fred_csv.fetch_many(ids, start)
    by_month: dict[str, dict[str, dict[str, float | None]]] = {m: {} for m in _MEASURES}
    months: set[str] = set()
    for c in codes:
        for m in _MEASURES:
            ds, vs = raw.get(series_id(m, c), ([], []))
            by_month[m][c] = {_ym(d): _bn(v) for d, v in zip(ds, vs)}
            months.update(_ym(d) for d in ds)
    axis = sorted(months)
    # FRED emits empty trailing observations for some series; a month where NO
    # net-flow series has a value must not advance asof and null every 12m sum
    while axis and all(by_month[m].get(c, {}).get(axis[-1]) is None
                       for m in ("treas_net", "corp_net") for c in codes):
        axis.pop()
    countries = []
    for key, name, code, custody in COUNTRIES:
        e = _entity(code, axis, by_month)
        e.update({"key": key, "name": name, "custody_centre": custody})
        countries.append(e)
    aggs = {}
    for key, name, code in AGGREGATES:
        e = _entity(code, axis, by_month)
        e.update({"key": key, "name": name, "label": LABELS[key]})
        aggs[key] = e
    return {
        "asof": axis[-1] if axis else None,
        "months": axis,
        "unit": "$bn",
        "basis": BASIS_LT,
        "countries": countries,
        "aggregates": aggs,
        "labels": LABELS,
        "src": {"fred_pattern": fred_csv.url("FORLT{TREAS|CORP}{NET|POS}<code>"),
                "japan_treas_net": fred_csv.url(series_id("treas_net", "42609")),
                "grand_total_corp_pos": fred_csv.url(series_id("corp_pos", "99996"))},
        "status": fred_csv.worst_status(ids),
    }


# ---------------------------------------------------------------------------
# CSLT zip: Treasuries including bills
# ---------------------------------------------------------------------------
_BILLS_IDS = {
    # key -> CSLT source_id. for_treas_* = all maturities; for_lt_treas_* = LT only.
    "japan_all": "for_treas_net_42609", "japan_lt": "for_lt_treas_net_42609",
    "all_countries_all": "for_treas_net_69995", "all_countries_lt": "for_lt_treas_net_69995",
    "grand_total_all": "for_treas_net_99996", "grand_total_lt": "for_lt_treas_net_99996",
}
_SRC_RE = re.compile(rb'"source_id"\s*:\s*"([a-z0-9_]+)"')
_OBS_RE = re.compile(rb'"observations"\s*:\s*\[')


def extract_cslt_series(stream, wanted: set[str], chunk: int = 1 << 20
                        ) -> dict[str, list[tuple[str, float | None]]]:
    """Stream the CSLT JSON and pull only `wanted` source_ids' observations.

    The file is ~122 MB pretty-printed JSON; json.load would need several
    hundred MB. Each series object is {"source_id", "metadata",
    "observations": [[date, value], ...]} in that order, so we scan for the
    id, then the observations array, and bracket-count to its end. Returns
    {source_id: [(YYYY-MM-DD, value|None), ...]} newest first as in the file.
    """
    found: dict[str, list[tuple[str, float | None]]] = {}
    buf = b""
    eof = False
    while not eof and len(found) < len(wanted):
        piece = stream.read(chunk)
        if not piece:
            eof = True
        buf += piece
        pos = 0
        hold: int | None = None   # start of a wanted series whose array is still incomplete
        while True:
            m = _SRC_RE.search(buf, pos)
            if not m:
                break
            sid = m.group(1).decode()
            if sid not in wanted or sid in found:
                pos = m.end()
                continue
            o = _OBS_RE.search(buf, m.end())
            if not o:
                hold = m.start()
                break  # need more data for this series
            depth, i, end = 1, o.end(), -1
            while i < len(buf):
                ch = buf[i]
                if ch == 0x5B:      # [
                    depth += 1
                elif ch == 0x5D:    # ]
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
                i += 1
            if end < 0:
                hold = m.start()
                break  # array continues in the next chunk
            try:
                obs = json.loads(buf[o.end() - 1:end + 1].decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("CSLT: could not parse observations of %s: %s", sid, exc)
                obs = []
            rows: list[tuple[str, float | None]] = []
            for item in obs:
                try:
                    d, v = item[0], item[1]
                    rows.append((str(d), None if v in (None, "", "n.a.") else float(v)))
                except (TypeError, ValueError, IndexError):
                    continue
            found[sid] = rows
            pos = end + 1
        if hold is not None:
            if len(buf) - hold > 64 << 20:
                logger.warning("CSLT: a single series exceeds the 64 MB scan window; giving up")
                break
            buf = buf[hold:]          # keep the unfinished series whole
        else:
            # keep a small overlap so a "source_id" token split across chunks is seen
            buf = buf[max(len(buf) - 4096, 0):]
    return found


def _series_from_zip(body: bytes, wanted: set[str]) -> dict[str, list[tuple[str, float | None]]]:
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".json")]
        if not names:
            raise ValueError("cslt.zip has no .json member")
        with zf.open(names[0]) as fh:
            return extract_cslt_series(fh, wanted)


def _is_zip(body: bytes) -> bool:
    return body[:2] == b"PK"


def bills_inclusive(window_months: int = 12, start: str = "2015-01-01") -> dict:
    """Japan and All-Countries net purchases of Treasuries, LT-only AND all
    maturities (bills included), from the CSLT zip. $bn.

    Headline: trailing `window_months` sums (the memo's 12m to Jul-26: Japan
    LT +4.0 vs incl. bills -48.6; All Countries +240.1 vs +291.8)."""
    body, st = fred_csv.download_cached("tic_cslt.zip", CSLT_URL, _CSLT_TTL, validate=_is_zip)
    empty = {"asof": None, "unit": "$bn", "window_months": window_months, "months": [],
             "series": {}, "japan": {}, "all_countries": {}, "grand_total": {},
             "labels": LABELS, "src": CSLT_URL, "status": "error",
             "note": ("TIC CSLT: Treasuries of all maturities vs long-term only; the gap is "
                      "bill trading. Net = foreign net purchases at market value, $bn.")}
    if body is None:
        return empty
    try:
        found = _series_from_zip(body, set(_BILLS_IDS.values()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("CSLT parse failed: %s", exc)
        return empty
    by_key = {k: dict((d[:7], _bn(v)) for d, v in found.get(sid, [])) for k, sid in _BILLS_IDS.items()}
    months = sorted({m for s in by_key.values() for m in s if m >= start[:7]})
    series = {k: [by_key[k].get(m) for m in months] for k in _BILLS_IDS}
    out = dict(empty)
    out.update({"asof": months[-1] if months else None, "months": months, "series": series,
                "status": st if all(found.get(s) for s in _BILLS_IDS.values()) else "error"})
    for ent in ("japan", "all_countries", "grand_total"):
        lt, al = series[f"{ent}_lt"], series[f"{ent}_all"]
        out[ent] = {
            "lt_12m": _sum_last(lt, window_months),
            "all_maturities_12m": _sum_last(al, window_months),
            "lt_label": "long-term Treasuries only (bills excluded)",
            "all_label": "Treasuries of all maturities (bills included)",
        }
    return out
