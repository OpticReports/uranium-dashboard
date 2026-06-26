"""Analyst layer: rating changes, price-target & estimate revisions.

Revision VELOCITY (rate of change) is what the scoring engine consumes as a
leading indicator — this module just records individual revisions with a
direction so the engine can weight them by recency.

Primary source: FMP (price targets, estimates) when FMP_API_KEY is set.
Fallback: yfinance upgrades/downgrades (no key). Degrades to a no-op otherwise.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from sqlmodel import Session, select

from ..config import settings
from ..models import AnalystRevision
from .base import IngestionSource

logger = logging.getLogger(__name__)


class AnalystIngestion(IngestionSource):
    name = "analyst"

    def __init__(self) -> None:
        self.use_fmp = bool(settings.fmp_api_key)

    def fetch(self, symbol: str) -> dict:
        if self.use_fmp:
            from .providers.fmp_provider import FMPProvider

            fmp = FMPProvider()
            return {
                "source": "fmp",
                "price_targets": fmp.get_price_targets(symbol),
                "estimates": fmp.get_estimates(symbol),
            }
        return {"source": "yfinance", "updowngrades": self._yf_updowns(symbol)}

    def _yf_updowns(self, symbol: str):
        try:
            import yfinance as yf

            t = yf.Ticker(symbol)
            df = getattr(t, "upgrades_downgrades", None)
            if df is None or df.empty:
                return []
            rows = []
            for idx, row in df.head(40).iterrows():
                rows.append(
                    {
                        "date": idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10],
                        "firm": row.get("Firm"),
                        "from_grade": row.get("FromGrade"),
                        "to_grade": row.get("ToGrade"),
                        "action": row.get("Action"),
                    }
                )
            return rows
        except Exception as exc:  # noqa: BLE001
            logger.warning("yfinance upgrades/downgrades(%s) failed: %s", symbol, exc)
            return []

    def normalize(self, symbol: str, raw: dict) -> list[AnalystRevision]:
        records: list[AnalystRevision] = []
        if raw.get("source") == "fmp":
            for pt in raw.get("price_targets", []) or []:
                d = _parse_date(pt.get("publishedDate") or pt.get("date"))
                if not d:
                    continue
                new = pt.get("priceTarget")
                old = pt.get("priceWhenPosted")
                direction = _direction(old, new)
                records.append(
                    AnalystRevision(
                        symbol=symbol, date=d, firm=pt.get("analystCompany"),
                        metric="price_target", old_value=old, new_value=new,
                        direction=direction, note=pt.get("newsTitle"), source="fmp",
                    )
                )
            # EPS estimate revisions: compare consecutive estimate snapshots.
            ests = sorted(
                (e for e in raw.get("estimates", []) or [] if e.get("date")),
                key=lambda e: e["date"],
            )
            prev = None
            for e in ests:
                d = _parse_date(e.get("date"))
                cur = e.get("epsAvg", e.get("estimatedEpsAvg"))  # stable | legacy
                if d and prev is not None and cur is not None:
                    records.append(
                        AnalystRevision(
                            symbol=symbol, date=d, metric="eps",
                            old_value=prev, new_value=cur,
                            direction=_direction(prev, cur), source="fmp",
                        )
                    )
                if cur is not None:
                    prev = cur
        else:
            grade_rank = {
                "strong sell": 0, "sell": 1, "underperform": 1, "hold": 2,
                "neutral": 2, "market perform": 2, "buy": 3, "outperform": 3,
                "overweight": 3, "strong buy": 4,
            }
            for row in raw.get("updowngrades", []):
                d = _parse_date(row.get("date"))
                if not d:
                    continue
                fr = grade_rank.get(str(row.get("from_grade", "")).lower())
                to = grade_rank.get(str(row.get("to_grade", "")).lower())
                direction = 0
                if fr is not None and to is not None:
                    direction = 1 if to > fr else (-1 if to < fr else 0)
                elif row.get("action") in ("up", "init"):
                    direction = 1
                elif row.get("action") == "down":
                    direction = -1
                records.append(
                    AnalystRevision(
                        symbol=symbol, date=d, firm=row.get("firm"),
                        metric="rating", direction=direction,
                        note=f"{row.get('from_grade')} -> {row.get('to_grade')}",
                        source="yfinance",
                    )
                )
        return records

    def upsert(self, session: Session, records: list[AnalystRevision]) -> int:
        n = 0
        for rec in records:
            exists = session.exec(
                select(AnalystRevision)
                .where(AnalystRevision.symbol == rec.symbol)
                .where(AnalystRevision.date == rec.date)
                .where(AnalystRevision.metric == rec.metric)
                .where(AnalystRevision.firm == rec.firm)
                .where(AnalystRevision.new_value == rec.new_value)
            ).first()
            if not exists:
                session.add(rec)
                n += 1
        session.commit()
        return n


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:19]).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _direction(old, new) -> int:
    if old is None or new is None:
        return 0
    if new > old:
        return 1
    if new < old:
        return -1
    return 0
