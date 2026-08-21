"""APScheduler ingestion + scoring cron jobs.

Each job is gated by intervals.yaml (enabled + interval). A job whose source
needs a missing key simply ingests nothing (the source logs + skips) — the
scheduler never crashes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

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
    "insiders": runner.run_insiders,
    "short_interest": runner.run_short_interest,
    "benchmarks": lambda session: runner.run_benchmarks(session),
    "news": runner.run_news,
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


def _calls_job():
    """Grade open trade calls and flag outcomes, then turn fresh flags into
    new calls. Evaluate FIRST so a symbol whose call just closed frees its slot.
    The H11/H8 shadow pass (trailing-exit re-grade + daily regime log) rides
    the same cycle right after live grading — OBSERVE-ONLY, it reads the same
    bars and writes only shadow_grade/regime_log rows; the live book is
    untouched."""
    from .calls.manager import evaluate_calls, generate_calls
    from .calls.postmortem import update_postmortems
    from .calls.shadow import evaluate_shadow_calls, log_regime
    from .scoring.outcomes import evaluate_flag_outcomes

    try:
        with Session(engine) as session:
            closed = evaluate_calls(session)
            shadows = evaluate_shadow_calls(session)
            regime = log_regime(session)
            graded = evaluate_flag_outcomes(session)
            pms = update_postmortems(session)
            made = generate_calls(session)
        logger.info(
            "Calls job done: %d closed, %d shadow-graded, regime %s, "
            "%d flag outcomes, %d post-mortems, %d generated",
            len(closed), len(shadows), regime.date if regime else None,
            graded, pms, len(made))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Calls job failed: %s", exc)


def _discovery_job():
    """Daily dynamic-universe-discovery sweep (see ingestion/discovery.py).
    Runs AFTER the main ingestion cycle has settled — an auto-promoted name is
    then picked up by the next normal ingestion pass, no special backfill."""
    from .ingestion.discovery import run_discovery

    try:
        with Session(engine) as session:
            summary = run_discovery(session)
        logger.info("Discovery job done: %s", summary)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Discovery job failed: %s", exc)


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    cfg = intervals_config()
    sched = BackgroundScheduler(timezone="UTC")
    now = datetime.utcnow()

    # Stagger an immediate first run of each job on startup (a few seconds apart)
    # so ingestion actually happens right after boot instead of waiting a full
    # interval — otherwise frequent restarts mean the hourly jobs never fire.
    for i, (name, func) in enumerate(_JOB_FUNCS.items()):
        job_cfg = cfg.get(name, {})
        if not job_cfg.get("enabled", True):
            logger.info("Job '%s' disabled in intervals.yaml", name)
            continue
        minutes = job_cfg.get("interval_minutes", 60)
        sched.add_job(_wrap(name, func), "interval", minutes=minutes,
                      id=name, max_instances=1, coalesce=True,
                      next_run_time=now + timedelta(seconds=5 + i * 5))
        logger.info("Scheduled '%s' every %d min (first run now)", name, minutes)

    scoring_cfg = cfg.get("scoring", {})
    if scoring_cfg.get("enabled", True):
        sched.add_job(_scoring_job, "interval",
                      minutes=scoring_cfg.get("interval_minutes", 60),
                      id="scoring", max_instances=1, coalesce=True,
                      # score after the initial ingestion sweep has had time to run
                      next_run_time=now + timedelta(minutes=3))
        logger.info("Scheduled 'scoring' every %d min (first run in 3 min)",
                    scoring_cfg.get("interval_minutes", 60))

    calls_cfg = cfg.get("calls", {})
    if calls_cfg.get("enabled", True):
        sched.add_job(_calls_job, "interval",
                      minutes=calls_cfg.get("interval_minutes", 60),
                      id="calls", max_instances=1, coalesce=True,
                      # run after scoring so calls see fresh flags/composites
                      next_run_time=now + timedelta(minutes=5))
        logger.info("Scheduled 'calls' every %d min (first run in 5 min)",
                    calls_cfg.get("interval_minutes", 60))

    discovery_cfg = cfg.get("discovery", {})
    if discovery_cfg.get("enabled", True):
        sched.add_job(_discovery_job, "interval",
                      minutes=discovery_cfg.get("interval_minutes", 1440),
                      id="discovery", max_instances=1, coalesce=True,
                      # after the initial ingestion + scoring sweep, so the
                      # census cache and universe state are warm
                      next_run_time=now + timedelta(minutes=10))
        logger.info("Scheduled 'discovery' every %d min (first run in 10 min)",
                    discovery_cfg.get("interval_minutes", 1440))

    sched.start()
    _scheduler = sched
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
