#!/usr/bin/env python3
"""Freeze the AI-debt deal tally (data/deals.csv) into the backend seed
backend/app/sources/ai_debt_seed.json — rev 1 of studies/ai-debt-flows.md.

    cd treasury-canary && python3 studies/ai_debt_flows/export_seed.py

The CSV is the finder's file with verifier C's two re-inclusions already
applied (103 included rows, $682.5bn). This script only (a) normalises
types and vocabulary (rating buckets per the BUILD.md convention, flags,
null for missing), (b) applies verifier C's C6 rating corrections, whose
basis is printed on each record, and (c) attaches the frozen share
denominators and 30y spread-at-issue points from the memo §3c / §5 / §9
with their URLs. It never changes a size, date or inclusion: the gate tests
in backend/tests/test_ai_debt_sources_issuance.py pin the memo tables, so a
CSV edit that moves the tally fails them until the memo is revised too.

Rules carried from the memo (Casey's defaults, 2026-10-15): refinancings
included and flagged `refi`; SPV / project-vehicle debt counted at pricing
and flagged `spv`; converts included and flagged `convert`; revolvers and
frameworks excluded; non-USD legs at FRED spot on/before the trade date
(`fx_basis` names the series) and flagged `non_usd`.
"""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "data", "deals.csv")
OUT_PATH = os.path.join(HERE, "..", "..", "backend", "app", "sources", "ai_debt_seed.json")

SEED_REV = "rev 1"
ASOF = "2026-10-15"            # the tally's freeze date (scoping memo rev 1)

# CSV rating_bucket -> BUILD.md convention. 'n/a' rows (equity-linked, no-issuance
# placeholders, announced frameworks) carry no rating concept at all -> null.
RATING_BUCKETS = {
    "AAA": "AAA", "AA": "AA", "A": "A", "BBB": "BBB", "BB": "BB", "B": "B",
    "unrated/private": "unrated-private",
    "ABS/CMBS-tranched": "ABS-tranched",
    "unknown": "not-captured",
    "n/a": None, "n/a-equity-linked": None, "": None,
}
BUCKETS = ("hyperscaler", "chips-memory", "neocloud", "ai-lab", "data-center",
           "power", "off-balance-sheet")

# Verifier C, claim C6 (2026-10-15): three ratings the finder marked "not in FWP /
# not parsed" are printed in its own downloaded FWPs. Memo §3b already carries the
# Meta re-bucketing (AA-2024 = 10.5, not-captured-2024 = 0). Keyed (date, issuer).
RATING_FIXES: dict[tuple[str, str], dict] = {
    ("2024-08-07", "Meta Platforms"): {
        "rating_bucket": "AA", "rating_at_issue": "Aa3 / AA- (FWP)", "rating_verified": True,
        "basis": "FWP d881153dfwp.htm prints 'Aa3 (Moody's) / AA- (S&P)'; verifier C6"},
    ("2025-11-17", "Amazon"): {
        "rating_at_issue": "A1(+) / AA / AA- (FWP)", "rating_verified": True,
        "basis": "FWP tm2530638d2_fwp.htm prints 'A1(+) by Moody's, AA by S&P, AA- by Fitch'; verifier C6"},
    ("2025-01-30", "Oracle"): {
        "rating_at_issue": "Baa2 / BBB / BBB (FWP)", "rating_verified": True,
        "basis": "FWP d901407dfwp.htm prints 'Baa2 (stable) / BBB (stable) / BBB (stable)'; verifier C6"},
    ("2024-09-25", "Oracle"): {
        "rating_at_issue": "Baa2 / BBB / BBB (FWP)", "rating_verified": True,
        "basis": "FWP d832142dfwp.htm prints 'Baa2 (stable) / BBB (stable) / BBB (stable)'; verifier C6"},
}

# Flag rules (documented so a reader can audit the list the seed prints).
# `repay` may carry an amount ("repay $20B bridge"); the GCP boilerplate "incl.
# debt repayment" (Alphabet, Amazon) is NOT a refinancing and does not match.
_REFI_RE = re.compile(r"\brefi\b|refinanc|redeem|retire |repay (?:\$?[\d.]+\s*[BMbn]*\s+)?(?:bridge|debt)|"
                      r"replaces bridge|repurchase", re.I)
_SPV_RE = re.compile(r"\bSPV\b|project (?:notes|bonds?|finance)|\bLLC\b|\bLP\b|Compute Acquisition|Financing DDTL|subsidiar|\bJV\b", re.I)
_CONVERT_RE = re.compile(r"convert|exchangeable", re.I)

# Memo §3c / §9: SIFMA US corporate bond issuance ($bn) — the share denominator.
SIFMA_PDF = "https://www.sifma.org/wp-content/uploads/2026/04/SIFMA-Research-Quarterly-Fixed-Income-IT-2Q26.pdf"
SIFMA_PAGE = "https://www.sifma.org/research/statistics/us-corporate-bonds-statistics/"
SHARE_DENOMINATORS = {
    "sifma_us_corp_bn": {"2024": 1972.7, "2025": 2218.6, "2026": 2195.1},
    "basis": {
        "2024": "full year; SIFMA Research Quarterly 2Q26 (corporate issuance table)",
        "2025": "full year (+12.5% vs 2024); SIFMA Research Quarterly 2Q26",
        "2026": "YTD through September (+24.5% Y/Y per the SIFMA statistics page, published 2026-10-14); "
                "H1-26 = 1,522.8 (+28.1% vs H1-25). The tally's 2026 column runs to 2026-10-13, so the share "
                "numerator is ~2 weeks longer than the denominator.",
    },
    "src": {"2024": SIFMA_PDF, "2025": SIFMA_PDF, "2026": SIFMA_PAGE},
    "ig_hy_2q26": {
        "total_bn": 732.6, "ig_pct": 75.2, "hy_pct": 14.3,
        "basis": "2Q26 US corporate issuance; IG/HY shares read from the SIFMA quarterly's pie chart "
                 "(verifier-derived: share x total -> IG ~551, HY ~105 $bn). Annual IG/HY dollars sit in "
                 "a gated xls (HubSpot form), UNVERIFIABLE here.",
        "src": SIFMA_PDF,
    },
    "note": "USD legs only over a US-only denominator; non-USD legs are not in SIFMA's series, so an "
            "all-currency numerator over this denominator is not a share of anything.",
}

# Memo §5 'Spread at issue, 30y tranche' (verifier C16-corrected), bp over the
# benchmark UST, from the pricing term sheets (FWP) — the cleanest free gauge of
# hyperscaler new-issue repricing. Oracle 2025-09-24: 30y = 125 (the 40y is 137).
# Rev-1 integration added the memo's "Nvidia 65" (2026-06-15, 2056) and the two
# earlier Oracle 30y points (2024-09-25: 125 at 2054; 2025-01-30: 122 at 2055),
# all re-derived from the local FWPs by the extractor.
SPREAD_AT_ISSUE_30Y = [
    {"issuer": "Meta Platforms", "date": "2024-08-07", "bp": 115, "maturity": 2054,
     "src": "https://www.sec.gov/Archives/edgar/data/1326801/000119312524196020/d881153dfwp.htm"},
    {"issuer": "Meta Platforms", "date": "2025-10-30", "bp": 98, "maturity": 2055,
     "src": "https://www.sec.gov/Archives/edgar/data/1326801/000119312525258837/d61769dfwp.htm"},
    {"issuer": "Meta Platforms", "date": "2026-04-30", "bp": 132, "maturity": 2056,
     "src": "https://www.sec.gov/Archives/edgar/data/1326801/000119312526197902/d148113dfwp.htm"},
    {"issuer": "Alphabet", "date": "2025-04-28", "bp": 62, "maturity": 2055,
     "src": "https://www.sec.gov/Archives/edgar/data/1652044/000119312525100802/d806252dfwp.htm"},
    {"issuer": "Alphabet", "date": "2025-11-04", "bp": 82, "maturity": 2055,
     "src": "https://www.sec.gov/Archives/edgar/data/1652044/000119312525263045/d41216dfwp.htm"},
    {"issuer": "Alphabet", "date": "2026-02-10", "bp": 83, "maturity": 2056,
     "src": "https://www.sec.gov/Archives/edgar/data/1652044/000119312526043127/d297481dfwp.htm"},
    {"issuer": "Alphabet", "date": "2026-08-07", "bp": 115, "maturity": 2056,
     "src": "https://www.sec.gov/Archives/edgar/data/1652044/000119312526338750/d159970dfwp.htm"},
    {"issuer": "Amazon", "date": "2025-11-17", "bp": 75, "maturity": 2055,
     "src": "https://www.sec.gov/Archives/edgar/data/1018724/000110465925113283/tm2530638d2_fwp.htm"},
    {"issuer": "Amazon", "date": "2026-03-10", "bp": 105, "maturity": 2056,
     "src": "https://www.sec.gov/Archives/edgar/data/1018724/000110465926025948/tm266670d5_fwp.htm"},
    {"issuer": "Amazon", "date": "2026-07-07", "bp": 110, "maturity": 2056,
     "src": "https://www.sec.gov/Archives/edgar/data/1018724/000110465926081334/tm2619352d3_fwp.htm"},
    {"issuer": "Oracle", "date": "2024-09-25", "bp": 125, "maturity": 2054,
     "src": "https://www.sec.gov/Archives/edgar/data/1341439/000119312524226101/d832142dfwp.htm"},
    {"issuer": "Oracle", "date": "2025-01-30", "bp": 122, "maturity": 2055,
     "src": "https://www.sec.gov/Archives/edgar/data/1341439/000119312525017365/d901407dfwp.htm"},
    {"issuer": "Oracle", "date": "2025-09-24", "bp": 125, "maturity": 2055,
     "src": "https://www.sec.gov/Archives/edgar/data/1341439/000119312525215807/d49252dfwp.htm"},
    {"issuer": "Oracle", "date": "2026-02-02", "bp": 180, "maturity": 2056,
     "src": "https://www.sec.gov/Archives/edgar/data/1341439/000119312526033882/d44245dfwp.htm"},
    {"issuer": "Nvidia", "date": "2026-06-15", "bp": 65, "maturity": 2056,
     "src": "https://www.sec.gov/Archives/edgar/data/1045810/000119312526271326/d49394dfwp.htm"},
]

# Repo files cited by the payload resolve to the repository blob so a `sources`
# tag is always a URL (BUILD.md: `sources: {tag: url}`).
REPO_BLOB = "https://github.com/OpticReports/uranium-dashboard/blob/main/treasury-canary/"

SOURCES = {
    "C-DEALS": REPO_BLOB + "studies/ai_debt_flows/data/deals.csv",
    "SIFMA-PDF": SIFMA_PDF,
    "SIFMA-PAGE": SIFMA_PAGE,
    "8K-CRWV-2505": "https://www.sec.gov/Archives/edgar/data/1769628/000176962825000025/crwv-20250527.htm",
    "FWP-META-2408": SPREAD_AT_ISSUE_30Y[0]["src"],
    "FWP-META-2510": SPREAD_AT_ISSUE_30Y[1]["src"],
    "FWP-META-2604": SPREAD_AT_ISSUE_30Y[2]["src"],
    "FWP-GOOGL-2504": SPREAD_AT_ISSUE_30Y[3]["src"],
    "FWP-GOOGL-2511": SPREAD_AT_ISSUE_30Y[4]["src"],
    "FWP-GOOGL-2602": SPREAD_AT_ISSUE_30Y[5]["src"],
    "FWP-GOOGL-2608": SPREAD_AT_ISSUE_30Y[6]["src"],
    "FWP-AMZN-2511": SPREAD_AT_ISSUE_30Y[7]["src"],
    "FWP-AMZN-2603": SPREAD_AT_ISSUE_30Y[8]["src"],
    "FWP-AMZN-2607": SPREAD_AT_ISSUE_30Y[9]["src"],
    "FWP-ORCL-2409": SPREAD_AT_ISSUE_30Y[10]["src"],
    "FWP-ORCL-2501": SPREAD_AT_ISSUE_30Y[11]["src"],
    "FWP-ORCL-2509": SPREAD_AT_ISSUE_30Y[12]["src"],
    "FWP-ORCL-2602": SPREAD_AT_ISSUE_30Y[13]["src"],
    "FWP-NVDA": SPREAD_AT_ISSUE_30Y[14]["src"],
}


def _num(s: str) -> float | None:
    """CSV cell -> float; empty -> None (missing is null, never 0)."""
    s = (s or "").strip()
    if not s:
        return None
    return float(s)


def _text(s: str) -> str | None:
    s = (s or "").strip()
    return s or None


def convert_row(r: dict) -> dict:
    key = (r["date"], r["issuer"])
    included = r["included_in_totals"].strip() == "Y"
    size_usd = _num(r["size_usd_bn"])
    size = _num(r["size_bn"])
    # Placeholder rows ('NO ISSUANCE ...', 'NOT TALLIED') carry size 0.0 with no USD
    # figure: that is "no deal", not a $0 deal, so both sizes are null.
    if size_usd is None and (size is None or size == 0.0):
        size = None
    bucket = r["bucket"].strip()
    if bucket not in BUCKETS:
        raise ValueError(f"{key}: unknown bucket {bucket!r}")
    rb_raw = r["rating_bucket"].strip()
    if rb_raw not in RATING_BUCKETS:
        raise ValueError(f"{key}: unknown rating bucket {rb_raw!r}")
    rec = {
        "date": r["date"],
        "issuer": r["issuer"].strip(),
        "bucket": bucket,
        "instrument": r["instrument"].strip(),
        "size_bn": size,
        "ccy": r["ccy"].strip() or None,
        "size_usd_bn": size_usd,
        "fx_basis": _text(r["fx_basis"]),
        "status": _text(r["status"]),
        "included": included,
        "rating_bucket": RATING_BUCKETS[rb_raw],
        "rating_at_issue": _text(r["ratings_at_issue"]),
        "rating_verified": r["rating_verified"].strip() == "Y",
        "tranches": _text(r["tranches"]),
        "pricing": _text(r["pricing"]),
        "book": _text(r["book"]),
        "uop": _text(r["uop"]),
        "verif": r["verif"].strip(),
        "src": _text(r["src_primary"]) or _text(r["src_press"]),
        "flags": [],
        "note": _text(r["notes"]),
    }
    if rec["verif"] not in ("P", "R", "S"):
        raise ValueError(f"{key}: verif must be P/R/S, got {rec['verif']!r}")
    fix = RATING_FIXES.get(key)
    if fix:
        rec.update({k: v for k, v in fix.items() if k != "basis"})
        rec["note"] = (rec["note"] + "; " if rec["note"] else "") + "rating: " + fix["basis"]
    blob = " ".join(filter(None, (rec["uop"], rec["note"])))
    if _REFI_RE.search(blob):
        rec["flags"].append("refi")
    if bucket == "off-balance-sheet" or _SPV_RE.search(rec["issuer"] + " " + rec["instrument"]):
        rec["flags"].append("spv")
    if _CONVERT_RE.search(rec["instrument"]):
        rec["flags"].append("convert")
    if rec["ccy"] and rec["ccy"] != "USD":
        rec["flags"].append("non_usd")
        if included and not rec["fx_basis"]:
            raise ValueError(f"{key}: included non-USD leg without fx_basis")
    if included and (size_usd is None or not rec["src"]):
        raise ValueError(f"{key}: included deal needs size_usd_bn and a source URL")
    return rec


def build_seed(csv_path: str = CSV_PATH) -> dict:
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    deals = [convert_row(r) for r in rows]
    inc = [d for d in deals if d["included"]]
    if max(d["date"] for d in inc) > ASOF:
        raise ValueError(f"deal dated after ASOF {ASOF}: bump ASOF (and the gate tests' pinned numbers)")
    return {
        "seed_rev": SEED_REV,
        "asof": ASOF,
        "generated": date.today().isoformat(),
        "source_csv": "studies/ai_debt_flows/data/deals.csv",
        "basis": "gross issuance at pricing (not net of redemptions), $bn; non-USD legs at FRED spot "
                 "on/before the trade date; refinancings, SPV/project debt and converts included and "
                 "flagged; revolvers and announced frameworks excluded; rating = S&P-style letter at pricing, "
                 "'not-captured' where no fetched document printed one",
        "n_rows": len(deals),
        "n_included": len(inc),
        "total_usd_bn": round(sum(d["size_usd_bn"] for d in inc), 2),
        "first_deal_date": min(d["date"] for d in inc),
        "last_deal_date": max(d["date"] for d in inc),
        "buckets": list(BUCKETS),
        "rating_buckets": ["AAA", "AA", "A", "BBB", "BB", "B", "unrated-private", "ABS-tranched", "not-captured"],
        "flag_rules": {
            "refi": "use-of-proceeds / notes mention refinancing, redemption, retiring or repaying debt or a bridge "
                    "(Broadcom's six VMware-refi deals, Micron, Constellation/Calpine, Vistra, Intel, Nvidia, SpaceX, SoftBank, ...); "
                    "the GCP boilerplate 'incl. debt repayment' (Alphabet, Amazon) does not count",
            "spv": "off-balance-sheet bucket, or a project / financing vehicle issuer (LLC, LP, 'Compute Acquisition', 'Financing DDTL', subsidiary, JV)",
            "convert": "convertible or exchangeable instrument",
            "non_usd": "priced in a currency other than USD; size_usd_bn at the FX named in fx_basis",
        },
        "deals": deals,
        "share_denominators": SHARE_DENOMINATORS,
        "spread_at_issue_30y": SPREAD_AT_ISSUE_30Y,
        "sources": SOURCES,
    }


def main() -> None:
    seed = build_seed()
    out = os.path.normpath(OUT_PATH)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(seed, f, indent=1, ensure_ascii=False)
        f.write("\n")
    inc = [d for d in seed["deals"] if d["included"]]
    print(f"wrote {out}: {seed['n_rows']} rows, {seed['n_included']} included, "
          f"${seed['total_usd_bn']}bn, {seed['first_deal_date']}..{seed['last_deal_date']}")
    for flag in ("refi", "spv", "convert", "non_usd"):
        hits = [f"{d['date']} {d['issuer'][:28]}" for d in inc if flag in d["flags"]]
        print(f"  {flag:8s} {len(hits):3d} included: " + "; ".join(hits))


if __name__ == "__main__":
    main()
