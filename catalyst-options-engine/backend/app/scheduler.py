"""APScheduler jobs + the scan orchestration they (and POST /scan) run.

Jobs (RUN_SCHEDULER env-gated, genomics pattern):
  * daily_scan    — every scan_interval_hours (default 24, first run ~10s
    after boot): catalysts + prices per radar name -> signals -> score ->
    persist setups -> proposals above min_score open paper positions ->
    mark/auto-close the book -> equity snapshot.
  * chain_refresh — hourly during US market hours (13:30-20:00 UTC, Mon-Fri),
    ONLY for hot names (days_to_event <= chain_refresh_days_to_event, default
    21): re-pulls chains, refreshes iv_ratio on the day's setups, re-marks
    open positions. Keeps the free Nasdaq endpoint traffic proportional to
    how close the money is.

Every lane failure inside a job degrades to a logged warning; the scheduler
itself never crashes (genomics scheduler convention).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

from .config import engine_config, radar_config
from .db import engine as db_engine
from .engine import ledger, proposer, scoring, signals
from .lanes import catalysts as catalysts_lane
from .lanes import chains as chains_lane
from .lanes import prices as prices_lane
from .models import Catalyst, Setup

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def radar_entries() -> list[dict]:
    return radar_config().get("radar", []) or []


def _events_for(session: Session, symbol: str) -> list[signals.EventView]:
    rows = session.exec(select(Catalyst).where(Catalyst.symbol == symbol)).all()
    return [signals.EventView(date=c.date, event_type=c.event_type,
                              impact_weight=c.impact_weight, title=c.title,
                              watch=c.watch, direction_lean=c.direction_lean)
            for c in rows]


def _chain_for(symbol: str):
    """(spot_from_chain, rows) with rows=None meaning lane dark."""
    res = chains_lane.fetch_chain(symbol)
    if res is None:
        return None, None
    return res


def scan_symbol(session: Session, entry: dict, asof: date,
                fetch_chain_now: bool | None = None) -> Setup:
    """Full signal + score pass for one radar name; persists/replaces the
    day's Setup row and returns it."""
    cfg = engine_config()
    symbol = entry["symbol"]
    aliases = entry.get("ctgov_names") or [entry.get("name", symbol)]

    # 1. catalysts (CT.gov alias union; manual rows already in DB)
    try:
        recs = catalysts_lane.scan_symbol(symbol, aliases, asof)
        catalysts_lane.upsert(session, recs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("catalyst scan failed for %s: %s", symbol, exc)
    events = _events_for(session, symbol)

    # 2. prices
    bars = prices_lane.fetch_history(symbol)
    closes = prices_lane.adj_closes(bars)
    prices_dark = not closes
    spot = closes[-1] if closes else None
    drift = signals.drift_z10(closes)
    rv20 = signals.realized_vol_20d(closes)

    # 3. event timing
    horizon = int(cfg.get("horizon_days", 60))
    min_impact = float(cfg.get("min_impact_for_event", 0.85))
    ev = signals.nearest_event(events, asof, horizon, min_impact)
    dte = None if ev is None or ev.date is None else (ev.date - asof).days
    watch = signals.has_interim_watch(events)

    # 4. chain / IV — only pull the chain when there's a dated event to price
    # (or the caller forces it); keeps traffic polite.
    hot_days = int(cfg.get("chain_refresh_days_to_event", 21))
    want_chain = fetch_chain_now if fetch_chain_now is not None else (
        dte is not None and dte <= max(horizon, hot_days))
    chain_dark, aiv, ivr = True, None, None
    if want_chain and ev is not None and ev.date is not None:
        chain_spot, rows = _chain_for(symbol)
        if rows is not None:
            chain_dark = False
            spot_for_iv = chain_spot or spot
            aiv = signals.atm_iv(rows, spot_for_iv, ev.date, asof)
            ivr = signals.iv_ratio(aiv, rv20)
            if chain_spot:
                spot = chain_spot

    # 5. score
    res = scoring.asymmetry_score(
        None if ev is None else ev.impact_weight, dte, drift, ivr,
        half_life_days=float(cfg.get("decay_half_life_days", 21)))
    flags = list(res.flags)
    if prices_dark:
        flags.append("price lane dark")
    if chain_dark and dte is not None:
        flags.append("chain lane dark")
    if watch:
        flags.append("interim watch (undated phase-3)")

    # 6. persist (replace the symbol's row for this asof date)
    for old in session.exec(select(Setup).where(Setup.symbol == symbol,
                                                Setup.asof == asof)).all():
        session.delete(old)
    setup = Setup(symbol=symbol, asof=asof, score=res.score,
                  days_to_event=dte,
                  event_date=None if ev is None else ev.date,
                  event_type=None if ev is None else ev.event_type,
                  event_title=None if ev is None else ev.title,
                  impact_weight=None if ev is None else ev.impact_weight,
                  watch=watch, drift_z10=drift, rv20=rv20, atm_iv=aiv,
                  iv_ratio=ivr, spot=spot, chain_dark=chain_dark,
                  prices_dark=prices_dark, flags=flags)
    session.add(setup)
    session.commit()
    session.refresh(setup)
    return setup


def _maybe_propose(session: Session, setup: Setup, asof: date) -> None:
    cfg = engine_config()
    paper = cfg.get("paper", {})
    starting_equity = float(paper.get("starting_equity", 100_000))
    positions = session.exec(select(ledger.PaperPosition)).all()
    equity = ledger.summarize(list(positions), starting_equity).equity

    if ledger.has_open_position(session, setup.symbol, setup.event_date):
        return

    # direction lean only from the operator-set catalyst row
    lean = None
    if setup.event_date is not None:
        cat = session.exec(select(Catalyst)
                           .where(Catalyst.symbol == setup.symbol,
                                  Catalyst.date == setup.event_date)).first()
        if cat is not None:
            lean = cat.direction_lean

    chain_rows = None
    if not setup.chain_dark:
        res = chains_lane.fetch_chain(setup.symbol)
        if res is not None:
            chain_rows = res[1]

    prop = proposer.propose(
        setup.symbol, score=setup.score, event_date=setup.event_date,
        asof=asof, spot=setup.spot, chain_rows=chain_rows,
        paper_equity=equity, direction_lean=lean,
        min_score=float(cfg.get("min_score", 55)),
        max_premium_bps=float(paper.get("max_premium_bps", 50)),
        scenario_iv=float(cfg.get("honesty_defaults", {}).get("scenario_iv", 1.0)))
    if prop is not None:
        ledger.open_position(session, prop, asof)
        logger.info("opened paper %s on %s: %d x %.2f (%s), max loss $%.0f",
                    prop.structure, prop.symbol, prop.contracts,
                    prop.unit_premium, prop.pricing_basis, prop.max_loss)


def run_daily_scan(session: Session) -> dict:
    """The whole daily sweep. Returns a summary dict (also used by POST /scan)."""
    asof = date.today()
    cfg = engine_config()
    paper = cfg.get("paper", {})
    scanned = proposals_before = 0
    for entry in radar_entries():
        if not entry.get("symbol"):
            continue
        try:
            setup = scan_symbol(session, entry, asof)
            scanned += 1
            if setup.score is not None and setup.score >= float(cfg.get("min_score", 55)):
                _maybe_propose(session, setup, asof)
                proposals_before += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("scan failed for %s: %s", entry.get("symbol"), exc)

    # book maintenance
    def _chain_lookup(sym: str):
        res = chains_lane.fetch_chain(sym)
        return None if res is None else res[1]

    def _price_lookup(sym: str):
        return prices_lane.last_close(prices_lane.fetch_history(sym))

    closed = ledger.auto_close_due(
        session, _chain_lookup, _price_lookup, asof,
        hold_trading_days=int(paper.get("hold_after_event_trading_days", 3)))
    for pos in session.exec(select(ledger.PaperPosition)
                            .where(ledger.PaperPosition.status == "open")).all():
        ledger.mark_position(session, pos, _chain_lookup(pos.symbol),
                             _price_lookup(pos.symbol), asof)
    point = ledger.snapshot_equity(
        session, float(paper.get("starting_equity", 100_000)), asof)
    return {"scanned": scanned, "auto_closed": len(closed),
            "equity": point.equity}


def run_chain_refresh(session: Session) -> dict:
    """Intraday chain pull for hot names only (days_to_event <= 21)."""
    asof = date.today()
    cfg = engine_config()
    hot_days = int(cfg.get("chain_refresh_days_to_event", 21))
    refreshed = 0
    hot = session.exec(select(Setup).where(Setup.asof == asof)).all()
    by_symbol = {s.symbol: s for s in hot}
    for entry in radar_entries():
        sym = entry.get("symbol")
        setup = by_symbol.get(sym)
        if (setup is None or setup.days_to_event is None
                or setup.days_to_event > hot_days):
            continue
        try:
            scan_symbol(session, entry, asof, fetch_chain_now=True)
            refreshed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("chain refresh failed for %s: %s", sym, exc)
    # re-mark open positions with fresh chains
    def _chain_lookup(s):
        res = chains_lane.fetch_chain(s)
        return None if res is None else res[1]

    def _price_lookup(s):
        return prices_lane.last_close(prices_lane.fetch_history(s))

    for pos in session.exec(select(ledger.PaperPosition)
                            .where(ledger.PaperPosition.status == "open")).all():
        ledger.mark_position(session, pos, _chain_lookup(pos.symbol),
                             _price_lookup(pos.symbol), asof)
    return {"refreshed": refreshed}


def _wrap(name: str, func):
    def _job():
        try:
            with Session(db_engine) as session:
                result = func(session)
            logger.info("Job '%s' done: %s", name, result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job '%s' failed: %s", name, exc)

    return _job


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    cfg = engine_config()
    sched = BackgroundScheduler(timezone="UTC")
    now = datetime.utcnow()

    hours = int(cfg.get("scan_interval_hours", 24))
    sched.add_job(_wrap("daily_scan", run_daily_scan), "interval", hours=hours,
                  id="daily_scan", max_instances=1, coalesce=True,
                  next_run_time=now + timedelta(seconds=10))
    logger.info("Scheduled 'daily_scan' every %dh (first run now)", hours)

    # Hourly during US market hours; only hot names actually hit the network.
    sched.add_job(_wrap("chain_refresh", run_chain_refresh),
                  CronTrigger(day_of_week="mon-fri", hour="13-20", minute=45,
                              timezone="UTC"),
                  id="chain_refresh", max_instances=1, coalesce=True)
    logger.info("Scheduled 'chain_refresh' hourly 13-20 UTC weekdays")

    sched.start()
    _scheduler = sched
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
