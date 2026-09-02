"""Gate tests for the keyless equity lane, using the REAL FAMI history and
quote payloads captured on 2026-09-02."""
from __future__ import annotations

from app.lanes.equity import (average_volume, parse_history, parse_quote,
                              parse_sec_universe)
from tests.conftest import load


def test_sec_universe_maps_ticker_to_the_exact_company_title():
    """This exactness is what makes the on-chain mapping deterministic: the
    tokenized Farmmi token is named byte-for-byte 'Farmmi, Inc.'."""
    universe = parse_sec_universe(load("sec_company_tickers.json"))
    assert universe["FAMI"] == "Farmmi, Inc."
    assert universe["MU"] == "MICRON TECHNOLOGY INC"


def test_sec_universe_survives_junk_rows():
    assert parse_sec_universe({"0": {"ticker": "X"}, "1": None,
                               "2": {"ticker": "OK", "title": "Ok Inc"}}) == {"OK": "Ok Inc"}


def test_history_is_normalised_oldest_first():
    bars = parse_history(load("fami_history.json"))
    assert len(bars) > 3
    assert bars[0]["date"] < bars[-1]["date"]
    assert all(b["volume"] is not None for b in bars)


def test_average_volume_is_a_median_so_one_spike_cannot_hide_the_next():
    """The event being hunted IS the volume spike. A 20-day MEAN including one
    720M-share day would lift the baseline ~35x and make the very next spike
    look unremarkable, so the baseline must be a median."""
    bars = parse_history(load("fami_history.json"))
    clean = average_volume(bars)
    spiked = average_volume(bars[:-1] + [{"date": "2026-09-02", "volume": 720_000_000}])
    assert clean is not None
    assert spiked is not None
    assert spiked < clean * 2, "one spike moved the baseline more than 2x"


def test_average_volume_needs_enough_bars():
    assert average_volume([{"date": "d", "volume": 1}]) is None


def test_parse_quote_maps_the_short_field_names():
    q = parse_quote({"status": 200, "data": {
        "p": 0.1518, "cl": 0.1187, "cp": 27.89, "v": 807631865,
        "h52": 2.05, "l52": 0.0919, "ex": "NASDAQ", "ms": "open"}})
    assert q["price"] == 0.1518
    assert q["prev_close"] == 0.1187
    assert q["exchange"] == "NASDAQ"


def test_parse_quote_on_junk_is_empty_not_an_exception():
    assert parse_quote({}) == {}
    assert parse_quote({"data": None}) == {}
    assert parse_history({"data": "nope"}) == []


def test_fmp_profile_parses_the_stable_shape():
    """FMP /stable/profile returns a single-element LIST, and the pre-2025
    /api/v3 routes refuse newer keys — so only this shape is supported."""
    from app.lanes.fundamentals import parse_profile
    out = parse_profile([{"symbol": "FAMI", "marketCap": 5_746_131,
                          "averageVolume": 2_454_838, "companyName": "Farmmi, Inc.",
                          "exchange": "NASDAQ", "industry": "Packaged Foods"}])
    assert out["market_cap"] == 5_746_131
    assert out["company"] == "Farmmi, Inc."


def test_fmp_profile_on_junk_is_empty():
    from app.lanes.fundamentals import parse_profile
    for junk in ([], {}, None, ["nope"], {"Error Message": "Invalid API KEY"}):
        assert parse_profile(junk) in ({}, {"market_cap": None, "avg_volume": None,
                                            "company": "", "exchange": "",
                                            "industry": ""})


def test_sec_user_agent_carries_a_contact_address():
    """sec.gov answers 403 to a User-Agent without contact info (verified
    2026-09-02), so this is a hard requirement, not etiquette."""
    from app.config import sec_user_agent, settings
    ua = sec_user_agent(settings.sec_contact)
    assert "@" in ua and "." in ua.split("@")[-1]


# --- the nanocap-first sweep order ----------------------------------------

def _band(rows):
    return [rows]


def test_microcap_universe_is_ordered_smallest_first():
    """Sweep ORDER is the whole point: the alphabetical fallback needs ~2 days
    to reach every ticker, so nanocaps have to come first or the Farmmi shape
    surfaces last on a fresh deploy."""
    from app.lanes.fundamentals import parse_microcap_universe
    out = parse_microcap_universe([[
        {"symbol": "BIG", "marketCap": 240_000_000, "exchangeShortName": "NYSE"},
        {"symbol": "TINY", "marketCap": 4_000_000, "exchangeShortName": "NASDAQ"},
        {"symbol": "MID", "marketCap": 60_000_000, "exchangeShortName": "AMEX"},
    ]])
    assert out == ["TINY", "MID", "BIG"]


def test_microcap_universe_drops_funds_and_foreign_venues():
    """A tokenized wrapper for a foreign listing cannot trade against the
    Nasdaq tape this service watches, and an ETF is not a squeeze candidate."""
    from app.lanes.fundamentals import parse_microcap_universe
    out = parse_microcap_universe([[
        {"symbol": "OK", "marketCap": 10_000_000, "exchangeShortName": "NASDAQ"},
        {"symbol": "ETF", "marketCap": 5_000_000, "exchangeShortName": "NASDAQ",
         "isEtf": True},
        {"symbol": "FUND", "marketCap": 6_000_000, "exchangeShortName": "AMEX",
         "isFund": True},
        {"symbol": "FOREIGN", "marketCap": 7_000_000, "exchangeShortName": "SHZ"},
    ]])
    assert out == ["OK"]


def test_microcap_universe_dedupes_across_bands():
    from app.lanes.fundamentals import parse_microcap_universe
    row = {"symbol": "DUP", "marketCap": 9_000_000, "exchangeShortName": "NASDAQ"}
    assert parse_microcap_universe([[row], [row]]) == ["DUP"]


def test_microcap_universe_survives_junk():
    from app.lanes.fundamentals import parse_microcap_universe
    assert parse_microcap_universe(None) == []
    assert parse_microcap_universe([None, "nope", [{"symbol": ""}, {}]]) == []
