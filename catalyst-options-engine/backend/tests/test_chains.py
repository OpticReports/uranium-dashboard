"""Chain lane parser against a REAL captured Nasdaq response shape
(tests/fixtures/nasdaq_chain_mrna.json, captured live 2026-08-19), including
the null-strike group-header rows."""
from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.engine.signals import atm_iv, expiry_after
from app.lanes import chains
from tests.conftest import FakeResponse, load_fixture

TODAY = date(2026, 8, 19)


@pytest.fixture()
def fixture():
    return load_fixture("nasdaq_chain_mrna.json")


def test_group_header_rows_are_skipped(fixture):
    raw_rows = fixture["data"]["table"]["rows"]
    n_headers = sum(1 for r in raw_rows if r.get("strike") is None)
    assert n_headers >= 3  # the fixture keeps three expiry groups
    _, rows = chains.parse_chain(fixture, TODAY)
    assert len(rows) == len(raw_rows) - n_headers
    assert all(r.strike is not None for r in rows)


def test_underlying_parsed_from_last_trade(fixture):
    underlying, _ = chains.parse_chain(fixture, TODAY)
    assert underlying == pytest.approx(145.5721)


def test_expiry_parsed_from_drilldown_url_including_next_year(fixture):
    _, rows = chains.parse_chain(fixture, TODAY)
    expiries = sorted({r.expiry for r in rows})
    assert date(2026, 8, 21) in expiries
    assert date(2026, 9, 18) in expiries
    # 'Jan 15' row: year comes from the drillDownURL (270115 -> 2027), not a guess
    assert date(2027, 1, 15) in expiries


def test_numeric_fields_parsed(fixture):
    _, rows = chains.parse_chain(fixture, TODAY)
    aug = [r for r in rows if r.expiry == date(2026, 8, 21)]
    r130 = next(r for r in aug if r.strike == 130.0)
    assert r130.c_bid == 16.00 and r130.c_ask == 19.00
    assert r130.p_bid == 5.00 and r130.p_ask == 7.10
    assert r130.c_last == 16.85


def test_short_expiry_year_inference():
    # no drillDownURL, no group header: 'Aug 21' -> current year;
    # a month >7d in the past rolls to next year.
    assert chains._expiry_from_short("Aug 21", TODAY) == date(2026, 8, 21)
    assert chains._expiry_from_short("Jan 15", TODAY) == date(2027, 1, 15)
    assert chains._expiry_from_short("garbage", TODAY) is None


def test_dash_and_empty_money_fields():
    assert chains._num("--") is None
    assert chains._num("") is None
    assert chains._num(None) is None
    assert chains._num("1,234.50") == 1234.5


def test_parsed_chain_feeds_atm_iv(fixture):
    """End-to-end: real shape -> rows -> a solvable ATM IV for a dated event."""
    underlying, rows = chains.parse_chain(fixture, TODAY)
    event = date(2026, 9, 10)
    exp = expiry_after(rows, event)
    assert exp == date(2026, 9, 18)
    iv = atm_iv(rows, underlying, event, TODAY)
    assert iv is not None
    assert 0.2 < iv < 5.0  # a real, plausible biotech pre-event vol


def test_fetch_chain_dark_lane_returns_none(monkeypatch, caplog):
    def boom(*a, **k):
        raise httpx.ConnectError("blocked from datacenter IP")

    monkeypatch.setattr(chains.httpx, "get", boom)
    monkeypatch.setattr(chains, "cached", lambda key, producer, ttl=None: producer())
    monkeypatch.setattr(chains, "with_backoff", lambda fn, **k: fn())
    with caplog.at_level("WARNING"):
        assert chains.fetch_chain("MRNA") is None
    assert any("DARK" in r.message for r in caplog.records)


def test_fetch_chain_parses_fixture(monkeypatch, fixture):
    monkeypatch.setattr(chains.httpx, "get",
                        lambda *a, **k: FakeResponse(fixture))
    monkeypatch.setattr(chains, "cached", lambda key, producer, ttl=None: producer())
    res = chains.fetch_chain("MRNA")
    assert res is not None
    underlying, rows = res
    assert underlying == pytest.approx(145.5721)
    assert len(rows) > 0
