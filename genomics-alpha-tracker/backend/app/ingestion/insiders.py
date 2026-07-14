"""Insider-transaction ingestion (Form 4 style), free via yfinance.

Open-market buys are the signal the desk cares about ("insiders putting their
own money in"); sales are stored too so the flag logic can evolve. Column
layouts vary across yfinance versions, so parsing is defensive — a symbol
whose insider table is unavailable simply writes nothing (never crashes).
"""
from __future__ import annotations

import logging
from datetime import date

from sqlmodel import Session, select

from ..models import InsiderTxn
from ..utils.ratelimit import with_backoff
from .base import IngestionSource

logger = logging.getLogger(__name__)

_BUY_WORDS = ("purchase", "buy")
_SELL_WORDS = ("sale", "sell")


def _classify(text: str | None) -> str:
    t = (text or "").lower()
    if any(w in t for w in _BUY_WORDS):
        return "buy"
    if any(w in t for w in _SELL_WORDS):
        return "sell"
    return "other"


def _f(v):
    try:
        if v is None:
            return None
        f = float(v)
        return None if f != f else f  # NaN -> None
    except (TypeError, ValueError):
        return None


class InsiderIngestion(IngestionSource):
    name = "insiders"

    def fetch(self, symbol: str):
        import yfinance as yf  # lazy import, consistent with the market provider

        t = yf.Ticker(symbol)
        return with_backoff(lambda: t.insider_transactions)

    def normalize(self, symbol: str, raw) -> list[InsiderTxn]:
        records: list[InsiderTxn] = []
        if raw is None or getattr(raw, "empty", True):
            return records
        df = raw.reset_index()
        cols = {str(c).strip().lower(): c for c in df.columns}

        def col(row, *names):
            for n in names:
                c = cols.get(n)
                if c is not None:
                    return row.get(c)
            return None

        for _, row in df.iterrows():
            when = col(row, "start date", "date", "startdate", "latest transaction date")
            try:
                d = date.fromisoformat(str(when)[:10])
            except (TypeError, ValueError):
                continue
            txn_text = col(row, "transaction", "transaction text", "text")
            records.append(
                InsiderTxn(
                    symbol=symbol,
                    date=d,
                    insider=str(col(row, "insider", "name") or "").strip()[:120],
                    title=(str(col(row, "position", "title") or "").strip()[:120] or None),
                    txn_type=_classify(str(txn_text) if txn_text is not None else None),
                    shares=_f(col(row, "shares")),
                    value=_f(col(row, "value")),
                    source="yfinance",
                )
            )
        return records

    def upsert(self, session: Session, records: list[InsiderTxn]) -> int:
        n = 0
        for rec in records:
            existing = session.exec(
                select(InsiderTxn)
                .where(InsiderTxn.symbol == rec.symbol)
                .where(InsiderTxn.date == rec.date)
                .where(InsiderTxn.insider == rec.insider)
                .where(InsiderTxn.shares == rec.shares)
                .where(InsiderTxn.txn_type == rec.txn_type)
            ).first()
            if existing is None:
                session.add(rec)
                n += 1
        session.commit()
        return n
