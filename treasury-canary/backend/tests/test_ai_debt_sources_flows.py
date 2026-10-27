"""AI-debt tab, flow sources (fred_csv, tic, boj_mof, z1, treasury_supply)
against trimmed real downloads — offline. The gate rows are the ones in
studies/ai_debt_flows/BUILD.md:

- TIC: "All Countries" vs "Grand Total" labelled; LT-only AND bills-inclusive
  Japan Treasury flows both present, 12m to Jul-26 = +4.0 vs -48.6.
- BoJ: sovereign + non-sovereign residual == total every month; JPY trn.
- MOF: trust accounts 12m to Sep-26 == +12.23; columns mapped by header name.
- Z.1: FA (SAAR) and FU (unannualised) never mixed; the fixture ratio is
  asserted (~4.5x latest quarter, ~4.0x over four); sector levels re-sum to
  within 1% of the "all sectors" total.
- MSPD: class sum equals Total Marketable for every month.
- Every fetch degrades to stale/error, never raises, never prints a 0 for a gap.

Fixtures (tests/fixtures/ai_debt) were cut from the 2026-10-15 scoping
downloads: FRED keyless CSVs, the TIC CSLT zip (six series + a decoy), the
BoJ bp_m_en zip (three series), MOF monthb3/week/jgbcm in their native cp932,
FiscalData MSPD rows, the NY Fed ACM daily series."""
from __future__ import annotations

import csv
import io
import json
import os
import zipfile
from datetime import date

import pytest

from app.sources import boj_mof, fred_csv, tic, treasury_supply, z1

FX = os.path.join(os.path.dirname(__file__), "fixtures", "ai_debt")
_FILES = {
    tic.CSLT_URL: "tic_cslt_mini.zip",
    boj_mof.BOJ_URL: "boj_bp_m_en_mini.zip",
    boj_mof.MOF_MONTHB3_URL: "mof_monthb3_trim.csv",
    boj_mof.MOF_WEEK_URL: "mof_week_trim.csv",
    boj_mof.MOF_JGB_ALL_URL: "mof_jgbcm_trim.csv",
    boj_mof.MOF_JGB_CUR_URL: "mof_jgbcme.csv",
}


def _fx(name: str) -> bytes:
    return open(os.path.join(FX, name), "rb").read()


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    """Every network call is answered from the fixtures (or None = failure);
    the disk cache lives in a fresh tmp dir so tests never share state."""
    monkeypatch.setattr(fred_csv.settings, "cache_dir", str(tmp_path))

    def fake_text(series_id, start):
        p = os.path.join(FX, f"fred_{series_id}.csv")
        return open(p, encoding="utf-8").read() if os.path.exists(p) else None

    def fake_bytes(u, headers=None):
        if u.startswith(treasury_supply.MSPD_URL.split("?")[0]):
            return _fx("mspd_trim.json")
        name = _FILES.get(u)
        return _fx(name) if name else None

    monkeypatch.setattr(fred_csv, "_fetch_text", fake_text)
    monkeypatch.setattr(fred_csv, "_http_get_bytes", fake_bytes)
    fred_csv._status.clear()


# ---------------------------------------------------------------------------
# fred_csv
# ---------------------------------------------------------------------------
def test_fred_csv_parse_dot_is_none():
    ds, vs = fred_csv.parse_csv("observation_date,X\n2026-01-02,4.10\n2026-01-03,.\n2026-01-06,4.05\n")
    assert ds == [date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 6)]
    assert vs == [4.10, None, 4.05]
    assert not fred_csv._looks_like_fred_csv(b"<!DOCTYPE html><html>404")


def test_fred_csv_cache_then_stale_then_error(monkeypatch):
    ds, vs = fred_csv.fetch_csv("THREEFYTP10", "2023-10-01")
    assert ds and fred_csv.status("THREEFYTP10") == "ok"
    assert fred_csv.latest(ds, vs) == (date(2026, 10, 9), 1.0729)
    # network gone: the cached copy is served, flagged stale (TTL ignored on failure)
    monkeypatch.setattr(fred_csv, "_fetch_text", lambda s, st: None)
    ds2, vs2 = fred_csv.fetch_csv("THREEFYTP10", "2023-10-01", use_cache=False)
    assert ds2 == ds and fred_csv.status("THREEFYTP10") == "stale"
    # nothing cached and no network: empty, error — never an exception, never zeros
    assert fred_csv.fetch_csv("NOPE123") == ([], [])
    assert fred_csv.status("NOPE123") == "error"
    assert fred_csv.worst_status(["THREEFYTP10", "NOPE123"]) == "error"


def test_download_cached_stale_on_error(monkeypatch):
    b, st = fred_csv.download_cached("x.bin", boj_mof.MOF_WEEK_URL, 10)
    assert b and st == "ok"
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: None)
    b2, st2 = fred_csv.download_cached("x.bin", boj_mof.MOF_WEEK_URL, 0)   # expired TTL
    assert b2 == b and st2 == "stale"
    assert fred_csv.download_cached("never.bin", "https://example.invalid/x", 0) == (None, "error")


# ---------------------------------------------------------------------------
# TIC
# ---------------------------------------------------------------------------
def test_tic_by_country_labels_and_japan_rows(monkeypatch):
    monkeypatch.setattr(tic, "COUNTRIES", [c for c in tic.COUNTRIES if c[0] == "japan"])
    p = tic.fetch_by_country("2023-08-01")
    assert p["status"] == "ok" and p["asof"] == "2026-07" and p["unit"] == "$bn"
    aggs = p["aggregates"]
    assert "international and regional organizations" in aggs["grand_total"]["label"]
    assert "excludes" in aggs["all_countries"]["label"]
    assert aggs["grand_total"]["corp_pos_latest"] != aggs["all_countries"]["corp_pos_latest"]
    assert aggs["grand_total"]["corp_pos_latest"] == pytest.approx(5272.819)
    assert aggs["grand_total"]["corp_net_12m"] == pytest.approx(452.0, abs=0.1)
    assert aggs["grand_total"]["treas_net_12m"] == pytest.approx(246.5, abs=0.1)
    assert aggs["grand_total"]["corp_share_of_lt_pct"] == pytest.approx(40.4, abs=0.05)
    jp = next(c for c in p["countries"] if c["key"] == "japan")
    assert jp["code"] == "42609" and jp["custody_centre"] is False
    assert jp["treas_net_12m"] == pytest.approx(4.0, abs=0.05)       # LT only
    assert jp["corp_net_12m"] == pytest.approx(12.5, abs=0.05)
    assert jp["treas_pos_latest"] == pytest.approx(1023.754)
    assert jp["corp_pos_latest"] == pytest.approx(312.507)
    assert jp["status"] == "ok"


def test_tic_by_country_missing_rows_are_null_and_flagged():
    p = tic.fetch_by_country("2023-08-01")        # full country list, only Japan fixtured
    assert p["status"] == "error"                 # the block is honest about its gaps
    jp = next(c for c in p["countries"] if c["key"] == "japan")
    uk = next(c for c in p["countries"] if c["key"] == "uk")
    assert jp["status"] == "ok" and jp["corp_net_12m"] == pytest.approx(12.5, abs=0.05)
    # countries without series are None-filled, never zero, and carry their own status
    assert uk["custody_centre"] and uk["status"] == "error"
    assert uk["treas_net_12m"] is None and set(uk["treas_net"]) == {None}
    assert p["aggregates"]["grand_total"]["status"] == "ok"


def test_tic_bills_inclusive_japan_sign_flips():
    b = tic.bills_inclusive()
    assert b["status"] == "ok" and b["asof"] == "2026-07"
    jp = b["japan"]
    assert jp["lt_12m"] == pytest.approx(4.0, abs=0.05)
    assert round(jp["all_maturities_12m"], 1) == -48.6
    assert jp["lt_12m"] > 0 > jp["all_maturities_12m"]
    assert "bills excluded" in jp["lt_label"] and "bills included" in jp["all_label"]
    ac = b["all_countries"]
    assert round(ac["all_maturities_12m"], 1) == 291.8 and round(ac["lt_12m"], 1) == 240.1
    assert b["grand_total"]["all_maturities_12m"] != ac["all_maturities_12m"]
    assert "All Countries = excludes" in b["labels"]["all_countries"]


def test_tic_cslt_streaming_extractor_survives_chunk_splits():
    with zipfile.ZipFile(io.BytesIO(_fx("tic_cslt_mini.zip"))) as zf:
        raw = zf.read("cslt.json")
    want = {"for_treas_net_42609", "for_lt_treas_net_69995"}
    whole = tic.extract_cslt_series(io.BytesIO(raw), want, chunk=1 << 20)
    tiny = tic.extract_cslt_series(io.BytesIO(raw), want, chunk=97)
    assert whole == tiny and set(whole) == want
    assert whole["for_treas_net_42609"][0] == ("2026-07-01", 891.0)
    assert "for_lt_corp_net_42609" not in whole       # the decoy is skipped


def test_tic_bills_inclusive_degrades(monkeypatch):
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: None)
    b = tic.bills_inclusive()
    assert b["status"] == "error" and b["japan"] == {} and b["months"] == []


# ---------------------------------------------------------------------------
# BoJ
# ---------------------------------------------------------------------------
def test_boj_residual_equals_total_minus_sovereign_every_month():
    p = boj_mof.fetch_boj_us_ltdebt("2014-01")
    assert p["status"] == "ok" and p["unit"] == "JPY trn" and p["asof"] == "2026-08"
    assert p["months"][0] == "2023-09" and len(p["months"]) == 36
    for t, s, r in zip(p["total"], p["sovereign"], p["nonsovereign"]):
        assert t is not None and s is not None
        assert r == pytest.approx(t - s, abs=1e-4)
    cy25 = [i for i, m in enumerate(p["months"]) if m.startswith("2025")]
    assert sum(p["total"][i] for i in cy25) == pytest.approx(10.527, abs=0.001)
    assert sum(p["sovereign"][i] for i in cy25) == pytest.approx(7.575, abs=0.001)
    assert sum(p["nonsovereign"][i] for i in cy25) == pytest.approx(2.952, abs=0.001)
    y26 = [i for i, m in enumerate(p["months"]) if m.startswith("2026")]
    assert sum(p["sovereign"][i] for i in y26) == pytest.approx(-5.466, abs=0.001)
    assert p["total_12m"] == pytest.approx(-2.54, abs=0.01)


def test_boj_degrades_without_zip(monkeypatch):
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: None)
    p = boj_mof.fetch_boj_us_ltdebt()
    assert p["status"] == "error" and p["total"] == [] and p["asof"] is None


# ---------------------------------------------------------------------------
# MOF
# ---------------------------------------------------------------------------
def test_mof_trust_accounts_12m_to_sep26():
    p = boj_mof.fetch_mof_by_investor_type("2023-10")
    assert p["status"] == "ok" and p["asof"] == "2026-09" and p["unit"] == "JPY trn"
    assert round(p["trust_accounts_12m"], 2) == 12.23
    assert round(p["all_12m"], 2) == -5.09
    assert round(p["banks_12m"], 2) == -12.83
    assert round(p["life_12m"], 2) == -2.11
    assert round(p["inv_trusts_12m"], 2) == -1.5
    assert p["column_map"]["trust_accounts"]["header"].startswith("Banks and Trust banks")
    assert p["column_map"]["all"]["net_column"] == 5


def _swap_groups(raw: bytes, a: str, b: str) -> bytes:
    """Move the 3-column (acq/disp/net) block headed `a` to where `b` sits and
    vice versa — header cells AND data cells — to prove name-based mapping."""
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


def test_mof_columns_are_mapped_by_header_name_not_position():
    raw = _fx("mof_monthb3_trim.csv")
    base = boj_mof.parse_monthb3(raw)
    swapped = boj_mof.parse_monthb3(_swap_groups(raw, "Life Insurance Companies",
                                                 "Banks and Trust banks"))
    assert swapped["months"] == base["months"]
    for key in boj_mof.MOF_INVESTOR_HEADERS:
        assert swapped[key] == base[key], key
    assert swapped["column_map"]["life"]["net_column"] != base["column_map"]["life"]["net_column"]
    # a file whose headers are missing is refused, not silently mis-mapped
    broken = raw.replace("Life Insurance Companies".encode("cp932"), b"Something Else")
    with pytest.raises(ValueError):
        boj_mof.parse_monthb3(broken)


def test_mof_weekly_and_year_rollover():
    p = boj_mof.fetch_mof_weekly("2025-12-01")
    assert p["status"] == "ok" and p["asof"] == "2026-10-03" and p["unit"] == "JPY trn"
    assert p["lt_debt_net"][-1] == pytest.approx(-0.3476)
    assert "2026-01-03" in p["weeks"]        # '2025．12．28～2026．1．3' parsed to its end date
    assert boj_mof._week_end("2006．12．31～ 2007．1．6") == date(2007, 1, 6)
    assert boj_mof._week_end("2005．11．27～ 12．3") == date(2005, 12, 3)


def test_jgb_curve_era_dates_and_splice():
    p = boj_mof.fetch_jgb_curve("1970-01-01")
    assert p["status"] == "ok" and p["dates"][0] == "1974-09-24"
    i = p["dates"].index("2026-09-30")
    assert p["y10"][i] == 3.057 and p["y30"][i] == 4.098
    assert p["dates"][-1] == "2026-10-14" and p["y10"][-1] == 3.015 and p["y30"][-1] == 4.072
    assert any(d.startswith("201") or d.startswith("200") or d.startswith("199") for d in p["dates"])
    assert boj_mof._jgb_date("H31.4.30") == date(2019, 4, 30)
    assert boj_mof._jgb_date("R1.5.1") == date(2019, 5, 1)


# ---------------------------------------------------------------------------
# Z.1
# ---------------------------------------------------------------------------
def test_z1_fa_fu_never_mixed():
    fa = z1.Series("BOGZ1FA893063005Q", [1.0, 2.0])
    fu = z1.Series("BOGZ1FU893063005Q", [1.0, 2.0])
    fl = z1.Series("BOGZ1FL893063005Q", [1.0, 2.0])
    assert (fa.kind, fu.kind, fl.kind) == ("FA", "FU", "FL")
    with pytest.raises(ValueError):
        z1.sum_flows([fa, fu])
    with pytest.raises(ValueError):
        z1.combine(fa, fl, "-")
    assert z1.sum_flows([fa, z1.Series("ROWCBAQ027S", [0.5, 0.5])]).values == [1.5, 2.5]
    with pytest.raises(ValueError):
        z1.kind("DGS10")


def test_z1_fixture_ratio_and_partition():
    p = z1.fetch_holders("2022-01-01")
    assert p["status"] == "ok" and p["asof"] == "2026Q2" and p["unit"] == "$bn"
    c = p["checks"]
    # SAAR vs unannualised: 2026Q2 1,351,916 / 299,829 = 4.51x; ~4.0x over four quarters
    assert 4.0 <= c["fa_over_fu_latest"] <= 4.6
    assert 4.0 <= c["fa_over_fu_4q"] <= 4.5
    assert c["units_consistent"] is True
    assert p["flows_saar"]["all_sectors"][-1] == pytest.approx(1351.916)
    assert p["flows_unadj"]["all_sectors"][-1] == pytest.approx(299.829)
    # the 17 display sectors re-sum to the L.213 total within 1% every quarter
    assert all(abs(g) < 1.0 for g in c["partition_gap_pct"] if g is not None)
    assert c["partition_gap_pct"][-1] is not None
    lv = p["levels"]
    assert lv["all_sectors"][-1] == pytest.approx(18115.721)
    direct = [k for k in z1._PARTITION if z1.SECTORS[k]["FL"]]
    assert sum(lv[k][-1] for k in direct) / lv["all_sectors"][-1] > 0.65
    # derived lines against the Z.1 package (verify_B, 2026Q2): ROW 5,195.694 to the dollar
    # (the monetary-authority line FL713011525 is subtracted; D6); households 192.0
    assert lv["rest_of_world"][-1] == pytest.approx(5195.694, abs=0.01)
    assert c["partition_gap_pct"][-1] != 0.0                       # no longer tautological: the MA line is the gap
    assert lv["households"][-1] == pytest.approx(543.097 - 337.106, abs=0.01)
    assert lv["life_insurers"][-1] == pytest.approx(3944.186)
    assert lv["etfs"][-1] == pytest.approx(1518.085)
    assert p["pensions"]["private"]["level"][-1] == pytest.approx(897.307)
    assert p["pensions"]["state_local"]["level"][-1] == pytest.approx(634.574)
    assert p["pensions"]["total"]["level"][-1] == pytest.approx(
        897.307 + 634.574 + 15.680, abs=0.01)
    assert p["flows_saar"]["rest_of_world"][-1] == pytest.approx(435.444)
    assert p["nfc_issuance"]["saar"][-1] == pytest.approx(327.0)
    assert p["nfc_issuance"]["unadj"][-1] == pytest.approx(81.75)
    assert p["nfc_issuance"]["saar_ex_reits"][-1] == pytest.approx(333.208)
    assert p["levels"]["rest_of_world_ex_abs"][-1] == pytest.approx(4714.319)
    derived = {s["key"] for s in p["sectors"] if s["derived_level"]}
    assert derived == {"rest_of_world", "households", "other_financial", "other_depository"}


def test_z1_missing_series_is_none_not_zero(monkeypatch):
    real = fred_csv._fetch_text
    monkeypatch.setattr(fred_csv, "_fetch_text",
                        lambda s, st: None if s == "BOGZ1FL543063005Q" else real(s, st))
    p = z1.fetch_holders("2022-01-01")
    assert p["status"] == "error"
    assert set(p["levels"]["life_insurers"]) == {None}
    assert p["levels"]["all_sectors"][-1] == pytest.approx(18115.721)


# ---------------------------------------------------------------------------
# MSPD / term premium / yields / auctions
# ---------------------------------------------------------------------------
def test_mspd_class_sum_equals_total_every_month():
    p = treasury_supply.fetch_mspd("2023-09-01")
    assert p["status"] == "ok" and p["asof"] == "2026-09-30" and p["unit"] == "$bn"
    assert len(p["months"]) == 37
    assert p["checks"]["class_sum_equals_total"] is True
    for cs, tot, gap in zip(p["class_sum"], p["total_marketable"], p["gap_bn"]):
        assert cs is not None and tot is not None and abs(gap) <= 0.001
    assert p["total_marketable"][-1] == pytest.approx(31834.878, abs=0.001)
    assert p["coupons"][-1] == pytest.approx(24713.142, abs=0.001)
    assert p["bills"][-1] == pytest.approx(7118.145, abs=0.001)
    n = treasury_supply.net_issuance(p)
    assert n["cy"][2025]["complete"] and n["cy"][2025]["net_marketable"] == pytest.approx(1991, abs=3)
    assert n["cy"][2025]["coupons"] == pytest.approx(1631, abs=3)
    assert n["cy"][2025]["bills"] == pytest.approx(360, abs=3)
    assert n["fy"][2026]["complete"] and n["fy"][2026]["from"] == "2025-09-30"
    assert 2100 < n["fy"][2026]["net_marketable"] < 2140
    assert n["cy"][2026]["complete"] is False and n["cy"][2026]["to"] == "2026-09-30"


def test_mspd_gap_is_flagged_not_hidden():
    recs = [{"record_date": "2026-09-30", "security_type_desc": "Marketable",
             "security_class_desc": "Bills", "total_mil_amt": "100"},
            {"record_date": "2026-09-30", "security_type_desc": "Total Marketable",
             "security_class_desc": "_", "total_mil_amt": "150"}]
    p = treasury_supply.parse_mspd(recs)
    assert p["gap_bn"] == [-0.05] and p["classes"]["notes"] == [None]


def test_term_premium_kw_primary_acm_optional():
    tp = treasury_supply.fetch_term_premium("2023-10-01")
    assert tp["kw10"]["latest"] == 1.0729 and tp["kw10"]["asof"] == "2026-10-09"
    assert tp["kw10"]["status"] == "ok" and tp["acm10"] is None     # xls not served offline
    rows = [(r["DATE"], r["ACMTP10"]) for r in csv.DictReader(open(os.path.join(FX, "acm_daily_trim.csv")))]
    ds, vs = treasury_supply.parse_acm_rows(rows, "2026-01-01")
    assert ds[-1] == date(2026, 10, 13) and round(vs[-1], 3) == 0.851
    hi = max(zip(vs, ds))
    assert round(hi[0], 3) == 0.985 and hi[1] == date(2026, 10, 7)
    ds2, vs2 = treasury_supply.parse_acm_rows([("14-Jun-1961", "0.0813"), ("junk", 1), ("1961-06-15", "")])
    assert ds2 == [date(1961, 6, 14), date(1961, 6, 15)] and vs2 == [0.0813, None]


def test_yields_block_and_tenor_labels(monkeypatch):
    y = treasury_supply.fetch_yields("2026-09-01")
    assert y["dgs30"]["latest"] == 5.56 and y["dgs30"]["asof"] == "2026-10-13"
    assert y["dgs10"]["status"] == "error" and y["dgs10"]["latest"] is None   # no fixture -> null
    assert y["fed_treast"]["unit"] == "$bn"
    assert treasury_supply.tenor_label("10-Year") == "10y"
    assert treasury_supply.tenor_label("29-Year 10-Month") == "30y"
    assert treasury_supply.tenor_label("19-Year 11-Month") == "20y"
    assert treasury_supply.tenor_label("6-Year 10-Month") == "7y"
    monkeypatch.setattr(treasury_supply, "fetch_recent_auctions", lambda limit=60: [
        {"auction_date": "2026-10-08", "security_type": "Bond", "security_term": "29-Year 10-Month",
         "bid_to_cover": 2.54, "indirect_pct": 72.3, "dealer_pct": 10.0, "direct_pct": 17.7,
         "high_yield": 5.618}])
    a = treasury_supply.fetch_auctions()
    assert a == [{"date": "2026-10-08", "tenor": "30y", "term": "29-Year 10-Month",
                  "security_type": "Bond", "high_yield": 5.618, "btc": 2.54,
                  "indirect_pct": 72.3, "dealer_pct": 10.0, "direct_pct": 17.7}]


# ---------------------------------------------------------------------------
# Reviewer defects D1 / D2 / D3 / D5: an error page never poisons the cache,
# zero rows is never "ok", a month without a Total row fails the MSPD check,
# a trailing empty FRED month does not advance the TIC axis
# ---------------------------------------------------------------------------
_HTML_WITH_KEYWORDS = (b"<!DOCTYPE html><html><head><title>Internet Error</title></head><body>"
                       b"Net Period Date Acquisition Disposition 10 Year" + b" x" * 2000 + b"</body></html>")


def test_mof_html_error_page_never_overwrites_the_cache(monkeypatch):
    good = boj_mof.fetch_mof_by_investor_type("2023-10")
    week = boj_mof.fetch_mof_weekly("2025-12-01")
    jgb = boj_mof.fetch_jgb_curve("2026-09-01")
    assert good["status"] == week["status"] == jgb["status"] == "ok"
    for name in ("mof_monthb3.csv", "mof_week.csv", "mof_jgbcm_all.csv", "mof_jgbcme.csv"):
        os.utime(os.path.join(fred_csv.settings.cache_dir, name), (0, 0))         # expire the good copies
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: _HTML_WITH_KEYWORDS)
    again = boj_mof.fetch_mof_by_investor_type("2023-10")
    assert again["status"] == "stale" and again["trust_accounts_12m"] == good["trust_accounts_12m"]
    assert boj_mof.fetch_mof_weekly("2025-12-01")["lt_debt_net"] == week["lt_debt_net"]
    assert boj_mof.fetch_jgb_curve("2026-09-01")["y10"] == jgb["y10"]
    # the cache files still hold the real data, not the HTML page
    for name in ("mof_monthb3.csv", "mof_week.csv", "mof_jgbcm_all.csv"):
        head = open(os.path.join(fred_csv.settings.cache_dir, name), "rb").read(40)
        assert not head.startswith(b"<!DOCTYPE"), name
    # and with the network then down the stale copy is still the good one
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: None)
    assert boj_mof.fetch_mof_by_investor_type("2023-10")["trust_accounts_12m"] == good["trust_accounts_12m"]


def _header_only_monthb3() -> bytes:
    rows = list(csv.reader(io.StringIO(_fx("mof_monthb3_trim.csv").decode("cp932"))))
    net_row = next(i for i, r in enumerate(rows) if sum(1 for c in r if c.strip() == "Net") >= 5)
    sio = io.StringIO()
    csv.writer(sio, lineterminator="\r\n").writerows(rows[:net_row + 1])
    return sio.getvalue().encode("cp932")


def test_header_only_bodies_are_error_not_ok(monkeypatch):
    with pytest.raises(ValueError):
        boj_mof.parse_monthb3(_header_only_monthb3())
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: _header_only_monthb3())
    p = boj_mof.fetch_mof_by_investor_type("2023-10")
    assert p["status"] == "error" and p["months"] == [] and p["asof"] is None
    # a parse that yields rows all before `start` is also not ok
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: _fx("mof_week_trim.csv"))
    w = boj_mof.fetch_mof_weekly("2099-01-01")
    assert w["status"] == "error" and w["weeks"] == []
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: b'{"data": []}')
    j = treasury_supply.fetch_mspd("2023-09-01")
    assert j["status"] == "error" and j["months"] == [] and j["checks"]["class_sum_equals_total"] is False
    # BoJ: every value cell empty (here: nothing from `start`) -> error, never an empty "ok"
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: _fx("boj_bp_m_en_mini.zip"))
    assert boj_mof.fetch_boj_us_ltdebt("2099-01")["status"] == "error"


def test_mspd_month_without_total_row_fails_the_check():
    recs = json.loads(_fx("mspd_trim.json"))["data"]
    recs = [r for r in recs if r["security_type_desc"] != "Total Marketable" or r["record_date"] < "2026-09-01"]
    p = treasury_supply.parse_mspd(recs)
    assert p["total_marketable"][-1] is None and p["gap_bn"][-1] is None
    import app.sources.fred_csv as fc
    real = fc._http_get_bytes
    try:
        fc._http_get_bytes = lambda u, h=None: json.dumps({"data": recs}).encode()
        m = treasury_supply.fetch_mspd("2023-09-01")
    finally:
        fc._http_get_bytes = real
    assert m["checks"]["class_sum_equals_total"] is False and m["checks"]["months_without_total"] == 1
    n = treasury_supply.net_issuance(m)
    assert n["fy"][2026]["net_marketable"] is None                 # no Total row -> null, never a partial sum


def test_tic_trailing_empty_month_does_not_advance_asof(monkeypatch):
    monkeypatch.setattr(tic, "COUNTRIES", [c for c in tic.COUNTRIES if c[0] == "japan"])
    real = fred_csv._fetch_text

    def with_trailing_blank(series_id, start):
        t = real(series_id, start)
        return t + "2026-08-01,.\n" if t and series_id == "FORLTCORPPOS99996" else t

    monkeypatch.setattr(fred_csv, "_fetch_text", with_trailing_blank)
    p = tic.fetch_by_country("2023-08-01")
    assert p["asof"] == "2026-07" and p["months"][-1] == "2026-07"
    jp = next(c for c in p["countries"] if c["key"] == "japan")
    assert jp["treas_net_12m"] == pytest.approx(4.0, abs=0.05) and jp["status"] == "ok"
