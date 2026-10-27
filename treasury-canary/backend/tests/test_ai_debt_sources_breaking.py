"""AI-debt tab, B3 sources (public_funds, breaking) against trimmed real
downloads — offline. Gate rows from studies/ai_debt_flows/BUILD.md:

- GPIF parse reproduces the memo §3f figures: Oracle JPY 11.06bn (53 lines),
  Amazon 8.60, Alphabet 6.41, Meta 4.11, Broadcom 3.66, Microsoft 1.75,
  Blue Owl Technology Finance 0.90 (3 lines, NOT the 12 "Blue Owl" lines),
  CoreWeave 0.14, Nvidia 0.11; US Treasuries JPY 36.84trn = 50.6%; sheet total
  JPY 72.82trn over 10,040 lines; columns found by header text.
- Breaking: CCC−B gap computed on matching dates only; BDC p_nav == price / nav
  and null when the NAV has no filing; every event has a provenance badge and
  a URL; 2026 highs/lows per bucket equal the verifier's table.
- Every fetch degrades to stale/error, never raises, never prints 0 for a gap;
  the assembled blocks json.dumps.

Fixtures (tests/fixtures/ai_debt, cut from the 2026-10-15 scoping downloads):
gpif_holdings_fixture.xlsx (the real Foreign Bonds sheet, all 10,040 rows, plus
a decoy Domestic Bonds sheet carrying an ORACLE-named line), the IMF PIP SDMX
XML trimmed to the LT-debt series, Fed EBP and OFR FSI csvs trimmed to 2024-/
2025-12-, FRED keyless csvs for the 12 breaking series from 2025-12-01, and
Yahoo chart JSONs trimmed to their last bars. The MOF / Z.1 / TIC fixtures of
test_ai_debt_sources_flows.py are reused for the pension helpers."""
from __future__ import annotations

import io
import json
import os
from datetime import date

import pytest

from app.sources import boj_mof, breaking, fred_csv, public_funds as pf

FX = os.path.join(os.path.dirname(__file__), "fixtures", "ai_debt")
_FILES = {
    pf.GPIF_URL: "gpif_holdings_fixture.xlsx",
    pf.IMF_PIP_URL: "gpif_imf_pip_jpn_usa_trim.xml",
    breaking.EBP_URL: "ebp_fed_trim.csv",
    breaking.OFR_FSI_URL: "ofr_fsi_trim.csv",
    boj_mof.MOF_MONTHB3_URL: "mof_monthb3_trim.csv",
}
_YAHOO = {breaking.yahoo_url(s): f"bdc_yahoo_{'MOVE' if s == breaking.MOVE_SYMBOL else s}.json"
          for s in breaking.BDC_TICKERS + [breaking.MOVE_SYMBOL]}


def _fx(name: str) -> bytes:
    return open(os.path.join(FX, name), "rb").read()


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    """Every network call is answered from the fixtures (None = failure); the
    disk cache lives in a fresh tmp dir so tests never share state."""
    monkeypatch.setattr(fred_csv.settings, "cache_dir", str(tmp_path))

    def fake_text(series_id, start):
        for pat in (f"oas_fred_{series_id}.csv", f"fred_{series_id}.csv"):
            p = os.path.join(FX, pat)
            if os.path.exists(p):
                return open(p, encoding="utf-8").read()
        return None

    def fake_bytes(u, headers=None):
        name = _FILES.get(u) or _YAHOO.get(u)
        return _fx(name) if name else None

    monkeypatch.setattr(fred_csv, "_fetch_text", fake_text)
    monkeypatch.setattr(fred_csv, "_http_get_bytes", fake_bytes)


def _no_network(monkeypatch):
    monkeypatch.setattr(fred_csv, "_fetch_text", lambda s, st: None)
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: None)


# ---------------------------------------------------------------------------
# GPIF
# ---------------------------------------------------------------------------
MEMO_GPIF = {  # key -> (JPY bn, lines), studies/ai-debt-flows.md §3f + verify_B B7
    "oracle": (11.06, 53), "amazon": (8.60, 36), "alphabet": (6.41, 21), "meta": (4.11, 20),
    "broadcom": (3.66, 34), "microsoft": (1.75, 18), "blue_owl_tech": (0.90, 3),
    "coreweave": (0.14, 2), "nvidia": (0.11, 4),
}


def test_gpif_parse_reproduces_memo_figures():
    g = pf.fetch_gpif()
    assert g["status"] == "ok"
    assert g["asof"] == "2026-03-31"
    assert g["n_lines"] == 10040
    assert g["foreign_bonds_jpy_trn"] == 72.821
    by = {r["key"]: r for r in g["ai_issuers"]}
    for key, (jpy_bn, lines) in MEMO_GPIF.items():
        assert by[key]["jpy_bn"] == jpy_bn, key
        assert by[key]["lines"] == lines, key
    assert g["ust_jpy_trn"] == 36.841 and g["ust_lines"] == 297 and g["ust_share_pct"] == 50.6
    # the memo's "0.044% of the book" is the five hyperscalers + Nvidia = JPY 32.0bn
    assert g["hyperscaler_plus_nvidia_jpy_bn"] == 32.04
    assert g["hyperscaler_plus_nvidia_share_pct"] == 0.044
    assert g["ai_issuers_total_jpy_bn"] == round(sum(v[0] for v in MEMO_GPIF.values()), 2) or \
        abs(g["ai_issuers_total_jpy_bn"] - sum(v[0] for v in MEMO_GPIF.values())) < 0.02
    assert g["src"] == pf.GPIF_URL and g["basis"]
    # the decoy ORACLE line in "Domestic Bonds" must not have leaked in
    assert by["oracle"]["jpy_bn"] == 11.06


def test_gpif_columns_by_header_not_position_and_sheet_by_name():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Domestic Bonds"
    ws.append(["No.", "ISIN", "Security Name", "Market Value (JPY)"])
    ws.append([1, "JP0000000001", "ORACLE CORP DECOY", 5_000_000_000])
    fb = wb.create_sheet("Foreign  bonds (JPY)")
    fb.append(["Foreign bonds", None, None, None])
    fb.append([None, "as of September 30, 2026", None, None])
    fb.append(["Market Value (JPY)", "Security Name", "ISIN", "No."])      # shuffled columns
    fb.append([1_000_000_000, "ORACLE CORP 5% 01/01/2035", "US68389XAA01", 1])
    fb.append([2_000_000_000, "US TREASURY N/B 4% 02/15/2035", "US91282CAA01", 2])
    fb.append([500_000_000, "BLUE OWL CAPITAL CORP 6% 2030", "US09581JAA01", 3])   # not Blue Owl Tech
    fb.append([400_000_000, "BLUE OWL TECHNOLOGY FINANCE CORP 7% 2030", "US09581JAB01", 4])
    fb.append([None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    p = pf.parse_gpif(buf.getvalue())
    assert p["sheet"] == "Foreign  bonds (JPY)" and p["asof"] == "2026-09-30"
    assert p["n_lines"] == 4 and p["total_jpy"] == 3_900_000_000
    assert p["by_issuer"]["oracle"] == (1_000_000_000, 1)
    assert p["by_issuer"]["blue_owl_tech"] == (400_000_000, 1)
    assert p["ust"] == (2_000_000_000, 1)


def test_gpif_degrades_to_nulls_not_zero(monkeypatch):
    _no_network(monkeypatch)
    g = pf.fetch_gpif()
    assert g["status"] == "error"
    assert g["foreign_bonds_jpy_trn"] is None and g["ust_jpy_trn"] is None and g["n_lines"] is None
    assert g["ai_issuers"] == [] and g["hyperscaler_plus_nvidia_share_pct"] is None
    assert g["src"] == pf.GPIF_URL


def test_gpif_bad_body_is_error_not_crash(monkeypatch):
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: b"<html>blocked</html>")
    assert pf.fetch_gpif()["status"] == "error"


# ---------------------------------------------------------------------------
# IMF PIP (optional)
# ---------------------------------------------------------------------------
def test_imf_pip_japan_us_semiannual_by_holder_sector():
    blk, st = pf.fetch_imf_pip_japan_us()
    assert st == "ok" and blk is not None and blk["status"] == "ok"
    assert blk["asof"] == "2025-S2" and blk["frequency"] == "semi-annual"
    assert blk["total_usd_bn"] == 1214.691                      # verifier: $1,214.7bn end-Dec 2025
    lat = blk["latest"]
    assert lat["S122"]["usd_bn"] == 404.722                      # banks
    assert lat["S12QU"]["usd_bn"] == 260.248                     # insurers & pension funds
    assert lat["S12P"]["usd_bn"] == 493.552                      # other financial (trusts)
    assert lat["S1V"]["usd_bn"] == 55.522
    assert blk["sectors"]["S12QU"]["label"].startswith("Insurance corporations and pension funds")
    assert all(p.endswith(("S1", "S2")) for p in blk["periods"])  # the annual decoy series was skipped
    # B3-7: dead series (last observation 2004-2012) are dropped and the axis is the live periods only
    assert blk["periods"] == ["2024-S2", "2025-S1", "2025-S2"]
    assert set(blk["sectors"]) == {"S1", "S122", "S12QU", "S12P", "S12R", "S13", "S1V"}
    assert {"OFM", "S125E", "S128", "S121"} <= set(blk["dropped_sectors"])
    assert blk["leaf_sectors"] == ["S122", "S12QU", "S12P", "S13", "S1V"] and "NOT additive" in blk["note"]
    assert blk["src"] == pf.IMF_PIP_URL


def test_imf_pip_optional_returns_none_with_status(monkeypatch):
    _no_network(monkeypatch)
    blk, st = pf.fetch_imf_pip_japan_us()
    assert blk is None and st == "error"
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: b"<?xml version='1.0'?><PIP/>")
    blk, st = pf.fetch_imf_pip_japan_us()
    assert blk is None and st == "error"


# ---------------------------------------------------------------------------
# Pension helpers on the sibling fetchers' outputs + the assembled block
# ---------------------------------------------------------------------------
def test_public_funds_block_from_sibling_fixtures():
    blk = pf.fetch_block()                       # MOF / Z.1 / TIC come through their own modules
    assert round(blk["trust_accounts_12m_jpy_trn"], 2) == 12.23   # MOF gate row, 12m to Sep-26
    assert blk["mof_by_type"]["asof"] == "2026-09"
    assert blk["mof_by_type"]["labels"]["trust_accounts"].startswith("Banks & trust banks, trust accounts")
    z = blk["z1_pensions"]
    assert z["status"] in ("ok", "stale") and z["units_consistent"] is True
    assert z["private"]["level_latest"] is not None and len(z["private"]["flow_saar_last4"]) == 4
    assert z["state_local"]["flow_saar_latest"] is not None
    assert "SAAR" in z["unit"]
    t = blk["tic_official_corp"]
    assert t["pos"] == 316.007 and t["grand_total_pos"] == 5272.819
    assert t["share_of_foreign_held_pct"] == 6.0                 # memo §3d: 316.0 = 6.0% of foreign-held
    assert t["net_12m"] is not None and t["non_official_pos"] == 4956.812
    assert blk["gpif"]["status"] == "ok" and blk["imf_pip_japan"]["total_usd_bn"] == 1214.691
    assert len(blk["can_see"]) >= 4 and len(blk["cannot_see"]) >= 5
    assert set(blk["status"]) == {"gpif", "imf_pip", "mof", "z1", "tic"}
    assert all(v in ("ok", "stale", "error") for v in blk["status"].values())
    json.dumps(blk)


def test_public_funds_block_with_nothing_is_null_not_zero():
    blk = pf.build_block(None, None, None, None, None, None)
    assert blk["trust_accounts_12m_jpy_trn"] is None
    assert blk["z1_pensions"]["private"]["level_latest"] is None
    assert blk["tic_official_corp"]["share_of_foreign_held_pct"] is None
    assert blk["imf_pip_japan"] is None and blk["gpif"]["foreign_bonds_jpy_trn"] is None
    assert set(blk["status"].values()) == {"error"}
    assert blk["can_see"] and blk["cannot_see"] and blk["src"]["gpif"] == pf.GPIF_URL
    json.dumps(blk)


def test_trust_accounts_helper_takes_the_mof_dict_shape():
    mof = {"asof": "2026-09", "months": ["2026-08", "2026-09"], "status": "stale", "basis": "b", "src": "u",
           "labels": {"trust_accounts": "T", "banks": "B", "life": "L", "inv_trusts": "I", "all": "A"},
           "trust_accounts": [1.0, 2.0], "banks": [-1.0, None], "life": [0.5, 0.5], "inv_trusts": [0.0, 0.1],
           "all": [0.5, None], "trust_accounts_12m": None}
    t = pf.trust_accounts_from_mof(mof)
    assert t["status"] == "stale" and t["trust_accounts"] == [1.0, 2.0]
    assert t["trust_accounts_12m"] is None                       # fewer than 12 months -> None, not a partial sum
    assert t["banks_12m"] is None


# ---------------------------------------------------------------------------
# Breaking: spreads, gap, yields
# ---------------------------------------------------------------------------
VERIFIER_2026 = {  # bucket -> (latest 10-14, end-2025, 2026 low, low date, 2026 high, high date)  [verify_E §1]
    "aaa": (0.40, 0.34, 0.31, "2026-01-28", 0.46, "2026-07-27"),
    "aa": (0.60, 0.49, 0.44, "2026-01-22", 0.61, "2026-07-28"),
    "a": (0.70, 0.65, 0.59, "2026-01-22", 0.79, "2026-03-16"),
    "bbb": (1.04, 1.01, 0.92, "2026-05-29", 1.16, "2026-03-16"),
    "ig": (0.84, 0.79, 0.73, "2026-01-22", 0.94, "2026-03-16"),
    "bb": (1.99, 1.69, 1.50, "2026-08-28", 2.22, "2026-03-30"),
    "b": (3.29, 3.01, 2.70, "2026-09-21", 3.77, "2026-03-30"),
    "ccc": (12.82, 8.85, 8.38, "2026-01-28", 12.82, "2026-10-14"),
    "hy": (3.25, 2.81, 2.60, "2026-08-28", 3.46, "2026-03-30"),
}


def test_spreads_latest_and_2026_ranges_match_verifier_table():
    spreads, gap = breaking.fetch_spreads()
    for k, (latest, end25, lo, lo_d, hi, hi_d) in VERIFIER_2026.items():
        b = spreads[k]
        assert b["status"] == "ok", k
        assert (b["latest"], b["asof"]) == (latest, "2026-10-14"), k
        assert b["end_2025"] == end25, k
        assert (b["lo_2026"], b["lo_2026_date"]) == (lo, lo_d), k
        assert (b["hi_2026"], b["hi_2026_date"]) == (hi, hi_d), k
        assert b["src"] == fred_csv.url(breaking.OAS[k][0]) and b["basis"]
    assert gap["latest"] == 9.53 and gap["asof"] == "2026-10-14" and gap["end_2025"] == 5.84
    assert gap["hi_2026"] == 9.53 and gap["status"] == "ok"


def test_ccc_b_gap_uses_matching_dates_only():
    d = [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    ccc = (d, [9.0, 9.5, None, 10.0])
    b = ([d[0], d[1], d[3]], [3.0, None, 3.5])      # 01-05 missing on B, 01-06 absent from B entirely
    gd, gv = breaking.gap_on_matching_dates(ccc, b)
    assert gd == [date(2026, 1, 2), date(2026, 1, 7)] and gv == [6.0, 6.5]
    spreads, gap = breaking.fetch_spreads()
    both = set(spreads["ccc"]["series"]["dates"]) & set(spreads["b"]["series"]["dates"])
    assert gap["n_dates"] <= len(both) and set(gap["series"]["dates"]) <= both
    for dt, v in zip(gap["series"]["dates"], gap["series"]["values"]):
        i, j = spreads["ccc"]["series"]["dates"].index(dt), spreads["b"]["series"]["dates"].index(dt)
        assert v == round(spreads["ccc"]["series"]["values"][i] - spreads["b"]["series"]["values"][j], 4)


def test_yields_and_baa10y():
    y = breaking.fetch_yields()
    assert (y["ig"]["latest"], y["ig"]["hi_2026"], y["ig"]["hi_2026_date"]) == (5.94, 6.03, "2026-10-02")
    assert (y["hy"]["latest"], y["hy"]["hi_2026"], y["hy"]["hi_2026_date"]) == (8.20, 8.22, "2026-10-01")
    b = breaking.fetch_baa10y()
    assert (b["latest"], b["asof"]) == (1.46, "2026-10-13") and b["src"].endswith("id=BAA10Y")


def test_year_range_ignores_gaps_and_other_years():
    d = [date(2025, 12, 31), date(2026, 1, 2), date(2026, 1, 5)]
    r = breaking.year_range(d, [99.0, None, 2.0])
    assert r == {"hi": 2.0, "hi_date": "2026-01-05", "lo": 2.0, "lo_date": "2026-01-05"}
    assert breaking.year_range(d, [None, None, None]) == {"hi": None, "hi_date": None, "lo": None, "lo_date": None}


# ---------------------------------------------------------------------------
# Breaking: EBP, OFR FSI, MOVE, BDC
# ---------------------------------------------------------------------------
def test_ebp_and_ofr_fsi_header_mapped():
    e = breaking.fetch_ebp()
    assert e["status"] == "ok" and e["asof"] == "2026-09-01" and e["months"][-1] == "2026-09"
    assert round(e["latest"], 4) == -0.3919 and round(e["gz_spread_latest"], 4) == 0.9259
    assert round(e["est_prob_latest"], 4) == 0.0912
    f = breaking.fetch_ofr_fsi()
    assert f["status"] == "ok" and f["asof"] == "2026-10-13"
    assert f["latest"] == -2.139 and f["credit_latest"] == -0.982
    assert f["dates"][0] >= "2025-12-29"


def test_ebp_ofr_bad_bodies_degrade(monkeypatch):
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: b"<html>maintenance</html>")
    assert breaking.fetch_ebp()["status"] == "error" and breaking.fetch_ebp()["latest"] is None
    assert breaking.fetch_ofr_fsi()["status"] == "error" and breaking.fetch_ofr_fsi()["latest"] is None


def test_move_latest_and_granularity_guard(monkeypatch):
    m = breaking.fetch_move()
    assert m["status"] == "ok" and m["asof"] == "2026-10-15" and round(m["latest"], 2) == 102.56
    assert m["wk52_high"] is not None and m["src"].startswith("https://query1.finance.yahoo.com/v8/finance/chart/%5EMOVE")
    assert m["cross_check"] == breaking.MOVE_XCHECK_URL
    bad = json.loads(_fx("bdc_yahoo_MOVE.json"))
    bad["chart"]["result"][0]["meta"]["dataGranularity"] = "3mo"
    with pytest.raises(ValueError):
        breaking.parse_yahoo_chart(json.dumps(bad).encode())                       # the granularity guard
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: json.dumps(bad).encode())
    os.utime(os.path.join(fred_csv.settings.cache_dir, "yahoo__MOVE.json"), (0, 0))   # expire the good copy
    m2 = breaking.fetch_move()
    # B3-2: a body that does not parse never replaces the last good copy -> stale, same values
    assert m2["status"] == "stale" and m2["latest"] == m["latest"]
    os.remove(os.path.join(fred_csv.settings.cache_dir, "yahoo__MOVE.json"))
    m3 = breaking.fetch_move()                                                      # nothing cached -> error, nulls
    assert m3["status"] == "error" and m3["latest"] is None


def test_bdc_p_nav_is_price_over_nav_and_null_without_filing():
    rows = breaking.fetch_bdc()
    assert [r["ticker"] for r in rows] == breaking.BDC_TICKERS
    for r in rows:
        assert r["status"] == "ok" and r["price"] is not None and r["asof"] == "2026-10-15"
        if r["nav"] is None:
            assert r["p_nav"] is None and r["nav_src"] is None and r["nav_asof"] is None
        else:
            assert r["p_nav"] == round(r["price"] / r["nav"], 3)
            assert r["nav_src"].startswith("https://www.sec.gov/Archives/edgar/data/")
            assert r["nav_asof"] == "2026-06-30" and r["nav_quote"]
    by = {r["ticker"]: r for r in rows}
    assert {t for t, r in by.items() if r["nav"] is not None} == {"ARCC", "BXSL", "GBDC"}
    assert (by["BXSL"]["nav"], by["BXSL"]["p_nav"]) == (25.53, 0.953)     # verifier 24.32 / 25.53
    assert (by["GBDC"]["nav"], by["GBDC"]["p_nav"]) == (14.25, 0.866)
    assert (by["ARCC"]["nav"], by["ARCC"]["p_nav"]) == (19.35, 0.979)
    assert breaking.p_nav(10.0, None) is None and breaking.p_nav(None, 10.0) is None and breaking.p_nav(10.0, 0) is None


def test_bdc_degrades_per_ticker(monkeypatch):
    _no_network(monkeypatch)
    rows = breaking.fetch_bdc()
    assert all(r["status"] == "error" and r["price"] is None and r["p_nav"] is None for r in rows)
    assert rows[2]["nav"] == 25.53                                  # the frozen table still carries the NAV


# ---------------------------------------------------------------------------
# Frozen events
# ---------------------------------------------------------------------------
def test_every_event_has_provenance_and_url():
    log = breaking.load_events()
    assert log["status"] == "ok" and log["n_dropped"] == 0 and log["rev"] == 1
    ev = log["events"]
    assert len(ev) >= 20
    for e in ev:
        assert breaking.validate_event(e) == [], e
        assert e["provenance"] in breaking.PROVENANCE
        assert e["src"].startswith("https://")
        assert "2026-06-01" <= e["date"] <= "2026-10-15"
        assert e["retrieved"] == "2026-10-15"
        assert e["verif"] in ("CONFIRMED", "CORRECTED")
    assert {e["provenance"] for e in ev} == set(breaking.PROVENANCE)
    assert ev == sorted(ev, key=lambda e: (e["date"], e.get("category", ""), e["text"]))
    texts = " ".join(e["text"] for e in ev)
    for must in ("BBB-", "1,194.5bp", "91.6 cents", "$4bn per operation", "$127bn", "12bp in 2026"):
        assert must in texts, must
    # corrected/dropped prints stay out: the finder's unsupported numbers never appear as facts
    assert "SoftBank 424" not in texts and "+74.5bp, ICE" not in texts.replace("'+74.5bp, ICE Data Services'", "")


def test_event_validation_rejects_bad_rows(tmp_path):
    good = {"date": "2026-10-15", "text": "x", "provenance": "press", "src": "https://a", "retrieved": "2026-10-15"}
    assert breaking.validate_event(good) == []
    assert "provenance" in breaking.validate_event({**good, "provenance": "blog"})
    assert "src" in breaking.validate_event({**good, "src": "see notes"})
    assert "date" in breaking.validate_event({**good, "date": "Oct 15"})
    assert "retrieved" in breaking.validate_event({**good, "retrieved": None})
    p = tmp_path / "ev.json"
    p.write_text(json.dumps({"rev": 9, "events": [good, {**good, "src": None}]}))
    log = breaking.load_events(str(p))
    assert len(log["events"]) == 1 and log["n_dropped"] == 1 and log["status"] == "ok"
    assert breaking.load_events(str(tmp_path / "missing.json"))["status"] == "error"


# ---------------------------------------------------------------------------
# The assembled breaking block
# ---------------------------------------------------------------------------
def test_breaking_block_json_status_and_sources():
    blk = breaking.fetch_block()
    json.dumps(blk)
    assert set(blk["status"]) == {"spreads", "yields", "baa10y", "ebp", "ofr_fsi", "move", "bdc", "events"}
    assert set(blk["status"].values()) == {"ok"}
    assert blk["asof"] == "2026-10-14"
    assert blk["ccc_b_gap"]["latest"] == 9.53
    for sub in ("spreads", "ccc_b_gap", "yields", "baa10y", "ebp", "ofr_fsi", "move"):
        node = blk[sub]
        if sub in ("spreads", "yields"):
            assert all("src" in v and "basis" in v for v in node.values())
        else:
            assert node["src"] and node["basis"]
    assert all(r["src"] and r["basis"] for r in [dict(r, basis=breaking.BDC_BASIS) for r in blk["bdc"]])
    assert blk["src"]["bdc_nav"]["BXSL"].startswith("https://www.sec.gov/") and blk["src"]["bdc_nav"]["OBDC"] is None
    assert len(blk["events"]) >= 20 and blk["events_meta"]["n_dropped"] == 0


def test_breaking_block_offline_degrades_to_nulls(monkeypatch):
    _no_network(monkeypatch)
    blk = breaking.fetch_block()
    json.dumps(blk)
    for k in ("spreads", "yields", "baa10y", "ebp", "ofr_fsi", "move", "bdc"):
        assert blk["status"][k] == "error", k
    assert blk["status"]["events"] == "ok"                          # the frozen log needs no network
    assert blk["ccc_b_gap"]["latest"] is None and blk["ccc_b_gap"]["n_dates"] == 0
    assert blk["spreads"]["ccc"]["latest"] is None and blk["spreads"]["ccc"]["hi_2026"] is None
    assert blk["move"]["latest"] is None and blk["ebp"]["latest"] is None
    assert all(r["price"] is None and r["p_nav"] is None for r in blk["bdc"])
    assert blk["asof"] is None


def test_stale_cache_served_when_fetch_fails(monkeypatch):
    first = breaking.fetch_ebp()
    assert first["status"] == "ok"
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: None)
    # expire the cache entry so the next call must try (and fail) the network
    path = os.path.join(fred_csv.settings.cache_dir, "fed_ebp.csv")
    os.utime(path, (0, 0))
    again = breaking.fetch_ebp()
    assert again["status"] == "stale" and again["latest"] == first["latest"]


# ---------------------------------------------------------------------------
# Reviewer defects B3-2 .. B3-6: parse-before-cache, header-resolved EBP,
# non-dict event rows, same-month share pairing, guarded optional fetches
# ---------------------------------------------------------------------------
def test_yahoo_error_body_never_poisons_the_cache(monkeypatch):
    good = breaking.fetch_yahoo_daily("ARCC")
    assert good["status"] == "ok" and good["closes"][-1] is not None
    os.utime(os.path.join(fred_csv.settings.cache_dir, "yahoo_ARCC.json"), (0, 0))
    err = b'{"chart":{"result":null,"error":{"code":"Not Found","description":"No data found"}}}'
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: err)
    again = breaking.fetch_yahoo_daily("ARCC")
    assert again["status"] == "stale" and again["closes"] == good["closes"]
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: None)            # network down next
    assert breaking.fetch_yahoo_daily("ARCC")["closes"] == good["closes"]
    assert not open(os.path.join(fred_csv.settings.cache_dir, "yahoo_ARCC.json"), "rb").read().startswith(err[:20])


def test_gpif_and_imf_bad_bodies_never_poison_the_cache(monkeypatch):
    g = pf.fetch_gpif()
    blk, _ = pf.fetch_imf_pip_japan_us()
    assert g["status"] == "ok" and blk["status"] == "ok"
    for name in ("gpif_holdings.xlsx", "imf_pip_jpn_usa.xml"):
        os.utime(os.path.join(fred_csv.settings.cache_dir, name), (0, 0))
    # a zip that is not the workbook (PK magic passes a structural check) / an SDMX body with no series
    monkeypatch.setattr(fred_csv, "_http_get_bytes",
                        lambda u, h=None: b"PK\x03\x04junk" if u == pf.GPIF_URL else b"<?xml version='1.0'?><PIP/>")
    g2 = pf.fetch_gpif()
    assert g2["status"] == "stale" and g2["foreign_bonds_jpy_trn"] == g["foreign_bonds_jpy_trn"]
    blk2, st2 = pf.fetch_imf_pip_japan_us()
    assert st2 == "stale" and blk2["total_usd_bn"] == blk["total_usd_bn"]
    # and an SDMX body without the <?xml declaration is still accepted (B3-11)
    raw = _fx("gpif_imf_pip_jpn_usa_trim.xml")
    stripped = raw[raw.index(b">") + 1:] if raw.lstrip().startswith(b"<?xml") else raw
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: stripped)
    os.utime(os.path.join(fred_csv.settings.cache_dir, "imf_pip_jpn_usa.xml"), (0, 0))
    assert pf.fetch_imf_pip_japan_us()[1] == "ok"


def test_ebp_renamed_or_missing_column_is_error_not_ok(monkeypatch):
    raw = _fx("ebp_fed_trim.csv")
    header, rest = raw.split(b"\n", 1)
    upper = header.replace(b"ebp", b"EBP").replace(b"gz_spread", b"GZ_Spread ") + b"\n" + rest
    p = breaking.parse_ebp(upper)                                   # case / whitespace differences resolve
    assert p["ebp"][-1] is not None and p["gz_spread"][-1] is not None
    renamed = header.replace(b"ebp", b"excess_bond_premium") + b"\n" + rest
    with pytest.raises(ValueError):
        breaking.parse_ebp(renamed)
    monkeypatch.setattr(fred_csv, "_http_get_bytes", lambda u, h=None: renamed)
    e = breaking.fetch_ebp()
    assert e["status"] == "error" and e["latest"] is None and e["ebp"] == []     # never ok with nulls (B3-3)
    empty = header + b"\n" + b"\n".join(l.rsplit(b",", 2)[0] + b",," for l in rest.split(b"\n") if l)
    with pytest.raises(ValueError):
        breaking.parse_ebp(empty)


def test_events_non_dict_row_is_dropped_not_fatal(tmp_path):
    good = {"date": "2026-10-15", "text": "x", "provenance": "press", "src": "https://a", "retrieved": "2026-10-15"}
    p = tmp_path / "ev.json"
    p.write_text(json.dumps({"rev": 9, "events": ["not a dict", 7, good]}))
    log = breaking.load_events(str(p))
    assert len(log["events"]) == 1 and log["n_dropped"] == 2 and log["status"] == "ok"
    p.write_text(json.dumps(["not", "an", "object"]))
    assert breaking.load_events(str(p))["status"] == "error"
    assert breaking.load_events()["src"].startswith("https://github.com/")


def test_official_share_pairs_the_same_month(monkeypatch):
    months = ["2026-06", "2026-07"]
    bc = {"asof": "2026-07", "months": months, "basis": "b", "src": {"fred_pattern": "u"}, "labels": {"official": "o"},
          "aggregates": {
              "official": {"status": "ok", "corp_pos": [310.0, 316.0], "corp_pos_latest": 316.0, "corp_net": [1, 2],
                           "corp_net_12m": 5.0, "treas_net_12m": 1.0},
              "non_official": {"status": "ok", "corp_pos": [4890.0, None], "corp_pos_latest": 4890.0, "corp_net": [3, 4],
                               "corp_net_12m": 9.0},
              "grand_total": {"status": "ok", "corp_pos": [5200.0, None], "corp_pos_latest": 5200.0}}}
    t = pf.official_corp_from_tic(bc)
    # July official over June Grand Total would be 6.1%; the same-month pairing is June over June
    assert t["share_asof"] == "2026-06" and t["pos"] == 310.0 and t["grand_total_pos"] == 5200.0
    assert t["share_of_foreign_held_pct"] == 6.0 and t["non_official_pos"] == 4890.0
    bc["aggregates"]["grand_total"]["corp_pos"] = [None, None]
    assert pf.official_corp_from_tic(bc)["share_of_foreign_held_pct"] is None


def test_fetch_block_survives_a_crashing_optional_fetch(monkeypatch):
    def boom():
        raise OSError("cache dir unwritable")
    monkeypatch.setattr(pf, "fetch_gpif", boom)
    monkeypatch.setattr(pf, "fetch_imf_pip_japan_us", boom)
    blk = pf.fetch_block()
    assert blk["status"]["gpif"] == "error" and blk["status"]["imf_pip"] == "error"
    assert blk["status"]["mof"] == "ok" and round(blk["trust_accounts_12m_jpy_trn"], 2) == 12.23   # the rest intact
    assert blk["z1_pensions"]["units_consistent"] is True
    assert "units_consistent" in pf.pensions_from_z1(None)                                     # B3-15
