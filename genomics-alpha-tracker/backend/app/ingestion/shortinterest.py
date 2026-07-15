"""Short-interest ingestion from FINRA's public API (official, no key).

Why this exists: the FMP plan carries no short-interest or options data, so
under MARKET_PROVIDER=fmp the positioning signal was structurally empty (every
name n/a). FINRA publishes consolidated short interest bi-monthly and its
equity dataset is queryable anonymously — this source fills
Fundamental.short_interest_pct from it.

Denominator note: FINRA reports short SHARES. We convert to a percentage
using shares outstanding approximated as market_cap / last_close (float data
isn't free). That slightly understates float-based SI%, but positioning is a
CROSS-SECTIONAL percentile, so a consistent proxy ranks names correctly.

Options IV/skew still needs a paid feed — positioning runs on the
short-interest leg alone until then (the engine averages whichever legs exist).
"""
from __future__ import annotations

import logging
from datetime import date

import httpx
from sqlmodel import Session, select

from ..config import settings
from ..models import Fundamental, PriceBar
from ..utils.ratelimit import with_backoff
from .base import IngestionSource

logger = logging.getLogger(__name__)

_FINRA_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"


def si_pct(short_shares: float | None, last_close: float | None,
           market_cap: float | None) -> float | None:
    """Short interest as a fraction of (approximate) shares outstanding."""
    if not short_shares or not last_close or not market_cap or market_cap <= 0:
        return None
    shares_out = market_cap / last_close
    if shares_out <= 0:
        return None
    return short_shares / shares_out


class ShortInterestIngestion(IngestionSource):
    name = "short_interest"

    def fetch(self, symbol: str):
        body = {
            "compareFilters": [
                {"fieldName": "symbolCode", "fieldValue": symbol.upper(),
                 "compareType": "EQUAL"}
            ],
            "limit": 5000,
        }
        resp = with_backoff(lambda: httpx.post(
            _FINRA_URL, json=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=settings.http_timeout_seconds,
        ))
        resp.raise_for_status()
        return resp.json() or []

    def normalize(self, symbol: str, raw) -> list[dict]:
        """Keep only the LATEST settlement (FINRA forbids server-side sort here)."""
        rows = [r for r in (raw or []) if r.get("settlementDate")]
        if not rows:
            return []
        latest = max(rows, key=lambda r: r["settlementDate"])
        shares = latest.get("currentShortPositionQuantity")
        if shares is None:
            return []
        return [{
            "symbol": symbol.upper(),
            "settlement_date": latest["settlementDate"],
            "short_shares": float(shares),
            "days_to_cover": latest.get("daysToCoverQuantity"),
        }]

    def upsert(self, session: Session, records: list[dict]) -> int:
        n = 0
        for rec in records:
            sym = rec["symbol"]
            bar = session.exec(
                select(PriceBar).where(PriceBar.symbol == sym)
                .where(PriceBar.close != None)  # noqa: E711
                .order_by(PriceBar.date.desc()).limit(1)
            ).first()
            fund = session.exec(
                select(Fundamental).where(Fundamental.symbol == sym)
                .order_by(Fundamental.asof.desc()).limit(1)
            ).first()
            pct = si_pct(
                rec["short_shares"],
                bar.close if bar else None,
                fund.market_cap if fund else None,
            )
            if pct is None:
                continue
            if fund is not None and fund.asof == date.today():
                fund.short_interest_pct = pct
                fund.source = f"{fund.source}+finra"
                session.add(fund)
            else:
                session.add(Fundamental(
                    symbol=sym, asof=date.today(),
                    market_cap=fund.market_cap if fund else None,
                    cash=fund.cash if fund else None,
                    quarterly_burn=fund.quarterly_burn if fund else None,
                    rd_spend=fund.rd_spend if fund else None,
                    runway_quarters=fund.runway_quarters if fund else None,
                    short_interest_pct=pct,
                    iv=fund.iv if fund else None,
                    iv_skew=fund.iv_skew if fund else None,
                    source="finra",
                ))
            n += 1
        session.commit()
        if n:
            from .market import _recompute_si_percentiles

            _recompute_si_percentiles(session)
        return n
