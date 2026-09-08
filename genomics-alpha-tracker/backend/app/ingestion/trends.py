"""Google Trends attention lane — RATE-BUDGETED, per-request billed.

Reads backend/config/trends.yaml (keyword -> traded proxy + theme), pulls
each keyword's past-5-years WEEKLY interest from DataForSEO, and stores it
in trend_point. The traded proxy's price history is kept the way benchmarks
are: an INACTIVE Security row (subsector ["trends_proxy"]) so it holds
price_bar rows without entering scoring or the universe views.

Budget rules (same shape as news_tiingo.py / social.py):
- $0.009 per request, one request per keyword per UTC day. The dedupe is
  DB-backed (max trend_point.fetched_at per keyword), so a restart or a
  redeploy - which fires the job immediately - never double-spends.
- TRENDS_DAILY_CAP (default 40) hard in-process cap per UTC day (resets on
  restart; the DB dedupe is what bounds spend across restarts).
- Any 401xx/402xx task status (bad key, unverified account, no funds,
  paused, cost limit, IP not whitelisted...) or HTTP 403 trips a 24h
  breaker; 402x2/402x9 rate limits get 1h. DataForSEO returns HTTP 200 with
  the error in the task status, so the match is by code family, not code.
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


def _already_today(keyword: str, session: Session | None = None) -> bool:
    today = _today()
    if _FETCHED["day"] != today:
        _FETCHED.update({"day": today, "keywords": set()})
    if keyword in _FETCHED["keywords"]:
        return True
    if session is not None:
        # survives restarts: the stored series carries its fetch time
        last = session.exec(select(TrendPoint.fetched_at)
                            .where(TrendPoint.keyword == keyword)
                            .order_by(TrendPoint.fetched_at.desc()).limit(1)).first()
        if last is not None and last.date().isoformat() == today:
            _FETCHED["keywords"].add(keyword)
            return True
    return False


_RATE_LIMIT_CODES = {40202, 40209}


def breaker_hours(status: int | None) -> int:
    """0 = not a breaker condition. Family match: 401xx auth/verification,
    402xx billing/limits (40200 payment, 40210 insufficient funds, 40201
    paused, 40203 cost limit, 40204 subscription, 40207 IP), HTTP 401/402/403."""
    if status is None:
        return 0
    if status in _RATE_LIMIT_CODES:
        return 1
    fam = status // 100 if status >= 10000 else status
    return 24 if fam in (401, 402, 403) else 0


def trip_breaker(status: int | None) -> None:
    hours = breaker_hours(status) or 6
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
        if _already_today(kw, session):
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
            if breaker_hours(exc.status):
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
