"""Google Trends attention lane — RATE-BUDGETED, per-request billed.

Reads backend/config/trends.yaml (keyword -> traded proxy + theme), pulls
each keyword's past-5-years WEEKLY interest from DataForSEO, and stores it
in trend_point. The traded proxy's price history is kept the way benchmarks
are: an INACTIVE Security row (subsector ["trends_proxy"]) so it holds
price_bar rows without entering scoring or the universe views.

Budget rules (same shape as news_tiingo.py / social.py):
- $0.009 per request, one request per keyword per UTC day. A keyword
  already refreshed today is skipped, so a restart never double-spends.
- TRENDS_DAILY_CAP (default 40) hard in-process cap per UTC day.
- 401/402/403 trips a 24h breaker (bad key / no funds / forbidden).
- No credentials: log once and return 0. The router serves what's stored.

Because the 0-100 index is renormalised per request window, a successful
fetch REPLACES the keyword's stored series rather than appending to it -
mixing two windows' scales would corrupt the ratios the detector uses.

OBSERVE-ONLY: nothing here feeds a score or a call (HYPOTHESES.md H14).
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta, timezone

from sqlmodel import Session, select, delete

from ..config import load_yaml_config, settings
from ..models import PriceBar, Security, TrendPoint
from ..trends.dataforseo import TrendsError, fetch_interest, redact

logger = logging.getLogger(__name__)

_BUDGET = {"day": None, "used": 0, "cost_usd": 0.0}
_BREAKER = {"until": 0.0, "reason": None}
_FETCHED = {"day": None, "keywords": set()}


def config() -> dict:
    return load_yaml_config("trends.yaml")


def keywords() -> list[dict]:
    return [k for k in (config().get("keywords") or []) if k.get("keyword")]


def _cap() -> int:
    return int(os.environ.get("TRENDS_DAILY_CAP", "40"))


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _spend(cost: float = 0.0) -> bool:
    today = _today()
    if _BUDGET["day"] != today:
        _BUDGET.update({"day": today, "used": 0, "cost_usd": 0.0})
    if _BUDGET["used"] >= _cap():
        return False
    _BUDGET["used"] += 1
    _BUDGET["cost_usd"] += cost
    return True


def _already_today(keyword: str) -> bool:
    today = _today()
    if _FETCHED["day"] != today:
        _FETCHED.update({"day": today, "keywords": set()})
    return keyword in _FETCHED["keywords"]


def trip_breaker(status: int | None) -> None:
    hours = 24 if status in (401, 402, 403, 40100, 40200) else 6
    _BREAKER.update({"until": time.time() + hours * 3600, "reason": status})
    logger.warning("trends: DataForSEO status %s - pausing %dh", status, hours)


def status() -> dict:
    """For /trends/status and /health: budget + breaker, never credentials."""
    return {"configured": bool(settings.dataforseo_login and settings.dataforseo_password),
            "daily_cap": _cap(), "used_today": _BUDGET["used"] if _BUDGET["day"] == _today() else 0,
            "cost_today_usd": round(_BUDGET["cost_usd"], 3) if _BUDGET["day"] == _today() else 0.0,
            "breaker_until": _BREAKER["until"] if _BREAKER["until"] > time.time() else None,
            "keywords": len(keywords())}


def replace_series(session: Session, keyword: str, points: list[dict], window: str) -> int:
    session.exec(delete(TrendPoint).where(TrendPoint.keyword == keyword))
    now = datetime.now(timezone.utc)
    n = 0
    for p in points:
        session.add(TrendPoint(keyword=keyword, date=date.fromisoformat(p["date"]),
                               value=p["value"], missing=p.get("missing", False),
                               window=window, fetched_at=now))
        n += 1
    session.commit()
    return n


def ensure_proxy_prices(session: Session, symbol: str, years: int = 5) -> int:
    """Benchmark pattern: inactive Security row + price backfill/top-up."""
    from .market import MarketIngestion
    sym = symbol.upper()
    if session.get(Security, sym) is None:
        session.add(Security(symbol=sym, name=f"{sym} (trends proxy)",
                             subsector=["trends_proxy"], active=False))
        session.commit()
    src = MarketIngestion()
    recent = session.exec(select(PriceBar).where(PriceBar.symbol == sym)
                          .where(PriceBar.date >= date.today() - timedelta(days=120))
                          .limit(1)).first()
    try:
        return src.run(session, sym) if recent is not None else src.backfill(session, sym, years=years)
    except Exception as exc:  # noqa: BLE001 - price is optional context for the detector
        logger.warning("trends: price top-up failed for %s: %s", sym, exc)
        return 0


def run_trends(session: Session, symbols: list[str] | None = None) -> int:
    """Scheduler entry point. Returns number of stored weekly points."""
    login, password = settings.dataforseo_login, settings.dataforseo_password
    kws = keywords()
    # Price proxies first: keyless-safe (uses the configured market provider)
    # and useful even before DataForSEO credentials exist.
    for k in kws:
        if k.get("price_symbol"):
            ensure_proxy_prices(session, k["price_symbol"])
    if not (login and password):
        logger.info("trends: DATAFORSEO_LOGIN/PASSWORD unset - interest fetch skipped")
        return 0
    if time.time() < _BREAKER["until"]:
        return 0
    window = str(config().get("time_range") or "past_5_years")
    stored = 0
    for k in kws:
        kw = k["keyword"]
        if _already_today(kw):
            continue
        if not _spend():
            logger.warning("trends: daily cap %d reached - deferring rest", _cap())
            break
        try:
            points, cost = fetch_interest(kw, login, password, time_range=window,
                                          search_type=str(k.get("type") or "web"),
                                          location_code=k.get("location_code"))
            _BUDGET["cost_usd"] += cost
        except TrendsError as exc:
            if exc.status in (401, 402, 403, 40100, 40200):
                trip_breaker(exc.status)
                return stored
            logger.warning("trends: %s failed: %s", kw, redact(str(exc)))
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("trends: %s failed: %s", kw, redact(str(exc)))
            continue
        if len(points) < 52:
            logger.warning("trends: %s returned %d points (<52) - kept previous series", kw, len(points))
            continue
        stored += replace_series(session, kw, points, window)
        _FETCHED["keywords"].add(kw)
    return stored
