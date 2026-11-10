"""Ingestion orchestration shared by the scheduler and backfill scripts."""
from __future__ import annotations

import logging

from sqlmodel import Session, select

from ..models import Security
from .analyst import AnalystIngestion
from .catalysts import CatalystIngestion
from .insiders import InsiderIngestion
from .market import MarketIngestion
from .science import ScienceIngestion
from .shortinterest import ShortInterestIngestion
from .social import SocialIngestion

logger = logging.getLogger(__name__)


def active_symbols(session: Session) -> list[str]:
    secs = session.exec(select(Security).where(Security.active == True)).all()  # noqa: E712
    return [s.symbol for s in secs]


def name_map(session: Session) -> dict[str, str]:
    return {s.symbol: s.name for s in session.exec(select(Security)).all()}


def ctgov_alias_map(session: Session) -> dict[str, list[str]]:
    """symbol -> CT.gov registered sponsor aliases (only names that set them)."""
    return {
        s.symbol: list(s.ctgov_names)
        for s in session.exec(select(Security)).all()
        if s.ctgov_names
    }


def run_market(session: Session, symbols: list[str] | None = None) -> int:
    src = MarketIngestion()
    symbols = symbols or active_symbols(session)
    return sum(src.run(session, sym) for sym in symbols)


def run_analyst(session: Session, symbols: list[str] | None = None) -> int:
    src = AnalystIngestion()
    symbols = symbols or active_symbols(session)
    return sum(src.run(session, sym) for sym in symbols)


def run_catalysts(session: Session, symbols: list[str] | None = None) -> int:
    src = CatalystIngestion(name_map=name_map(session), alias_map=ctgov_alias_map(session))
    symbols = symbols or active_symbols(session)
    return sum(src.run(session, sym) for sym in symbols)


def run_science(session: Session, symbols: list[str] | None = None) -> int:
    src = ScienceIngestion(name_map=name_map(session))
    symbols = symbols or active_symbols(session)
    return sum(src.run(session, sym) for sym in symbols)


def run_social(session: Session, symbols: list[str] | None = None) -> int:
    src = SocialIngestion()
    symbols = symbols or active_symbols(session)
    return sum(src.run(session, sym) for sym in symbols)


def run_insiders(session: Session, symbols: list[str] | None = None) -> int:
    src = InsiderIngestion()
    symbols = symbols or active_symbols(session)
    return sum(src.run(session, sym) for sym in symbols)


def run_short_interest(session: Session, symbols: list[str] | None = None) -> int:
    src = ShortInterestIngestion()
    symbols = symbols or active_symbols(session)
    return sum(src.run(session, sym) for sym in symbols)


def run_benchmarks(session: Session) -> int:
    """Ingest benchmark ETF price series (XBI/ARKG/NBI...) for relative strength.

    Benchmarks live as INACTIVE Security rows (subsector ["benchmark"]) so they
    hold price history without entering scoring, views, or per-name ingestion.
    First run backfills two years; subsequent runs top up the recent window.
    """
    from datetime import date, timedelta

    from ..config import scoring_config
    from ..models import PriceBar

    symbols = scoring_config().get("benchmarks", []) or []
    src = MarketIngestion()
    n = 0
    for sym in symbols:
        sym = str(sym).upper()
        sec = session.get(Security, sym)
        if sec is None:
            session.add(Security(symbol=sym, name=f"{sym} (benchmark)",
                                 subsector=["benchmark"], active=False))
            session.commit()
        has_history = session.exec(
            select(PriceBar).where(PriceBar.symbol == sym)
            .where(PriceBar.date >= date.today() - timedelta(days=120)).limit(1)
        ).first() is not None
        if has_history:
            n += src.run(session, sym)
        else:
            n += src.backfill(session, sym, years=2)
    return n


def backfill_symbol(session: Session, symbol: str, years: int = 2) -> dict:
    """Full backfill for a single (often newly added) name. Best-effort per layer."""
    logger.info("Backfilling %s", symbol)
    nm = name_map(session)
    results = {}
    results["market"] = MarketIngestion().backfill(session, symbol, years=years)
    results["analyst"] = AnalystIngestion().run(session, symbol)
    results["catalysts"] = CatalystIngestion(
        name_map=nm, alias_map=ctgov_alias_map(session)
    ).run(session, symbol)
    results["science"] = ScienceIngestion(name_map=nm).run(session, symbol)
    results["social"] = SocialIngestion().run(session, symbol)
    return results


def run_all(session: Session, symbols: list[str] | None = None) -> dict:
    return {
        "market": run_market(session, symbols),
        "analyst": run_analyst(session, symbols),
        "catalysts": run_catalysts(session, symbols),
        "science": run_science(session, symbols),
        "social": run_social(session, symbols),
        "insiders": run_insiders(session, symbols),
        "short_interest": run_short_interest(session, symbols),
        "benchmarks": run_benchmarks(session),
    }


def run_news(session: Session, symbols: list[str] | None = None) -> int:
    from .news_tiingo import run_news as _rn
    return _rn(session, symbols)
