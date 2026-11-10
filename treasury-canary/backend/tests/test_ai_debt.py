"""Merge-blocking gate tests for GET /ai-debt (studies/ai_debt_flows/BUILD.md),
offline: the production path — fetch_inputs() through every source module,
then build_ai_debt() — runs against the fixtures the source builders saved
under tests/fixtures/ai_debt plus the frozen seed and event log. Every network
call is monkeypatched at the transport layer (fred_csv._fetch_text /
_http_get_bytes, edgar_debt.submissions / fetch_document, the auctions
fetcher), so the parsers, the status plumbing and the assembly are the real
ones.

Gate rows (BUILD.md): seed reproduces the frozen tally and the memo's §3a/§3b/
§3c tables; tranche sums re-derive the parsed FWP headlines; share denominators
USD-only and FX per row; Z.1 FA/FU never mixed and the fixture ratio asserted;
TIC Grand Total vs All Countries labelled with LT-only AND bills-inclusive Japan
flows of the fixture's signs; BoJ identity every month; MOF trust accounts
+12.23 with header-mapped columns; MSPD class sum == total every month; EDGAR
whitelist names + the Meta 2026-04-30 FWP extraction; CCC-B gap on matching
dates; BDC p_nav; events provenance + URL; payload json-serialisable, every
block carries a status, numbers carry sources, nulls never zeros.

Fixture-known statuses: crowding is "error" on the pure fixture set because
DGS10 / T10YIE / TREAST have no fixture (their readings must be null, never 0);
one test substitutes stand-in series for those three ids purely to prove the
all-ok path — none of their values is ever asserted."""
from __future__ import annotations

import csv
import io
import json
import os
import time

import pytest

from app.metrics import ai_debt as m
from app.sources import ai_debt_seed as seed_mod
from app.sources import boj_mof, breaking, edgar_debt as edgar, fred_csv, public_funds as pf, tic, treasury_supply, z1

FX = os.path.join(os.path.dirname(__file__), "fixtures", "ai_debt")
META_FWP_URL = "https://www.sec.gov/Archives/edgar/data/1326801/000119312526197902/d148113dfwp.htm"
_FILES = {
    tic.CSLT_URL: "tic_cslt_mini.zip",
    boj_mof.BOJ_URL: "boj_bp_m_en_mini.zip",
    boj_mof.MOF_MONTHB3_URL: "mof_monthb3_trim.csv",
    boj_mof.MOF_WEEK_URL: "mof_week_trim.csv",
    boj_mof.MOF_JGB_ALL_URL: "mof_jgbcm_trim.csv",
    boj_mof.MOF_JGB_CUR_URL: "mof_jgbcme.csv",
    pf.GPIF_URL: "gpif_holdings_fixture.xlsx",
    pf.IMF_PIP_URL: "gpif_imf_pip_jpn_usa_trim.xml",
    breaking.EBP_URL: "ebp_fed_trim.csv",
    breaking.OFR_FSI_URL: "ofr_fsi_trim.csv",
}
_YAHOO = {breaking.yahoo_url(s): f"bdc_yahoo_{'MOVE' if s == breaking.MOVE_SYMBOL else s}.json"
          for s in breaking.BDC_TICKERS + [breaking.MOVE_SYMBOL]}
_NO_FIXTURE_YIELDS = ("DGS10", "T10YIE", "TREAST")
AUCTION = [{"auction_date": "2026-10-08", "security_type": "Bond", "security_term": "29-Year 10-Month",
            "bid_to_cover": 2.54, "indirect_pct": 72.3, "dealer_pct": 10.0, "direct_pct": 17.7,
            "high_yield": 5.618},
           {"auction_date": "2026-10-09", "security_type": "Note", "security_term": "10-Year",
            "bid_to_cover": 2.4, "indirect_pct": 70.1, "dealer_pct": 12.0, "direct_pct": 17.9,
            "high_yield": 5.21}]

# studies/ai-debt-flows.md §3a (bucket x year), §3b (rating x year), §3c (shares); $bn to 1 dp
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
    "not-captured": (0.0, 10.5, 26.0),        # 8.5 printed + the re-included CoreWeave $2.0bn (BUILD.md)
}
MEMO_SHARE_PCT = {"2024": 0.85, "2025": 4.2, "2026": 7.2}
SIFMA = {"2024": 1972.7, "2025": 2218.6, "2026": 2195.1}
HEADLINES = [("2025-10-30", "Meta Platforms", "USD", 30.0), ("2026-04-30", "Meta Platforms", "USD", 25.0),
             ("2026-02-02", "Oracle", "USD", 25.0), ("2026-06-15", "Nvidia", "USD", 25.0),
             ("2026-06-08", "Amazon", "CAD", 14.0)]


def _fx(name: str) -> bytes:
    return open(os.path.join(FX, name), "rb").read()


def _sub(cik: int) -> dict:
    with open(os.path.join(FX, f"edgar_submissions_CIK{cik:010d}.json"), encoding="utf-8") as f:
        return json.load(f)


def close(a, b, tol: float = 0.05) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol + 1e-9


def patch_offline(mp, cache_dir, countries=("japan",), stand_ins: bool = False, network: bool = True) -> None:
    """Answer every transport call from the fixtures. countries=None keeps the
    full TIC list (the un-fixtured rows must come back null); stand_ins serves
    the DGS30 fixture under the three un-fixtured yield ids (status plumbing
    only); network=False fails everything (no fixtures, no cache)."""
    mp.setattr(fred_csv.settings, "cache_dir", str(cache_dir))

    def fake_text(series_id, start):
        if not network:
            return None
        sid = "DGS30" if stand_ins and series_id in _NO_FIXTURE_YIELDS else series_id
        for pat in (f"fred_{sid}.csv", f"oas_fred_{sid}.csv"):
            p = os.path.join(FX, pat)
            if os.path.exists(p):
                return open(p, encoding="utf-8").read()
        return None

    def fake_bytes(u, headers=None):
        if not network:
            return None
        if u.startswith(treasury_supply.MSPD_URL.split("?")[0]):
            return _fx("mspd_trim.json")
        name = _FILES.get(u) or _YAHOO.get(u)
        return _fx(name) if name else None

    mp.setattr(fred_csv, "_fetch_text", fake_text)
    mp.setattr(fred_csv, "_http_get_bytes", fake_bytes)
    fred_csv._status.clear()
    if countries is not None:
        mp.setattr(tic, "COUNTRIES", [c for c in tic.COUNTRIES if c[0] in countries])
    subs = {1326801: _sub(1326801), 1341439: _sub(1341439)} if network else {}
    meta_doc = open(os.path.join(FX, "fwp_meta_2026-04-30_d148113dfwp.htm"), encoding="utf-8", errors="replace").read()
    mp.setattr(edgar, "submissions", lambda cik, use_cache=True: subs.get(cik))
    mp.setattr(edgar, "fetch_document", lambda url: meta_doc if network and url == META_FWP_URL else None)
    mp.setattr(edgar, "CIK_WHITELIST", {k: edgar.CIK_WHITELIST[k] for k in (1326801, 1341439)})
    mp.setattr(treasury_supply, "fetch_recent_auctions", lambda limit=60: list(AUCTION) if network else [])


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """One production-path build on the pure fixtures, shared by the gate tests."""
    with pytest.MonkeyPatch.context() as mp:
        patch_offline(mp, tmp_path_factory.mktemp("cache"))
        inputs = m.fetch_inputs()
        return inputs, m.build_ai_debt(inputs)


@pytest.fixture(scope="module")
def payload(built):
    return built[1]


@pytest.fixture(scope="module")
def inputs(built):
    return built[0]


@pytest.fixture
def offline(monkeypatch, tmp_path):
    patch_offline(monkeypatch, tmp_path)
    return tmp_path


def _readings(node, path="payload"):
    """Every dict carrying a `latest` (a reading) with its path."""
    if isinstance(node, dict):
        if "latest" in node:
            yield path, node
        for k, v in node.items():
            yield from _readings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _readings(v, f"{path}[{i}]")


def _numeric_leaves(node, path="", skip=()):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in skip:
                continue
            yield from _numeric_leaves(v, f"{path}.{k}", skip)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _numeric_leaves(v, f"{path}[{i}]", skip)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        yield path, node


# ---------------------------------------------------------------------------
# payload shape: json, statuses, bases, sources
# ---------------------------------------------------------------------------
def test_payload_json_every_block_status_basis_and_source(payload):
    json.dumps(payload, allow_nan=False)                 # Starlette renders with allow_nan=False
    assert set(payload["status"]) == set(m.BLOCKS) | {"overall"}
    for b in m.BLOCKS:
        blk = payload[b]
        assert blk["status"] in ("ok", "stale", "error"), b
        assert payload["status"][b] == blk["status"]
        assert blk["basis"] and blk["src"], b
    assert payload["basis"] and set(payload["basis"]) >= {"issuance", "holders", "foreign", "japan", "breaking"}
    assert payload["generated"] and payload["asof"] == "2026-10-14"      # latest daily print in the fixtures
    # fixture-known statuses: everything loads except the three un-fixtured yield ids
    assert payload["status"] == {"issuance": "ok", "holders": "ok", "foreign_bid": "ok", "japan": "ok",
                                 "public_funds": "ok", "crowding": "error", "breaking": "ok", "overall": "error"}
    assert payload["crowding"]["status_detail"]["dgs10"] == "error"
    assert payload["crowding"]["yields"]["dgs10"]["latest"] is None            # null, never 0
    assert payload["crowding"]["yields"]["dgs30"]["latest"] == 5.56
    # every reading carries a source URL
    for path, r in _readings(payload):
        assert r.get("src"), path
    # the sources map: every tag resolves to a URL (repo files resolve to the repository blob)
    src = payload["sources"]
    assert len(src) >= 60
    for tag, url in src.items():
        assert url.startswith("https://"), (tag, url)
    assert src["C-DEALS"].endswith("studies/ai_debt_flows/data/deals.csv") and src["EVENTS"].endswith("ai_debt_events.json")
    assert payload["issuance"]["src"]["seed"] == src["C-DEALS"]
    for tag in ("C-DEALS", "SIFMA-PDF", "FWP-META-2604", "EDGAR-SUB", "FRED-FA893", "FRED-FU893", "TIC-CSLT",
                "FRED-TIC-JP-TSY", "BOJ-BP", "MOF-SOV", "MOF-B3", "MOF-WEEK", "MOF-JGB", "GPIF", "IMF-PIP", "MSPD",
                "ACM", "FRED-KW", "FRED-DGS30", "FRED-TREAST", "TD-AUCTIONS", "FRED-CCC", "FRED-BAA10Y", "FED-EBP",
                "OFR-FSI", "MOVE-YH", "BDC-YH", "ARCC-10Q", "BXSL-8K", "GBDC-8K", "EVENTS", "FWP-NVDA"):
        assert tag in src, tag
    assert src["TIC-CSLT"] == tic.CSLT_URL and src["GPIF"] == pf.GPIF_URL and src["FED-EBP"] == breaking.EBP_URL
    assert "watch" in payload["note"] and "warning" not in payload["note"]


def test_honesty_box_is_the_spec_text_verbatim(payload):
    hon = payload["honesty"]
    assert hon[:5] == m.HONESTY
    assert hon[0] == "Scoping rev 1, not a study: nothing pre-registered or graded."
    assert hon[1].startswith("Tally = gross issuance at pricing, not net of redemptions; non-USD legs at trade-date FX;")
    assert "new EDGAR filings are auto-extracted and NOT in the tally until reviewed." in hon[1]
    assert hon[2].startswith("TIC attributes by custody country, not beneficial owner;")
    assert hon[2].endswith("MOF trust accounts, Z.1 pension sectors and annual fund lists.")
    assert hon[3] == ("FRED serves 3 years of ICE OAS history; CDS and single-name prices are dated press "
                      "prints, not a feed.")
    assert hon[4] == "Nothing here is a forecast."
    assert any("OBDC, FSK and MAIN" in h for h in hon[5:])     # accuracy additions follow the verbatim text
    # the BDC line is derived from the NAV table, never a frozen string (B4-V-07)
    assert hon[5].startswith("BDC NAVs: ARCC (10-Q, as of 2026-06-30), BXSL (8-K, as of 2026-06-30), GBDC (8-K, as of 2026-06-30)")


# ---------------------------------------------------------------------------
# issuance: the seed reproduces the frozen tally
# ---------------------------------------------------------------------------
def test_seed_reproduces_the_frozen_tally(payload):
    iss = payload["issuance"]
    assert iss["status"] == "ok" and iss["seed_rev"] == "rev 1" and iss["asof"] == "2026-10-15"
    assert close(iss["total_usd_bn"], 682.5) and iss["n_included"] == 103
    tot = iss["totals_by_year"]
    assert set(tot) == set(MEMO_TOTALS) and all(close(tot[y], v) for y, v in MEMO_TOTALS.items())
    assert close(sum(tot.values()), 682.5)
    tab = iss["by_bucket_year"]
    assert set(tab) == set(MEMO_BUCKETS)
    for b, row in MEMO_BUCKETS.items():
        for y, v in zip(("2024", "2025", "2026"), row):
            assert close(tab[b][y], v), (b, y, tab[b][y], v)
    rat = iss["by_rating_year"]
    assert set(rat) == set(MEMO_RATINGS)
    for rb, row in MEMO_RATINGS.items():
        for y, v in zip(("2024", "2025", "2026"), row):
            assert close(rat[rb][y], v), (rb, y, rat[rb][y], v)
    for y in tot:
        assert close(sum(tab[b][y] for b in tab), tot[y]) and close(sum(rat[r][y] for r in rat), tot[y])
    for y, pct in MEMO_SHARE_PCT.items():
        assert close(iss["share"][y]["pct_hyperscaler"], pct) and iss["share"][y]["sifma_us_corp_bn"] == SIFMA[y]
        assert iss["share"][y]["src"].startswith("https://www.sifma.org/")
    deals = iss["deals"]
    assert len(deals) == 123 and sum(d["included"] for d in deals) == 103
    for d in deals:
        if d["included"]:
            assert d["src"] and d["src"].startswith("http"), d
            assert d["verif"] in ("P", "R", "S") and d["size_usd_bn"] > 0, d
        assert d["size_bn"] != 0.0 and d["size_usd_bn"] != 0.0, d      # a placeholder is null, not 0
    assert iss["by_month"][0]["month"] == "2024-01" and iss["by_month"][-1]["month"] == "2026-10"
    assert set(iss["by_month_rating"][0]) == {"month", *iss["rating_buckets"]}
    assert iss["verif"]["basis"] == "% of included $bn" and 19 < iss["verif"]["S"] < 22
    assert set(iss["flag_rules"]) == {"refi", "spv", "convert", "non_usd"}


@pytest.mark.parametrize("date,issuer,ccy,headline", HEADLINES)
def test_tranche_sums_rederive_the_headline(payload, date, issuer, ccy, headline):
    d = next(x for x in payload["issuance"]["deals"] if x["date"] == date and x["issuer"] == issuer)
    assert d["included"] and d["ccy"] == ccy and d["verif"] == "P" and d["size_bn"] == headline
    sizes = seed_mod.tranche_sizes(d["tranches"])
    assert sizes and close(sum(sizes), headline, tol=1e-6), (d["tranches"], sizes)
    if ccy == "CAD":            # C$14.0bn at the recorded FX -> US$10.04bn
        assert d["fx_basis"] == "FRED DEXCAUS on/before 2026-06-08" and close(d["size_usd_bn"], 10.037, tol=0.001)


def test_share_denominators_are_usd_only_and_non_usd_legs_carry_fx(payload):
    iss = payload["issuance"]
    for y, s in iss["share"].items():
        assert s["hyperscaler_usd_bn"] <= s["all_ai_usd_bn"] <= s["all_ai_bn"], y
        assert close(s["pct_all"], 100.0 * s["all_ai_usd_bn"] / s["sifma_us_corp_bn"], tol=0.01), y
        assert close(s["pct_hyperscaler"], 100.0 * s["hyperscaler_usd_bn"] / s["sifma_us_corp_bn"], tol=0.01), y
        assert "USD legs" in s["basis"]
    assert iss["share"]["2026"]["all_ai_bn"] > iss["share"]["2026"]["all_ai_usd_bn"]
    assert close(iss["share"]["2026"]["hyperscaler_usd_bn"], 157.0)
    legs = [d for d in iss["deals"] if d["included"] and "non_usd" in d["flags"]]
    assert len(legs) == 19
    for d in legs:
        assert d["ccy"] != "USD" and d["fx_basis"].startswith("FRED DEX") and d["size_usd_bn"] != d["size_bn"], d
    for d in iss["deals"]:
        if d["included"] and d["ccy"] == "USD":
            assert d["size_usd_bn"] == d["size_bn"] and "non_usd" not in d["flags"], d
    den = iss["denominators"]
    assert den["sifma_us_corp_bn"] == SIFMA and all(u.startswith("https://www.sifma.org/") for u in den["src"].values())
    assert den["ig_hy_2q26"]["total_bn"] == 732.6


def test_vs_treasury_pairs_each_window_consistently(payload, inputs):
    vt = payload["issuance"]["vs_treasury"]
    assert {"FY2025", "FY2026", "CY2025", "CY2026"} <= set(vt)
    inc = [d for d in payload["issuance"]["deals"] if d["included"]]
    for key, row in vt.items():
        expect = round(sum(d["size_usd_bn"] for d in inc if row["from"] < d["date"] <= row["to"]), 2)
        assert row["ai_bn"] == expect, key
        assert row["pct"] == round(100.0 * row["ai_bn"] / row["net_marketable_ust_bn"], 1), key
        assert "GROSS" in row["basis"] and "NET" in row["basis"] and "gross of Fed" in row["basis"], key
    # CY2025 = the memo's 2025 pairing: the tally's 2025 column over CY2025 net marketable (+1,991)
    assert vt["CY2025"]["ai_bn"] == payload["issuance"]["totals_by_year"]["2025"]
    assert close(vt["CY2025"]["net_marketable_ust_bn"], 1991, tol=3) and vt["CY2025"]["complete"]
    assert vt["CY2025"]["pct"] == 12.2
    assert vt["FY2026"]["from"] == "2025-09-30" and vt["FY2026"]["to"] == "2026-09-30" and vt["FY2026"]["complete"]
    assert 2100 < vt["FY2026"]["net_marketable_ust_bn"] < 2140
    assert vt["CY2026"]["complete"] is False and vt["CY2026"]["to"] == "2026-09-30"


# ---------------------------------------------------------------------------
# holders: Z.1 units
# ---------------------------------------------------------------------------
def test_z1_fa_fu_never_mixed_and_fixture_ratio_asserted(payload):
    fa = z1.Series("BOGZ1FA893063005Q", [1.0, 2.0])
    fu = z1.Series("BOGZ1FU893063005Q", [1.0, 2.0])
    with pytest.raises(ValueError):
        z1.sum_flows([fa, fu])
    with pytest.raises(ValueError):
        z1.combine(fa, z1.Series("BOGZ1FL893063005Q", [1.0, 2.0]), "-")
    h = payload["holders"]
    assert h["status"] == "ok" and h["asof"] == "2026Q2" and h["unit"] == "$bn"
    c = h["z1"]["checks"]
    assert 4.0 <= c["fa_over_fu_latest"] <= 4.6 and 4.0 <= c["fa_over_fu_4q"] <= 4.5    # SAAR / unannualised
    assert c["units_consistent"] is True and abs(c["partition_gap_pct_latest"]) < 1.0
    lv = h["z1"]["levels"]
    assert lv["all_sectors"] == pytest.approx(18115.721)
    assert lv["life_insurers"] == pytest.approx(3944.186) and lv["etfs"] == pytest.approx(1518.085)
    assert lv["rest_of_world"] == pytest.approx(5195.694, abs=0.01)        # exact: the MA line is subtracted (D6)
    assert h["z1"]["src"].endswith("id=BOGZ1FL893063005Q")                     # a fetchable link, not a pattern (B5-16)
    sectors = [s["key"] for s in h["z1"]["sectors"] if s["in_partition"]]
    assert sum(lv[k] for k in sectors) == pytest.approx(lv["all_sectors"], rel=0.01)
    assert {s["key"] for s in h["z1"]["sectors"] if s["derived_level"]} == {"rest_of_world", "households",
                                                                           "other_financial", "other_depository"}
    fl = h["z1"]["flows_saar_last4"]
    assert len(fl["rest_of_world"]) == 4 and fl["rest_of_world"][-1] == pytest.approx(435.444)
    assert h["z1"]["flows_quarters"] == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    pens = h["z1"]["pensions"]
    assert pens["private"]["level"] == pytest.approx(897.307) and pens["private"]["flow_saar"] == pytest.approx(23.448)
    assert pens["state_local"]["level"] == pytest.approx(634.574) and pens["private"]["asof"] == "2026Q2"
    assert "SAAR" in h["note"] and "NOT quarterly" in h["note"] and "consistent" in h["note"]
    nfc = h["z1"]["nfc_issuance"]
    assert nfc["saar_latest"] == pytest.approx(327.0) and nfc["unadj_latest"] == pytest.approx(81.75)
    assert nfc["src"].endswith("id=BOGZ1FA103163005Q")


# ---------------------------------------------------------------------------
# foreign bid: TIC labels, LT vs bills-inclusive
# ---------------------------------------------------------------------------
def test_tic_labels_and_lt_vs_bills_inclusive_japan_flows(payload):
    fb = payload["foreign_bid"]
    assert fb["status"] == "ok" and fb["asof"] == "2026-07" and fb["unit"] == "$bn"
    assert "international and regional organizations" in fb["labels"]["grand_total"]
    assert "excludes" in fb["labels"]["all_countries"]
    aggs = {a["key"]: a for a in fb["aggregates"]}
    assert aggs["grand_total"]["label"] != aggs["all_countries"]["label"]
    assert aggs["grand_total"]["corp_pos"] != aggs["all_countries"]["corp_pos"]
    assert aggs["grand_total"]["corp_pos"] == pytest.approx(5272.819)
    assert aggs["grand_total"]["corp_net_12m"] == pytest.approx(452.0, abs=0.1)
    assert aggs["grand_total"]["corp_share_of_lt"] == pytest.approx(40.4, abs=0.05)
    jp = next(c for c in fb["countries"] if c["key"] == "japan")
    assert jp["code"] == "42609" and jp["custody_centre"] is False and jp["status"] == "ok"
    assert jp["treas_net_12m"] == pytest.approx(4.0, abs=0.05)              # LT only
    assert jp["corp_net_12m"] == pytest.approx(12.5, abs=0.05)
    assert jp["treas_pos"] == pytest.approx(1023.754) and jp["corp_pos"] == pytest.approx(312.507)
    assert len(jp["treas_spark"]) == 24 and len(jp["corp_spark"]) == 24
    bi = fb["bills_inclusive"]
    assert bi["asof"] == "2026-07" and bi["status"] == "ok" and bi["src"] == tic.CSLT_URL
    assert bi["japan_lt_12m"] == pytest.approx(4.0, abs=0.05) and round(bi["japan_12m"], 1) == -48.6
    assert bi["japan_lt_12m"] > 0 > bi["japan_12m"]                           # the sign flips with bills
    assert round(bi["all_12m"], 1) == 291.8 and round(bi["all_lt_12m"], 1) == 240.1
    assert bi["grand_total_12m"] != bi["all_12m"]
    assert "bills included" in bi["labels"]["all"] and "bills excluded" in bi["labels"]["lt"]
    s = fb["series"]
    assert s["months"][-1] == "2026-07" and len(s["japan"]["treas"]) == len(s["months"])
    assert {"grand_total", "official", "non_official", "all_countries", "japan"} <= set(s)


# ---------------------------------------------------------------------------
# Japan: BoJ identity, MOF trust accounts and header mapping
# ---------------------------------------------------------------------------
def test_boj_residual_equals_total_minus_sovereign_every_month(payload):
    boj = payload["japan"]["boj"]
    assert boj["status"] == "ok" and boj["unit"] == "JPY trn" and boj["asof"] == "2026-08"
    assert len(boj["months"]) == 36
    for t, s, r in zip(boj["total"], boj["sovereign"], boj["nonsovereign"]):
        assert t is not None and s is not None and r == pytest.approx(t - s, abs=1e-4)
    s12 = boj["sum_12m"]
    assert s12["total"] == pytest.approx(s12["sovereign"] + s12["nonsovereign"], abs=1e-3)
    assert s12["total"] == pytest.approx(-2.54, abs=0.01) and s12["sovereign"] < 0 < s12["nonsovereign"]
    assert boj["rolling_12m"]["total"][-1] == pytest.approx(s12["total"])
    assert boj["src"] == boj_mof.BOJ_URL and "sovereign_definition" in boj["src_detail"]


def _swap_groups(raw: bytes, a: str, b: str) -> bytes:
    """Swap the 3-column (acq/disp/net) blocks headed `a` and `b` — headers AND
    data — so only name-based mapping can get the series right."""
    rows = list(csv.reader(io.StringIO(raw.decode("cp932"))))
    net_row = next(i for i, r in enumerate(rows) if sum(1 for c in r if c.strip() == "Net") >= 5)
    name_row = next(i for i, r in enumerate(rows[:net_row]) if any(a in c for c in r))
    ca = next(j for j, c in enumerate(rows[name_row]) if a in c)
    cb = next(j for j, c in enumerate(rows[name_row]) if b in c)
    for r in rows:
        if len(r) > max(ca, cb) + 2:
            for k in range(3):
                r[ca + k], r[cb + k] = r[cb + k], r[ca + k]
    sio = io.StringIO()
    csv.writer(sio, lineterminator="\r\n").writerows(rows)
    return sio.getvalue().encode("cp932")


def test_mof_trust_accounts_12m_and_columns_mapped_by_header(payload):
    jp = payload["japan"]
    mof = jp["mof_by_type"]
    assert mof["status"] == "ok" and mof["asof"] == "2026-09" and mof["unit"] == "JPY trn"
    assert round(mof["sum_12m"]["trust_accounts"], 2) == 12.23
    assert round(mof["sum_12m"]["all"], 2) == -5.09 and round(mof["sum_12m"]["banks"], 2) == -12.83
    assert round(mof["sum_12m"]["life"], 2) == -2.11 and round(mof["sum_12m"]["inv_trusts"], 2) == -1.5
    assert mof["rolling_12m"]["trust_accounts"][-1] == pytest.approx(mof["sum_12m"]["trust_accounts"])
    assert mof["column_map"]["trust_accounts"]["header"].startswith("Banks and Trust banks")
    assert round(payload["public_funds"]["trust_accounts_12m_jpy_trn"], 2) == 12.23
    assert payload["public_funds"]["trust_accounts_asof"] == "2026-09"
    assert payload["public_funds"]["trust_accounts_src"] == boj_mof.MOF_MONTHB3_URL
    raw = _fx("mof_monthb3_trim.csv")
    base = boj_mof.parse_monthb3(raw)
    swapped = boj_mof.parse_monthb3(_swap_groups(raw, "Life Insurance Companies", "Banks and Trust banks"))
    for key in boj_mof.MOF_INVESTOR_HEADERS:
        assert swapped[key] == base[key], key
    assert swapped["column_map"]["life"]["net_column"] != base["column_map"]["life"]["net_column"]
    with pytest.raises(ValueError):
        boj_mof.parse_monthb3(raw.replace("Life Insurance Companies".encode("cp932"), b"Something Else"))
    assert jp["mof_weekly"]["asof"] == "2026-10-03" and jp["mof_weekly"]["net"][-1] == pytest.approx(-0.3476)
    assert jp["jgb"]["asof"] == "2026-10-14" and jp["jgb"]["y10_latest"] == 3.015 and jp["jgb"]["y30_latest"] == 4.072


def test_japan_read_is_derived_from_the_signs_that_loaded(payload):
    read = payload["japan"]["read"]
    assert "repatriation, not substitution" in read
    assert "trust accounts (pension money)" in read and "pension and public funds" in read
    assert "12m to 2026-08" in read and "-48.6" in read and "+12.23" in read
    assert "warning" not in read.lower()
    # B4-4: the MOF clause names every net-buying group; "the only" is never claimed while another is positive
    assert "largest buying with trust accounts (pension money)" in read and "alongside financial instruments firms" in read
    assert "the only net-buying group" not in read
    one_buyer = m.japan_read({"total_12m": -2.5, "sovereign_12m": -3.2, "nonsovereign_12m": 0.7, "asof": "x"},
                             {"asof": "y", "all_12m": -5.0, "banks_12m": -12.8, "trust_accounts_12m": 12.2, "life_12m": -2.1,
                              "inv_trusts_12m": -1.5, "fin_instruments_12m": -1.0}, None, None)
    assert "the only net-buying group" in one_buyer and "alongside" not in one_buyer
    # B4-V-01: every sign pattern has its own sentence
    rd = lambda sov, non: m.japan_read({"total_12m": sov + non, "sovereign_12m": sov, "nonsovereign_12m": non, "asof": "x"}, None, None, None)
    assert "net buyer of US sovereign debt and a net seller" in rd(1.0, -1.0) and "seller of both" not in rd(1.0, -1.0)
    assert "net buyer of US sovereign debt and a net seller" in rd(1.0, -3.0)
    assert "matches or exceeds" in rd(-2.0, 2.0) and "seller of both" not in rd(-2.0, 2.0)
    assert "matches or exceeds" in rd(-2.0, 3.0)
    assert "seller of both" in rd(-2.0, -1.0) and "repatriation across the board" in rd(-2.0, -1.0)
    assert "net buyer of both" in rd(0.0, 0.0)
    assert "repatriation, not substitution" in rd(-3.0, 0.5) and "pension and public funds" not in rd(-3.0, 0.5)
    assert "not evaluable" in m.japan_read(None, None, None, None)
    assert "not evaluable" in m.japan_read({"total_12m": -1.0, "sovereign_12m": None, "nonsovereign_12m": None,
                                            "asof": "2026-08"}, None, None, None)
    both = m.japan_read({"total_12m": 2.0, "sovereign_12m": 1.0, "nonsovereign_12m": 1.0, "asof": "x"}, None, None, None)
    assert "net buyer of both" in both


# ---------------------------------------------------------------------------
# public funds: visibility derived from what loaded
# ---------------------------------------------------------------------------
def test_public_funds_block_and_visibility(payload):
    p = payload["public_funds"]
    assert p["status"] == "ok" and set(p["status_detail"]) == {"gpif", "imf_pip", "mof", "z1", "tic"}
    assert len(p["can_see"]) == 5 and not any(c.startswith("NOT LOADED") for c in p["cannot_see"])
    assert len(p["cannot_see"]) == len(pf.CANNOT_SEE)
    assert any("specific bond" in c for c in p["cannot_see"])
    z = p["z1_pensions"]
    assert z["private"]["level"] == pytest.approx(897.307) and z["private"]["asof"] == "2026Q2"
    assert z["state_local"]["flow_saar"] is not None and len(z["private"]["flow_saar_last4"]) == 4
    assert z["units_consistent"] is True and "SAAR" in z["unit"] and z["src"]
    t = p["tic_official_corp"]
    assert t["share_of_foreign_held"] == 6.0 and t["pos"] == 316.007 and t["net_12m"] is not None and t["src"]
    g = p["gpif"]
    assert g["asof"] == "2026-03-31" and g["hyperscaler_plus_nvidia_share_pct"] == 0.044 and g["lines_total"] == 10040
    assert g["ust_jpy_trn"] == 36.841 and g["src"] == pf.GPIF_URL
    assert {r["issuer"] for r in g["ai_issuers"]} >= {"Oracle", "Amazon", "Alphabet", "Meta Platforms", "Nvidia"}
    assert p["imf_pip_japan"]["total_usd_bn"] == 1214.691 and p["asof"]["imf_pip"] == "2025-S2"


# ---------------------------------------------------------------------------
# crowding: MSPD identity
# ---------------------------------------------------------------------------
def test_mspd_class_sum_equals_total_marketable_every_month(payload):
    c = payload["crowding"]
    um = c["ust_monthly"]
    assert um["status"] == "ok" and um["asof"] == "2026-09-30" and um["unit"] == "$bn" and len(um["months"]) == 37
    assert c["ust_checks"]["class_sum_equals_total"] is True
    for cs, tot, gap in zip(um["class_sum"], um["marketable"], um["gap_bn"]):
        assert cs is not None and tot is not None and abs(cs - tot) <= 0.001 and abs(gap) <= 0.001
    assert um["marketable"][-1] == pytest.approx(31834.878, abs=0.001)
    assert um["coupons"][-1] == pytest.approx(24713.142, abs=0.001) and um["bills"][-1] == pytest.approx(7118.145, abs=0.001)
    ust = c["ust"]
    assert set(ust) >= {"FY2024", "FY2025", "FY2026", "CY2024", "CY2025", "CY2026"}
    assert ust["CY2025"]["net_marketable"] == pytest.approx(1991, abs=3) and ust["CY2025"]["coupons"] == pytest.approx(1631, abs=3)
    assert ust["CY2025"]["bills"] == pytest.approx(360, abs=3) and ust["CY2025"]["complete"]
    assert 2100 < ust["FY2026"]["net_marketable"] < 2140 and ust["FY2026"]["from"] == "2025-09-30"
    assert ust["CY2026"]["complete"] is False and "incomplete" in ust["CY2026"]["basis"]
    assert "gross of Fed" in c["basis"]
    kw = c["term_premium"]["kw10"]
    assert kw["latest"] == 1.0729 and kw["asof"] == "2026-10-09" and kw["series"]["dates"][-1] >= "2026-10-09"
    assert c["term_premium"]["acm10"] is None and c["status_detail"]["acm10"] == "missing (optional)"
    assert c["auctions"] == [{"date": "2026-10-08", "tenor": "30y", "term": "29-Year 10-Month", "security_type": "Bond",
                              "high_yield": 5.618, "btc": 2.54, "indirect_pct": 72.3, "dealer_pct": 10.0,
                              "direct_pct": 17.7, "reopening": True},
                             {"date": "2026-10-09", "tenor": "10y", "term": "10-Year", "security_type": "Note",
                              "high_yield": 5.21, "btc": 2.4, "indirect_pct": 70.1, "dealer_pct": 12.0,
                              "direct_pct": 17.9, "reopening": False}]          # False = known term, no month part (B4-V-04)
    assert c["auctions_src"] == treasury_supply.AUCTION_SRC


# ---------------------------------------------------------------------------
# EDGAR: whitelist names and the Meta FWP through the payload
# ---------------------------------------------------------------------------
def test_edgar_whitelist_resolves_to_the_expected_names():
    """Unpatched module constant: all 24 CIKs against the names read live on 2026-10-15."""
    with open(os.path.join(FX, "edgar_names_2026-10-15.json"), encoding="utf-8") as f:
        names = json.load(f)["names"]
    assert len(edgar.CIK_WHITELIST) == 24
    for cik, (label, expected) in edgar.CIK_WHITELIST.items():
        assert str(cik) in names, (cik, label)
        assert edgar.verify_name({"name": names[str(cik)]}, expected), (cik, label, names[str(cik)])
    assert not edgar.verify_name({"name": names["1868941"]}, "Constellation Energy Corp")    # BUILD.md's wrong CIKs
    assert not edgar.verify_name({"name": names["1662684"]}, "Nebius Group N.V.")
    assert edgar.CIK_WHITELIST[1868275][0] == "Constellation Energy" and edgar.CIK_WHITELIST[1513845][0] == "Nebius"


def test_edgar_meta_fwp_extraction_through_the_payload(offline, inputs):
    # a poll window that contains the 2026-04-30 term sheet, assembled through the payload
    poll = edgar.poll_detailed(since="2026-04-25")
    p = m.build_ai_debt(dict(inputs, poll=poll))
    iss = p["issuance"]
    assert iss["status"] == "ok" and iss["new_filings_meta"]["checked"] == ["Meta Platforms", "Oracle"]
    rows = iss["new_filings"]
    fwp = [r for r in rows if r["url"] == META_FWP_URL]
    assert len(fwp) == 1 and fwp[0]["form"] == "FWP" and fwp[0]["filed"] == "2026-04-30"
    x = fwp[0]["extracted"]
    assert x["n_tranches"] == 6 and close(x["size_bn"], 25.0, tol=1e-6) and x["ccy"] == "USD"
    assert x["maturities"] == [2031, 2033, 2036, 2046, 2056, 2066]
    assert x["spreads"] == [53.0, 68.0, 90.0, 122.0, 132.0, 147.0]
    assert fwp[0]["status"] == "auto-extracted, not in tally"
    assert fwp[0]["seed_match"].startswith("2026-04-30 Meta Platforms 25.0 USD")
    assert all(r["status"].endswith("not in tally") for r in rows)
    assert iss["new_filings_meta"]["rate_limited"] is False and iss["new_filings_meta"]["doc_failed"] == 0
    json.dumps(p, allow_nan=False)


# ---------------------------------------------------------------------------
# breaking: gap on matching dates, BDC p_nav, events provenance
# ---------------------------------------------------------------------------
def test_breaking_gap_bdc_and_events(payload):
    b = payload["breaking"]
    assert b["status"] == "ok" and b["asof"] == "2026-10-14"
    sp = b["spreads"]
    assert sp["ccc"]["latest"] == 12.82 and sp["ccc"]["hi_2026"] == 12.82 and sp["b"]["latest"] == 3.29
    gap = b["ccc_b_gap"]
    assert gap["latest"] == 9.53 and gap["asof"] == "2026-10-14" and gap["end_2025"] == 5.84
    ccc = dict(zip(sp["ccc"]["series"]["dates"], sp["ccc"]["series"]["values"]))
    bb = dict(zip(sp["b"]["series"]["dates"], sp["b"]["series"]["values"]))
    assert gap["n_dates"] == len(gap["series"]["dates"]) > 0
    for d, v in zip(gap["series"]["dates"], gap["series"]["values"]):
        assert d in ccc and d in bb and ccc[d] is not None and bb[d] is not None
        assert v == round(ccc[d] - bb[d], 4)
    assert "src" in gap and gap["src"]["ccc"].endswith("id=BAMLH0A3HYC")
    rows = b["bdc"]
    assert [r["ticker"] for r in rows] == breaking.BDC_TICKERS
    for r in rows:
        assert r["price"] is not None and r["px_src"].startswith("https://query1.finance.yahoo.com/")
        if r["nav"] is None:
            assert r["p_nav"] is None and r["nav_src"] is None
        else:
            assert r["p_nav"] == round(r["price"] / r["nav"], 3)
            assert r["nav_src"].startswith("https://www.sec.gov/Archives/edgar/data/") and r["nav_asof"] == "2026-06-30"
    assert {r["ticker"] for r in rows if r["nav"] is not None} == {"ARCC", "BXSL", "GBDC"}
    assert b["bdc_basis"] == breaking.BDC_BASIS
    ev = b["events"]
    assert len(ev) >= 20
    for e in ev:
        assert e["provenance"] in breaking.PROVENANCE and e["src"].startswith("https://") and e["retrieved"]
        assert breaking.validate_event(e) == []
    pts = b["spread_at_issue_30y"]
    assert len(pts) == 15 and all(p["src"].endswith("fwp.htm") and "FWP" in p["basis"] for p in pts)
    assert b["ccc_b_gap"]["range_year"] == 2026 and b["ccc_b_gap"]["hi_ytd"] == b["ccc_b_gap"]["hi_2026"]   # B3-8
    assert sp["ccc"]["range_year"] == 2026 and sp["ccc"]["end_prior_year"] == sp["ccc"]["end_2025"]
    assert b["ebp"]["latest"] == pytest.approx(-0.3919, abs=1e-4) and b["ebp"]["series"]["dates"][-1] == "2026-09-01"
    assert b["ofr_fsi"]["latest"] == -2.139 and b["ofr_fsi"]["credit_latest"] == -0.982
    assert round(b["move"]["latest"], 2) == 102.56 and b["baa10y"]["latest"] == 1.46
    assert b["yields"]["ig"]["latest"] == 5.94 and b["yields"]["hy"]["latest"] == 8.20


# ---------------------------------------------------------------------------
# degradation: nulls not zeros, statuses propagate, stale never shows as ok
# ---------------------------------------------------------------------------
def test_no_network_build_is_null_not_zero_and_every_block_errors(monkeypatch, tmp_path):
    patch_offline(monkeypatch, tmp_path, network=False)
    p = m.build_ai_debt(m.fetch_inputs())
    json.dumps(p, allow_nan=False)
    assert set(p["status"].values()) == {"error"}
    assert p["asof"] is None and p["generated"]
    # the frozen pieces still ship (seed, events, NAV table, spread points), the live ones are null
    assert p["issuance"]["status_detail"] == {"seed": "ok", "new_filings": "error"}
    assert close(p["issuance"]["total_usd_bn"], 682.5) and p["issuance"]["new_filings"] == []
    assert p["issuance"]["vs_treasury"] is None
    assert p["holders"]["z1"] is None and "not loaded" in p["holders"]["note"]
    assert p["foreign_bid"]["countries"] is None and p["foreign_bid"]["bills_inclusive"]["japan_12m"] is None
    assert p["japan"]["boj"]["sum_12m"] == {"total": None, "sovereign": None, "nonsovereign": None}
    assert "not evaluable" in p["japan"]["read"]
    assert p["public_funds"]["trust_accounts_12m_jpy_trn"] is None and p["public_funds"]["can_see"] == []
    assert sum(c.startswith("NOT LOADED") for c in p["public_funds"]["cannot_see"]) == 5
    assert p["crowding"]["ust"] is None and p["crowding"]["yields"]["dgs30"]["latest"] is None
    assert p["crowding"]["auctions"] == [] and p["crowding"]["term_premium"]["acm10"] is None
    assert p["breaking"]["spreads"]["ccc"]["latest"] is None and p["breaking"]["ccc_b_gap"]["n_dates"] == 0
    assert all(r["price"] is None and r["p_nav"] is None for r in p["breaking"]["bdc"])
    assert p["breaking"]["status_detail"]["events"] == "ok" and len(p["breaking"]["events"]) >= 20
    for path, r in _readings(p):
        assert r["latest"] is None, path
    counts = {"n_dates", "n_dropped", "n_tranches", "n_sized", "window_months", "rev", "cik", "lines", "n_lines",
              "lines_total", "maturity", "bp", "nav", "net_column"}
    zeros = [(path, v) for b in m.BLOCKS if b != "issuance"
             for path, v in _numeric_leaves(p[b], b, skip=counts) if v == 0]
    assert zeros == [], zeros


def test_unfixtured_country_rows_are_null_and_the_block_says_error(monkeypatch, tmp_path):
    patch_offline(monkeypatch, tmp_path, countries=None)          # the full TIC list; only Japan is fixtured
    p = m.build_ai_debt(m.fetch_inputs())
    fb = p["foreign_bid"]
    assert fb["status"] == "error" and p["status"]["foreign_bid"] == "error"
    assert fb["status_detail"] == {"fred_tic": "error", "cslt_bills": "ok"}
    uk = next(c for c in fb["countries"] if c["key"] == "uk")
    assert uk["custody_centre"] and uk["status"] == "error"
    assert uk["treas_net_12m"] is None and uk["corp_pos"] is None and set(uk["treas_spark"]) == {None}
    jp = next(c for c in fb["countries"] if c["key"] == "japan")
    assert jp["status"] == "ok" and jp["corp_net_12m"] == pytest.approx(12.5, abs=0.05)
    assert p["public_funds"]["status"] == "ok"                       # official/non-official rows are fixtured


def test_stale_source_propagates_to_block_and_overall(offline, inputs):
    first = breaking.fetch_ebp()
    assert first["status"] == "ok"
    monkeypatch_fail = pytest.MonkeyPatch()
    try:
        monkeypatch_fail.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: None)
        os.utime(os.path.join(fred_csv.settings.cache_dir, "fed_ebp.csv"), (0, 0))   # expire, then fail
        stale = breaking.fetch_ebp()
    finally:
        monkeypatch_fail.undo()
    assert stale["status"] == "stale" and stale["latest"] == first["latest"]
    brk = dict(inputs["breaking"], ebp=stale, status=dict(inputs["breaking"]["status"], ebp="stale"))
    p = m.build_ai_debt(dict(inputs, breaking=brk))
    assert p["breaking"]["status"] == "stale" and p["status"]["breaking"] == "stale"
    assert p["breaking"]["status_detail"]["ebp"] == "stale" and p["breaking"]["ebp"]["status"] == "stale"
    assert p["status"]["overall"] != "ok"
    assert m.worst(["ok", "stale"]) == "stale" and m.worst(["stale", "error"]) == "error" and m.worst([]) == "error"
    assert m.worst(["ok", None]) == "error" and m.worst(["ok", "ok"]) == "ok"


def test_all_blocks_ok_when_every_input_loads(monkeypatch, tmp_path):
    patch_offline(monkeypatch, tmp_path, stand_ins=True)         # DGS30 served under the three un-fixtured ids
    p = m.build_ai_debt(m.fetch_inputs())
    assert set(p["status"].values()) == {"ok"}
    assert p["crowding"]["status_detail"]["acm10"] == "missing (optional)"   # optional, reported, never counted
    assert p["public_funds"]["status_detail"]["imf_pip"] == "ok"
    for b in m.BLOCKS:
        assert not any(v == "error" for k, v in (p[b].get("status_detail") or {}).items() if k != "acm10"), b


# ---------------------------------------------------------------------------
# route: TTL cache, warm-up, GET /ai-debt
# ---------------------------------------------------------------------------
def test_route_cache_warm_and_get(offline, payload, monkeypatch):
    from app.api import routes_ai_debt as r
    from app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(r, "_cache", {"ts": time.time(), "data": payload, "retry_after": 0.0})   # restored by pytest (B4-7)
    monkeypatch.setattr(r, "_building", {"on": False})
    assert r.ai_debt() is payload                                    # served from the in-process cache
    assert r.ai_debt_payload() is payload
    client = TestClient(app)                                         # no lifespan: no scheduler, no DB
    resp = client.get("/ai-debt")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == payload["status"] and body["issuance"]["seed_rev"] == "rev 1"
    assert set(body["honesty"][:5]) == set(m.HONESTY)
    rebuilt = r.warm_ai_debt(force=True)                             # the scheduler path rebuilds offline
    assert rebuilt is not payload and rebuilt["status"] == payload["status"]
    assert r.ai_debt() is rebuilt
    # a degraded build is kept for the shorter TTL only
    assert r._ttl(rebuilt) == r._TTL_DEGRADED and r._ttl({"status": {"overall": "ok"}}) == r._TTL


def test_route_never_builds_on_a_page_view_once_warm(payload, monkeypatch):
    """B4-V-02 / B4-1: an expired cache is served as-is while ONE background
    thread rebuilds; B4-V-03 / B4-2: a build that raises keeps the last good
    payload and is retried after the degraded TTL, never 500 per request."""
    import threading
    from app.api import routes_ai_debt as r

    monkeypatch.setattr(r, "_cache", {"ts": time.time() - 7 * 3600, "data": payload, "retry_after": 0.0})
    monkeypatch.setattr(r, "_building", {"on": False})
    gate, builds = threading.Event(), []

    def slow_inputs():
        builds.append(1)
        gate.wait(5)
        return {}

    monkeypatch.setattr(r, "fetch_inputs", slow_inputs)
    t0 = time.time()
    assert r.ai_debt_payload() is payload and time.time() - t0 < 1.0     # served immediately, expired or not
    assert r.ai_debt_payload() is payload                                # a second view does not start a second build
    gate.set()
    for _ in range(100):
        time.sleep(0.05)
        if not r._building["on"]:
            break
    assert builds == [1] and r._cache["data"] is not payload and r._cache["data"]["status"]["overall"] == "error"
    # a build that raises: the last good payload stays, the next attempt waits for the degraded TTL
    good = r._cache["data"]
    r._cache.update(ts=0.0)
    monkeypatch.setattr(r, "fetch_inputs", lambda: (_ for _ in ()).throw(KeyError("asof")))
    assert r.ai_debt_payload() is good
    for _ in range(100):
        time.sleep(0.05)
        if not r._building["on"]:
            break
    assert r._cache["data"] is good and r._cache["retry_after"] > time.time()
    assert r.ai_debt_payload() is good and not r._building["on"]          # no new build inside the retry window
    # cold start with a raising build: the all-null payload (every block error) is served and cached
    monkeypatch.setattr(r, "_cache", {"ts": 0.0, "data": None, "retry_after": 0.0})
    cold = r.ai_debt_payload()
    assert set(cold["status"].values()) == {"error"} and cold["build_error"].startswith("KeyError")
    assert r.ai_debt_payload() is cold


def test_public_funds_block_survives_a_raising_sibling_fetcher(monkeypatch, tmp_path):
    """B4-3 / B4-V-08: a MOF fetcher that raises is called once, is None in
    the Japan block, and leaves GPIF / IMF / Z.1 / TIC in public_funds intact."""
    patch_offline(monkeypatch, tmp_path)
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("MOF down")

    monkeypatch.setattr(boj_mof, "fetch_mof_by_investor_type", boom)
    inputs = m.fetch_inputs()
    assert calls == [1] and inputs["mof"] is None and inputs["public_funds"] is not None
    p = m.build_ai_debt(inputs)
    st = p["public_funds"]["status_detail"]
    assert st["mof"] == "error" and st["gpif"] == "ok" and st["imf_pip"] == "ok" and st["z1"] == "ok" and st["tic"] == "ok"
    assert p["public_funds"]["gpif"]["hyperscaler_plus_nvidia_share_pct"] == 0.044
    assert p["japan"]["status_detail"]["mof_by_type"] == "error" and p["japan"]["mof_by_type"] is None
