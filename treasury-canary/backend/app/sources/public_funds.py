"""Public funds and pensions — the investor types Casey flagged (2026-10-15) as
the likely marginal buyer of AI-complex debt: not sovereigns but pension funds
and other large public pools of money. Everything free that can see them:

  GPIF        the world's largest pension fund publishes an ISIN-level list of
              its foreign bonds once a year (as of Mar 31, out early July):
              market value by security, JPY. We sum it by AI issuer and against
              the US Treasury line and the sheet total. Annual; one snapshot.
  MOF         monthb3 "trust accounts" = pension and other trust money run by
              trust banks (GPIF's and corporate DB plans' foreign-bond mandates
              settle here). Monthly, all foreign LT debt, all countries — no
              Treasuries-vs-corporates split. Fetched by sources/boj_mof.py.
  Z.1         US private DB/DC pension funds, state & local DB plans and the
              federal retirement funds: holdings and SAAR flows of corporate &
              foreign bonds, quarterly. Fetched by sources/z1.py.
  TIC         Foreign Official (central banks, sovereign funds, government
              pension schemes holding through official accounts) vs non-official
              purchases and positions of US corporate bonds, monthly, by custody
              country. Fetched by sources/tic.py.
  IMF PIP     Japan's holdings of US long-term debt by Japanese HOLDER sector
              (banks, insurers & pension funds, other financial, nonfinancial),
              semi-annual, private holders only (reserve assets excluded). The
              SDMX call is optional: when it fails the block carries null and a
              status, nothing else degrades.

This module does NOT re-implement the MOF / Z.1 / TIC fetchers: the helpers
below take their outputs (the dicts those modules return) and cut the pension
view out of them, so the metrics builder calls each fetcher once. Every series
says in `can_see` / `cannot_see` which investor types it does and does not
observe — no free source names the buyer of a specific bond.
"""
from __future__ import annotations

import io
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

from . import fred_csv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GPIF annual ISIN-level holdings
# ---------------------------------------------------------------------------
GPIF_URL = "https://www.gpif.go.jp/en/performance/73509681gpif/unyoujoukyou_2025_20_en_2.xlsx"
GPIF_PUBLISHED = "2026-07-03"       # GPIF topics page: "Portfolio holdings ... as of Mar 31, 2026"
_GPIF_TTL = 7 * 24 * 3600           # annual file; a weekly re-pull is plenty
_GPIF_MAX_BYTES = 50 * 1024 * 1024  # the real file is ~1.1 MB; refuse anything absurd

# key, display name, bucket, security-name prefixes (upper-cased, as GPIF prints
# them). Prefix match, not substring: "BLUE OWL TECHNOLOGY FINA" must not pick
# up Blue Owl Capital Corp / Blue Owl Credit Income / Blue Owl Finance LLC, and
# the Cayman "BROADCOM CRP" line is Broadcom.
GPIF_ISSUERS: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("oracle", "Oracle", "hyperscaler", ("ORACLE CORP",)),
    ("amazon", "Amazon", "hyperscaler", ("AMAZON.COM INC",)),
    ("alphabet", "Alphabet", "hyperscaler", ("ALPHABET INC",)),
    ("meta", "Meta Platforms", "hyperscaler", ("META PLATFORMS INC",)),
    ("microsoft", "Microsoft", "hyperscaler", ("MICROSOFT CORP",)),
    ("broadcom", "Broadcom", "chips", ("BROADCOM INC", "BROADCOM CRP")),
    ("nvidia", "Nvidia", "chips", ("NVIDIA CORP",)),
    ("coreweave", "CoreWeave", "neocloud", ("COREWEAVE INC",)),
    ("blue_owl_tech", "Blue Owl Technology Finance", "private_credit",
     ("BLUE OWL TECHNOLOGY FINA",)),
]
GPIF_UST_PREFIX = ("US TREASURY N/B",)
# the memo's §3f headline ("six hyperscalers + Nvidia = 0.044% of the book")
# is arithmetically the five hyperscaler names plus Nvidia; kept as its own
# figure so the published number is reproducible.
_MEMO_SUBSET = ("oracle", "amazon", "alphabet", "meta", "microsoft", "nvidia")

GPIF_BASIS = ("GPIF portfolio holdings by asset category, 'Foreign Bonds' sheet: market value "
              "in JPY per ISIN as of the fiscal year end; issuers matched on the printed "
              "security-name prefix; shares are of the foreign-bond sheet total. Annual "
              "snapshot — says what the fund HELD, not what it bought in the year")

_AS_OF_RE = re.compile(r"as of\s+([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s*(\d{4})", re.IGNORECASE)


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower() if s is not None else ""


def _as_of(cell) -> str | None:
    m = _AS_OF_RE.search(str(cell)) if cell is not None else None
    if not m:
        return None
    for fmt in ("%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _pick_sheet(names: list[str]) -> str | None:
    for n in names:
        k = _norm(n)
        if "foreign" in k and "bond" in k:
            return n
    return None


def parse_gpif(body: bytes) -> dict:
    """GPIF xlsx bytes -> {asof, n_lines, total_jpy, by_issuer: {key: (jpy, lines)},
    ust: (jpy, lines), columns}. Columns are located by header text ("ISIN",
    "Market Value"), not by position. Raises on an unrecognisable workbook."""
    import openpyxl  # production dep (Dockerfile + pyproject); imported lazily like the ACM parser

    wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        sheet = _pick_sheet(wb.sheetnames)
        if sheet is None:
            raise ValueError(f"GPIF: no foreign-bond sheet in {wb.sheetnames}")
        ws = wb[sheet]
        asof: str | None = None
        cols: dict[str, int] | None = None
        n = 0
        total = 0.0
        by_issuer: dict[str, list[float]] = {k: [0.0, 0] for k, *_ in GPIF_ISSUERS}
        ust = [0.0, 0]
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if cols is None:
                if i > 40:
                    raise ValueError("GPIF: header row (ISIN / Market Value) not found")
                if asof is None:
                    for c in row:
                        asof = _as_of(c)
                        if asof:
                            break
                hdr = {_norm(c): j for j, c in enumerate(row) if c is not None}
                isin = next((j for h, j in hdr.items() if h == "isin"), None)
                mv = next((j for h, j in hdr.items() if "market value" in h), None)
                name = next((j for h, j in hdr.items() if "name" in h), None)
                if isin is not None and mv is not None and name is not None:
                    cols = {"isin": isin, "name": name, "mv": mv}
                continue
            if len(row) <= max(cols.values()):
                continue
            isin_v, name_v, mv_v = row[cols["isin"]], row[cols["name"]], row[cols["mv"]]
            if not isinstance(isin_v, str) or len(isin_v.strip()) < 10 or not isinstance(mv_v, (int, float)):
                continue
            v = float(mv_v)
            n += 1
            total += v
            up = str(name_v or "").upper().strip()
            if up.startswith(GPIF_UST_PREFIX):
                ust[0] += v
                ust[1] += 1
                continue
            for key, _label, _bucket, prefixes in GPIF_ISSUERS:
                if up.startswith(prefixes):
                    by_issuer[key][0] += v
                    by_issuer[key][1] += 1
                    break
        if n == 0:
            raise ValueError("GPIF: no security rows parsed")
        return {"asof": asof, "sheet": sheet, "n_lines": n, "total_jpy": total,
                "by_issuer": {k: (v[0], int(v[1])) for k, v in by_issuer.items()},
                "ust": (ust[0], int(ust[1])), "columns": cols}
    finally:
        wb.close()


def _gpif_empty(status: str) -> dict:
    return {"asof": None, "published": GPIF_PUBLISHED, "unit": "JPY", "n_lines": None,
            "foreign_bonds_jpy_trn": None, "ai_issuers": [], "ai_issuers_total_jpy_bn": None,
            "ai_share_pct": None, "hyperscaler_plus_nvidia_jpy_bn": None,
            "hyperscaler_plus_nvidia_share_pct": None, "ust_jpy_trn": None, "ust_share_pct": None,
            "ust_lines": None, "basis": GPIF_BASIS, "src": GPIF_URL, "status": status,
            "read": None}


def fetch_gpif() -> dict:
    """The `gpif` sub-block: AI-issuer holdings (JPY bn, line counts), the US
    Treasury line and the sheet total, with shares. status ok/stale/error."""
    # validate = the parser: a re-laid-out or truncated workbook that would not
    # parse is never written over the last good copy (7-day TTL), so the stale
    # fallback stays recoverable
    body, st = fred_csv.download_cached(
        "gpif_holdings.xlsx", GPIF_URL, _GPIF_TTL,
        validate=lambda b: b[:2] == b"PK" and len(b) <= _GPIF_MAX_BYTES and fred_csv.parses(parse_gpif)(b))
    if body is None:
        return _gpif_empty("error")
    try:
        p = parse_gpif(body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("GPIF parse failed: %s", exc)
        return _gpif_empty("error")
    total = p["total_jpy"]
    issuers = []
    for key, label, bucket, _ in GPIF_ISSUERS:
        jpy, lines = p["by_issuer"][key]
        issuers.append({"key": key, "issuer": label, "bucket": bucket,
                        "jpy_bn": round(jpy / 1e9, 2), "lines": lines,
                        "share_pct": round(100.0 * jpy / total, 4) if total else None})
    ai_total = sum(p["by_issuer"][k][0] for k in p["by_issuer"])
    memo = sum(p["by_issuer"][k][0] for k in _MEMO_SUBSET)
    ust_jpy, ust_lines = p["ust"]
    out = _gpif_empty(st)
    out.update({
        "asof": p["asof"], "n_lines": p["n_lines"],
        "foreign_bonds_jpy_trn": round(total / 1e12, 3),
        "ai_issuers": issuers,
        "ai_issuers_total_jpy_bn": round(ai_total / 1e9, 2),
        "ai_share_pct": round(100.0 * ai_total / total, 3) if total else None,
        "hyperscaler_plus_nvidia_jpy_bn": round(memo / 1e9, 2),
        "hyperscaler_plus_nvidia_share_pct": round(100.0 * memo / total, 3) if total else None,
        "ust_jpy_trn": round(ust_jpy / 1e12, 3), "ust_lines": ust_lines,
        "ust_share_pct": round(100.0 * ust_jpy / total, 1) if total else None,
        "read": ("Passive, government-benchmarked: US Treasuries are about half of the foreign-bond "
                 "book and the AI issuers together a few hundredths of a percent — GPIF is not the "
                 "marginal corporate buyer, and an annual list cannot show what was bought when"),
    })
    return out


# ---------------------------------------------------------------------------
# IMF PIP (Portfolio Investment Positions by Counterpart Economy, ex-CPIS):
# Japan vs USA, long-term debt, by Japanese holder sector. Optional.
# ---------------------------------------------------------------------------
IMF_PIP_URL = "https://api.imf.org/external/sdmx/2.1/data/IMF.STA,PIP/JPN.....USA.?lastNObservations=3"
IMF_PIP_INDICATOR = "P_F3_L_P_USD"   # portfolio investment, debt securities, long-term, position, USD
_IMF_TTL = 7 * 24 * 3600
_IMF_MAX_BYTES = 20 * 1024 * 1024
# IMF codelist CL_SECTOR labels for the holder sectors Japan reports vs the USA
IMF_SECTOR_LABELS = {
    "S1": "All sectors (total, private holders; reserve assets excluded)",
    "S121": "Central bank (reserve assets are reported separately — this line is ~0)",
    "S122": "Deposit-taking corporations (banks)",
    "S12R": "Other financial corporations (S12QU + S12P)",
    "S12QU": "Insurance corporations and pension funds",
    "S12P": "Other financial institutions ex MFIs, insurers and pension funds (investment trusts, trust accounts)",
    "S13": "General government",
    "S1V": "Nonfinancial corporations, households and NPISH",
}
IMF_BASIS = ("IMF PIP (ex-CPIS) reporter-side positions: Japanese residents' holdings of US-issued "
             "long-term debt securities by Japanese holder sector, USD bn, semi-annual, counterpart "
             "sector S1 only (no Treasuries-vs-corporates split); excludes reserve assets, so it is "
             "a PRIVATE-holder view; ~6-9 month lag")


def parse_imf_pip(body: bytes, indicator: str = IMF_PIP_INDICATOR, freq: str = "S") -> dict:
    """SDMX 2.1 structure-specific XML -> {periods, sectors: {code: {label, values}}}.
    OBS_VALUE is in USD (the SCALE attribute is informational; the S1 total
    re-derives the verifier's $1,214.7bn for 2025-S2 only when read as USD),
    converted to $bn here. Raises on malformed XML."""
    root = ET.fromstring(body)
    series: dict[str, dict[str, float | None]] = {}
    periods: set[str] = set()
    for el in root.iter():
        if not el.tag.endswith("Series"):
            continue
        a = el.attrib
        if (a.get("INDICATOR") != indicator or a.get("ACCOUNTING_ENTRY", "A") != "A"
                or a.get("FREQUENCY") != freq or a.get("COUNTERPART_SECTOR", "S1") != "S1"):
            continue
        sector = a.get("SECTOR")
        if not sector:
            continue
        obs = series.setdefault(sector, {})
        for o in el:
            if not o.tag.endswith("Obs"):
                continue
            tp = o.attrib.get("TIME_PERIOD")
            raw = o.attrib.get("OBS_VALUE")
            if not tp:
                continue
            try:
                obs[tp] = None if raw in (None, "", "NaN") else round(float(raw) / 1e9, 3)
            except ValueError:
                obs[tp] = None
            periods.add(tp)
    if not series:
        raise ValueError(f"IMF PIP: no {indicator}/{freq} series in response")
    # the response carries dead series (last observation 2004-2012, no label): a
    # sector is live only if it prints in one of the two latest periods overall;
    # the axis is rebuilt from the live series so no None-padded 2002-2012 columns ship
    recent = sorted(periods)[-2:]
    live = {code: vals for code, vals in series.items()
            if any(vals.get(p) is not None for p in recent)}
    if not live:
        raise ValueError("IMF PIP: no series with a recent observation")
    axis = sorted({p for vals in live.values() for p, v in vals.items() if v is not None})
    return {"periods": axis,
            "sectors": {code: {"label": IMF_SECTOR_LABELS.get(code),
                               "values": [vals.get(p) for p in axis]}
                        for code, vals in live.items()},
            "dropped_sectors": sorted(set(series) - set(live))}


def fetch_imf_pip_japan_us() -> tuple[dict | None, str]:
    """(block | None, status). None means the optional call failed or parsed to
    nothing; the caller publishes null for the sub-block and the status."""
    # validate = the parser (an SDMX body without the <?xml declaration is still valid)
    body, st = fred_csv.download_cached(
        "imf_pip_jpn_usa.xml", IMF_PIP_URL, _IMF_TTL,
        validate=lambda b: b.lstrip()[:1] == b"<" and len(b) <= _IMF_MAX_BYTES and fred_csv.parses(parse_imf_pip)(b))
    if body is None:
        return None, "error"
    try:
        p = parse_imf_pip(body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("IMF PIP parse failed: %s", exc)
        return None, "error"
    latest = {}
    for code, s in p["sectors"].items():
        idx = next((i for i in range(len(s["values"]) - 1, -1, -1) if s["values"][i] is not None), None)
        latest[code] = None if idx is None else {"period": p["periods"][idx], "usd_bn": s["values"][idx]}
    total = latest.get("S1")
    return {
        "asof": total["period"] if total else (p["periods"][-1] if p["periods"] else None),
        "unit": "$bn", "frequency": "semi-annual", "indicator": IMF_PIP_INDICATOR,
        "total_usd_bn": total["usd_bn"] if total else None,
        "periods": p["periods"], "sectors": p["sectors"], "latest": latest,
        "leaf_sectors": [c for c in ("S121", "S122", "S12QU", "S12P", "S13", "S1V") if c in p["sectors"]],
        "dropped_sectors": p.get("dropped_sectors", []),
        "note": ("S1 = S121 + S122 + S12QU + S12P + S13 + S1V; S12R = S12QU + S12P and is NOT additive with "
                 "them; sectors with no observation in the two latest periods are dropped"),
        "basis": IMF_BASIS, "src": IMF_PIP_URL, "status": st,
    }, st


# ---------------------------------------------------------------------------
# Views cut from the sibling fetchers' outputs (no re-fetching)
# ---------------------------------------------------------------------------
def _last_n(vals: list, n: int) -> list:
    return list(vals[-n:]) if vals else []


def _latest(vals: list) -> float | None:
    for v in reversed(vals or []):
        if v is not None:
            return v
    return None


def trust_accounts_from_mof(mof: dict | None) -> dict:
    """Pension view of boj_mof.fetch_mof_by_investor_type(): trust accounts vs
    banks, life insurers and investment trusts, monthly JPY trn plus 12m sums."""
    from .boj_mof import sum_last  # the 12m rule shared with the Japan block (None if any month missing)

    keys = ("trust_accounts", "banks", "life", "inv_trusts", "all")
    out: dict = {"asof": None, "months": [], "unit": "JPY trn", "status": "error",
                 "basis": None, "src": None, "labels": None}
    for k in keys:
        out[k] = []
        out[f"{k}_12m"] = None
    if not mof or not mof.get("months"):
        return out
    out.update({"asof": mof.get("asof"), "months": list(mof["months"]), "status": mof.get("status", "error"),
                "basis": mof.get("basis"), "src": mof.get("src"),
                "labels": {k: (mof.get("labels") or {}).get(k) for k in keys}})
    for k in keys:
        out[k] = list(mof.get(k) or [])
        out[f"{k}_12m"] = mof.get(f"{k}_12m", sum_last(out[k]) if out[k] else None)
    return out


def pensions_from_z1(holders: dict | None) -> dict:
    """Pension sectors of z1.fetch_holders(): levels (FL, $bn) and SAAR flows
    (FA, $bn/yr) for private, state & local, federal and the Z.1 pension total,
    with the latest quarter and the last four flows. FA stays FA: nothing here
    is converted to a quarterly flow, so the FA/FU unit check in z1 still holds."""
    sectors = ("private", "state_local", "federal", "total")
    out: dict = {"asof": None, "quarters": [], "unit": "$bn (levels) / $bn SAAR (flows)",
                 "status": "error", "basis": None, "src": None, "units_consistent": None}
    for s in sectors:
        out[s] = {"level": [], "flow_saar": [], "level_latest": None, "flow_saar_latest": None,
                  "flow_saar_last4": []}
    if not holders or not holders.get("quarters"):
        return out
    pens = holders.get("pensions") or {}
    out.update({"asof": holders.get("asof"), "quarters": list(holders["quarters"]),
                "status": holders.get("status", "error"), "basis": holders.get("basis"),
                "src": (holders.get("src") or {}).get("fred_pattern"),
                "units_consistent": (holders.get("checks") or {}).get("units_consistent")})
    for s in sectors:
        lv = list((pens.get(s) or {}).get("level") or [])
        fl = list((pens.get(s) or {}).get("flow_saar") or [])
        out[s] = {"level": lv, "flow_saar": fl, "level_latest": _latest(lv),
                  "flow_saar_latest": _latest(fl), "flow_saar_last4": _last_n(fl, 4)}
    return out


def official_corp_from_tic(by_country: dict | None) -> dict:
    """Official vs non-official view of tic.fetch_by_country(): corporate-bond net
    purchases (12m) and positions, and the official share of foreign-held US
    corporates (official position / Grand Total position)."""
    out: dict = {"asof": None, "months": [], "unit": "$bn", "status": "error", "basis": None, "src": None,
                 "net_12m": None, "pos": None, "share_of_foreign_held_pct": None, "share_asof": None,
                 "non_official_net_12m": None, "non_official_pos": None, "grand_total_pos": None,
                 "official_corp_net": [], "non_official_corp_net": [], "official_treas_net_12m": None}
    if not by_country or not by_country.get("months"):
        return out
    aggs = by_country.get("aggregates") or {}
    off, non, gt = aggs.get("official") or {}, aggs.get("non_official") or {}, aggs.get("grand_total") or {}
    months = list(by_country["months"])
    # the share pairs official and Grand Total positions on the SAME month (the
    # last one where both print), never the latest of each independently
    off_pos, gt_pos, non_pos = (list(off.get("corp_pos") or []), list(gt.get("corp_pos") or []),
                                list(non.get("corp_pos") or []))
    i = next((j for j in range(min(len(off_pos), len(gt_pos), len(months)) - 1, -1, -1)
              if off_pos[j] is not None and gt_pos[j] is not None), None)
    pos, gpos = (off_pos[i], gt_pos[i]) if i is not None else (off.get("corp_pos_latest"), None)
    out.update({
        "asof": by_country.get("asof"), "months": months,
        "status": _worst([off.get("status"), non.get("status"), gt.get("status")]),
        "basis": by_country.get("basis"),
        "src": (by_country.get("src") or {}).get("fred_pattern"),
        "net_12m": off.get("corp_net_12m"), "pos": pos,
        "official_treas_net_12m": off.get("treas_net_12m"),
        "share_of_foreign_held_pct": round(100.0 * pos / gpos, 1) if i is not None and gpos else None,
        "share_asof": months[i] if i is not None else None,
        "non_official_net_12m": non.get("corp_net_12m"),
        "non_official_pos": (non_pos[i] if i is not None and i < len(non_pos) and non_pos[i] is not None
                             else non.get("corp_pos_latest")),
        "grand_total_pos": gpos,
        "official_corp_net": list(off.get("corp_net") or []),
        "non_official_corp_net": list(non.get("corp_net") or []),
        "label": ((by_country.get("labels") or {}).get("official")),
    })
    return out


def _worst(statuses: list) -> str:
    if any(s in (None, "error") for s in statuses):
        return "error"
    return "stale" if "stale" in statuses else "ok"


# ---------------------------------------------------------------------------
# The public_funds block
# ---------------------------------------------------------------------------
CAN_SEE = [
    "MOF trust accounts (monthly): pension and other trust money that Japanese trust banks run — "
    "GPIF's and corporate DB plans' foreign-bond mandates settle here; all foreign LT debt, all "
    "countries, net purchases",
    "Z.1 pension sectors (quarterly): US private DB/DC pension funds, state & local DB plans and "
    "federal retirement funds — holdings and SAAR flows of corporate & foreign bonds",
    "GPIF (annual, as of Mar 31): the ISIN-level holdings of the largest pension fund in the world, "
    "including the AI issuers and the US Treasury line",
    "TIC Foreign Official (monthly): central banks, sovereign wealth funds and government pension "
    "schemes that hold through official accounts — US corporate bond purchases and positions, "
    "attributed by custody country",
    "IMF PIP (semi-annual, optional): Japanese holder sectors — banks, insurers & pension funds, other "
    "financial, nonfinancial — of US long-term debt, private holders only",
]
CANNOT_SEE = [
    "The buyer of any specific bond: no free source attributes an issuer's bonds to a fund, a "
    "country or an investor type, and deal allocation statistics are not published",
    "A Treasuries-vs-corporates split inside MOF trust accounts, Z.1 'corporate & foreign bonds' "
    "or IMF PIP (only BoJ BoP and TIC separate sovereign from other debt, and neither by investor)",
    "Non-Japanese public pension funds at issuer level — Dutch, Canadian, Korean, Australian and "
    "most Nordic funds publish no machine-readable bond lists (AP3 is a semi-annual PDF; NBIM "
    "needs a Snowflake account)",
    "Gulf and Chinese reserve managers and sovereign funds: TIC Official aggregates them without a "
    "country split and IMF PIP excludes reserve assets",
    "Japanese life insurers, Norinchukin and Japan Post at issuer level — only aggregate LIAJ "
    "balances and the MOF 'life insurers' flow line",
    "Pension money routed through external managers domiciled in Luxembourg, Ireland or the Cayman "
    "Islands — TIC books it to the custody centre, not the beneficial owner",
    "Flows inside the year for GPIF and AP3: annual and semi-annual lists show holdings, not purchases",
]
BASIS = ("Pension and public-fund buying is visible only through MOF trust accounts (monthly, all "
         "foreign LT debt), Z.1 pension sectors (quarterly, FA = SAAR), TIC Foreign Official (monthly, "
         "custody-attributed) and annual fund lists (GPIF). Nothing here names the buyer of a bond")


def build_block(mof: dict | None = None, holders: dict | None = None, by_country: dict | None = None,
                gpif: dict | None = None, imf: dict | None = None, imf_status: str | None = None) -> dict:
    """Assemble the payload's `public_funds` block from the pieces. Each input
    may be None (the block then carries nulls and the status says why)."""
    trust = trust_accounts_from_mof(mof)
    pens = pensions_from_z1(holders)
    off = official_corp_from_tic(by_country)
    gpif = gpif if gpif is not None else _gpif_empty("error")
    return {
        "asof": {"mof": trust["asof"], "z1": pens["asof"], "gpif": gpif.get("asof"), "tic": off["asof"],
                 "imf_pip": imf.get("asof") if imf else None},
        "trust_accounts_12m_jpy_trn": trust["trust_accounts_12m"],
        "mof_by_type": trust,
        "z1_pensions": pens,
        "gpif": gpif,
        "tic_official_corp": off,
        "imf_pip_japan": imf,
        "can_see": list(CAN_SEE),
        "cannot_see": list(CANNOT_SEE),
        "basis": BASIS,
        "src": {"gpif": GPIF_URL, "imf_pip": IMF_PIP_URL, "mof_monthb3": trust["src"],
                "z1_fred_pattern": pens["src"], "tic_fred_pattern": off["src"]},
        "status": {"gpif": gpif.get("status", "error"),
                   "imf_pip": imf_status or (imf.get("status") if imf else "error"),
                   "mof": trust["status"], "z1": pens["status"], "tic": off["status"]},
    }


def fetch_block(mof: dict | None = None, holders: dict | None = None,
                by_country: dict | None = None) -> dict:
    """Fetch GPIF and IMF PIP here; take the MOF / Z.1 / TIC dicts from the
    caller when it already has them (the route fetches each once for the Japan,
    holders and foreign-bid blocks), else fetch them through their own modules."""
    if mof is None:
        from .boj_mof import fetch_mof_by_investor_type
        mof = fetch_mof_by_investor_type()
    if holders is None:
        from .z1 import fetch_holders
        holders = fetch_holders()
    if by_country is None:
        from .tic import fetch_by_country
        by_country = fetch_by_country()
    # a crash in one optional fetch (unwritable cache dir, corrupt cache file)
    # must leave the MOF / Z.1 / TIC pension views intact
    try:
        gpif = fetch_gpif()
    except Exception as exc:  # noqa: BLE001
        logger.warning("GPIF fetch failed: %s", exc)
        gpif = _gpif_empty("error")
    try:
        imf, imf_status = fetch_imf_pip_japan_us()
    except Exception as exc:  # noqa: BLE001
        logger.warning("IMF PIP fetch failed: %s", exc)
        imf, imf_status = None, "error"
    return build_block(mof, holders, by_country, gpif, imf, imf_status)
