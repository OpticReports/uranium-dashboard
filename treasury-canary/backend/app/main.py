"""FastAPI app — Treasury Canary. Serves the API and (in the single-service image)
the built React SPA. Lifespan: init DB, optional startup backfill (background),
and the refresh scheduler.
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .store.db import init_db, session_scope

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


def _background_backfill() -> None:
    try:
        from .jobs.refresh import run_backfill
        with session_scope() as s:
            summary = run_backfill(s)
        logger.info("Startup backfill complete: %s", summary)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Startup backfill failed (non-fatal): %s", exc)


def _start_scheduler(app: FastAPI) -> None:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    sched = BackgroundScheduler(timezone="UTC")

    def _job():
        try:
            from .jobs.refresh import run_refresh
            with session_scope() as s:
                logger.info("Scheduled refresh: %s", run_refresh(s))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Scheduled refresh failed: %s", exc)

    from datetime import datetime, timedelta, timezone
    sched.add_job(_job, IntervalTrigger(minutes=settings.refresh_interval_minutes),
                  next_run_time=datetime.now(timezone.utc) + timedelta(seconds=10),
                  id="refresh", max_instances=1, coalesce=True)
    sched.start()
    app.state.scheduler = sched
    logger.info("Scheduler started (every %d min)", settings.refresh_interval_minutes)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.backfill_on_startup:
        threading.Thread(target=_background_backfill, daemon=True).start()
    if settings.run_scheduler:
        _start_scheduler(app)
    else:
        logger.info("Scheduler disabled (RUN_SCHEDULER=false)")
    yield


app = FastAPI(title="Treasury Canary", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"],
    allow_headers=["*"], allow_credentials=True,
)

from .api import (  # noqa: E402
    routes_composite, routes_events, routes_flows, routes_labor, routes_metrics,
    routes_news, routes_pins,
)

app.include_router(routes_metrics.router)
app.include_router(routes_composite.router)
app.include_router(routes_events.router)
app.include_router(routes_news.router)
app.include_router(routes_labor.router)
app.include_router(routes_flows.router)
app.include_router(routes_pins.router)


@app.get("/health")
def health():
    return {
        "status": "ok", "service": "treasury-canary",
        "fred_key_present": bool(settings.fred_api_key),
        "scheduler": bool(settings.run_scheduler),
        "display_tz": settings.display_tz,
    }


@app.post("/refresh")
def manual_refresh():
    from .jobs.refresh import run_refresh
    with session_scope() as s:
        return run_refresh(s)


# --- Single-service SPA serving (set FRONTEND_DIST in the deploy image) --------
if settings.frontend_dist:
    import os
    from fastapi.staticfiles import StaticFiles
    if os.path.isdir(settings.frontend_dist):
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="spa")
