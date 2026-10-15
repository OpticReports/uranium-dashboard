"""Issuance sources for the AI-debt tab, offline.

The frozen seed (sources/ai_debt_seed.py + ai_debt_seed.json, rev 1 of
studies/ai-debt-flows.md) must reproduce the memo's §3a / §3b / §3c tables;
the EDGAR poll (sources/edgar_debt.py) is exercised on fixtures: the Meta
2026-04-30 pricing term sheet, the live Meta and Oracle submissions JSONs of
2026-10-15 and the whitelist names read the same day. The memo prints $bn to
one decimal; the seed carries cents, so "equal" means within 0.05.
"""
from __future__ import annotations

import json
import os

import pytest

from app.sources import ai_debt_seed as seed_mod
from app.sources import edgar_debt as edgar

FX = os.path.join(os.path.dirname(__file__), "fixtures", "ai_debt")
META_FWP_URL = "https://www.sec.gov/Archives/edgar/data/1326801/000119312526197902/d148113dfwp.htm"

# studies/ai-debt-flows.md §3a (bucket x year), §3b (rating x year), §3c (shares)
MEMO_TOTALS = {"2024": 39.7, "2025": 242.8, "2026": 400.0}
MEMO_BUCKETS = {
    "hyperscaler": (16.8, 108.4, 217.5), "chips-memory": (13.6, 18.2, 40.8),
    "neocloud": (8.0, 21.5, 49.5), "ai-lab": (0.0, 5.0, 25.0), "data-center": (1.4, 9.3, 9.3),
    "power": (0.0, 5.6, 17.1), "off-balance-sheet": (0.0, 74.7, 40.9),
}
MEMO_RATINGS = {
    "AAA": (0.0, 0.0, 0.0), "AA": (10.5, 82.7, 217.5), "A": (2.5, 33.8, 30.1),
    "BBB": (17.9, 43.3, 70.6), "BB": (0.0, 5.9, 26.3), "B": (0.0, 0.0, 0.0),
    "unrated-private": (8.0, 62.4, 26.7), "ABS-tranched": (0.8, 4.2, 2.7),
    # memo prints 8.5 for 2025 and notes the re-included CoreWeave $2.0bn was not
    # re-bucketed: with it the row is 10.5 (BUILD.md)
    "not-captured": (0.0, 10.5, 26.0),
}
MEMO_SHARE_PCT = {"2024": 0.85, "2025": 4.2, "2026": 7.2}
SIFMA = {"2024": 1972.7, "2025": 2218.6, "2026": 2195.1}


def close(a: float, b: float, tol: float = 0.05) -> bool:
    return abs(a - b) <= tol + 1e-9


@pytest.fixture(scope="module")
def seed():
    return seed_mod.load_seed()


# ----------------------------------------------------------------- the seed

def test_seed_identity(seed):
    assert seed["seed_rev"] == "rev 1" and seed["asof"] == "2026-10-15"
    assert seed["n_included"] == 103
    assert close(seed["total_usd_bn"], 682.5)
    assert seed["last_deal_date"] == "2026-10-13"
    json.dumps(seed)                      # the payload embeds it as-is


def test_totals_by_year(seed):
    tot = seed_mod.totals_by_year(seed)
    assert set(tot) == set(MEMO_TOTALS)
    for y, v in MEMO_TOTALS.items():
        assert close(tot[y], v), (y, tot[y], v)
    assert close(sum(tot.values()), 682.5)


def test_by_bucket_year_matches_memo_3a(seed):
    tab = seed_mod.by_bucket_year(seed)
    assert set(tab) == set(MEMO_BUCKETS)
    for b, row in MEMO_BUCKETS.items():
        for y, v in zip(("2024", "2025", "2026"), row):
            assert close(tab[b][y], v), (b, y, tab[b][y], v)
    tot = seed_mod.totals_by_year(seed)
    for y in tot:                          # columns add up to the year totals
        assert close(sum(tab[b][y] for b in tab), tot[y])


def test_by_rating_year_matches_memo_3b(seed):
    tab = seed_mod.by_rating_year(seed)
    assert set(tab) == set(MEMO_RATINGS)
    for rb, row in MEMO_RATINGS.items():
        for y, v in zip(("2024", "2025", "2026"), row):
            assert close(tab[rb][y], v), (rb, y, tab[rb][y], v)
    tot = seed_mod.totals_by_year(seed)
    for y in tot:
        assert close(sum(tab[rb][y] for rb in tab), tot[y])
    # the 2025 not-captured row contains the CoreWeave 2025-05-21 $2.0bn notes
    crwv = seed_mod.find_deal("2025-05-21", "CoreWeave", seed)
    assert crwv and crwv["included"] and crwv["rating_bucket"] == "not-captured" and crwv["size_usd_bn"] == 2.0
    # and the Meta 2024-08-07 deal sits in AA (its FWP prints Aa3 / AA-), with the basis on the record
    meta = seed_mod.find_deal("2024-08-07", "Meta Platforms", seed)
    assert meta["rating_bucket"] == "AA" and meta["rating_verified"] and "FWP" in meta["note"]


def test_hyperscaler_usd_share_matches_memo_3c(seed):
    share = seed_mod.hyperscaler_usd_share(seed)
    for y, pct in MEMO_SHARE_PCT.items():
        row = share[y]
        assert row["sifma_us_corp_bn"] == SIFMA[y]
        assert row["src"].startswith("https://www.sifma.org/")
        assert close(row["pct_hyperscaler"], pct, tol=0.05), (y, row["pct_hyperscaler"], pct)
        # a USD-only share never uses an all-currency numerator
        assert row["hyperscaler_usd_bn"] <= row["all_ai_usd_bn"] <= row["all_ai_bn"]
        assert close(row["pct_all"], 100 * row["all_ai_usd_bn"] / SIFMA[y], tol=0.01)
        assert "USD legs" in row["basis"]
    assert share["2026"]["all_ai_bn"] > share["2026"]["all_ai_usd_bn"]      # 2026 has non-USD legs
    assert close(share["2026"]["hyperscaler_usd_bn"], 157.0)


def test_every_included_deal_is_sourced_sized_and_typed(seed):
    for d in seed_mod.included(seed):
        assert d["src"] and d["src"].startswith("http"), d
        assert isinstance(d["size_usd_bn"], float) and d["size_usd_bn"] > 0, d
        assert d["verif"] in ("P", "R", "S"), d
        assert d["bucket"] in seed["buckets"] and d["rating_bucket"] in seed["rating_buckets"], d
        assert d["date"][:4] in ("2024", "2025", "2026")
    # placeholder / excluded rows never carry a fake zero
    for d in seed["deals"]:
        assert d["size_bn"] != 0.0 and d["size_usd_bn"] != 0.0, d


def test_non_usd_legs_carry_their_fx(seed):
    legs = [d for d in seed_mod.included(seed) if "non_usd" in d["flags"]]
    assert len(legs) == 19
    for d in legs:
        assert d["ccy"] != "USD" and d["fx_basis"].startswith("FRED DEX"), d
        assert d["size_usd_bn"] != d["size_bn"], d
    for d in seed_mod.included(seed):
        if d["ccy"] == "USD":
            assert d["size_usd_bn"] == d["size_bn"] and "non_usd" not in d["flags"], d


@pytest.mark.parametrize("date,issuer,ccy,headline", [
    ("2025-10-30", "Meta Platforms", "USD", 30.0),
    ("2026-04-30", "Meta Platforms", "USD", 25.0),
    ("2026-02-02", "Oracle", "USD", 25.0),
    ("2026-06-15", "Nvidia", "USD", 25.0),
    ("2026-06-08", "Amazon", "CAD", 14.0),
])
def test_tranche_sums_rederive_the_headline(seed, date, issuer, ccy, headline):
    d = seed_mod.find_deal(date, issuer, seed)
    assert d["included"] and d["ccy"] == ccy and d["verif"] == "P"
    sizes = seed_mod.tranche_sizes(d["tranches"])
    assert sizes and close(sum(sizes), headline, tol=1e-6), (d["tranches"], sizes)
    assert d["size_bn"] == headline
    if ccy == "CAD":                        # C$14.0bn at the recorded FX -> US$10.04bn
        assert d["fx_basis"] == "FRED DEXCAUS on/before 2026-06-08"
        assert close(d["size_usd_bn"], 10.037, tol=0.001)
        assert 0.70 < d["size_usd_bn"] / d["size_bn"] < 0.74   # USD per CAD, 2026 range


def test_flags_follow_the_stated_rules(seed):
    inc = seed_mod.included(seed)
    for d in inc:
        if d["issuer"] == "Broadcom":
            assert "refi" in d["flags"], d                     # VMware refinancing
        if d["bucket"] == "off-balance-sheet":
            assert "spv" in d["flags"], d
        if "convert" in d["instrument"].lower():
            assert "convert" in d["flags"], d
        for f in d["flags"]:
            assert f in ("refi", "spv", "convert", "non_usd")
    # revolvers / frameworks stay out
    for d in seed["deals"]:
        if "revolver" in d["instrument"].lower() or "framework" in d["instrument"].lower():
            assert not d["included"], d
    assert sum("refi" in d["flags"] for d in inc) == 18
    assert sum("convert" in d["flags"] for d in inc) == 13
    # the two bridge refinancings are flagged alike (S2): "repay $20B bridge" and "replaces bridge"
    assert "refi" in seed_mod.find_deal("2026-06-23", "SpaceX (parent of xAI)", seed)["flags"]
    assert "refi" in seed_mod.find_deal("2026-09-24", "SoftBank Group (OpenAI final $10B tranche)", seed)["flags"]
    # the legend lists exactly what the rule produces: GCP "incl. debt repayment" boilerplate stays out
    assert "does not count" in seed["flag_rules"]["refi"]
    for d in inc:
        if (d["uop"] or "").startswith("GCP incl. debt repayment"):
            assert "refi" not in d["flags"], d


def test_by_month_is_continuous_and_adds_up(seed):
    rows = seed_mod.by_month(seed)
    assert rows[0]["month"] == "2024-01" and rows[-1]["month"] == "2026-10" and len(rows) == 34
    assert set(rows[0]) == {"month", *seed["buckets"]}
    tot = seed_mod.totals_by_year(seed)
    for y in tot:
        assert close(sum(v for r in rows if r["month"].startswith(y) for k, v in r.items() if k != "month"), tot[y], tol=0.1)
    by_rating = seed_mod.by_month(seed, key="rating_bucket")
    assert set(by_rating[0]) == {"month", *seed["rating_buckets"]}
    with pytest.raises(ValueError):
        seed_mod.by_month(seed, key="issuer")


def test_frozen_spread_points_and_denominators(seed):
    pts = seed_mod.spread_at_issue_30y(seed)
    assert len(pts) == 15                                  # 12 + Nvidia 65 and the two earlier Oracle points (B2-9)
    for p in pts:
        assert p["src"].startswith("https://www.sec.gov/Archives/edgar/data/") and p["src"].endswith("fwp.htm")
        assert isinstance(p["bp"], int) and 50 <= p["bp"] <= 200
    by = {(p["issuer"], p["date"]): p["bp"] for p in pts}
    assert by[("Meta Platforms", "2025-10-30")] == 98 and by[("Meta Platforms", "2026-04-30")] == 132
    assert by[("Oracle", "2025-09-24")] == 125 and by[("Oracle", "2026-02-02")] == 180
    assert by[("Amazon", "2025-11-17")] == 75 and by[("Amazon", "2026-07-07")] == 110
    assert by[("Alphabet", "2025-04-28")] == 62 and by[("Alphabet", "2026-08-07")] == 115
    assert by[("Nvidia", "2026-06-15")] == 65                                    # memo §5 "Nvidia 65"
    assert by[("Oracle", "2024-09-25")] == 125 and by[("Oracle", "2025-01-30")] == 122
    assert {"FWP-NVDA", "FWP-ORCL-2409", "FWP-ORCL-2501"} <= set(seed["sources"])
    assert seed["sources"]["C-DEALS"].startswith("https://github.com/")            # a tag is always a URL
    den = seed_mod.share_denominators(seed)
    assert den["sifma_us_corp_bn"] == SIFMA
    assert den["ig_hy_2q26"]["total_bn"] == 732.6 and den["ig_hy_2q26"]["ig_pct"] == 75.2
    assert all(u.startswith("https://www.sifma.org/") for u in den["src"].values())


def test_verif_mix(seed):
    mix = seed_mod.verif_mix(seed)
    assert close(mix["P"] + mix["R"] + mix["S"], 100.0, tol=0.2)
    assert 65 < mix["P"] < 70 and 19 < mix["S"] < 22


# ---------------------------------------------------------------- EDGAR

def _fixture_sub(cik: int) -> dict:
    with open(os.path.join(FX, f"edgar_submissions_CIK{cik:010d}.json"), encoding="utf-8") as f:
        return json.load(f)


def test_whitelist_ciks_resolve_to_the_expected_names():
    with open(os.path.join(FX, "edgar_names_2026-10-15.json"), encoding="utf-8") as f:
        names = json.load(f)["names"]
    assert len(edgar.CIK_WHITELIST) == 24
    for cik, (label, expected) in edgar.CIK_WHITELIST.items():
        assert str(cik) in names, (cik, label)
        assert edgar.verify_name({"name": names[str(cik)]}, expected), (cik, label, names[str(cik)])
    # the two CIKs BUILD.md listed for Constellation and Nebius belong to other companies
    assert not edgar.verify_name({"name": names["1868941"]}, "Constellation Energy Corp")
    assert not edgar.verify_name({"name": names["1662684"]}, "Nebius Group N.V.")
    assert edgar.CIK_WHITELIST[1868275][0] == "Constellation Energy"
    assert edgar.CIK_WHITELIST[1513845][0] == "Nebius"


def test_submissions_fixtures_verify_and_list():
    meta, orcl = _fixture_sub(1326801), _fixture_sub(1341439)
    assert edgar.verify_name(meta, "Meta Platforms, Inc.") and not edgar.verify_name(meta, "ORACLE CORP")
    assert edgar.verify_name(orcl, "ORACLE CORP")
    fl = edgar.list_filings(meta, since="2026-04-25")
    assert all(f["form"] in edgar.FORMS and f["filed"] >= "2026-04-25" for f in fl)
    assert fl == sorted(fl, key=lambda f: f["filed"], reverse=True)
    fwp = [f for f in fl if f["form"] == "FWP" and f["filed"] == "2026-04-30"]
    assert len(fwp) == 1 and fwp[0]["url"] == META_FWP_URL
    assert edgar.filing_url(1326801, "0001193125-26-197902", "d148113dfwp.htm") == META_FWP_URL
    # the Oracle file lists its 2026-02-02 term sheets
    orcl_fwp = [f["url"] for f in edgar.list_filings(orcl, since="2026-02-01") if f["form"] == "FWP"]
    assert "https://www.sec.gov/Archives/edgar/data/1341439/000119312526033882/d44245dfwp.htm" in orcl_fwp


def test_extractor_on_the_meta_term_sheet():
    with open(os.path.join(FX, "fwp_meta_2026-04-30_d148113dfwp.htm"), encoding="utf-8", errors="replace") as f:
        x = edgar.extract_tranches(edgar.html_to_text(f.read()))
    assert x["n_tranches"] == 6 and x["n_sized"] == 6 and x["ccy"] == "USD"
    assert close(x["size_bn"], 25.0, tol=1e-6)
    assert x["maturities"] == [2031, 2033, 2036, 2046, 2056, 2066]
    assert x["coupons"] == [4.55, 4.875, 5.25, 6.2, 6.3, 6.45]
    assert x["spreads"] == [53.0, 68.0, 90.0, 122.0, 132.0, 147.0]
    assert all(t["benchmark"] == "UST" and t["ccy"] == "USD" and not t["floating"] for t in x["tranches"])
    assert "Aa3" in x["ratings"] and "AA-" in x["ratings"]
    # the 30y point the seed freezes is what the document says
    assert [t["spread_bp"] for t in x["tranches"] if t["maturity"] == 2056] == [132.0]


def test_extractor_returns_nulls_not_guesses():
    x = edgar.extract_tranches("")
    assert x["n_tranches"] == 0 and x["size_bn"] is None and x["ccy"] is None and x["ratings"] is None
    # settlement "T+2" and make-whole "T+15 bps for any redemption" are not spreads
    x = edgar.extract_tranches("Settlement Date (T+2). 4.650% Senior Notes due 2031 | Size: | $1,000,000,000 | "
                               "Make-Whole: T+15 bps for any redemption prior to May 1, 2031")
    assert x["n_tranches"] == 1 and x["size_bn"] == 1.0 and x["spreads"] == [None]


def test_poll_offline_lists_and_extracts(monkeypatch):
    subs = {1326801: _fixture_sub(1326801), 1341439: _fixture_sub(1341439)}
    with open(os.path.join(FX, "fwp_meta_2026-04-30_d148113dfwp.htm"), encoding="utf-8", errors="replace") as f:
        meta_doc = f.read()
    fetched: list[str] = []

    def fake_doc(url):
        fetched.append(url)
        return meta_doc if url == META_FWP_URL else None

    monkeypatch.setattr(edgar, "submissions", lambda cik, use_cache=True: subs.get(cik))
    monkeypatch.setattr(edgar, "fetch_document", fake_doc)
    ciks = {k: edgar.CIK_WHITELIST[k] for k in (1326801, 1341439)}
    res = edgar.poll_detailed(since="2026-04-25", ciks=ciks)
    assert res["status"] == "ok" and res["checked"] == ["Meta Platforms", "Oracle"] and not res["failed"]
    rows = res["filings"]
    assert rows == sorted(rows, key=lambda r: (r["filed"], r["issuer"]), reverse=True)
    fwp = [r for r in rows if r["url"] == META_FWP_URL]
    assert len(fwp) == 1
    assert fwp[0]["status"] == "auto-extracted, not in tally" and fwp[0]["form"] == "FWP"
    assert close(fwp[0]["extracted"]["size_bn"], 25.0, tol=1e-6)
    assert fwp[0]["seed_match"].startswith("2026-04-30 Meta Platforms 25.0 USD")
    # the same-day 424B2 is listed but not fetched again (the FWP carries the pricing)
    b2 = [r for r in rows if r["form"] == "424B2" and r["filed"] in ("2026-04-30", "2026-05-01")]
    assert b2 and all(r["extracted"] is None and r["status"].startswith("listed") for r in b2)
    assert all(u == META_FWP_URL for u in fetched)
    # only debt-relevant 8-Ks (items 2.03 / 1.01) are listed
    for r in rows:
        if r["form"] == "8-K":
            assert "2.03" in r["items"] or "1.01" in r["items"], r
        assert r["status"].endswith("not in tally")
    json.dumps(res)
    assert edgar.poll(since="2026-04-25", ciks=ciks) == rows


def test_poll_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(edgar, "submissions", lambda cik, use_cache=True: None)
    res = edgar.poll_detailed(since="2026-10-13", ciks={1326801: edgar.CIK_WHITELIST[1326801]})
    assert res["status"] == "error" and res["filings"] == [] and res["failed"] == ["Meta Platforms"]
    assert edgar.poll(since="2026-10-13", ciks={1326801: edgar.CIK_WHITELIST[1326801]}) == []
    # a CIK whose name is not the whitelist's is dropped, never parsed
    monkeypatch.setattr(edgar, "submissions", lambda cik, use_cache=True: _fixture_sub(1341439))
    res = edgar.poll_detailed(since="2026-01-01", ciks={1326801: edgar.CIK_WHITELIST[1326801]})
    assert res["name_mismatch"] == ["Meta Platforms"] and res["filings"] == []


# ---------------------------------------------------------------------------
# Reviewer defects on the extractor and the poll (B2-1 .. B2-7, S1, S3, M1 .. M9)
# ---------------------------------------------------------------------------
def test_by_month_survives_a_deal_after_the_asof_month(seed):
    late = dict(seed, deals=seed["deals"] + [dict(seed["deals"][0], date="2026-11-02", included=True,
                                                   size_usd_bn=1.0, bucket="hyperscaler", rating_bucket="AA")],
                last_deal_date="2026-11-02")
    rows = seed_mod.by_month(late)                         # KeyError before B2-2
    assert rows[-1]["month"] == "2026-11" and rows[-1]["hyperscaler"] == 1.0
    assert seed_mod.by_month(late, key="rating_bucket")[-1]["AA"] == 1.0


def test_extractor_benchmark_follows_the_sheet_not_a_hard_coded_ust():
    X = edgar.extract_tranches
    cad = X("C$1,500,000,000 4.500% Notes due 2031 | Re-Offer Spread: | 2031 Notes: +50 bps versus the applicable "
            "Government of Canada curve (GoC Curve)")
    assert cad["tranches"][0]["benchmark"] == "GoC" and cad["spreads"] == [50.0]
    eur = X("€1,000,000,000 3.500% Notes due 2034 | Spread to Benchmark Bund: 2034 Notes: +114.8 bps")
    assert eur["tranches"][0]["benchmark"] == "Bund"
    gbp = X("£500,000,000 5.000% Notes due 2034 | Spread to Benchmark Gilt: | 2034 Notes: +60 bps")
    assert gbp["tranches"][0]["benchmark"] == "Gilt"
    jpy = X("¥100,000,000,000 2.412% Notes due 2031 | Spread to Reference Rate: 2031 Notes: +50 bps")
    assert jpy["tranches"][0]["benchmark"] == "swap"
    # no header: UST only for a USD (or currency-less) sheet, never for a non-USD one
    assert X("$500,000,000 5.000% Notes due 2034 | 2034 Notes: +60 bps")["tranches"][0]["benchmark"] == "UST"
    assert X("£500,000,000 5.000% Notes due 2034 | 2034 Notes: +60 bps")["tranches"][0]["benchmark"] is None
    # the Meta sheet still reads UST under its "Spread to Benchmark Treasury" header
    with open(os.path.join(FX, "fwp_meta_2026-04-30_d148113dfwp.htm"), encoding="utf-8", errors="replace") as f:
        meta = edgar.extract_tranches(edgar.html_to_text(f.read()))
    assert {t["benchmark"] for t in meta["tranches"]} == {"UST"} and meta["partial"] is False


def test_extractor_skips_existing_notes_and_keys_tranches_by_numeric_coupon():
    X = edgar.extract_tranches
    refi = X("$1,000,000,000 5.000% Senior Notes due 2035 | Use of Proceeds: to redeem all $1,250,000,000 of our "
             "outstanding 4.975% Senior Notes due 2026 | Spread to Benchmark Treasury: +102 bps")
    assert refi["n_tranches"] == 1 and refi["maturities"] == [2035] and refi["spreads"] == [102.0]      # S3
    iren = X("holders of our 3.50% Convertible Senior Notes due 2029 and our 3.25% Convertible Senior Notes due 2030 "
             "| $1,000,000,000 0.250% Convertible Senior Notes due 2032 | $1,000,000,000 1.000% Convertible Senior "
             "Notes due 2033")
    assert iren["maturities"] == [2032, 2033] and iren["size_bn"] == 2.0
    one = X("Pricing Term Sheet $3,000,000,000 4.55% Senior Notes due 2031 ... 4.550% Senior Notes due 2031 | "
            "Principal Amount: | $3,000,000,000 |")
    assert one["n_tranches"] == 1 and one["size_bn"] == 3.0 and one["coupons"] == [4.55]                 # M1
    # the label form needs the unit: "T+3" is a settlement convention, not a 3 bp spread (M2)
    assert X("2031 Notes: T+3 settlement | 4.550% Senior Notes due 2031")["spreads"] == [None]


def test_extractor_series_heads_column_amounts_frn_owner_and_partial():
    X = edgar.extract_tranches
    vistra = X("Series A Junior Subordinated Notes due 2057 | | Series B Junior Subordinated Notes due 2057 | "
               "Principal Amount: | | $850,000,000 | | $650,000,000")
    assert vistra["n_tranches"] == 2 and vistra["maturities"] == [2057, 2057]                          # M8 / B2-7
    assert [t["size_bn"] for t in vistra["tranches"]] == [0.85, 0.65] and vistra["size_bn"] == 1.5
    assert vistra["partial"] is False and vistra["coupons"] == [None, None]
    # two floaters with unlabelled SOFR lines: never "the first FRN without a spread" (M3)
    two = X("Floating Rate Notes due 2028 | Floating Rate Notes due 2030 | Interest Rate: Compounded SOFR plus "
            "0.80% per annum | Interest Rate: Compounded SOFR plus 0.44% per annum")
    assert two["spreads"] == [None, None]
    # ... but a floater named in the same cell owns its spread
    named = X("Floating Rate Notes due 2028 | Floating Rate Notes due 2030 | Coupon: In the case of the 2028 "
              "Floating Rate Notes, Compounded SOFR plus 0.80% per annum, and in the case of the 2030 Floating "
              "Rate Notes, Compounded SOFR plus 0.44% per annum")
    assert named["spreads"] == [80.0, 44.0] and {t["benchmark"] for t in named["tranches"]} == {"SOFR"}
    # a deal-total "Aggregate Principal Amount" far below several headings is not a tranche size (M9)
    agg = X("Security: 4.550% Senior Notes due 2031, 4.875% Senior Notes due 2033 | " + "x " * 160
            + "Aggregate Principal Amount: | $5,000,000,000 |")
    assert agg["size_bn"] is None and agg["n_sized"] == 0
    # an unsized tranche flags the headline as partial (B2-6)
    part = X("$2,000,000,000 4.000% Notes due 2030 | 4.500% Notes due 2035")
    assert part["partial"] is True and part["size_bn"] == 2.0 and part["n_sized"] == 1


class _Resp:
    def __init__(self, status_code: int, text: str = "", payload=None):
        self.status_code, self.text, self._payload = status_code, text, payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_rate_threshold_block_pauses_all_sec_requests(monkeypatch, tmp_path):
    monkeypatch.setattr(edgar.settings, "cache_dir", str(tmp_path))
    monkeypatch.setitem(edgar._blocked_until, "t", 0.0)
    calls: list[str] = []

    def blocked(url, headers=None, timeout=None, follow_redirects=True):
        calls.append(url)
        return _Resp(403, "Request Rate Threshold Exceeded")

    monkeypatch.setattr(edgar.httpx, "get", blocked)
    res = edgar.poll_detailed(since="2026-01-01")
    assert len(calls) == 1                                  # one 403, then every other request is skipped (S1)
    assert res["rate_limited"] is True and res["status"] == "error" and len(res["failed"]) == 24
    assert edgar.rate_limited()
    monkeypatch.setitem(edgar._blocked_until, "t", 0.0)
    assert not edgar.rate_limited()
    # the User-Agent refusal is reported per host and only for THIS run (B2-3, M6)
    def refused(url, headers=None, timeout=None, follow_redirects=True):
        return _Resp(403, "Your Request Originates from an Undeclared Automated Tool")
    monkeypatch.setattr(edgar.httpx, "get", refused)
    assert edgar.submissions(1326801, use_cache=False) is None
    assert edgar.doc_access_error() is None                 # data.sec.gov's refusal is not the document host's
    assert "data.sec.gov" in edgar._doc_access
    res = edgar.poll_detailed(since="2026-10-13", ciks={1326801: edgar.CIK_WHITELIST[1326801]})
    assert res["doc_access_error"] is None and res["failed"] == ["Meta Platforms"]


def test_submissions_and_documents_never_cache_bad_bodies(monkeypatch, tmp_path):
    monkeypatch.setattr(edgar.settings, "cache_dir", str(tmp_path))
    monkeypatch.setitem(edgar._blocked_until, "t", 0.0)
    good = _fixture_sub(1326801)
    monkeypatch.setattr(edgar.httpx, "get", lambda url, headers=None, timeout=None, follow_redirects=True:
                        _Resp(200, "{}", good))
    assert edgar.submissions(1326801)["name"] == "Meta Platforms, Inc."
    path = edgar._sub_path(1326801)
    os.utime(path, (0, 0))                                                        # expire the good copy
    monkeypatch.setattr(edgar.httpx, "get", lambda url, headers=None, timeout=None, follow_redirects=True:
                        _Resp(200, "{}", {}))
    sub = edgar.submissions(1326801)                                              # `{}` is not a submissions document (B2-4)
    assert sub["name"] == "Meta Platforms, Inc." and sub.get("_stale") is True
    assert json.load(open(path, encoding="utf-8"))["name"] == "Meta Platforms, Inc."
    # a transient error page served with 200 is not frozen as the filing (M4)
    monkeypatch.setattr(edgar.httpx, "get", lambda url, headers=None, timeout=None, follow_redirects=True:
                        _Resp(200, "<html><body>Service Unavailable</body></html>"))
    assert edgar.fetch_document("https://www.sec.gov/Archives/edgar/data/1/2/x.htm") is None
    with open(os.path.join(FX, "fwp_meta_2026-04-30_d148113dfwp.htm"), encoding="utf-8", errors="replace") as f:
        real_doc = f.read()
    monkeypatch.setattr(edgar.httpx, "get", lambda url, headers=None, timeout=None, follow_redirects=True:
                        _Resp(200, real_doc))
    assert edgar.fetch_document("https://www.sec.gov/Archives/edgar/data/1/2/x.htm") == real_doc


def test_poll_bookkeeping_doc_failures_empty_primary_doc_and_explicit_empty_whitelist(monkeypatch):
    sub = _fixture_sub(1326801)
    monkeypatch.setattr(edgar, "submissions", lambda cik, use_cache=True: sub)
    monkeypatch.setattr(edgar, "fetch_document", lambda url: None)
    res = edgar.poll_detailed(since="2026-04-25", ciks={1326801: edgar.CIK_WHITELIST[1326801]})
    assert res["doc_failed"] >= 1 and res["status"] == "stale"                   # a failed document fetch degrades (M7)
    assert all(r["status"] == "listed; document fetch failed; not in tally" for r in res["filings"] if r["form"] == "FWP")
    blank = json.loads(json.dumps(sub))
    i = blank["filings"]["recent"]["form"].index("FWP")
    blank["filings"]["recent"]["primaryDocument"][i] = ""
    monkeypatch.setattr(edgar, "submissions", lambda cik, use_cache=True: blank)
    fetched: list[str] = []
    monkeypatch.setattr(edgar, "fetch_document", lambda url: fetched.append(url))
    res = edgar.poll_detailed(since="2026-04-25", ciks={1326801: edgar.CIK_WHITELIST[1326801]})
    fwp = [r for r in res["filings"] if r["form"] == "FWP" and r["filed"] == "2026-04-30"]
    assert fwp and fwp[0]["status"] == "listed; no primary document; not in tally"   # B2-13
    assert not any(u.endswith("/") for u in fetched)
    assert edgar.poll_detailed(since="2026-01-01", ciks={})["checked"] == []          # B2-14: {} means nothing
