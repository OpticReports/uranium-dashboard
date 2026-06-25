"""Market / financials ingestion (OHLCV + fundamentals + positioning).

Uses the configured MarketProvider. Computes cash runway as a first-class risk
metric. Missing options/short-interest data is stored as NULL, never 0.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from ..models import Fundamental, PriceBar
from .base import IngestionSource
from .providers.base import get_provider

logger = logging.getLogger(__name__)


class MarketIngestion(IngestionSource):
    name = "market"

    def __init__(self, lookback_days: int = 7) -> None:
        self.provider = get_provider()
        self.lookback_days = lookback_days

    def fetch(self, symbol: str, start: date | None = None, end: date | None = None) -> dict:
        end = end or date.today() + timedelta(days=1)
        start = start or (end - timedelta(days=self.lookback_days))
        ohlcv = self.provider.get_ohlcv(symbol, start, end)
        fundamentals = self.provider.get_fundamentals(symbol)
        return {"ohlcv": ohlcv, "fundamentals": fundamentals}

    def normalize(self, symbol: str, raw: dict) -> list:
        records: list = []
        for bar in raw.get("ohlcv", []):
            try:
                d = date.fromisoformat(bar["date"][:10])
            except (KeyError, ValueError):
                continue
            records.append(
                PriceBar(
                    symbol=symbol,
                    date=d,
                    open=bar.get("open"),
                    high=bar.get("high"),
                    low=bar.get("low"),
                    close=bar.get("close"),
                    adj_close=bar.get("adj_close"),
                    volume=bar.get("volume"),
                    source=self.provider.name,
                )
            )
        f = raw.get("fundamentals") or {}
        if any(v is not None for v in f.values()):
            records.append(
                Fundamental(
                    symbol=symbol,
                    asof=date.today(),
                    market_cap=f.get("market_cap"),
                    cash=f.get("cash"),
                    quarterly_burn=f.get("quarterly_burn"),
                    rd_spend=f.get("rd_spend"),
                    runway_quarters=f.get("runway_quarters"),
                    short_interest_pct=f.get("short_interest_pct"),
                    iv=f.get("iv"),
                    iv_skew=f.get("iv_skew"),
                    source=self.provider.name,
                )
            )
        return records

    def upsert(self, session: Session, records: list) -> int:
        n = 0
        for rec in records:
            if isinstance(rec, PriceBar):
                existing = session.exec(
                    select(PriceBar)
                    .where(PriceBar.symbol == rec.symbol)
                    .where(PriceBar.date == rec.date)
                ).first()
                if existing:
                    existing.open, existing.high, existing.low = rec.open, rec.high, rec.low
                    existing.close, existing.adj_close = rec.close, rec.adj_close
                    existing.volume, existing.source = rec.volume, rec.source
                    session.add(existing)
                else:
                    session.add(rec)
                n += 1
            elif isinstance(rec, Fundamental):
                existing = session.exec(
                    select(Fundamental)
                    .where(Fundamental.symbol == rec.symbol)
                    .where(Fundamental.asof == rec.asof)
                ).first()
                if existing:
                    for field in (
                        "market_cap", "cash", "quarterly_burn", "rd_spend",
                        "runway_quarters", "short_interest_pct", "iv", "iv_skew", "source",
                    ):
                        setattr(existing, field, getattr(rec, field))
                    session.add(existing)
                else:
                    session.add(rec)
                n += 1
        session.commit()
        # Recompute cross-sectional short-interest percentiles after writes.
        _recompute_si_percentiles(session)
        return n

    def backfill(self, session: Session, symbol: str, years: int = 2) -> int:
        """Build price history from day one for a (possibly newly added) name."""
        end = date.today() + timedelta(days=1)
        start = end - timedelta(days=365 * years)
        raw = self.fetch(symbol, start=start, end=end)
        records = self.normalize(symbol, raw)
        n = self.upsert(session, records)
        logger.info("Backfilled %d market rows for %s", n, symbol)
        return n


def _recompute_si_percentiles(session: Session) -> None:
    """Universe-relative short-interest percentile on the latest fundamentals."""
    latest: dict[str, Fundamental] = {}
    for f in session.exec(select(Fundamental).order_by(Fundamental.asof.asc())).all():
        latest[f.symbol] = f  # keep the newest per symbol
    values = [f.short_interest_pct for f in latest.values() if f.short_interest_pct is not None]
    if not values:
        return
    sorted_vals = sorted(values)
    for f in latest.values():
        if f.short_interest_pct is None:
            f.short_interest_percentile = None
        else:
            below = sum(1 for v in sorted_vals if v <= f.short_interest_pct)
            f.short_interest_percentile = below / len(sorted_vals)
        session.add(f)
    session.commit()
