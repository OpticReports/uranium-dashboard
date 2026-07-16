"""Short-interest ingestion tests (offline — FINRA payloads are stubbed)."""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import select

from app.ingestion.shortinterest import ShortInterestIngestion, si_pct
from app.models import Fundamental, PriceBar, Security


def test_si_pct_math():
    # 10M short shares, $50 close, $2B mcap -> 40M shares out -> 25%
    assert abs(si_pct(10e6, 50.0, 2e9) - 0.25) < 1e-9
    assert si_pct(None, 50.0, 2e9) is None
    assert si_pct(10e6, None, 2e9) is None
    assert si_pct(10e6, 50.0, None) is None
    assert si_pct(10e6, 50.0, 0) is None


def test_normalize_picks_latest_settlement():
    src = ShortInterestIngestion()
    raw = [
        {"settlementDate": "2026-05-15", "currentShortPositionQuantity": 1_000_000},
        {"settlementDate": "2026-06-30", "currentShortPositionQuantity": 3_000_000},
        {"settlementDate": "2026-06-13", "currentShortPositionQuantity": 2_000_000},
    ]
    recs = src.normalize("crsp", raw)
    assert len(recs) == 1
    assert recs[0]["symbol"] == "CRSP"
    assert recs[0]["settlement_date"] == "2026-06-30"
    assert recs[0]["short_shares"] == 3_000_000.0


def test_normalize_empty_and_missing_fields():
    src = ShortInterestIngestion()
    assert src.normalize("CRSP", []) == []
    assert src.normalize("CRSP", None) == []
    assert src.normalize("CRSP", [{"settlementDate": "2026-06-30"}]) == []


def test_upsert_writes_todays_fundamental(session):
    session.add(Security(symbol="CRSP", name="CRISPR", active=True))
    session.add(PriceBar(symbol="CRSP", date=date.today() - timedelta(days=1), close=50.0))
    session.add(Fundamental(symbol="CRSP", asof=date.today() - timedelta(days=1),
                            market_cap=2e9, cash=1e9, runway_quarters=10.0))
    session.commit()

    src = ShortInterestIngestion()
    n = src.upsert(session, [{"symbol": "CRSP", "settlement_date": "2026-06-30",
                              "short_shares": 10e6, "days_to_cover": 3.1}])
    assert n == 1
    fund = session.exec(
        select(Fundamental).where(Fundamental.symbol == "CRSP")
        .order_by(Fundamental.asof.desc())
    ).first()
    assert fund.asof == date.today()
    assert abs(fund.short_interest_pct - 0.25) < 1e-9
    assert fund.market_cap == 2e9          # carried forward, not wiped
    assert fund.runway_quarters == 10.0
    assert fund.short_interest_percentile is not None


def test_upsert_skips_without_market_cap(session):
    session.add(Security(symbol="NOMC", name="No MCap", active=True))
    session.add(PriceBar(symbol="NOMC", date=date.today(), close=10.0))
    session.commit()
    src = ShortInterestIngestion()
    n = src.upsert(session, [{"symbol": "NOMC", "settlement_date": "2026-06-30",
                              "short_shares": 1e6, "days_to_cover": 1.0}])
    assert n == 0  # no denominator -> no fake number
