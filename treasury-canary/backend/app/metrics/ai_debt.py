"""AI-debt tab (studies/ai_debt_flows/BUILD.md, phase 1): assembles the
GET /ai-debt payload from the keyless sources.

Context, not a signal: nothing here is pre-registered, graded or alerted on;
status language is "watch". The module is two layers so the assembly can be
tested offline on the source builders' fixtures:

  fetch_inputs()   calls every source ONCE (the public-funds block reuses the
                   MOF / Z.1 / TIC dicts the Japan, holders and foreign-bid
                   blocks already fetched) and never raises — a source that
                   blows up is None and its block says "error".
  build_ai_debt()  pure: inputs -> the spec's payload. Every block carries a
                   status (ok | stale | error, the worst of its parts), a
                   basis string, source URLs and its as-of; missing data is
                   None, never 0; the honesty list is the spec's text verbatim.

Units are stated per block: $bn (TIC, Z.1, MSPD, TREAST), JPY trn (BoJ, MOF),
% (yields, term premia), percentage points (OAS, EBP, BAA10Y), index (OFR
FSI). Z.1 flows stay SAAR — nothing is divided by four here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..sources import ai_debt_seed as seed_mod
from ..sources import boj_mof, breaking, edgar_debt, fred_csv, public_funds, tic, treasury_supply, z1

logger = logging.getLogger(__name__)

BLOCKS = ("issuance", "holders", "foreign_bid", "japan", "public_funds", "crowding", "breaking")

# BUILD.md "Honesty box text (ship verbatim, edit only for accuracy)" — one
# sentence per entry, unchanged. Accuracy additions follow in HONESTY_EXTRA.
HONESTY = [
    "Scoping rev 1, not a study: nothing pre-registered or graded.",
    "Tally = gross issuance at pricing, not net of redemptions; non-USD legs at trade-date FX; "
    "~20% of tally dollars rest on search snippets pending filings; new EDGAR filings are "
    "auto-extracted and NOT in the tally until reviewed.",
    "TIC attributes by custody country, not beneficial owner; no free source names the buyer of "
    "a specific bond; GPIF/AP lists are annual; pension and public-fund buying is visible only "
    "via MOF trust accounts, Z.1 pension sectors and annual fund lists.",
    "FRED serves 3 years of ICE OAS history; CDS and single-name prices are dated press prints, "
    "not a feed.",
    "Nothing here is a forecast.",
]
def _bdc_nav_honesty() -> str:
    """Derived from breaking.BDC_NAV (the source of truth) so the honesty box
    can never contradict the table beneath it when a NAV is added or re-dated."""
    sourced = [(t, r) for t, r in breaking.BDC_NAV.items() if r.get("nav") is not None]
    unsourced = [t for t in breaking.BDC_TICKERS if breaking.BDC_NAV.get(t, {}).get("nav") is None]
    line = "BDC NAVs: " + ", ".join(f"{t} ({str(r.get('nav_form') or 'filing').split()[0]}, as of {r.get('nav_asof')})"
                                    for t, r in sourced)
    if unsourced:
        names = unsourced[0] if len(unsourced) == 1 else ", ".join(unsourced[:-1]) + " and " + unsourced[-1]
        line += (f"; {names} " + ("is" if len(unsourced) == 1 else "are")
                 + " not yet sourced to a filing, so their NAV and price/NAV are null.")
    else:
        line += "."
    return line


HONESTY_EXTRA = [
    _bdc_nav_honesty(),
    "GPIF list is annual as of 2026-03-31: holdings, not purchases. IMF PIP excludes reserve "
    "assets (private holders only). MOVE via Yahoo, cross-checked against investing.com.",
    "Z.1 rest-of-world and households levels are derived from partition identities (FRED does "
    "not mirror those lines); flows are SAAR, never quarterly dollars; the FA/FU ratio is "
    "published as the unit check.",
    "Net Treasury supply is the change in MSPD marketable outstanding, gross of Fed holdings; "
    "the tally over it is gross issuance over net supply, stated in each row's basis.",
]
NOTE = ("Context, not a signal: nothing on this tab is pre-registered or graded and no alert "
        "fires from it. Status language is 'watch'.")

ISSUANCE_BASIS = ("Gross issuance at pricing, $bn; non-USD legs at trade-date FX (fx_basis per row); "
                  "seed = studies/ai_debt_flows deals.csv frozen as rev 1; EDGAR filings since the "
                  "seed's last deal are auto-extracted and NOT in the tally")
JAPAN_BASIS = ("BoJ BoP: residents' net purchases of US long-term debt, JPY trn, sovereign = government "
               "+ agency + local government (MOF footnote), non-sovereign = residual; MOF monthb3: net "
               "purchases of FOREIGN long-term debt by investor type, all countries, JPY trn; MOF "
               "week.csv: weekly, no investor split; MOF JGB par curve, %")
CROWDING_BASIS = ("MSPD marketable Treasury debt outstanding by class (gross of Fed holdings) and its "
                  "change by fiscal / calendar year, $bn; Kim-Wright 10y term premium primary, ACM 10y "
                  "optional, %; DGS10 / DGS30 / T10YIE %; Fed TREAST $bn; FiscalData auction stats "
                  "(no when-issued field, so no tail)")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def worst(statuses) -> str:
    """"error" if any part errored or is missing, else "stale" if any part is
    stale, else "ok". An empty list is "error" (nothing loaded)."""
    seen = set(statuses)
    if not seen or "error" in seen or None in seen:
        return "error"
    return "stale" if "stale" in seen else "ok"


def _safe(fn, *args, **kwargs):
    """Call a source; a raised exception becomes None (the block says error)."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — a crashed source must not take the tab down
        logger.warning("AI-debt source %s failed: %s", getattr(fn, "__name__", fn), exc)
        return None


def _last(vals) -> float | None:
    for v in reversed(vals or []):
        if v is not None:
            return v
    return None


def _reading(block: dict | None, note: str | None = None) -> dict | None:
    """treasury_supply/fred-style {dates, values, latest, asof, ...} -> the tab's
    reading shape {latest, asof, series: {dates, values}, unit, src, basis, status}."""
    if not block:
        return None
    return {"latest": block.get("latest"), "asof": block.get("asof"), "unit": block.get("unit"),
            "src": block.get("src"), "basis": block.get("basis"), "status": block.get("status") or "error",
            "series": {"dates": list(block.get("dates") or []), "values": list(block.get("values") or [])},
            "note": note}


def _fmt(v: float | None, dp: int = 2) -> str:
    return "n/a" if v is None else f"{v:+.{dp}f}"


# ---------------------------------------------------------------------------
# fetch (once per source, sequential: the CSLT zip and the ACM xls never overlap)
# ---------------------------------------------------------------------------
def fetch_inputs() -> dict:
    """Every source once. Order matters for memory on a small instance: the
    TIC CSLT zip (9 MB streamed) and the ACM workbook (10 MB) are fetched one
    after the other, never concurrently. Cold ~45-60 s; each source has its
    own disk cache (12h FRED, 24h files, 3d CSLT, 7d GPIF/IMF)."""
    seed = _safe(seed_mod.load_seed)
    poll = _safe(edgar_debt.poll_detailed)
    holders = _safe(z1.fetch_holders)
    by_country = _safe(tic.fetch_by_country)
    bills = _safe(tic.bills_inclusive)
    boj = _safe(boj_mof.fetch_boj_us_ltdebt)
    mof = _safe(boj_mof.fetch_mof_by_investor_type)
    weekly = _safe(boj_mof.fetch_mof_weekly)
    jgb = _safe(boj_mof.fetch_jgb_curve)
    # GPIF and IMF are fetched here, once each, and the block is ASSEMBLED from the
    # dicts already in hand: a MOF / Z.1 / TIC fetcher that raised (None above) is
    # never re-fetched through public_funds, and never takes GPIF / IMF down with it
    gpif = _safe(public_funds.fetch_gpif)
    imf = _safe(public_funds.fetch_imf_pip_japan_us)
    pf = _safe(public_funds.build_block, mof, holders, by_country, gpif,
               imf[0] if imf else None, imf[1] if imf else "error")
    mspd = _safe(treasury_supply.fetch_mspd)
    term_premium = _safe(treasury_supply.fetch_term_premium)
    yields = _safe(treasury_supply.fetch_yields)
    auctions = _safe(treasury_supply.fetch_auctions)
    brk = _safe(breaking.fetch_block)
    return {"seed": seed, "poll": poll, "holders": holders, "by_country": by_country, "bills": bills,
            "boj": boj, "mof": mof, "weekly": weekly, "jgb": jgb, "public_funds": pf, "mspd": mspd,
            "term_premium": term_premium, "yields": yields, "auctions": auctions, "breaking": brk}


# ---------------------------------------------------------------------------
# issuance
# ---------------------------------------------------------------------------
def _vs_treasury(seed: dict, net: dict | None) -> dict | None:
    """{FY2026: {ai_bn, net_marketable_ust_bn, pct, basis, from, to, complete}, CY2025: ...}
    — tally dollars priced inside each MSPD window over the change in marketable
    outstanding. Numerator gross (all currencies at FX), denominator net."""
    if not net:
        return None
    inc = seed_mod.included(seed)
    first_year = min(int(d["date"][:4]) for d in inc) if inc else 9999
    out: dict = {}
    for kind, book in (("FY", net.get("fy") or {}), ("CY", net.get("cy") or {})):
        for year, row in sorted(book.items()):
            if int(year) < first_year or row.get("net_marketable") is None:
                continue
            lo, hi = row["from"], row["to"]
            ai = round(sum(d["size_usd_bn"] for d in inc if lo < d["date"] <= hi), 2)
            nm = row["net_marketable"]
            out[f"{kind}{year}"] = {
                "ai_bn": ai, "net_marketable_ust_bn": nm, "coupons_ust_bn": row.get("coupons"),
                "pct": round(100.0 * ai / nm, 1) if nm else None,
                "pct_of_coupons": (round(100.0 * ai / row["coupons"], 1) if row.get("coupons") else None),
                "from": lo, "to": hi, "complete": row.get("complete"),
                "basis": (f"numerator GROSS: AI-complex issuance priced {lo} < date <= {hi}, all currencies "
                          f"at trade-date FX; denominator NET: change in MSPD marketable outstanding (net "
                          f"supply, gross of Fed holdings); "
                          f"{'window complete' if row.get('complete') else 'window runs to the latest month'}"),
            }
    return out


def issuance_block(seed: dict | None, poll: dict | None, net: dict | None) -> dict:
    filings_status = poll.get("status", "error") if poll else "error"
    meta = ({k: poll.get(k) for k in ("since", "asof", "checked", "failed", "stale", "name_mismatch",
                                      "doc_failed", "doc_access_error", "rate_limited", "status")} if poll else
            {"since": None, "asof": None, "checked": [], "failed": [], "stale": [], "name_mismatch": [],
             "doc_failed": None, "doc_access_error": None, "rate_limited": None, "status": "error"})
    base = {"status": "error", "status_detail": {"seed": "error", "new_filings": filings_status},
            "seed_rev": None, "asof": None, "basis": ISSUANCE_BASIS, "unit": "$bn",
            "deals": None, "totals_by_year": None, "by_bucket_year": None, "by_rating_year": None,
            "by_month": None, "by_month_rating": None, "share": None, "vs_treasury": None,
            "verif": None, "buckets": None, "rating_buckets": None, "flag_rules": None,
            "denominators": None, "n_included": None, "total_usd_bn": None, "last_deal_date": None,
            "new_filings": list(poll["filings"]) if poll else None, "new_filings_meta": meta,
            "src": {"seed": None, "edgar_submissions": "https://data.sec.gov/submissions/CIK##########.json"}}
    if not seed:
        return base
    base.update({
        "status": worst(["ok", filings_status]),
        "status_detail": {"seed": "ok", "new_filings": filings_status},
        "seed_rev": seed["seed_rev"], "asof": seed["asof"], "basis": seed.get("basis") or ISSUANCE_BASIS,
        "deals": list(seed["deals"]),
        "totals_by_year": seed_mod.totals_by_year(seed),
        "by_bucket_year": seed_mod.by_bucket_year(seed),
        "by_rating_year": seed_mod.by_rating_year(seed),
        "by_month": seed_mod.by_month(seed),
        "by_month_rating": seed_mod.by_month(seed, key="rating_bucket"),
        "share": seed_mod.hyperscaler_usd_share(seed),
        "vs_treasury": _vs_treasury(seed, net),
        "verif": seed_mod.verif_mix(seed),
        "buckets": list(seed["buckets"]), "rating_buckets": list(seed["rating_buckets"]),
        "flag_rules": dict(seed["flag_rules"]),
        "denominators": seed_mod.share_denominators(seed),
        "n_included": seed["n_included"], "total_usd_bn": seed["total_usd_bn"],
        "last_deal_date": seed["last_deal_date"],
    })
    base["src"]["seed"] = (seed.get("sources") or {}).get("C-DEALS")
    return base


# ---------------------------------------------------------------------------
# who holds US corporates (Z.1)
# ---------------------------------------------------------------------------
def holders_block(h: dict | None) -> dict:
    if not h or not h.get("quarters"):
        return {"status": "error", "asof": None, "unit": "$bn", "basis": z1.BASIS, "z1": None,
                "note": "Z.1 holder data not loaded this run (FRED keyless mirrors)",
                "src": {"fred_pattern": fred_csv.url("BOGZ1FL<sector>3063005Q")}}
    q = h["quarters"]
    checks = h.get("checks") or {}
    pens = {}
    for key, cell in (h.get("pensions") or {}).items():
        lv, fl = cell.get("level") or [], cell.get("flow_saar") or []
        pens[key] = {"level": lv[-1] if lv else None, "flow_saar": fl[-1] if fl else None,
                     "asof": h["asof"], "flow_saar_last4": fl[-4:], "level_series": lv, "flow_saar_series": fl}
    labels = {s["key"]: s["label"] for s in h.get("sectors") or []}
    derived = {s["key"] for s in h.get("sectors") or [] if s.get("derived_level")}
    units = checks.get("units_consistent")
    gap = (checks.get("partition_gap_pct") or [None])[-1]
    nfc = h.get("nfc_issuance") or {}
    unit_checks = {k: checks.get(k) for k in ("fa_over_fu_latest", "fa_over_fu_4q", "units_consistent")}
    unit_checks["partition_gap_pct_latest"] = gap
    note = (f"Z.1 L.213/F.213 via FRED, corporate & foreign bonds, $bn; levels end-{h['asof']}, flows SAAR "
            f"($bn per year, NOT quarterly dollars), last four quarters {q[-4:][0]}..{q[-1]}. Unit check: FA/FU "
            f"latest {checks.get('fa_over_fu_latest')}, 4q {checks.get('fa_over_fu_4q')} "
            f"({'consistent' if units else 'INCONSISTENT' if units is False else 'n/a'}); partition gap "
            f"{gap}% of the all-sectors total. Derived (FRED does not mirror the line): "
            f"{', '.join(sorted(derived)) or 'none'}. Rest of world = foreign holders.")
    return {
        "status": h.get("status", "error"),
        "asof": h["asof"], "unit": "$bn", "basis": h.get("basis") or z1.BASIS,
        "z1": {
            "quarters": list(q),
            "levels": {k: (v[-1] if v else None) for k, v in (h.get("levels") or {}).items()},
            "levels_series": {k: list(v) for k, v in (h.get("levels") or {}).items()},
            "flows_saar_last4": {k: list(v[-4:]) for k, v in (h.get("flows_saar") or {}).items()},
            "flows_quarters": list(q[-4:]),
            "flows_saar_series": {k: list(v) for k, v in (h.get("flows_saar") or {}).items()},
            "flows_unadj_all_sectors": list((h.get("flows_unadj") or {}).get("all_sectors") or []),
            "pensions": pens,
            "labels": labels, "sectors": list(h.get("sectors") or []), "derived": dict(h.get("derived") or {}),
            "checks": unit_checks,
            "nfc_issuance": {"saar_latest": _last(nfc.get("saar")), "saar_ex_reits_latest": _last(nfc.get("saar_ex_reits")),
                             "unadj_latest": _last(nfc.get("unadj")), "quarter": h["asof"],
                             "saar_series": list(nfc.get("saar") or []), "unadj_series": list(nfc.get("unadj") or []),
                             "codes": dict(nfc.get("codes") or {}), "unit": "$bn (SAAR unless 'unadj')",
                             "src": (h.get("src") or {}).get("nfc_issuance_saar")},
            # a fetchable link (the all-sectors level); the per-sector pattern lives in src_detail
            "src": (h.get("src") or {}).get("all_sectors_level") or (h.get("src") or {}).get("fred_pattern"),
            "src_detail": dict(h.get("src") or {}),
        },
        "note": note,
        "src": dict(h.get("src") or {}),
    }


# ---------------------------------------------------------------------------
# foreign bid by country (TIC)
# ---------------------------------------------------------------------------
_SPARK = 24   # months of history behind each table row's sparkline


def _tic_row(e: dict) -> dict:
    return {"key": e.get("key"), "name": e.get("name"), "code": e.get("code"),
            "custody_centre": bool(e.get("custody_centre", False)), "label": e.get("label"),
            "treas_net_12m": e.get("treas_net_12m"), "corp_net_12m": e.get("corp_net_12m"),
            "treas_pos": e.get("treas_pos_latest"), "corp_pos": e.get("corp_pos_latest"),
            "corp_share_of_lt": e.get("corp_share_of_lt_pct"),
            "treas_spark": list((e.get("treas_net") or [])[-_SPARK:]),
            "corp_spark": list((e.get("corp_net") or [])[-_SPARK:]),
            "status": e.get("status", "error")}


def foreign_block(bc: dict | None, bills: dict | None) -> dict:
    fred_status = bc.get("status", "error") if bc else "error"
    cslt_status = bills.get("status", "error") if bills else "error"
    out: dict = {"status": worst([fred_status, cslt_status]),
                 "status_detail": {"fred_tic": fred_status, "cslt_bills": cslt_status},
                 "asof": None, "unit": "$bn", "basis": tic.BASIS_LT, "countries": None, "aggregates": None,
                 "series": None, "labels": dict(tic.LABELS), "bills_inclusive": None,
                 "src": fred_csv.url("FORLT{TREAS|CORP}{NET|POS}<code>"),
                 "src_detail": {"cslt": tic.CSLT_URL}}
    if bc and bc.get("months"):
        aggs = bc.get("aggregates") or {}
        out.update({
            "asof": bc.get("asof"), "basis": bc.get("basis") or tic.BASIS_LT,
            "countries": [_tic_row(c) for c in bc.get("countries") or []],
            "aggregates": [_tic_row(aggs[k]) for k in ("grand_total", "all_countries", "official", "non_official") if k in aggs],
            "series": {"months": list(bc["months"]),
                       **{k: {"treas": list(aggs[k].get("treas_net") or []), "corp": list(aggs[k].get("corp_net") or []),
                              "status": aggs[k].get("status", "error")}
                          for k in ("grand_total", "official", "non_official", "all_countries") if k in aggs},
                       **{c["key"]: {"treas": list(c.get("treas_net") or []), "corp": list(c.get("corp_net") or []),
                                     "status": c.get("status", "error")}
                          for c in bc.get("countries") or [] if c.get("key") == "japan"}},
            "labels": dict(bc.get("labels") or tic.LABELS),
        })
        out["src_detail"].update(bc.get("src") or {})
    if bills:
        jp, ac, gt = bills.get("japan") or {}, bills.get("all_countries") or {}, bills.get("grand_total") or {}
        out["bills_inclusive"] = {
            "japan_12m": jp.get("all_maturities_12m"), "japan_lt_12m": jp.get("lt_12m"),
            "all_12m": ac.get("all_maturities_12m"), "all_lt_12m": ac.get("lt_12m"),
            "grand_total_12m": gt.get("all_maturities_12m"), "grand_total_lt_12m": gt.get("lt_12m"),
            "labels": {"all": jp.get("all_label") or "Treasuries of all maturities (bills included)",
                       "lt": jp.get("lt_label") or "long-term Treasuries only (bills excluded)",
                       "all_countries": (bills.get("labels") or {}).get("all_countries"),
                       "grand_total": (bills.get("labels") or {}).get("grand_total")},
            "asof": bills.get("asof"), "window_months": bills.get("window_months"), "unit": "$bn",
            "note": bills.get("note"), "months": list(bills.get("months") or []),
            "series": dict(bills.get("series") or {}),
            "src": bills.get("src") or tic.CSLT_URL, "status": cslt_status,
        }
    return out


# ---------------------------------------------------------------------------
# Japan
# ---------------------------------------------------------------------------
_MOF_SHORT = {"banks": "banks", "trust_banks_banking": "trust banks (banking accounts)",
              "trust_accounts": "trust accounts (pension money)", "fin_instruments": "financial instruments firms",
              "life": "life insurers", "nonlife": "non-life insurers", "inv_trusts": "investment trusts",
              "others": "others"}


def _mof_split_clause(mof: dict | None) -> str:
    """Who sold and who bought over 12 months across ALL MOF investor groups —
    the largest seller, the largest buyer, and every other net buyer named, so
    the text never claims 'the only' buyer while another group was positive."""
    if not mof:
        return ""
    groups = {k: mof.get(f"{k}_12m") for k in boj_mof.MOF_INVESTOR_HEADERS if k != "all"}
    groups = {k: v for k, v in groups.items() if v is not None}
    buyers = {k: v for k, v in groups.items() if v > 0}
    sellers = {k: v for k, v in groups.items() if v < 0}
    if not buyers or not sellers:
        return ""
    top_s = min(sellers, key=sellers.get)
    top_b = max(buyers, key=buyers.get)
    others = [_MOF_SHORT.get(k, k) for k in sorted(buyers, key=buyers.get, reverse=True) if k != top_b]
    return (f" and the MOF split puts the largest selling with {_MOF_SHORT.get(top_s, top_s)} "
            f"({_fmt(sellers[top_s])}) and the largest buying with {_MOF_SHORT.get(top_b, top_b)} "
            f"({_fmt(buyers[top_b])})"
            + (f", alongside {', '.join(others)}" if others else " — the only net-buying group"))


def japan_read(boj: dict | None, mof: dict | None, bills: dict | None, jp_row: dict | None) -> str:
    """The verdict text, derived from the signs that actually loaded (the
    memo's reading was 'repatriation, not substitution'); says so when the
    inputs are missing instead of repeating the memo. Every sign pattern of
    (sovereign_12m, nonsovereign_12m) has its own explicit sentence."""
    parts: list[str] = []
    sov = boj.get("sovereign_12m") if boj else None
    non = boj.get("nonsovereign_12m") if boj else None
    tot = boj.get("total_12m") if boj else None
    if tot is not None:
        parts.append(f"BoJ BoP, 12m to {boj['asof']}: Japanese residents' net purchases of US long-term "
                     f"debt {_fmt(tot)} JPY trn = sovereign {_fmt(sov)} + non-sovereign (~corporate) {_fmt(non)}.")
    bj = (bills or {}).get("japan") or {}
    if bj.get("all_maturities_12m") is not None:
        corp = jp_row.get("corp_net_12m") if jp_row else None
        parts.append(f"TIC, 12m to {bills['asof']}: Japan net Treasuries {_fmt(bj.get('lt_12m'), 1)} $bn "
                     f"long-term only vs {_fmt(bj['all_maturities_12m'], 1)} $bn including bills"
                     + (f"; US corporate bonds {_fmt(corp, 1)} $bn" if corp is not None else "") + ".")
    banks = mof.get("banks_12m") if mof else None
    trust = mof.get("trust_accounts_12m") if mof else None
    if mof and mof.get("all_12m") is not None:
        parts.append(f"MOF, 12m to {mof['asof']}, foreign long-term debt (all countries) by investor: all "
                     f"{_fmt(mof.get('all_12m'))}; banks {_fmt(banks)}; life insurers {_fmt(mof.get('life_12m'))}; "
                     f"trust accounts (pension money) {_fmt(trust)}; investment trusts "
                     f"{_fmt(mof.get('inv_trusts_12m'))} JPY trn.")
    if sov is None or non is None:
        parts.append("Read: not evaluable this run — the BoJ sovereign / non-sovereign split did not load.")
    elif sov < 0 and non >= 0 and abs(non) < abs(sov):
        parts.append("Read: repatriation, not substitution — Japan is selling US sovereign debt while the "
                     "non-sovereign residual is small" + _mof_split_clause(mof) + ". "
                     + ("Consistent with pension and public funds, not the sovereign, being the marginal "
                        "buyer of foreign debt; " if trust is not None and trust > 0 else "")
                     + "no free source names the buyer of a specific bond.")
    elif sov < 0 and non >= abs(sov):
        parts.append("Read: the non-sovereign residual now matches or exceeds the sovereign selling — a "
                     "substitution reading would need issuer-level allocation data this tab does not have.")
    elif sov >= 0 and non >= 0:
        parts.append("Read: Japan is a net buyer of both US sovereign and non-sovereign debt over 12 months; "
                     "no rotation in the BoJ data.")
    elif sov >= 0 and non < 0:
        parts.append("Read: Japan is a net buyer of US sovereign debt and a net seller of non-sovereign "
                     "(~corporate) debt over 12 months — the opposite of a rotation into corporates.")
    else:  # sov < 0 and non < 0
        parts.append("Read: Japan is a net seller of both US sovereign and non-sovereign debt over 12 months; "
                     "repatriation across the board, not substitution.")
    return " ".join(parts)


def japan_block(boj: dict | None, mof: dict | None, weekly: dict | None, jgb: dict | None,
                bills: dict | None, jp_row: dict | None) -> dict:
    s_boj = boj.get("status", "error") if boj else "error"
    s_mof = mof.get("status", "error") if mof else "error"
    s_wk = weekly.get("status", "error") if weekly else "error"
    s_jgb = jgb.get("status", "error") if jgb else "error"
    out: dict = {"status": worst([s_boj, s_mof, s_wk, s_jgb]),
                 "status_detail": {"boj": s_boj, "mof_by_type": s_mof, "mof_weekly": s_wk, "jgb": s_jgb},
                 "basis": JAPAN_BASIS, "boj": None, "mof_by_type": None, "mof_weekly": None, "jgb": None,
                 "read": japan_read(boj, mof, bills, jp_row),
                 "src": {"boj": boj_mof.BOJ_URL, "sovereign_definition": boj_mof.MOF_SOV_DEF_URL,
                         "mof_monthb3": boj_mof.MOF_MONTHB3_URL, "mof_week": boj_mof.MOF_WEEK_URL,
                         "jgb": boj_mof.MOF_JGB_ALL_URL, "jgb_current_month": boj_mof.MOF_JGB_CUR_URL}}
    if boj:
        out["boj"] = {"months": list(boj.get("months") or []), "total": list(boj.get("total") or []),
                      "sovereign": list(boj.get("sovereign") or []), "nonsovereign": list(boj.get("nonsovereign") or []),
                      "rolling_12m": {k: boj_mof.rolling_12m(boj.get(k) or []) for k in ("total", "sovereign", "nonsovereign")},
                      "sum_12m": {k: boj.get(f"{k}_12m") for k in ("total", "sovereign", "nonsovereign")},
                      "unit": boj.get("unit", "JPY trn"), "asof": boj.get("asof"), "basis": boj.get("basis"),
                      "series": dict(boj.get("series") or {}), "src": (boj.get("src") or {}).get("boj"),
                      "src_detail": dict(boj.get("src") or {}), "status": s_boj}
    if mof:
        keys = [k for k in boj_mof.MOF_INVESTOR_HEADERS if k in mof]
        out["mof_by_type"] = {"months": list(mof.get("months") or []),
                              **{k: list(mof.get(k) or []) for k in keys},
                              "sum_12m": {k: mof.get(f"{k}_12m") for k in keys},
                              "rolling_12m": {k: boj_mof.rolling_12m(mof.get(k) or []) for k in keys},
                              "labels": dict(mof.get("labels") or boj_mof.MOF_INVESTOR_LABELS),
                              "column_map": dict(mof.get("column_map") or {}),
                              "unit": mof.get("unit", "JPY trn"), "asof": mof.get("asof"), "basis": mof.get("basis"),
                              "src": mof.get("src"), "status": s_mof}
    if weekly:
        out["mof_weekly"] = {"weeks": list(weekly.get("weeks") or []), "net": list(weekly.get("lt_debt_net") or []),
                             "equity_net": list(weekly.get("equity_net") or []),
                             "st_debt_net": list(weekly.get("st_debt_net") or []),
                             "unit": weekly.get("unit", "JPY trn"), "asof": weekly.get("asof"),
                             "basis": weekly.get("basis"), "src": weekly.get("src"), "status": s_wk}
    if jgb:
        out["jgb"] = {"dates": list(jgb.get("dates") or []), "y10": list(jgb.get("y10") or []),
                      "y30": list(jgb.get("y30") or []), "y10_latest": _last(jgb.get("y10")),
                      "y30_latest": _last(jgb.get("y30")), "unit": jgb.get("unit", "%"), "asof": jgb.get("asof"),
                      "basis": jgb.get("basis"), "src": (jgb.get("src") or {}).get("history"),
                      "src_detail": dict(jgb.get("src") or {}), "status": s_jgb}
    return out


# ---------------------------------------------------------------------------
# public funds & pensions
# ---------------------------------------------------------------------------
# which public_funds.CAN_SEE line rests on which status key
_CAN_SEE_KEY = (("MOF trust accounts", "mof"), ("Z.1 pension sectors", "z1"), ("GPIF", "gpif"),
                ("TIC Foreign Official", "tic"), ("IMF PIP", "imf_pip"))


def _visibility(statuses: dict) -> tuple[list[str], list[str], list[str]]:
    """can_see / cannot_see derived from what loaded: a series whose source
    failed this run cannot be seen either, and says so."""
    can, cannot, missing = [], [], []
    for line in public_funds.CAN_SEE:
        key = next((k for prefix, k in _CAN_SEE_KEY if line.startswith(prefix)), None)
        st = statuses.get(key) if key else None
        if st in ("ok", "stale"):
            can.append(line + (" [stale: served from cache]" if st == "stale" else ""))
        else:
            missing.append(line)
            cannot.append(f"NOT LOADED THIS RUN (status {st or 'error'}): " + line)
    return can, cannot + list(public_funds.CANNOT_SEE), missing


def public_funds_block(pf: dict | None) -> dict:
    if not pf:
        can, cannot, _ = _visibility({})
        return {"status": "error", "status_detail": {k: "error" for k in ("gpif", "imf_pip", "mof", "z1", "tic")},
                "asof": None, "basis": public_funds.BASIS, "trust_accounts_12m_jpy_trn": None,
                "trust_accounts_asof": None, "trust_accounts_src": boj_mof.MOF_MONTHB3_URL,
                "mof_by_type": None, "z1_pensions": None, "gpif": None, "tic_official_corp": None,
                "imf_pip_japan": None, "can_see": can, "cannot_see": cannot,
                "src": {"gpif": public_funds.GPIF_URL, "imf_pip": public_funds.IMF_PIP_URL}}
    st = dict(pf.get("status") or {})
    can, cannot, _ = _visibility(st)
    trust = pf.get("mof_by_type") or {}
    pens_in = pf.get("z1_pensions") or {}
    pens = {s: {"level": c.get("level_latest"), "flow_saar": c.get("flow_saar_latest"), "asof": pens_in.get("asof"),
                "flow_saar_last4": list(c.get("flow_saar_last4") or []),
                "level_series": list(c.get("level") or []), "flow_saar_series": list(c.get("flow_saar") or [])}
            for s, c in pens_in.items() if isinstance(c, dict)}
    pens.update({"quarters": list(pens_in.get("quarters") or []), "unit": pens_in.get("unit"),
                 "units_consistent": pens_in.get("units_consistent"), "basis": pens_in.get("basis"),
                 "src": pens_in.get("src"), "asof": pens_in.get("asof"), "status": pens_in.get("status", "error")})
    gpif = dict(pf.get("gpif") or {})
    if gpif:
        gpif["lines_total"] = gpif.get("n_lines")
    off = dict(pf.get("tic_official_corp") or {})
    if off:
        off["share_of_foreign_held"] = off.get("share_of_foreign_held_pct")
    # the optional IMF block is reported but never degrades the whole block
    core = {k: v for k, v in st.items() if k != "imf_pip"}
    return {
        "status": worst(core.values()), "status_detail": st,
        "asof": dict(pf.get("asof") or {}), "basis": pf.get("basis") or public_funds.BASIS,
        "trust_accounts_12m_jpy_trn": pf.get("trust_accounts_12m_jpy_trn"),
        "trust_accounts_asof": trust.get("asof"), "trust_accounts_src": trust.get("src"),
        "mof_by_type": trust or None,
        "z1_pensions": pens,
        "gpif": gpif or None,
        "tic_official_corp": off or None,
        "imf_pip_japan": pf.get("imf_pip_japan"),
        "can_see": can, "cannot_see": cannot,
        "src": dict(pf.get("src") or {}),
    }


# ---------------------------------------------------------------------------
# crowding
# ---------------------------------------------------------------------------
_YIELD_BASIS = {"dgs10": "10y Treasury constant-maturity yield (H.15 via FRED), %, daily",
                "dgs30": "30y Treasury constant-maturity yield (H.15 via FRED), %, daily",
                "t10yie": "10y breakeven inflation (nominal minus TIPS, FRED), %, daily"}


def _ust_rows(net: dict | None, first_year: int = 2024) -> dict | None:
    if not net:
        return None
    out: dict = {}
    for kind, book in (("FY", net.get("fy") or {}), ("CY", net.get("cy") or {})):
        for year, row in sorted(book.items()):
            if int(year) < first_year:
                continue
            out[f"{kind}{year}"] = {"net_marketable": row.get("net_marketable"), "coupons": row.get("coupons"),
                                    "bills": row.get("bills"), "ffb": row.get("ffb"), "from": row.get("from"),
                                    "to": row.get("to"), "complete": row.get("complete"),
                                    "basis": (net.get("basis") or "") + (
                                        "" if row.get("complete") else "; year incomplete, measured to the latest month")}
    return out


def crowding_block(mspd: dict | None, tp: dict | None, yields: dict | None, auctions: list | None,
                   net: dict | None) -> dict:
    s_mspd = mspd.get("status", "error") if mspd else "error"
    kw = (tp or {}).get("kw10")
    acm = (tp or {}).get("acm10")
    s_kw = kw.get("status", "error") if kw else "error"
    ys = yields or {}
    s_y = {k: (ys.get(k) or {}).get("status", "error") for k in ("dgs10", "dgs30", "t10yie", "fed_treast")}
    s_auc = "ok" if auctions else "error"
    detail = {"mspd": s_mspd, "kw10": s_kw, "acm10": (acm or {}).get("status") if acm else "missing (optional)",
              **s_y, "auctions": s_auc}
    out: dict = {
        "status": worst([s_mspd, s_kw, *s_y.values(), s_auc]),    # ACM is optional: reported, not counted
        "status_detail": detail, "basis": CROWDING_BASIS,
        "ust": _ust_rows(net), "ust_monthly": None, "ust_checks": dict((mspd or {}).get("checks") or {}),
        "ust_src": (mspd or {}).get("src") or treasury_supply.MSPD_URL.format(start="2001-01-01"),
        "term_premium": {"kw10": _reading(kw, "Kim-Wright is the primary gauge"),
                         "acm10": _reading(acm, "NY Fed ACM, optional (xls)") if acm else None},
        "yields": {k: _reading(dict(ys[k], basis=ys[k].get("basis") or _YIELD_BASIS[k]) if ys.get(k) else None)
                   for k in ("dgs10", "dgs30", "t10yie")},
        "fed_treast": _reading(ys.get("fed_treast"), "Fed holdings compete for the same paper; a demand-side "
                                                    "factor the crowding pieces rarely net out"),
        "auctions": [{"date": a.get("date"), "tenor": a.get("tenor"), "term": a.get("term"),
                      "security_type": a.get("security_type"), "high_yield": a.get("high_yield"),
                      "btc": a.get("btc"), "indirect_pct": a.get("indirect_pct"), "dealer_pct": a.get("dealer_pct"),
                      "direct_pct": a.get("direct_pct"),
                      # False = a known term with no month component; None only when the term is missing
                      "reopening": ("month" in str(a["term"]).lower()) if a.get("term") else None}
                     for a in (auctions or [])] if auctions is not None else None,
        "auctions_src": treasury_supply.AUCTION_SRC,
        "auctions_basis": ("FiscalData auctions_query, completed Note/Bond auctions; high yield %, bid-to-cover, "
                           "indirect = foreign-demand proxy; reopenings pooled by tenor; no when-issued field"),
        "src": {"mspd": (mspd or {}).get("src"), "kw10": fred_csv.url(treasury_supply.KW_SERIES),
                "acm10": treasury_supply.ACM_URL, "auctions": treasury_supply.AUCTION_SRC,
                **{k: fred_csv.url(v) for k, v in treasury_supply.YIELD_SERIES.items()},
                "fed_treast": fred_csv.url(treasury_supply.FED_SERIES["treast"])},
    }
    if mspd and mspd.get("months"):
        out["ust_monthly"] = {"months": list(mspd["months"]), "marketable": list(mspd.get("total_marketable") or []),
                              "coupons": list(mspd.get("coupons") or []), "bills": list(mspd.get("bills") or []),
                              "classes": {k: list(v) for k, v in (mspd.get("classes") or {}).items()},
                              "class_sum": list(mspd.get("class_sum") or []), "gap_bn": list(mspd.get("gap_bn") or []),
                              "unit": "$bn", "asof": mspd.get("asof"), "basis": mspd.get("basis"),
                              "src": mspd.get("src"), "status": s_mspd}
    return out


# ---------------------------------------------------------------------------
# breaking
# ---------------------------------------------------------------------------
def _ebp_reading(e: dict | None) -> dict | None:
    if not e:
        return None
    r = _reading({"latest": e.get("latest"), "asof": e.get("asof"), "unit": e.get("unit"), "src": e.get("src"),
                  "basis": e.get("basis"), "status": e.get("status"),
                  "dates": [f"{m}-01" for m in e.get("months") or []], "values": e.get("ebp") or []},
                 "monthly; gz_spread and est_prob alongside")
    r.update({"gz_spread_latest": e.get("gz_spread_latest"), "est_prob_latest": e.get("est_prob_latest"),
              "gz_spread_series": list(e.get("gz_spread") or []), "est_prob_series": list(e.get("est_prob") or [])})
    return r


def _fsi_reading(f: dict | None) -> dict | None:
    if not f:
        return None
    r = _reading({"latest": f.get("latest"), "asof": f.get("asof"), "unit": f.get("unit"), "src": f.get("src"),
                  "basis": f.get("basis"), "status": f.get("status"), "dates": f.get("dates") or [],
                  "values": f.get("fsi") or []}, "0 = average stress; credit sub-index alongside")
    r.update({"credit_latest": f.get("credit_latest"), "credit_series": list(f.get("credit") or [])})
    return r


def breaking_block(brk: dict | None, seed: dict | None) -> dict:
    spread_pts = ([{**p, "basis": "30y tranche, bp over the benchmark UST at pricing, from the FWP"}
                   for p in seed_mod.spread_at_issue_30y(seed)] if seed else None)
    if not brk:
        return {"status": "error", "status_detail": {}, "asof": None, "basis": breaking.BASIS, "spreads": None,
                "ccc_b_gap": None, "yields": None, "baa10y": None, "ebp": None, "ofr_fsi": None, "move": None,
                "bdc": None, "spread_at_issue_30y": spread_pts, "events": None, "events_meta": None,
                "src": {"fred_pattern": fred_csv.url("<SERIES>"), "ebp": breaking.EBP_URL,
                        "ofr_fsi": breaking.OFR_FSI_URL}}
    st = dict(brk.get("status") or {})
    move = dict(brk.get("move") or {})
    if move:
        move["note"] = "Yahoo chart daily close; last bar may be the current session"
    bdc = [{**r, "px_src": r.get("src")} for r in brk.get("bdc") or []]
    return {
        "status": worst(st.values()), "status_detail": st,
        "asof": brk.get("asof"), "basis": brk.get("basis") or breaking.BASIS,
        "spreads": brk.get("spreads"), "ccc_b_gap": brk.get("ccc_b_gap"), "yields": brk.get("yields"),
        "baa10y": brk.get("baa10y"), "ebp": _ebp_reading(brk.get("ebp")), "ofr_fsi": _fsi_reading(brk.get("ofr_fsi")),
        "move": move or None, "bdc": bdc, "bdc_basis": breaking.BDC_BASIS,
        "spread_at_issue_30y": spread_pts,
        "events": brk.get("events"), "events_meta": brk.get("events_meta"),
        "src": dict(brk.get("src") or {}),
    }


# ---------------------------------------------------------------------------
# sources map and the payload
# ---------------------------------------------------------------------------
def sources_map(seed: dict | None) -> dict[str, str]:
    """tag -> URL for every source the payload cites (memo §9 tags where one
    exists). URLs come from the source modules' constants so they cannot drift."""
    out: dict[str, str] = dict((seed or {}).get("sources") or {})
    u = fred_csv.url
    out.update({
        "EDGAR-SUB": "https://data.sec.gov/submissions/CIK##########.json",
        "FRED-FA893": u("BOGZ1FA893063005Q"), "FRED-FU893": u("BOGZ1FU893063005Q"),
        "FRED-FL893": u("BOGZ1FL893063005Q"), "FRED-FA103": u(z1.NFC_ISSUANCE_SAAR),
        "FRED-ROWCB": u("ROWCBAQ027S"), "Z1-RELEASE": "https://www.federalreserve.gov/releases/z1/",
        "FRED-TIC-JP-TSY": u("FORLTTREASNET42609"), "FRED-TIC-JP-TSYPOS": u("FORLTTREASPOS42609"),
        "FRED-TIC-JP-CORP": u("FORLTCORPNET42609"), "FRED-TIC-JP-CORPPOS": u("FORLTCORPPOS42609"),
        "FRED-TIC-GT-CORP": u("FORLTCORPNET99996"), "FRED-TIC-GT-CORPPOS": u("FORLTCORPPOS99996"),
        "FRED-TIC-OFF": u("FORLTCORPNET99990"), "FRED-TIC-OFFPOS": u("FORLTTREASPOS99990"),
        "FRED-TIC-NONOFF": u("FORLTCORPNET99991"), "FRED-TIC-UK": u("FORLTTREASNET13005"),
        "TIC-CSLT": tic.CSLT_URL,
        "BOJ-BP": boj_mof.BOJ_URL, "MOF-SOV": boj_mof.MOF_SOV_DEF_URL, "MOF-B3": boj_mof.MOF_MONTHB3_URL,
        "MOF-WEEK": boj_mof.MOF_WEEK_URL, "MOF-JGB": boj_mof.MOF_JGB_ALL_URL, "MOF-JGB-CUR": boj_mof.MOF_JGB_CUR_URL,
        "GPIF": public_funds.GPIF_URL, "IMF-PIP": public_funds.IMF_PIP_URL,
        "MSPD": treasury_supply.MSPD_URL.format(start="2001-01-01"), "ACM": treasury_supply.ACM_URL,
        "FRED-KW": u(treasury_supply.KW_SERIES), "FRED-DGS10": u("DGS10"), "FRED-DGS30": u("DGS30"),
        "FRED-T10YIE": u("T10YIE"), "FRED-TREAST": u("TREAST"), "TD-AUCTIONS": treasury_supply.AUCTION_SRC,
        "FRED-CCC": u(breaking.OAS["ccc"][0]), "FRED-B": u(breaking.OAS["b"][0]), "FRED-BB": u(breaking.OAS["bb"][0]),
        "FRED-BBB": u(breaking.OAS["bbb"][0]), "FRED-A": u(breaking.OAS["a"][0]), "FRED-AA": u(breaking.OAS["aa"][0]),
        "FRED-AAA": u(breaking.OAS["aaa"][0]), "FRED-IG": u(breaking.OAS["ig"][0]), "FRED-HY": u(breaking.OAS["hy"][0]),
        "FRED-IGEY": u(breaking.YIELDS["ig"][0]), "FRED-HYEY": u(breaking.YIELDS["hy"][0]),
        "FRED-BAA10Y": u(breaking.BAA10Y), "FRED-NOTICE": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
        "FED-EBP": breaking.EBP_URL, "OFR-FSI": breaking.OFR_FSI_URL,
        "MOVE-YH": breaking.yahoo_url(breaking.MOVE_SYMBOL), "MOVE-INV": breaking.MOVE_XCHECK_URL,
        "BDC-YH": breaking.YAHOO_CHART.format(sym="<TICKER>"),
        "EVENTS": breaking.EVENTS_SRC_URL,
    })
    for t, row in breaking.BDC_NAV.items():      # memo tags ARCC-10Q, BXSL-8K, GBDC-8K
        if row.get("nav_src"):
            out[f"{t}-{str(row.get('nav_form') or 'FILING').split()[0].replace('-', '')}"] = row["nav_src"]
    return out


def build_ai_debt(inputs: dict, now: datetime | None = None) -> dict:
    """inputs = fetch_inputs() (or the same keys from fixtures) -> the payload."""
    seed = inputs.get("seed")
    mspd = inputs.get("mspd")
    net = treasury_supply.net_issuance(mspd) if mspd and mspd.get("months") else None
    bc = inputs.get("by_country")
    jp_row = next((c for c in (bc or {}).get("countries") or [] if c.get("key") == "japan"), None)
    blocks = {
        "issuance": issuance_block(seed, inputs.get("poll"), net),
        "holders": holders_block(inputs.get("holders")),
        "foreign_bid": foreign_block(bc, inputs.get("bills")),
        "japan": japan_block(inputs.get("boj"), inputs.get("mof"), inputs.get("weekly"), inputs.get("jgb"),
                             inputs.get("bills"), jp_row),
        "public_funds": public_funds_block(inputs.get("public_funds")),
        "crowding": crowding_block(mspd, inputs.get("term_premium"), inputs.get("yields"),
                                  inputs.get("auctions"), net),
        "breaking": breaking_block(inputs.get("breaking"), seed),
    }
    now = now or datetime.now(timezone.utc)
    # data as-of = the latest daily print among the breaking / crowding series
    daily = [blocks["breaking"].get("asof"),
             ((blocks["crowding"].get("yields") or {}).get("dgs30") or {}).get("asof"),
             ((blocks["crowding"].get("term_premium") or {}).get("kw10") or {}).get("asof")]
    daily = [d for d in daily if isinstance(d, str)]
    status = {k: v["status"] for k, v in blocks.items()}
    return {
        "asof": max(daily) if daily else None,
        "generated": now.isoformat(timespec="seconds"),
        "note": NOTE,
        "basis": {"issuance": blocks["issuance"]["basis"], "holders": blocks["holders"]["basis"],
                  "foreign": blocks["foreign_bid"]["basis"], "japan": JAPAN_BASIS,
                  "public_funds": blocks["public_funds"]["basis"], "crowding": CROWDING_BASIS,
                  "breaking": blocks["breaking"]["basis"]},
        **blocks,
        "honesty": list(HONESTY) + list(HONESTY_EXTRA),
        "sources": sources_map(seed),
        "status": {**status, "overall": worst(status.values())},
    }
