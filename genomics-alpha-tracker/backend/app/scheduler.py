"""APScheduler ingestion + scoring cron jobs.

Each job is gated by intervals.yaml (enabled + interval). A job whose source
needs a missing key simply ingests nothing (the source logs + skips) — the
scheduler never crashes.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session

from .config import intervals_config
from .db import engine
from .ingestion import runner
from .scoring.engine import compute_scores

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

_JOB_FUNCS = {
    "market": runner.run_market,
    "analyst": runner.run_analyst,
    "catalysts": runner.run_catalysts,
    "science": runner.run_science,
    "social": runner.run_social,
}


def _wrap(name: str, func):
    def _job():
        try:
            with Session(engine) as session:
                result = func(session)
            logger.info("Job '%s' done: %s", name, result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job '%s' failed: %s", name, exc)

    return _job


def _scoring_job():
    try:
        with Session(engine) as session:
            snaps = compute_scores(session)
        logger.info("Scoring job done: %d snapshots", len(snaps))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scoring job failed: %s", exc)


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    cfg = intervals_config()
    sched = BackgroundScheduler(timezone="UTC")

    for name, func in _JOB_FUNCS.items():
        job_cfg = cfg.get(name, {})
        if not job_cfg.get("enabled", True):
            logger.info("Job '%s' disabled in intervals.yaml", name)
            continue
        minutes = job_cfg.get("interval_minutes", 60)
        sched.add_job(_wrap(name, func), "interval", minutes=minutes,
                      id=name, max_instances=1, coalesce=True)
        logger.info("Scheduled '%s' every %d min", name, minutes)

    scoring_cfg = cfg.get("scoring", {})
    if scoring_cfg.get("enabled", True):
        sched.add_job(_scoring_job, "interval",
                      minutes=scoring_cfg.get("interval_minutes", 60),
                      id="scoring", max_instances=1, coalesce=True)
        logger.info("Scheduled 'scoring' every %d min",
                    scoring_cfg.get("interval_minutes", 60))

    sched.start()
    _scheduler = sched
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
