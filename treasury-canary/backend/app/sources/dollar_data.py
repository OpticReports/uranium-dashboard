"""Dollar watch tab sources (studies/dollar-watch.md §5): keyless FRED CSVs, the
OFR FSI's funding / safe-asset / emerging-market columns, ICE DXY and EMB daily
from Yahoo with an FMP fallback, FMP spot gold, and three BIS SDMX CSVs.

Every fetch rides an existing cached primitive (fred_csv.fetch_csv,
fred_csv.download_cached, breaking.fetch_yahoo_daily, fmp.fetch_gold), so the
degradation contract is the repo's: a failed fetch serves the last cached copy
marked "stale"; nothing cached -> empty series marked "error". Nothing here
raises on a network problem. Series are returned as
{dates: [iso], values: [float | None], status, src, basis}.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date

from . import breaking, fmp, fred_csv

logger = logging.getLogger(__name__)

_TTL_BIS = 24 * 3600          # quarterly / semiannual / monthly releases

# FRED series the tab reads: id -> (start, label). Starts reach back far enough
# for each series' own-history percentile (layer 2) and the live rule (2006+).
FRED_SERIES = {
    "DTWEXBGS": ("2006-01-01", "Fed broad dollar index (goods and services)"),
    "DTWEXAFEGS": ("2006-01-01", "Fed dollar index vs advanced foreign economies"),
    "DTWEXEMEGS": ("2006-01-01", "Fed dollar index vs emerging-market economies"),
    "DGS10": ("2006-01-01", "10-year Treasury yield"),
    "VIXCLS": ("2006-01-01", "VIX (index days of the frozen rule)"),
    "DGS2": ("2000-01-01", "2-year Treasury yield"),
    "DFEDTARU": ("2008-12-16", "Fed funds target, upper bound"),
    "THREEFYTP10": ("2000-01-01", "10-year term premium (Kim-Wright)"),
    "WMTSECL1": ("2002-12-18", "Treasuries held in custody for foreign official accounts"),
    "DCPF3M": ("1997-01-01", "3-month AA financial commercial paper"),
    "DCPN3M": ("1997-01-01", "3-month AA nonfinancial commercial paper"),
    "DTB3": ("1997-01-01", "3-month Treasury bill"),
    "NFCIRISK": ("1971-01-01", "Chicago Fed NFCI risk subindex"),
    "SOFR": ("2018-04-02", "SOFR"),
    "SOFR99": ("2018-04-02", "SOFR 99th percentile"),
    "IORB": ("2021-07-29", "interest on reserve balances"),
    "SWPT": ("2002-12-18", "Fed central-bank liquidity swaps outstanding"),
    "DEXSZUS": ("2000-01-01", "Swiss francs per dollar"),
    "DEXJPUS": ("2000-01-01", "yen per dollar"),
    "DCOILBRENTEU": ("2000-01-01", "Brent crude, $/bbl"),
    "SP500": ("2016-01-01", "S&P 500 (ledger outcomes; FRED serves ten years)"),
    "BAA10Y": ("2006-01-01", "Moody's Baa minus the 10-year (ledger outcomes)"),
    # the eight-pair EM FX basket (TRY and IDR are not on FRED daily)
    "DEXBZUS": ("1995-01-01", "Brazilian reais per dollar"),
    "DEXMXUS": ("1995-01-01", "Mexican pesos per dollar"),
    "DEXSFUS": ("1995-01-01", "South African rand per dollar"),
    "DEXINUS": ("1995-01-01", "Indian rupees per dollar"),
    "DEXKOUS": ("1995-01-01", "Korean won per dollar"),
    "DEXTHUS": ("1995-01-01", "Thai baht per dollar"),
    "DEXCHUS": ("1995-01-01", "Chinese yuan per dollar"),
    "DEXMAUS": ("1995-01-01", "Malaysian ringgit per dollar"),
}
EMFX_IDS = ["DEXBZUS", "DEXMXUS", "DEXSFUS", "DEXINUS", "DEXKOUS", "DEXTHUS", "DEXCHUS", "DEXMAUS"]

OFR_COLUMNS = ("OFR FSI", "Funding", "Safe assets", "Emerging markets", "Credit", "Volatility")

BIS_GLI_TOTAL = "https://stats.bis.org/api/v1/data/WS_GLI/Q.USD.3P.N.A.I.B.USD/all?format=csv"
BIS_GLI_EME = "https://stats.bis.org/api/v1/data/WS_GLI/Q.USD.4T.N.A.I.B.USD/all?format=csv"
BIS_FX_ALL = "https://stats.bis.org/api/v1/data/WS_OTC_DERIV2/H.A.C.B.5J.A.5J.A.TO1.TO1.A.A.3.C/all?format=csv"
BIS_FX_USD = "https://stats.bis.org/api/v1/data/WS_OTC_DERIV2/H.A.C.B.5J.A.5J.A.USD.TO1.A.A.3.C/all?format=csv"
BIS_CBPOL_AREAS = ["US", "XM", "JP", "GB", "CH", "BR", "MX", "IN", "KR", "ZA", "TR", "ID", "CN"]
BIS_CBPOL = ("https://stats.bis.org/api/v1/data/WS_CBPOL/M." + "+".join(BIS_CBPOL_AREAS)
             + "/all?format=csv&startPeriod=2000-01")

DXY_SYMBOL = "DX-Y.NYB"
DXY_BASIS = "ICE US Dollar Index (DXY), daily close; Yahoo DX-Y.NYB, FMP fallback"
GOLD_BASIS = {"fmp": "spot gold XAUUSD, daily (FMP)", "yahoo": "COMEX gold front-month futures GC=F, daily (Yahoo fallback; futures, not spot)"}
EMB_BASIS = "iShares JP Morgan USD Emerging Markets Bond ETF (EMB), daily close"


def _iso(ds: list[date]) -> list[str]:
    return [d.isoformat() for d in ds]


def _empty(src: str, basis: str) -> dict:
    return {"dates": [], "values": [], "status": "error", "src": src, "basis": basis}


def fetch_fred() -> dict[str, dict]:
    """Every FRED series the tab reads, concurrently, each with its own status."""
    out: dict[str, dict] = {}
    by_start: dict[str, list[str]] = {}
    for sid, (start, _) in FRED_SERIES.items():
        by_start.setdefault(start, []).append(sid)
    for start, ids in by_start.items():
        got = fred_csv.fetch_many(ids, start)
        for sid in ids:
            ds, vs = got.get(sid, ([], []))
            st = fred_csv.status(sid) or ("ok" if ds else "error")
            out[sid] = {"dates": _iso(ds), "values": vs, "status": st if ds else "error",
                        "src": fred_csv.url(sid), "basis": FRED_SERIES[sid][1]}
    return out


def _yahoo(symbol: str, basis: str) -> dict:
    y = breaking.fetch_yahoo_daily(symbol)
    if not y["dates"]:
        return _empty(breaking.yahoo_url(symbol), basis)
    return {"dates": _iso(y["dates"]), "values": y["closes"], "status": y["status"],
            "src": breaking.yahoo_url(symbol), "basis": basis}


def _fmp(symbol: str, basis: str) -> dict:
    ds, vs = fmp.fetch_gold(symbol)          # /stable/historical-price-eod/light works for any symbol
    src = f"{fmp._URL}?symbol={symbol}"
    if not ds:
        return _empty(src, basis)
    return {"dates": _iso(ds), "values": vs, "status": "ok", "src": src, "basis": basis}


def fetch_dxy() -> dict:
    """ICE DXY daily: Yahoo first (2 years, keyless), FMP if Yahoo has nothing."""
    y = _yahoo(DXY_SYMBOL, DXY_BASIS)
    if y["dates"]:
        y["provider"] = "yahoo"
        return y
    f = _fmp(DXY_SYMBOL, DXY_BASIS)
    f["provider"] = "fmp" if f["dates"] else None
    return f


def fetch_gold() -> dict:
    """Spot gold from FMP (needs FMP_API_KEY); COMEX futures from Yahoo otherwise, labelled as such."""
    f = _fmp("XAUUSD", GOLD_BASIS["fmp"])
    if f["dates"]:
        f["provider"] = "fmp"
        return f
    y = _yahoo("GC=F", GOLD_BASIS["yahoo"])
    y["provider"] = "yahoo" if y["dates"] else None
    return y


def fetch_emb() -> dict:
    y = _yahoo("EMB", EMB_BASIS)
    if y["dates"]:
        y["provider"] = "yahoo"
        return y
    f = _fmp("EMB", EMB_BASIS)
    f["provider"] = "fmp" if f["dates"] else None
    return f


# ---------------------------------------------------------------------------- OFR FSI columns
def parse_ofr_columns(body: bytes, columns=OFR_COLUMNS) -> dict:
    """fsi.csv -> {dates: [iso], <column>: [float | None]} for the named columns.
    Raises on a missing Date column or no rows (download_cached's validate)."""
    text = body.decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("OFR FSI csv: no rows")
    keys = {k.strip().lower(): k for k in rows[0] if k}
    if "date" not in keys:
        raise ValueError("OFR FSI csv: no Date column")
    out: dict = {"dates": []}
    for c in columns:
        out[c] = []
    for r in rows:
        ds = (r.get(keys["date"]) or "").strip()[:10]
        if len(ds) != 10:
            continue
        out["dates"].append(ds)
        for c in columns:
            k = keys.get(c.lower())
            raw = (r.get(k) or "").strip() if k else ""
            try:
                out[c].append(float(raw) if raw not in ("", ".") else None)
            except ValueError:
                out[c].append(None)
    if not out["dates"]:
        raise ValueError("OFR FSI csv: no dated rows")
    return out


def fetch_ofr() -> dict:
    body, st = fred_csv.download_cached("ofr_fsi.csv", breaking.OFR_FSI_URL, 6 * 3600,
                                        validate=fred_csv.parses(parse_ofr_columns))
    if body is None:
        return {"dates": [], "status": "error", "src": breaking.OFR_FSI_URL, **{c: [] for c in OFR_COLUMNS}}
    try:
        p = parse_ofr_columns(body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OFR FSI columns parse failed: %s", exc)
        return {"dates": [], "status": "error", "src": breaking.OFR_FSI_URL, **{c: [] for c in OFR_COLUMNS}}
    p.update(status=st, src=breaking.OFR_FSI_URL)
    return p


# ---------------------------------------------------------------------------- BIS SDMX CSV
def parse_bis_csv(body: bytes, key_col: str | None = None) -> dict:
    """SDMX-CSV -> {key: [(TIME_PERIOD, value)]} (key = key_col's value, or "_" for one series)."""
    text = body.decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or "TIME_PERIOD" not in rows[0] or "OBS_VALUE" not in rows[0]:
        raise ValueError("BIS csv: TIME_PERIOD / OBS_VALUE columns not found")
    out: dict[str, list] = {}
    for r in rows:
        raw = (r.get("OBS_VALUE") or "").strip()
        try:
            v = float(raw) if raw not in ("", "NaN") else None
        except ValueError:
            v = None
        out.setdefault(r.get(key_col, "_") if key_col else "_", []).append((r["TIME_PERIOD"].strip(), v))
    for k in out:
        out[k].sort()
    return out


def _bis(name: str, u: str, key_col: str | None = None) -> dict:
    body, st = fred_csv.download_cached(name, u, _TTL_BIS, validate=fred_csv.parses(lambda b: parse_bis_csv(b, key_col)))
    if body is None:
        return {"series": {}, "status": "error", "src": u}
    try:
        return {"series": parse_bis_csv(body, key_col), "status": st, "src": u}
    except Exception as exc:  # noqa: BLE001
        logger.warning("BIS %s parse failed: %s", name, exc)
        return {"series": {}, "status": "error", "src": u}


def fetch_bis() -> dict:
    return {"gli_total": _bis("bis_gli_usd_3p.csv", BIS_GLI_TOTAL),
            "gli_eme": _bis("bis_gli_usd_4t.csv", BIS_GLI_EME),
            "fx_all": _bis("bis_otc_fx_all.csv", BIS_FX_ALL),
            "fx_usd": _bis("bis_otc_fx_usd.csv", BIS_FX_USD),
            "cbpol": _bis("bis_cbpol.csv", BIS_CBPOL, key_col="REF_AREA")}


def fetch_all() -> dict:
    """Every input once; a source that raises becomes None (its block says error)."""
    out: dict = {}
    for key, fn in (("fred", fetch_fred), ("dxy", fetch_dxy), ("gold", fetch_gold), ("emb", fetch_emb),
                    ("ofr", fetch_ofr), ("bis", fetch_bis)):
        try:
            out[key] = fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning("dollar-watch source %s failed: %s", key, exc)
            out[key] = None
    return out
