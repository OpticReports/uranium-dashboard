"""APScheduler jobs. Every job swallows its own failures — a dark lane must
never take the scheduler down (genomics/catalyst convention).

Cadence is deliberately uneven, matching how fast each thing actually moves:
  hot_sweep          default 2m — nanocap wrappers only, US session. The
                                  meme rung's window was 13 minutes wide, so
                                  cadence IS the signal on that rung.
  registry_sweep    default 30m — launch detection across the whole registry.
  discovery_sweep   default 10m — cheap feeds, catches a wrapper early.
  priority_sweep    default 15m — the SMALLEST US listings first; covers the
                                  ~2,100 names under $250M in about an hour.
  universe_sweep    hourly      — one slice of the SEC list alphabetically, the
                                  keyless completeness backstop (~2d for all).
  equity_refresh     default 5m — quotes for live candidates during US hours,
                                  because that is the only window in which the
                                  equity leg of a trade can actually be placed.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import Session

from . import scan
from .config import screener_config
from .db import engine as db_engine

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _guarded(name: str, fn) -> None:
    try:
        with Session(db_engine) as session:
            result = fn(session)
        logger.info("job %s ok: %s", name, result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("job %s FAILED (scan continues next tick): %s", name, exc)


def job_registry_sweep() -> None:
    _guarded("registry_sweep", lambda s: (scan.registry_sweep(s), scan.rollup(s)))


def job_discovery_sweep() -> None:
    _guarded("discovery_sweep", scan.discovery_sweep)


def job_universe_sweep() -> None:
    _guarded("universe_sweep", scan.universe_sweep)


def job_priority_sweep() -> None:
    _guarded("priority_sweep", scan.priority_sweep)


def job_hot_sweep() -> None:
    _guarded("hot_sweep", lambda s: (scan.hot_registry_sweep(s), scan.rollup(s)))


def job_equity_refresh() -> None:
    _guarded("equity_refresh", scan.rollup)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    cfg = screener_config().get("scan", {})
    sched = BackgroundScheduler(timezone="UTC")

    sched.add_job(job_discovery_sweep, IntervalTrigger(
        minutes=int(cfg.get("discovery_sweep_minutes", 10))),
        id="discovery_sweep", max_instances=1, coalesce=True)
    sched.add_job(job_registry_sweep, IntervalTrigger(
        minutes=int(cfg.get("registry_sweep_minutes", 30))),
        id="registry_sweep", max_instances=1, coalesce=True)
    sched.add_job(job_universe_sweep, IntervalTrigger(hours=1),
                  id="universe_sweep", max_instances=1, coalesce=True)
    sched.add_job(job_priority_sweep, IntervalTrigger(
        minutes=int(cfg.get("priority_sweep_minutes", 15))),
        id="priority_sweep", max_instances=1, coalesce=True)
    # Nanocap wrappers, tight loop during the US session — the meme rung's
    # window was 13 minutes wide.
    sched.add_job(job_hot_sweep, CronTrigger(
        day_of_week="mon-fri", hour="13-20",
        minute=f"*/{int(cfg.get('hot_sweep_minutes', 2))}"),
        id="hot_sweep", max_instances=1, coalesce=True)
    # US regular session, 13:30-20:00 UTC Mon-Fri.
    sched.add_job(job_equity_refresh, CronTrigger(
        day_of_week="mon-fri", hour="13-20",
        minute=f"*/{int(cfg.get('equity_refresh_minutes', 5))}"),
        id="equity_refresh", max_instances=1, coalesce=True)
    # Seed shortly after boot so a cold start is not blind for half an hour.
    sched.add_job(job_priority_sweep, "date", id="boot_priority")
    sched.add_job(job_discovery_sweep, "date", id="boot_discovery")
    sched.add_job(job_registry_sweep, "date", id="boot_registry")

    sched.start()
    _scheduler = sched
    logger.info("scheduler started with %d jobs", len(sched.get_jobs()))


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def job_status() -> list[dict]:
    if _scheduler is None:
        return []
    return [{"id": j.id, "next_run": str(getattr(j, "next_run_time", None))}
            for j in _scheduler.get_jobs()]
